# 03 – FAR ingestion: fetch → parse → clause-aware chunk → embed → index

> Written by Claude at Aditya's request (2026-11-14). Every decision has a **Why**.
> Facts measured read-only before writing (not guesses):
> - eCFR API `GET /api/versioner/v1/full/{date}/title-48.xml?part=6` → **200, 65 KB** XML.
>   Without `Accept-Encoding: gzip` it returns **406** ("requires response compression").
> - `?chapter=1` is **ignored** by the full endpoint: it returned all of Title 48 (20 MB, incl.
>   DFARS 2xx and DOE 9xx parts). So we fetch **per part**.
> - FAR = Title 48 Chapter 1, parts 1–53: **51 parts, 3,399 sections, ~996K words (~1.34M tokens)**.
>   Section length: median 154 words, p90 651, p99 2,316, max 15,193 (`2.101` Definitions).
>   132 sections are `[Reserved]`. Part 6 alone: 34 sections, ~8K words.
> - XML shape: `DIV5 TYPE=PART` → `DIV6 TYPE=SUBPART` → `DIV8 TYPE=SECTION N="6.302-1"` →
>   `HEAD` + `P` paragraphs whose text starts with `(a)`, `(1)`, `(i)`, `(A)`. Amendment history in `CITA`.
> - eCFR versions API gives a per-section `amendment_date` (Part 6 latest: 2025-10-01). Title 48 is
>   up to date as of 2026-11-12; latest issue 2026-10-28.
> - Search `srch-cczq9h` (Free) `GET /servicestats`: **storage quota 50 MB total**, 3 indexes, vector
>   quota not separately reported.
> - Embedding quota (francecentral, GlobalStandard text-embedding-3-small): **50K of 1,000K TPM used**.
>
> Done = all FAR parts indexed in `far-chunks-v1`; a hybrid query for "sole source only one
> responsible source" returns `FAR 6.302-1` in the top 3; re-running the same date embeds 0 chunks.

## 1. Requirements
**Functional**
- One command ingests a FAR snapshot: `uv run python -m ingestion.run --date 2026-10-28 [--parts 6]`.
- Raw XML for every part is kept in Blob (`far-raw`) so any chunk can be traced back to its source bytes.
- Chunks follow the regulation's structure: **a chunk never crosses a section boundary**, and splits
  inside a long section happen only at top-level paragraph boundaries (`(a)`, `(b)`, …).
- Every chunk carries a citable reference (`FAR 6.302-1(b)–(c)`), its part/subpart/section, the
  section's amendment date, the snapshot date, and a link to acquisition.gov.
- **Idempotent and incremental:** re-running the same snapshot embeds nothing; a new snapshot re-embeds
  only changed chunks and deletes chunks that no longer exist.
- Index supports **hybrid** search (BM25 keywords + vectors, fused with RRF) and filters by part/section.

**Non-functional**
- Cost per full ingest ≈ **$0.03** of embeddings (1.34M tokens × $0.02/1M). Storage and Search Free: $0.
- Index must fit in **50 MB** (Free tier) with ≥ 30% headroom → design target ≤ 35 MB.
- Full run < 10 min (needs embed TPM raised, see §4).
- Runs locally as Aditya (Week 1). The steps are plain functions so the Week 2 event-driven worker
  can call the same code per part.

**Out of scope**
- DFARS / AFFARS (Title 48 chapters 2 and 53xx). Relevant to the Air Force, but FAR first.
- Event Grid / Service Bus / Functions (Week 2). The RAG endpoint and golden questions (feature 04).
- Table layout fidelity: tables and images are flattened to text; the ~90 images become `[image omitted]`.
- Integrated vectorization (Search calling OpenAI itself). We embed in our own code.

## 2. Core entities
- `Section`: part, subpart, number (`6.302-1`), title, paragraphs, amended_on.
- `Paragraph`: label (`a`, `1`, `i`, `A`), depth, text.
- `Chunk`: id, section fields, `paragraph_range` (`(b)–(c)`), `citation`, `content` (header + text), `content_hash`, `vector`.
- `IngestReport`: parts fetched, sections, chunks total / embedded / skipped / deleted, tokens embedded, index size.

## 3. API
No HTTP endpoint in this feature. CLI only:
```
uv run python -m ingestion.run --date YYYY-MM-DD [--parts 6,15] [--dry-run]
  --dry-run: fetch + parse + chunk, print stats, no embed/index writes
Output: IngestReport JSON on stdout; exit 0 ok, 1 on any failed document (partial 207 counts as failure)

uv run python -m ingestion.probe "query text" [--part 6]
  hybrid search sanity check: prints top 5 citations + scores
```

## 4. Data types, access patterns & scale
**Index `far-chunks-v1` schema**
| Field | Type | Attributes | Why |
|---|---|---|---|
| `id` | String (key) | | `6_302-1--001`. Deterministic from section + chunk number, so re-runs overwrite. Keys allow only letters, digits, `_ - =`, so `.` becomes `_` |
| `content` | String | searchable (`en.microsoft` analyzer) | BM25 side of hybrid; also what the LLM reads |
| `content_vector` | Collection(Single), **512 dims** | searchable, `stored: false`, HNSW cosine | vector side. Not retrievable (we never return vectors), so no stored copy costs storage |
| `section` | String | filterable, facetable | `6.302-1`: exact citation filter |
| `part`, `subpart` | String | filterable, facetable | scope a question to Part 6 |
| `section_title` | String | searchable | headings carry strong keywords ("Only one responsible source") |
| `paragraph_range` | String | retrievable | `(b)–(c)` |
| `citation` | String | retrievable | `FAR 6.302-1(b)–(c)`: the string we show the user |
| `url` | String | retrievable | `https://www.acquisition.gov/far/6.302-1` |
| `amended_on` | DateTimeOffset | filterable, sortable | the "effective date" metadata context.md asks for |
| `snapshot_date` | DateTimeOffset | filterable | which eCFR point-in-time this came from |
| `content_hash` | String | filterable, retrievable | sha256 of content + embed deployment + dims. Unchanged hash ⇒ skip re-embedding |

**Sizing (estimate, to be measured on Part 6 first)**
- Chunks ≈ 4.7K (sections ≤ 700 tokens stay whole; 689 sections > 400 words get split).
- Vectors: 4.7K × 512 × 4 B ≈ **9.6 MB** (+ HNSW graph overhead). At 1536 dims it would be ≈ 29 MB, plus
  text and inverted index: too close to 50 MB.
- Text + inverted index: ~6.5 MB raw text, roughly × 1.5–2 indexed ≈ 10–13 MB.
- Projection ≈ 25 MB. **Gate:** after indexing Part 6, read `GET /servicestats`, divide by chunk count,
  extrapolate to 4.7K. If the projection > 35 MB, stop and revisit (int8 quantization or fewer parts).

**Access patterns**
- Write: bulk, rare (a FAR amendment is published every few weeks). Read: per user question, top-k 5–10 hybrid.
- Blob: `far-raw/ecfr/{date}/part-{N}.xml`, written once per snapshot, read on re-parse. ~51 blobs, ~6 MB.

**Embed throughput**: the `embed` deployment is 50K TPM, so 1.34M tokens would take ≥ 27 min.
Raise to **300K TPM** in `infra/setup.sh` step 6 (we have 950K unused quota). **No cost change:**
GlobalStandard bills per token, and capacity is only a rate limit. Then a full run is ≈ 5 min.

### Decisions
| Decision | Why | Alternative rejected |
|---|---|---|
| **eCFR versioner API** as source | Structured XML with the exact hierarchy, point-in-time by date (gives version metadata for free), per-section amendment dates, no auth | acquisition.gov HTML (no point-in-time API); PDF + OCR (loses structure, adds errors). eCFR isn't the "official legal edition", which is fine for a portfolio project; noted in answers |
| **Fetch per part** | `chapter=1` filter is ignored; per-part keeps each blob small and maps 1:1 to a Week 2 event/message | one 20 MB Title-48 blob with non-FAR parts mixed in |
| **Section is the chunk unit; split only at top-level paragraphs** | A citation must point to a real provision. Sections are the unit lawyers cite. Splitting mid-paragraph separates a rule from its exceptions | fixed 512-token windows with overlap: crosses provision boundaries, citations become fuzzy |
| **Max 700 tokens per chunk, greedy-pack top-level paragraphs** | Median section (~210 tokens) stays whole; long ones like 6.302-1 split into (a), (b)–(c), … Larger chunks dilute the vector; smaller ones lose the rule's context | per-sentence chunks |
| **Contextual header prepended to every chunk** (`FAR 6.302-1 Only one responsible source… — Part 6 Competition Requirements > Subpart 6.3`) | A split-off "(c) Application…" paragraph is meaningless alone. The header puts the section and its ancestors into both BM25 and the vector | storing the header only as metadata (invisible to the embedding) |
| **No overlap between chunks** | Boundaries are structural, so there is nothing to "bridge". At answer time we can fetch the sibling chunks of the same section by filter | 10–20% overlap: duplicates text and cost |
| **512 embedding dims** (text-embedding-3-small supports `dimensions`) | Fits Free tier with headroom. OpenAI reports only a small quality drop vs 1536 for this model. Must be the **same at query time** | 1536 dims (doesn't fit); int8 quantization (keeps full-precision originals for rescoring ⇒ no saving unless rescoring is off) |
| **content_hash ⇒ skip unchanged** | Re-runs are free and fast; a FAC touching 10 sections re-embeds ~10 chunks | delete-and-rebuild the index every time |
| **Delete stale chunk ids per section** | If 6.302-1 shrinks from 4 chunks to 3, `--003` would otherwise linger and get cited | ignore (silent stale citations) |
| **Index name carries a version** (`far-chunks-v1`), from config `SEARCH_INDEX` | Schema changes (analyzer, dims) need a new index. Build v2 alongside, switch config, then delete v1 (with Aditya's OK). Free tier allows 3 indexes | mutate in place (most field changes are rejected by Search) |
| **Runs as Aditya locally; app MI stays read-only** | Least privilege: the internet-facing app can't modify the index. The Week 2 worker gets its own write role | give the app MI Index Data Contributor |
| **`defusedxml`** for parsing | Cheap guard against entity-expansion XML attacks, even from a trusted source | plain `xml.etree` |

### Paragraph labels (the tricky part)
FAR nests `(a)` → `(1)` → `(i)` → `(A)` → `(*1*)`. Only **top-level** labels matter for splitting and
citations. `(i)` is ambiguous: roman numeral 1 *or* the letter after `(h)`. Rule: a lowercase letter
is top-level **iff it is the expected next letter** after the previous top-level label (`(h)` → `(i)`
is a letter; `(1)` → `(i)` is roman). Text before the first label (a lead-in sentence) joins the first chunk.
Unit tests cover 6.302-1 and a section that really has `(i)` as a letter.

## 5. Data flow (numbered hops) for `--parts 6`
Credential: `DefaultAzureCredential` → locally resolves to **AzureCliCredential** (Aditya). Tokens cached per scope.
1. **CLI → eCFR versions:** `GET https://www.ecfr.gov/api/versioner/v1/versions/title-48.json?part=6` · no auth ·
   → `content_versions[]` with `identifier`, `amendment_date`. Fails: 429/5xx → retry with backoff; network → abort.
2. **CLI → eCFR full:** `GET …/full/2026-10-28/title-48.xml?part=6`, `Accept-Encoding: gzip` · no auth · → XML.
   Fails: **406** without compression (seen); 404 if the date is outside the title's history; 400 if the date is in the future.
3. **CLI → Blob:** `PUT https://stcczq9h.blob.core.windows.net/far-raw/ecfr/2026-10-28/part-6.xml` · Bearer token,
   scope `https://storage.azure.com/.default` · role *Storage Blob Data Contributor* · body = XML.
   Fails: 403 `AuthorizationPermissionMismatch` if the role is missing; shared key is disabled, so only Entra works.
4. **Parse + chunk (local, no network):** XML → Sections → Chunks + sha256. Fails: unexpected structure → that section is logged and skipped, and the run exits 1.
5. **CLI → Search (control plane):** `GET https://srch-cczq9h.search.windows.net/indexes/far-chunks-v1?api-version=2024-07-01`;
   on 404 → `PUT /indexes/far-chunks-v1` with the schema · scope `https://search.azure.com/.default` · role
   *Search Service Contributor*. Fails: 403 without the role; 400 on an invalid schema; quota error if 3 indexes exist.
6. **CLI → Search (read existing):** `POST /indexes/far-chunks-v1/docs/search` `{search:"*", filter:"part eq '6'", select:"id,content_hash", top:1000}` (paged) · role *Search Index Data Contributor* (includes read).
   → diff: new/changed ids, unchanged ids, stale ids.
7. **CLI → Azure OpenAI:** `POST https://ais-cczq9h.cognitiveservices.azure.com/openai/deployments/embed/embeddings?api-version=…`
   `{input:[≤64 texts], dimensions:512}` · scope `https://cognitiveservices.azure.com/.default` · role *Cognitive Services OpenAI User*.
   Fails: **429** with `retry-after` → sleep and retry (SDK `max_retries` stays 0 in the app; ingestion uses 5);
   400 if an input > 8,191 tokens (prevented by the 700 cap); 401 right after a role change (propagation, seen in 00).
8. **CLI → Search (write):** `POST /indexes/far-chunks-v1/docs/index` `{value:[{"@search.action":"mergeOrUpload",…}]}` in batches ≤ 500 ·
   role *Search Index Data Contributor*. Fails: **207 Multi-Status** = some docs failed while the HTTP call "succeeded";
   we check each item's `status`, retry 503/429 items once, otherwise exit 1. 413 if a batch > 16 MB.
   Quota: index full → 403/`StorageQuotaExceeded`-style error per item.
9. **CLI → Search (delete stale):** same endpoint, `"@search.action":"delete"` for stale ids.
10. **CLI → Search:** `GET /servicestats` → record storage usage in the IngestReport (feeds the sizing gate).

Query side (used by `ingestion.probe` now, feature 04 later): embed the question with **the same 512 dims** →
`POST /docs/search {search:q, vectorQueries:[{kind:"vector", vector:[…], fields:"content_vector", k:50}], top:5}` →
Search runs BM25 and HNSW, then fuses ranks with **RRF**.

## 6. High-level design
```
ingestion/
  ecfr.py      fetch_versions(part), fetch_part_xml(date, part)        (httpx, retries)
  parse.py     part_xml → [Section]                                     (defusedxml, label logic)
  chunk.py     Section → [Chunk]  (header, greedy pack ≤700 tok, ids, hash; tiktoken)
  index.py     ensure_index(), existing_hashes(part), upsert(chunks), delete(ids)
  embed.py     embed_batch(texts) → vectors (dims from config, 429 backoff)
  run.py       CLI: for part in parts: fetch → blob → parse → chunk → diff → embed → upsert → delete
  probe.py     CLI: hybrid query sanity check
app/config.py  + search_index="far-chunks-v1", embed_dimensions=512   (shared by app + ingestion)
infra/setup.sh step 6: embed capacity 50 → 300
```
New deps: `httpx`, `defusedxml`, `tiktoken`.

**Tests** (`uv run pytest`, no network): a trimmed real Part 6 XML fixture (public domain) →
- the parser finds the right sections, titles and amendment dates; reserved sections are skipped
- label logic: 6.302-1 splits at (a)/(b)/…; the `(h)`→`(i)` letter case; the lead-in joins the first chunk
- every chunk ≤ 700 tokens; ids are deterministic across runs; the header is present
- diff: unchanged hash ⇒ not embedded; a removed chunk ⇒ deleted; a 207 with one failed item ⇒ exit 1 (fake clients)

**Build order (one concept per commit)**
1. infra: raise embed TPM (record in setup.sh, run with --debug)
2. feat: eCFR fetch + parser + tests
3. feat: clause-aware chunker + tests
4. feat: index schema + embed + upsert/diff + run CLI (Part 6 only) → **sizing gate**
5. run all parts; probe queries; trace; fill "Trace vs prediction"

## 7. Expected deep-dive questions
1. **Why chunk by section/paragraph instead of fixed token windows, and what breaks?** (citation precision,
   rule + exception kept together; breaks on huge sections like 2.101, where per-definition splits are
   the next step, and on cross-references "see 13.501" that the chunk doesn't contain.)
2. **How do you keep the index correct when the FAR changes?** (snapshot dates, content hashes, stale
   deletes, versioned index name, and the Week 2 event trigger per part. What about a question asked
   *about* an old version?)
3. **Why hybrid search, and why 512 dims?** (BM25 nails exact clause numbers and terms of art like "J&A";
   vectors catch paraphrase; RRF needs no score calibration. 512 dims: a storage/quality trade-off forced
   by Free tier, and the query must use the same dims or Search rejects it.)

---
## After building
### Trace vs prediction (what I got wrong)
-
### Break-it results (planned drills)
- Query with 1536-dim vector against the 512-dim field → expect 400 from Search
- Remove *Search Index Data Contributor* from Aditya → expect 403 at hop 6/8
- Re-run same snapshot → expect 0 embedded (proves idempotency)
### 30-second explanation
-
