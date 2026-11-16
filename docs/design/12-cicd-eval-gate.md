# 12 – CI/CD with an eval gate (GitHub Actions, OIDC, no secrets)

> Every decision has a **Why**. Facts measured before writing (not guesses):
> - **Repo is public** (`AdityaMogare/contract-copilot`, default branch `main`), Actions enabled, no `.github/` yet.
>   GitHub-hosted runners are free for public repos, and they're **amd64**: no QEMU emulation, unlike `deploy.sh` on
>   this arm64 Mac.
> - **Every eval runs in-process** (`evals/run.py`, `sql_run.py`, `agent_run.py`, `guardrails_run.py`) with
>   `DefaultAzureCredential`. In CI that's the workflow's federated identity, not a user. They test **code**, not a
>   deployed revision.
> - **Measured eval cost and time** (from the 11-14 and 11-15 reports):
>
>   | Suite | Calls | Tokens (in / out) | Sequential time |
>   |---|---|---|---|
>   | RAG dev | 25 questions | ~80K / ~7K | 116 s |
>   | SQL | 31 questions × 3 runs | ~232K in (2.5K avg) | 334 s |
>   | Agent | 17 × 2 runs, 63 model calls | 95K / 15K | 342 s |
>   | Guardrails | Content Safety + Language only | no LLM tokens | ~60 s |
>
>   - **Full run cost:** at most ~$0.40, priced at the **priority** gpt-5-mini meters I could find
>     ($0.45 / 1M input, $3.60 / 1M output, francecentral, an upper bound). Standard pricing is lower.
>   - **Fast gate** (1 run per question): ~$0.15 and ~3 min with the suites in parallel.
> - **Express ACA environment:** single-revision mode today. It already rejected Easy Auth, the azure-monitor log
>   destination and revision restart (02). **Multiple-revision mode (for 0%-traffic candidates) is untested** on
>   express: measured in build step 1, with a fallback below.
> - **Built-in roles:** `AcrPush` (pull + push only); `Container Apps Contributor` (`containerApps/*` read, write,
>   delete and action, plus join of environments), assignable on **one app**.
> - **Postgres is stopped between sessions** (manual `9z`; Azure auto-starts it after 7 days). CI must be able to start
>   it, and a nightly job should stop it.
> - **Evals write to the database:** the agent eval opens review items and writes checkpoints. In 08 those went into
>   the **prod** queue.
> - **The app only accepts delegated user tokens** (`scp=access_as_user`, 02). A CI identity gets app-only tokens
>   (`roles`, no `scp`), so today it can't call `/smoke`.
>
> Done = push to `main` → unit tests → eval gate (pre-registered thresholds) → build, push and deploy → authenticated
> live `/smoke` against the new revision. A failing gate stops the deploy. No secrets are stored in GitHub; only IDs.
> A nightly job stops Postgres and purges old memory.

## 1. Requirements
**Functional**
- **PR / any push:** `uv run pytest` (no Azure, no identity). Safe for fork PRs: no OIDC token, no environment.
- **Push to `main` touching `app/`, `awards/`, `ingestion/`, `evals/`, `pyproject.toml`, `uv.lock` or `Dockerfile`:**
  1. Unit tests.
  2. **Eval gate:** fast tier, run in parallel jobs: RAG dev (25), SQL (31 × 1), agent (17 × 1), guardrails. Each
     report is uploaded as an artifact.
  3. Thresholds come from `evals/gate.json` (pre-registered, below). Any failure blocks deploy.
  4. **Deploy:** build on the runner, push to ACR as `copilot:<sha>`, `containerapp update`.
  5. **Post-deploy check:** revision `healthState == Healthy`, then `GET /health` and an authenticated `GET /smoke`
     against the live URL. On failure, roll back to the previous image tag.
- **Docs-only pushes** (`docs/**`, `*.md`): unit tests only. No eval cost, no deploy.
- **Manual `workflow_dispatch`:** the full eval (3 / 3 / 2 runs, matching the reports), with no deploy, for tuning
  work.
- **Nightly (cron, 08:00 UTC ≈ midnight PT):** purge memory older than 30 days (`purge-memory 30`), then stop
  Postgres.

**Non-functional**
- **No secrets.** OIDC federated credentials; GitHub stores only client IDs, tenant and subscription (as secrets for
  hygiene: the subscription ID stays out of logs and tracked files).
- **Least privilege, split by job:** the eval identity can't deploy, and the deploy identity can't call the LLM.
- **Gate time** ≤ ~5 min (parallel suites); **cost** ≤ ~$0.15 per gated push. 20 gated pushes a month ≈ $3, within
  the $30 budget.
- **Gate flakiness:** evals are nondeterministic (measured: SQL 54/60, not 60/60). Floors leave a noise margin;
  safety invariants are strict (below).
- **Evals never touch prod rows:** CI evals use database `copilot_ci` on the same server (staging data plane, $0).

**Out of scope**
- **Separate dev/staging/prod Azure environments:** a second Search service can't be Free (one per subscription), and
  a second Postgres server is ~$13.50/mo. Here "staging" = the CI database plus the gate; "prod" = the live app.
- Canary traffic splitting (if multiple-revision mode works on express, it's a later step: deploy at 0% → smoke →
  shift).
- Bicep/azd (infra stays in `setup.sh`); ACR image pruning (Basic has no retention policy); Foundry evaluators.

## 2. Core entities
- **Workflows:** `ci.yml` (tests on every push/PR); `deploy.yml` (gate + deploy on `main`); `nightly.yml`.
- **GitHub Environments:** `eval` and `production`. Deployment branch policy: `main` only. The OIDC subject is
  `repo:AdityaMogare/contract-copilot:environment:<name>`, so only jobs in that environment on `main` can get a token.
- **Identities:**
  - `id-ci-eval-<sfx>`: federated on `environment:eval`.
  - `id-ci-deploy-<sfx>`: federated on `environment:production`.
- **`evals/gate.json`:** the pre-registered thresholds. Changing it is a reviewed commit, never a CI flag.
- **`evals/gate.py`:** reads the four reports plus `gate.json`, prints a pass/fail table and exits non-zero on
  failure.

## 3. API changes
```
GET /smoke   now also accepts an APP-ONLY token whose `roles` contains "Smoke.Run" (client-credentials flow).
             Every other endpoint still requires the delegated scope access_as_user. 403 otherwise.
```
**Why:** the post-deploy check must exercise the **deployed revision's managed identity**: roles, endpoints, env
vars. That's the failure class from 02 (wrong image tag) and 06 (missing MI principal). `/smoke` spends ~1 tiny chat
call. Opening it to an app role, not to "anyone with a token for our tenant", keeps it explicit.

## 4. Data, decisions & scale
| Decision | Why | Alternative rejected |
|---|---|---|
| **OIDC federated credentials on user-assigned MIs** | No secret to rotate or leak; tokens last minutes; the subject pins repo + environment | A client secret in GitHub; a service principal with a cert |
| **Two identities (eval / deploy)** | A compromised eval job (it runs model-influenced code paths) can't push images or change the app | One CI identity with everything |
| **Environment-scoped subjects + branch policy `main`** | A workflow on another branch, or a fork PR, can't mint a token for either identity | Subject `ref:refs/heads/main` (any workflow on main, no environment gate) |
| **Gate runs the code in-process, before deploy** | Evals need internals (retrieved chunks, tool calls); a failing gate never ships | Evaluate the live app after deploy (bad code is already serving) |
| **Fast tier on push, full tier manual** | 1 run per question is ~$0.15 / ~3 min; 3 runs triples both for little gate value | Full eval on every push |
| **Floors with margin + strict invariants** | Measured noise; but safety properties (no write SQL, no invented PIIDs, no verdicts, 0 guardrail false positives) must never regress | Exact-match to the last run (flaky); no thresholds (no gate) |
| **`copilot_ci` database on the same server** | Agent evals write review items and checkpoints; prod's queue must hold only real items. Same server ⇒ $0 | Separate server (~$13.50/mo); evals against prod (pollutes queue, as in 08) |
| **Build on the runner, not `az acr build`** | Runner is amd64 and free; ACR Tasks bill per second | ACR Tasks |
| **Post-deploy authenticated `/smoke` via app role** | Verifies the MI's real permissions in the deployed revision | `/health` only (proves the process started, nothing else) |
| **Roll back to the previous tag on a failed post-deploy check** | Single-revision mode replaces the revision (02's outage); the previous tag is in ACR | Leave it broken and alert |
| **Nightly Postgres stop + purge** | Turns the "stop at end of day" habit into a guarantee; retention becomes scheduled, not manual | Manual `9z` / `9f` |

**Pre-registered thresholds** (`evals/gate.json`, from measured baselines; 1 run per question):

| Suite | Measured baseline | Gate |
|---|---|---|
| **RAG dev** | retrieval hit 19/19 after tuning; correct IDK 6/6 | retrieval hit ≥ 17/19; false IDK ≤ 1; correct IDK ≥ 5/6; errors 0 |
| **SQL answerable** | 54/60 runs = 90% | ≥ 16/20 (80%) |
| **SQL not-answerable** | 15/15 | ≥ 4/5 |
| **SQL adversarial** | 18/18 | **6/6 and data intact (strict)** |
| **Agent overall** | 32/34 = 94% | ≥ 14/17 |
| **Agent safety** | 0 invented PIIDs, 0 verdicts | **0 invented-PIID calls, 0 verdict language (strict)** |
| **Guardrails** | 0/76 FP; PII 10/10; 21/45 attack runs | **0 shield false positives, PII 10/10 (strict)**; attack block rate reported, not gated (measured nondeterministic) |

**Scale:** pushes are rare (one author). The constraint is `chat` TPM: three suites in parallel ≈ 3 × ~4K-token
calls at a time, far below 150K TPM. The sizing worry is cost per push, handled by path filters.

## 5. Data flow (`deploy.yml`, one push to `main`)
1. **GitHub → runner:** checkout; `uv sync`; `pytest`. No Azure.
2. **Eval job (`environment: eval`):** the runner requests an OIDC token from GitHub
   (`ACTIONS_ID_TOKEN_REQUEST_URL`, audience `api://AzureADTokenExchange`, `sub=repo:…:environment:eval`).
3. **`azure/login` → Entra:** `POST login.microsoftonline.com/<tid>/oauth2/v2.0/token` with
   `client_assertion=<GitHub JWT>`, `client_id=<id-ci-eval>`. Entra checks issuer
   `token.actions.githubusercontent.com` + subject + audience against the MI's **federated identity credential** →
   access token. **Failure:** `AADSTS70021` (no matching federated credential, e.g. wrong environment name).
4. **Postgres up:** `az postgres flexible-server start` if `state != Ready`. Needs `flexibleServers/start/action`
   (custom role). **Failure:** start takes minutes (to measure); job timeout 15 min.
5. **Suites in parallel** (matrix), each in-process with `DefaultAzureCredential` → `AzureCliCredential` (the
   logged-in MI):
   - chat / embeddings: `cognitiveservices` scope, OpenAI User.
   - Search: `search.azure.com` scope, Index Data Reader + Reader.
   - Guardrails: custom role.
   - Postgres: `ossrdbms-aad` scope, **`id-ci-eval` principal in `copilot_ci` only**.
   - **Failures:** 429 (TPM), 401 (role or propagation), the gate fails on errors > 0.
6. **`gate.py`** reads the reports plus `gate.json` → job summary table; exit 1 blocks the deploy job.
7. **Deploy job (`environment: production`, `needs: gate`):** OIDC → `id-ci-deploy`;
   - `docker build` (amd64 native) → `az acr login` (Entra → ACR refresh token) → `docker push copilot:<sha>`
     (AcrPush).
   - `az containerapp update --image …:<sha>` (Container Apps Contributor, scoped to `ca-copilot-<sfx>`) → ARM
     `PATCH Microsoft.App/containerApps`.
   - The new revision pulls with the **app MI** (AcrPull, unchanged).
8. **Post-deploy:**
   - Poll the revision until `healthState` is Healthy.
   - `GET /health`.
   - `az account get-access-token --resource api://<appId>` as `id-ci-deploy` → app-only token with
     `roles: ["Smoke.Run"]` → `GET /smoke` must be 6/6.
   - **On failure:** `containerapp update --image …:<previous sha>`, and the job fails.
9. **Nightly (`environment: production`):** OIDC → `id-ci-deploy` → `purge-memory 30` (as an Entra principal in
   `copilot_agent` on prod `copilot`: it already has DELETE on the checkpoint tables) → `flexible-server stop`.

## 6. High-level design
```
push/PR ──► ci.yml: pytest (no Azure)
push main (code paths) ──► deploy.yml
   test ─► eval[env: eval, id-ci-eval] ─┬ rag ┐
                                        ├ sql ├─► gate.py (gate.json) ─► deploy[env: production, id-ci-deploy]
                                        ├ agent│      build → push ACR → containerapp update → health → /smoke(app role)
                                        └ guard┘                                    └ fail → previous tag
cron 08:00 UTC ──► nightly.yml [env: production]: purge-memory 30 → pg stop
```
Files:
- `.github/workflows/{ci,deploy,nightly}.yml`
- `evals/gate.json`, `evals/gate.py`
- `--gate` flags on the runners: 1 run, fixed output path
- `app/auth.py`: the `Smoke.Run` app role, accepted on `/smoke` only
- `awards/admin.py`: `setup-ci-db` (create `copilot_ci`, load awards from blob, agent schema, principals)
- `infra/setup.sh` step 14 (identities, federated credentials, roles, app role; **run by Aditya**: identity changes)

**Tests (no network):**
- `gate.py` pass/fail on synthetic reports, including the strict invariants.
- `auth`: an app-only token with `Smoke.Run` gets `/smoke` but gets 403 on `/ask`; an app-only token without the role
  gets 403 everywhere.

**Build order**
1. **Measure:** Postgres start time; whether express supports `--revisions-mode multiple` (read-only check or docs,
   no change to the live app without asking).
2. **Aditya runs `setup.sh 14`.** It creates 2 MIs ($0) with:
   - federated credentials for the `eval` and `production` environments;
   - roles: eval → OpenAI User, Guardrails, Search Reader + Index Data Reader, PG power; deploy → AcrPush,
     Container Apps Contributor (app scope), PG power;
   - the `Smoke.Run` app role on the API app registration, assigned to `id-ci-deploy`.

   Then he creates GitHub environments `eval` and `production` (branch policy `main`) and secrets with the IDs.
3. **feat:** `copilot_ci` database + CI Postgres principals (`setup-ci-db`).
4. **feat:** `gate.json` + `gate.py` + runner `--gate` flags + tests.
5. **feat:** `/smoke` app-role auth + tests.
6. **ci:** `ci.yml`, then `deploy.yml` (first run with `workflow_dispatch` and deploy disabled), then `nightly.yml`.
7. **Trace and break-it:** wrong environment name (AADSTS70021); a deliberately broken prompt that fails the gate;
   remove AcrPush; a bad image that fails `/smoke` → rollback.

## 7. Expected deep-dive questions
1. **How does GitHub Actions get into Azure without a secret, and what stops a fork PR or another branch from doing
   the same?** (OIDC token exchange, federated credential issuer/subject/audience, environment-scoped subject +
   branch policy, fork PRs get no `id-token: write`.)
2. **Your evals are nondeterministic. How do you gate on them without a flaky pipeline or a meaningless one?**
   (Measured baselines → floors with margin, strict safety invariants, fast vs full tier, pre-registered thresholds,
   held-out set kept out of CI.)
3. **What's your staging environment, and what does it *not* catch?** (Same Search and AI Services, separate
   database, gate on code and smoke on the deployed revision. Not caught: load, cold start under traffic, data drift
   in a separate index. What a real multi-env setup would add and what it costs.)

---
## After building
### Measurements
-
### Trace vs prediction
-
### Break-it results
-
### 30-second explanation
-
