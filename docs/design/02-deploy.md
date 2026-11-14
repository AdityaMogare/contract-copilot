# 02 – Deploy: the skeleton on Azure Container Apps behind Entra sign-in

> Written by Claude at Aditya's request (2026-11-14). Every decision has a **Why**.
> Facts checked read-only before writing: USC tenant allows users to create app registrations
> (`allowedToCreateApps: true`); Container Apps is available in canadacentral;
> `Microsoft.App` and `Microsoft.ContainerRegistry` are **not registered** yet; local Docker is
> **linux/arm64** (Apple silicon) with buildx available.
> Done = `/smoke` returns 200 on the public URL after an Entra sign-in, using the managed identity.

## ⚠️ Revision (2026-11-14, during build): Easy Auth → Entra token validation in FastAPI
**What happened:** our environment came up as an ACA *express* environment, which rejects
Easy Auth (`400 ExpressAuthConfigNotSupported`) and the azure-monitor log destination. See
`docs/debugging-log.md`. Aditya chose app-level auth. **Everything below that mentions Easy
Auth, the 302 redirect or `/.auth/*` is superseded by this section.**

**New design**
- The app registration `contract-copilot-web` also **exposes an API**: identifier URI
  `api://<appId>`, delegated scope `access_as_user`, v2 access tokens. **Azure CLI is
  pre-authorized** for that scope, so `az account get-access-token --scope api://<appId>/access_as_user`
  works without a consent prompt. Assignment required stays on, so Entra refuses to issue the
  token to anyone not assigned (AADSTS50105). That's the "only Aditya" control.
- FastAPI dependency `require_user` on every route except `/health`. It checks the
  `Authorization: Bearer` JWT: **signature** against the tenant's public keys
  (`https://login.microsoftonline.com/{tid}/discovery/v2.0/keys`, cached), **issuer**
  `https://login.microsoftonline.com/{tid}/v2.0`, **audience** = appId, **expiry**, and **scope**
  `access_as_user` in `scp`. Failures: missing/invalid token → **401** + `WWW-Authenticate: Bearer`;
  valid token without the scope → **403**.
- *Why validate in the app, not trust the platform:* it works on any host (express ACA, local,
  later anything else), there's no secret involved (validation uses *public* keys), and it's the
  exact JWT-validation story interviewers probe.
- Config: `AUTH_REQUIRED` (default **true**, fail-closed: the app refuses to start if it's true but
  tenant/audience are missing), `AUTH_TENANT_ID`, `AUTH_AUDIENCE`. Locally `.env` sets `AUTH_REQUIRED=false`.
- **Deploy order is fail-closed:** roll the auth-enabled revision with ingress off, verify, and only
  then enable external ingress. (The first attempt created ingress first and auth second, which
  left the app public when auth failed.)
- Trade-off: no browser sign-in page. You call it with curl + a token. A browser UI is future work (MSAL in a frontend).

**New request flow (replaces §5B steps 1–5)**
1. Laptop: `az account get-access-token --scope api://<appId>/access_as_user` → the CLI asks Entra
   (`POST /{tid}/oauth2/v2.0/token`, refresh-token grant) → Entra checks assignment → v2 access token, `aud=<appId>`, `scp=access_as_user`.
2. `curl -H "Authorization: Bearer <token>" https://ca-copilot-…/smoke` → ACA ingress (TLS) → container.
3. `require_user`: read the header → `kid` from the JWT header → public key from the cached JWKS → verify
   signature, `iss`, `aud`, `exp`, `scp` → 401/403 or continue. (Then hops 6–8 of §5B are unchanged.)

## 1. Requirements
**Functional**
- The app from feature 01 runs as a container on Azure Container Apps (ACA) at an HTTPS URL.
- **Every path except `/health` requires Entra sign-in.** Only Aditya can sign in (not all of USC).
- In Azure, the app authenticates to AI Services, Search, Key Vault and Storage as
  `id-app-cczq9h` (managed identity), with the same code as local. Only env vars differ.
- The image is pulled from our registry with the managed identity (no registry password).
- One command redeploys a new image: `infra/deploy.sh` (build → push → new revision).

**Non-functional**
- Cost: **ACR Basic ≈ $5/month is the only fixed cost** added. ACA consumption with
  `min-replicas 0` stays inside the monthly free grant (180K vCPU-s, 360K GiB-s, 2M requests).
  Running total ≈ $5/month + tokens, inside the $30 budget.
- Cold start: with min replicas 0, the first request after idle waits for a replica to start.
  *Target* < 15 s (to measure). This is the accepted trade-off for $0 idle cost.
- Security: no secrets anywhere: no ACR admin user, no client secret for sign-in, no
  Log Analytics shared key (see §6).

**Out of scope**
- Postgres (step 9, still deferred). CI/CD with GitHub Actions + OIDC (Week 3; manual script now).
- Custom domain, VNet/private endpoints (cost and complexity; public endpoints + Entra auth for now).
- OpenTelemetry → App Insights (comes with the first real endpoint).

## 2. Core entities
- **ACR** `acrcczq9h`: stores images, tagged with the git SHA (never `latest`).
- **ACA environment** `cae-cczq9h`: the shared boundary (network, logging) the app runs in.
- **Container App** `ca-copilot-cczq9h`: ingress, revisions, scale rules, the identity, env vars.
- **App registration** `contract-copilot-web` + its **enterprise app** (service principal): what
  Entra issues sign-in tokens for. "Assignment required" = only assigned users can sign in.
- **Revision**: an immutable snapshot (image + config). Every deploy makes a new one.

## 3. API
Unchanged from 01. What changes is in front of it:
```
GET https://ca-copilot-cczq9h.<env-default-domain>/health   → 200, no sign-in (excluded path)
GET https://…/smoke   (no session)  → 302 to login.microsoftonline.com/<tenant>/oauth2/v2.0/authorize
GET https://…/smoke   (signed in)   → 200/503 as in design 01
GET https://…/.auth/me              → who is signed in (provided by Easy Auth, not our code)
Errors: 401/302 from the auth layer (never reaches FastAPI); 403 if the user isn't assigned to the app.
```

## 4. Data types, access patterns & scale
- No new data. The image (~200 MB) is pulled per new replica.
- Scale: HTTP scale rule, min 0 / max 1 replica. *Why max 1:* cost cap, and /smoke can't overload
  anything at one replica. At 10x (RAG traffic) raise max replicas; the limit then is model TPM, not ACA.

## 5. Data flow (numbered hops)
**A. Deploy (from the laptop, `infra/deploy.sh`)**
1. `docker buildx build --platform linux/amd64` locally. *Why amd64:* ACA runs amd64, and an
   arm64 image from this Mac would fail to start with "exec format error".
   *Failure:* emulation missing → fall back to `az acr build` (builds in Azure).
2. `az acr login -n acrcczq9h`: the CLI exchanges my **Entra token** for an **ACR refresh token**
   (`POST https://acrcczq9h.azurecr.io/oauth2/exchange`), then gives Docker a token as its password.
   *Needs:* AcrPush on the registry for me (Owner can't push data either: same control/data split).
3. `docker push acrcczq9h.azurecr.io/copilot:<git-sha>`.
4. `az containerapp update --image …:<git-sha>` → ARM `PATCH …/Microsoft.App/containerApps/ca-copilot-cczq9h`
   → a new **revision**; traffic moves to it once it's healthy.
5. ACA → ACR **image pull as `id-app-cczq9h`**: the platform gets an MI token, exchanges it at
   ACR, and pulls. *Failure:* AcrPull missing or still propagating → revision stuck in
   "Activating" / `ImagePullBackOff` in system logs.

**B. A signed-in `/smoke` request (embed check)**
1. Browser → `https://ca-copilot-…/smoke` → ACA ingress (TLS terminated by the platform).
2. Ingress → **Easy Auth sidecar**: no session cookie → **302** to
   `login.microsoftonline.com/9ddaaca1-…/oauth2/v2.0/authorize?client_id=<app-reg>&response_type=id_token…`.
3. User signs in (MFA). Entra checks the user is **assigned** to the enterprise app; if not, it shows an error and no token is issued.
4. Entra → `POST /.auth/login/aad/callback` with an **ID token** → the sidecar validates it
   (signature, audience = app-reg client ID, issuer = USC tenant) → sets the `AppServiceAuthSession` cookie → 302 back to `/smoke`.
5. Sidecar → container: request forwarded with `X-MS-CLIENT-PRINCIPAL-NAME` / `-ID` headers.
   FastAPI ignores them for now (it could audit-log the user later).
6. `/smoke` → `DefaultAzureCredential`: `EnvironmentCredential` is skipped; **ManagedIdentityCredential**
   sees ACA's `IDENTITY_ENDPOINT` + `IDENTITY_HEADER` env vars and calls that local endpoint
   with `client_id=$AZURE_CLIENT_ID` (picking `id-app-cczq9h`) and `resource=https://cognitiveservices.azure.com`.
   *Failure:* `AZURE_CLIENT_ID` unset → it asks for a system-assigned identity that doesn't exist → error.
7. → `POST https://ais-cczq9h.cognitiveservices.azure.com/openai/deployments/embed/embeddings` with the
   **MI's** token. RBAC: Cognitive Services OpenAI User (granted in step 8, already propagated).
8. Response → aggregate → 200/503 → back through the sidecar to the browser.

## 6. High-level design
```
laptop ──build/push (my Entra→ACR token)──▶ ACR acrcczq9h
                                              │ pull (MI token, AcrPull)
browser ─HTTPS─▶ ACA ingress ─▶ Easy Auth ─▶ container (FastAPI) ──MI tokens──▶ AI Services (francecentral)
                 (cae-cczq9h, canadacentral)                                 ├▶ Search / Key Vault / Storage
                       └─ console + system logs ─▶ Azure Monitor (diagnostic setting) ─▶ log-cczq9h
```
**New infra steps (in `infra/setup.sh`)**
| Step | Resource | Key settings | Why |
|---|---|---|---|
| 0 (amend) | register `Microsoft.App`, `Microsoft.ContainerRegistry` | | ARM refuses unregistered namespaces (we hit this in step 0) |
| 10 | ACR `acrcczq9h` Basic | `--admin-enabled false` | admin user = a static password, the thing we're avoiding |
| 10 | roles | me: **AcrPush**; app MI: **AcrPull** (scoped to the registry) | push vs pull split; least privilege |
| 11 | ACA env `cae-cczq9h` | `--logs-destination azure-monitor` + diagnostic setting → `log-cczq9h` | the default `log-analytics` destination needs the workspace **shared key** passed to ARM; azure-monitor doesn't |
| 12 | App registration `contract-copilot-web` | ID tokens enabled, redirect `https://<fqdn>/.auth/login/aad/callback`, **no client secret**; enterprise app `appRoleAssignmentRequired=true`, assign Aditya | with no secret, Easy Auth uses the ID-token (implicit) flow: sign-in works, but no access tokens for downstream APIs. We don't need those, because the app calls Azure as itself (MI) |
| 13 | Container App `ca-copilot-cczq9h` | user-assigned identity `id-app-cczq9h`; `--registry-identity` = same MI; ingress external, port 8000; min 0 / max 1; 0.25 vCPU / 0.5 GiB; liveness + readiness probes on `/health`; env vars from `.env.example` + `AZURE_CLIENT_ID` | probes on `/health` so a slow model never restarts the app (design 01) |
| 13 | Easy Auth | provider Microsoft, client ID = app reg, issuer = USC tenant, unauthenticated action = **RedirectToLoginPage**, excluded path `/health` | sign-in enforced at the platform, before our code runs |

**App changes:** a `Dockerfile` (python:3.12-slim, `uv sync --frozen --no-dev`, non-root user,
`uvicorn app.main:app --host 0.0.0.0 --port 8000`) and `.dockerignore` (`.env`, `.venv`, `infra/logs`, `.git`).
*Why `.dockerignore` lists `.env`:* the image goes to a registry; nothing local should end up in it.

**Risks to verify at build time (not assumed)**
- Implicit-flow Easy Auth without a client secret on ACA. If ACA demands a secret, fall back to a
  client secret stored **in Key Vault** and referenced by the Container App via its MI (still not in git or env files).
- Local amd64 emulation. If buildx can't emulate, fall back to `az acr build` (ACR Tasks may be restricted on student subscriptions: check).
- Whether the Students region policy allows `Microsoft.App` in canadacentral (it's an allowed region, so expected yes).

## 7. Expected deep-dive questions
1. Your container has no credentials in it. Walk through how it pulls its own image and then calls the model. Which token, from where, at each step?
2. Why `/health` excluded from auth and used for probes, but `/smoke` behind sign-in? What breaks if you swap them?
3. Min replicas 0 saves money. What does the first user after idle experience, and how would you fix it for production without paying for an always-on replica?

---
## After building
### Trace vs prediction (what I got wrong)
-
### Break-it results
-
### 30-second explanation
-
