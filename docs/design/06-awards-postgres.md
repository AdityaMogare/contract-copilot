# 06 – Award data: USAspending → PostgreSQL (the data platform for Text-to-SQL and the competition check)

> Written by Claude at Aditya's request (2026-11-14). Every decision has a **Why**.
> Facts measured before writing (not guesses):
> - USAspending `POST /api/v2/search/spending_by_award_count/`, awarding subtier "Department of the Air
>   Force": FY2024 **63,685 contracts** + 6,138 IDVs; FY2025 **58,554 contracts** + 6,468 IDVs.
> - `POST /api/v2/bulk_download/awards/` (contracts A–D, action_date 2024-10-01..2024-12-31) is async:
>   status `running` for ~3.3 min, then a zip URL. **One quarter = 21,650 transactions, 8.6 MB zip, 51 MB CSV,
>   297 columns, 16,795 distinct awards, 6,825 base actions (mod 0).**
> - Competition fields are present on every transaction. `other_than_full_and_open_competition` carries the
>   **FAR authority in the text**: "ONLY ONE SOURCE-OTHER (FAR 6.302-1 OTHER)" 2,605 rows, "AUTHORIZED BY
>   STATUTE (FAR 6.302-5(A)(2)(I))" 1,281, "NATIONAL SECURITY (FAR 6.302-6)" 377, …; `extent_competed`:
>   FULL AND OPEN 7,674, NOT COMPETED 3,660, COMPETED UNDER SAP 3,200, …
> - PostgreSQL Flexible **Standard_B1ms available in canadacentral**; retail **$0.0185/hour ≈ $13.50/month**
>   if left running (storage billed separately, even when stopped).
> - Our ACA environment (express) has **no static IP, no VNet, and no published outbound IPs**, so a
>   Postgres firewall rule can't name the app's address.
>
> Done = FY2025 Air Force contract data in Postgres (`awards`, `transactions`), loaded idempotently from a
> blob-archived download; the app's managed identity can only `SELECT` through a read-only role; `/smoke`
> has a 6th check (`postgres`: `SELECT 1` as the MI) green locally and live.

## 1. Requirements
**Functional**
- `uv run python -m awards.load --fy 2025` downloads Air Force contract transactions for that fiscal year
  (4 quarterly bulk downloads), archives the zips in Blob, and loads Postgres. Re-running replaces that FY.
- Tables designed for Text-to-SQL (feature 07): few tables, plain names, every column commented, codes
  kept next to readable labels, the FAR authority parsed into its own column (`far_authority = '6.302-1'`).
- Read-only access path: the app's managed identity logs in with an Entra token and is a member of
  `copilot_reader` only (SELECT on the two tables, read-only transactions, 5 s statement timeout).
- `/smoke` gains a `postgres` check.

**Non-functional**
- Cost: **~$13.50/month if running 24/7** + ~32 GB storage. Mitigation: `az postgres flexible-server stop`
  when idle (Azure **auto-starts a stopped server after 7 days**). Students subscriptions may include free
  B1ms hours; verify on the bill after a week, don't assume.
- Security: **no passwords anywhere**. Entra-only authentication (password auth disabled), TLS required,
  least-privilege DB roles. Network is the weak spot (see Decisions).
- Load time: dominated by USAspending's async file generation (~3–4 min per quarter). Loading ~85K rows
  with `COPY` is seconds.

**Out of scope**
- Text-to-SQL itself (07), the competition-check agent (08). This feature only makes the data trustworthy.
- IDVs (`IDV_A..E`), grants, sub-awards; other agencies; FY2024 (one flag away once FY2025 works).
- LangGraph checkpoint tables (08 creates them in the same server, separate schema).

## 2. Core entities
- `awards`: one row per contract (`contract_award_unique_key`): who, what (NAICS, PSC, description), how it
  was competed, values, dates.
- `transactions`: one row per contract action (base award + each modification): date, obligation, mod number.
- `load_runs`: audit of each load (fy, files, row counts, started/finished, source URLs).

## 3. API
No new endpoint (07 adds the query path). Changes:
```
GET /smoke   +{"name":"postgres","ok":true,"ms":..,"detail":"SELECT 1 as copilot_reader (aad)"}   (unchanged shape)
CLI: uv run python -m awards.load --fy 2025 [--quarters 1,2] [--from-blob]
     --from-blob: skip USAspending, reload from the archived zips (reproducible, fast)
```

## 4. Data types, access patterns & scale
**Schema `awards` (Postgres 16)** (abridged; every column gets a `COMMENT ON COLUMN` used by 07's prompt)
```
awards(
  award_key text PK,                -- contract_award_unique_key
  piid text, parent_idv_piid text,  award_type text,          -- e.g. DELIVERY ORDER, DEFINITIVE CONTRACT
  recipient_name text, recipient_uei text,
  naics_code text, naics_description text, psc_code text, psc_description text,
  description text,                 -- base award description
  awarding_office text, pop_state text,
  first_action_date date, last_action_date date, fiscal_year int,
  total_obligated numeric(18,2),    -- sum of federal_action_obligation in loaded transactions
  current_total_value numeric(18,2), potential_total_value numeric(18,2),
  extent_competed_code text, extent_competed text,
  other_than_full_open_code text, other_than_full_open text,
  far_authority text,               -- parsed: '6.302-1', '6.302-5(a)(2)(i)', NULL when competed
  solicitation_procedures text, number_of_offers_received int,
  type_of_set_aside text, fair_opportunity_limited_sources text,
  type_of_contract_pricing text, commercial_item_procedures text,
  competition_source text           -- 'base_action' | 'earliest_loaded_action' (see below)
)
transactions(award_key FK, modification_number text, action_date date, fiscal_year int,
             federal_action_obligation numeric(18,2), action_type text, description text,
             PRIMARY KEY (award_key, modification_number, action_date))
```
Indexes: `awards(far_authority)`, `awards(extent_competed_code)`, `awards(naics_code)`,
`transactions(action_date)`. Size estimate FY2025: ~85K transactions, ~60K awards → < 200 MB.

**Competition fields come from the base action when it's in the data** (mod 0), else from the earliest loaded
action (`competition_source` says which). Why: a FY2025 window contains modifications of contracts awarded
years earlier; their competition coding is carried on each mod, but the base action is the authoritative one.

**Access patterns**: analytical reads only (counts, sums, group-bys by competition reason, NAICS, recipient).
Writes: one bulk load per FY, rare.

### Decisions
| Decision | Why | Alternative rejected |
|---|---|---|
| **Bulk download API, archived to Blob, then `COPY`** | One async request per quarter returns every column; the zip in Blob makes loads reproducible (`--from-blob`) and is the raw-data lineage, same pattern as `far-raw` | Paging `spending_by_award` (no competition fields) or per-award detail calls (~60K requests) |
| **FY2025, Air Force, contracts A–D only** | context.md: one agency, 1–2 FYs. ~85K rows is enough for real analytics and small enough to reason about | Both FYs now (doubles load + validation before anything uses it) |
| **Two tables + a load audit, not the 297-column CSV** | Text-to-SQL accuracy depends on a small, well-named, commented schema. Codes + labels side by side let the LLM filter on stable codes | Raw wide table (the LLM must guess among 297 columns) |
| **`far_authority` parsed from the label** (`(FAR 6.302-1 OTHER)` → `6.302-1`) | It's the join key to the FAR index for the competition check (08): "this award cites 6.302-1 → retrieve 6.302-1" | Leaving it inside free text |
| **Entra-only auth; MI mapped to a DB principal in role `copilot_reader`** | Same no-secrets story as everything else. The token (scope `https://ossrdbms-aad.database.windows.net/.default`) is the password; it expires ~1 h, so the pool fetches a fresh one per new connection | Password in Key Vault (works, but it's a long-lived secret to rotate) |
| **`copilot_reader`: SELECT only, `default_transaction_read_only=on`, `statement_timeout=5s`** | Defense in depth for 07: even if a bad query got past sqlglot, the DB itself refuses writes and long scans | Rely on the app-side SQL validator alone |
| **Public endpoint + "allow Azure services" firewall + my IP; no VNet** | Express env exposes no outbound IPs and no VNet, so IP pinning is impossible. With password auth disabled, reaching 5432 isn't enough: a caller needs an Entra token for a principal we created. **Accepted risk, written down** | VNet integration (needs a non-express env: recreate the ACA environment, out of scope now) |
| **Loader runs as Aditya (Entra admin), app is read-only** | Least privilege, like ingestion in 03 | MI with write access |
| **psycopg 3 (async) + psycopg_pool** | Native async for FastAPI; `COPY` support for loading | asyncpg (no `COPY FROM STDIN` from a file-like as simple) |
| **Stop when idle** | B1ms bills by the hour; idle most of the week | Always on (~$13.50/mo of a $30 budget) |

## 5. Data flow (numbered hops)
**Load (local, as Aditya)**
1. **CLI → USAspending:** `POST https://api.usaspending.gov/api/v2/bulk_download/awards/` `{filters:{prime_award_types:[A,B,C,D],
   agencies:[{type:awarding,tier:subtier,name:"Department of the Air Force",toptier_name:"Department of Defense"}],
   date_type:action_date, date_range:{Q}}, file_format:csv}` · no auth → `{status_url, file_url}`.
   Fails: 400 bad filter; 429/5xx → backoff.
2. **CLI → USAspending (poll):** `GET /api/v2/download/status?file_name=…` every 10 s until `finished` (~3–4 min) or `failed`.
3. **CLI → files.usaspending.gov:** `GET file_url` → zip (~9 MB/quarter). Saved to its own temp dir (untrusted file).
4. **CLI → Blob:** `PUT https://stcczq9h.blob.core.windows.net/usaspending-raw/fy2025/q1.zip` · scope
   `https://storage.azure.com/.default` · *Storage Blob Data Contributor*.
5. **CLI → Entra:** token for `https://ossrdbms-aad.database.windows.net/.default` (AzureCliCredential).
6. **CLI → Postgres:** TLS to `pg-cczq9h.postgres.database.azure.com:5432`, user = my UPN, password = token.
   `BEGIN; CREATE TEMP TABLE staging…; COPY staging FROM STDIN (CSV); DELETE … WHERE fiscal_year=2025;
   INSERT INTO transactions/awards SELECT … FROM staging; INSERT INTO load_runs…; COMMIT; ANALYZE`.
   Fails: 28000 (no such Entra principal / token for wrong scope), 08001 (firewall: my IP changed), COPY
   type errors → the whole FY load rolls back (old data stays).

**Read (app, as MI)** (`/smoke` now; 07 later)
7. **App → ACA identity endpoint:** `GET /msi/token` for the ossrdbms scope (cached ~1 h; refreshed per new pool connection).
8. **App → Postgres:** TLS, user = `id-app-cczq9h` (the Entra principal name), password = token → session as
   member of `copilot_reader` → `SELECT 1`. Fails: 28P01/28000 if the principal isn't created or the token is
   for the wrong scope; 57014 on statement timeout; 25006 if anything tries to write.

## 6. High-level design
```
awards/
  usaspending.py   request_download(fy, q) → poll → download (httpx, retries)
  transform.sql    staging → awards/transactions (competition_source, far_authority regex)
  load.py          CLI: per quarter: download|from-blob → blob → COPY → transform; one transaction per FY
  schema.sql       tables, comments, indexes, role copilot_reader + grants
app/db.py          AsyncConnectionPool(min 0, max 4) whose connect() fetches an Entra token per connection
app/smoke_checks.py + check_postgres
infra/setup.sh     step 9: Postgres Flexible B1ms PG16, Entra-only, Aditya as Entra admin, firewall rules;
                   step 9b: blob container usaspending-raw; step 9c: create MI principal + grant copilot_reader
                   (SQL via psql as Entra admin: pgaadauth_create_principal('id-app-cczq9h', false, false))
```
New deps: `psycopg[binary]`, `psycopg-pool`.

**Tests** (no network): far_authority parser on the real labels seen above; competition_source rule
(base vs earliest); transform SQL run against a tiny CSV fixture in a **local** Postgres? → no: keep tests
DB-free by testing the Python-side parsers and running transform.sql only in the live load (verified by
row-count reconciliation in `load_runs`: CSV rows = transactions rows; distinct award keys = awards rows).

**Build order (one concept per commit)**
1. infra: Postgres server (⚠ starts billing), firewall, Entra admin; blob container (run with --debug, flag cost)
2. feat: schema + roles (applied as Entra admin)
3. feat: USAspending client + loader (Q1 first → reconcile counts → full FY)
4. feat: app pool with Entra tokens + `/smoke` postgres check; MI principal + grant
5. deploy; live `/smoke` 6/6; trace (App Insights shows the `/msi/token` for the ossrdbms scope + the DB span)

## 7. Expected deep-dive questions
1. **How does the app log in to Postgres without a password, and what happens when the token expires
   mid-session?** (Entra principal mapped to a role; token as password; validated at connect only, so an open
   connection outlives its token; pool refreshes per new connection; max connection lifetime < token lifetime.)
2. **Your database has a public endpoint. Defend that.** (express env, no outbound IPs; Entra-only auth means no
   password to brute-force; read-only role + timeouts; what you'd do in production: VNet-integrated environment +
   private endpoint, and why that wasn't worth recreating the environment for a portfolio.)
3. **How do you know the data you loaded is correct and complete?** (row reconciliation per load, `load_runs`
   audit, base-vs-mod competition rule, idempotent per-FY replace in one transaction, raw zips archived for replays.)

---
## After building
### Results
- FY2025 load: 4 quarters, **105,408 transactions → 56,832 awards**, reconciled in the same DB transaction
  (`load_runs`), 803 s end to end (≈ 3–4 min per quarter waiting for USAspending; COPY is seconds).
  Quarter sizes: 21,650 / 22,891 / 25,242 / 35,625 (Q4 = fiscal-year-end spending).
- `competition_source`: base_action 32,791, earliest_loaded_action 24,041 (42% are mods of pre-FY2025 awards).
- Sanity: $98.39B obligated; top `far_authority` 6.302-1 (6,417 awards, $27.9B); 6,526 awards coded as
  competed (A/D) with exactly one offer, a signal for the competition check (08).
- Live `/smoke` 6/6: `postgres ok user=id-app-cczq9h read_only=on copilot_reader=True` (178 ms).

### Trace vs prediction
| Predicted | Observed | Why it matters |
|---|---|---|
| Step 9 creates the server | **409 `MissingSubscriptionRegistration`** for `Microsoft.DBforPostgreSQL`; hidden at first because I piped the script through `tail` | Register providers up front (now in step 0); never trust `$?` through a pipe |
| `--public-access None` = public endpoint with no rules | It **disables** the public endpoint; firewall rules then fail ("not supported for a server without public access") | `update --public-access Enabled`, then rules |
| `ALTER ROLE copilot_reader SET statement_timeout …` covers the app | **Group-role settings don't apply to members**; they apply to the role that logs in | Set on the MI's login role (`id-app-cczq9h`), plus per-session options from the pool |
| transform.sql (staging → tables) | Transform in Python (`awards/transform.py`) | Testable without a database; COPY still does the bulk write |
| FY2025 ≈ 85K transactions, ~60K awards | 105,408 and 56,832 | Q4 is 1.6× Q1. The search API's count (58,554 contracts) uses a different time filter than "action dated in FY2025" |
| Quarter download ≈ 3–4 min | Same; Q1 was instant on reload because USAspending served the file it had already generated | Their cache is keyed by the filter |
| — | A failed `containerapp update` (image tag never built) **still replaced the revision** and took the app down for minutes | Step 13 now refuses a tag that isn't in ACR (debugging log) |

### Break-it results (as `copilot_reader` with the app's exact session options)
| Drill | Result |
|---|---|
| `INSERT INTO awards …` | **25006** read-only transaction (blocked before permissions are even checked) |
| `SELECT * FROM load_runs` | **42501** permission denied (role only has SELECT on awards, transactions) |
| `SELECT pg_sleep(10)` | **57014** statement timeout after **5.1 s** |
| Remove the MI's principal | not run (would break live `/smoke`; planned with the other drills) |
### 30-second explanation
-
