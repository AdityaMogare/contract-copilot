# 05 – Retrieval tuning: measured before/after, without fooling ourselves

> Written by Claude at Aditya's request (2026-11-14). Every decision has a **Why**.
> Facts measured before writing:
> - Baseline (design 04): retrieval hit@8 **16/19**; misses g06 (2.101 SAT definition), g10 (16.202-2
>   "Application." not retrieved for "when is FFP appropriate"), g15 (15.403-1 exceptions).
> - 2.101 holds **235 definitions** (`<P><I>Term</I> means …`), packed today into 33 chunks of ~650
>   tokens, so each vector averages ~7 definitions. Other definition-heavy sections: 31.001 (58),
>   25.003 (34), 45.101 (20), 52.245-1 (20).
> - Of 1,556 subsections (`N.NNN-N`), many have generic titles: "General" 42, "Contract clause(s)" 32,
>   "Definitions" 10, "Policy" 10, "Procedures" 8, "Application" 7, … The parent section's title
>   ("16.202 Firm-fixed-price contracts") is not in our chunk header today.
> - Search: storage 17.3 MB / 50 MB, 1 of 3 indexes. A second full index fits (≈ 35–37 MB total).
>
> Done = a before/after table on a **held-out** set the tuning never saw, the alias switched to the
> winner (or left on v1 if nothing wins), and every experiment recorded, including the ones that lost.

## 1. Requirements
**Functional**
- A **retrieval-only** eval (embed + search, no chat): hit@k, MRR, and per-question rank of the first
  expected section, for k ∈ {3, 5, 8}. Cheap (~$0.0001/run) and fast (~15 s), so experiments are many.
- A **held-out set** of 12 new questions (10 answerable, 2 unanswerable) written and committed *before*
  any experiment runs, and scored only once, at the end, for before vs after.
- Experiments, one change at a time, on a **new index `far-chunks-v2`** built side by side; the
  alias flips only if the held-out result is better. Rollback = flip the alias back.

**Non-functional**
- Cost: one re-embed per index build ≈ $0.03; held-out end-to-end eval ≈ 12 × $0.003. Total < $0.25.
- Search storage stays < 45 MB while v1 and v2 coexist (gate; stop if exceeded).
- No change to `/ask`'s API. Latency must not get worse (top_k changes affect chat tokens).

**Out of scope**
- Semantic ranker (Basic tier, ~$74/mo), query rewriting with an LLM (adds a call per request),
  fine-tuning embeddings, larger dims. Each is a later, separately justified step.
- Changing the answer prompt (that's answer quality, not retrieval).

## 2. Methodology (the part interviewers probe)
| Rule | Why |
|---|---|
| **Dev set = the existing 19 answerable golden questions; held-out = 10 new ones** | Tuning on the same questions you report is overfitting: g06/g10/g15 would get "fixed" by changes that only help them. The held-out number is the one quoted |
| **Held-out written before the first experiment, committed, then not looked at** | If I see held-out failures while tuning, they become dev questions in disguise |
| **One variable per experiment, retrieval-only metric first** | Attribution: if two changes ship together, we can't say which one helped. Retrieval-only is cheap enough to run every variant |
| **Report losing experiments too** | A table of only wins is a red flag in an interview (and in science) |
| **Small-n honesty** | 19 + 10 questions: a difference of 1 question is noise. Say "3 more hits out of 19", not "+16%" |

## 3. Experiments (in order; each builds on the previous winner)
| # | Change | Hypothesis | Affects | Needs re-index? |
|---|---|---|---|---|
| E0 | **Ablation**: BM25-only vs vector-only vs hybrid (current) | Shows what each half contributes; expect hybrid ≥ both | query only | no |
| E1 | **Parent-section title in the chunk header** for subsections: `FAR 16.202-2 Application — under 16.202 Firm-fixed-price contracts` | Generic subsection titles lose the topic; adding the parent title fixes g10-type misses | chunker | yes (v2) |
| E2 | **One chunk per definition** in definition lists (2.101 and any section with ≥ 5 `<I>Term</I> means` paragraphs); header `FAR 2.101 Definitions — "Simplified acquisition threshold"` | One definition per vector makes the term the dominant signal; fixes g06-type misses. Cost: 2.101 goes 33 → ~235 chunks (+~200 for the other sections) | parser + chunker | yes (v2) |
| E3 | **top_k 8 → 12** (only if E1+E2 still miss at 8 but hit at 12) | More context for multi-section questions; costs ~50% more prompt tokens | query only | no |

E1 and E2 are built into v2 together **but evaluated separately**: v2 is built with both; E1-alone is
measured by building with only E1 first on dev (retrieval-only), then E2 added. (Two builds of v2 ≈ $0.06.)

**Not chosen up front, recorded as ideas:** sibling expansion (fetch the other chunks of the cited
section), field-weighted BM25 scoring profile on `section_title`, query-side "FAR term" synonym map.

## 4. Data / index changes
- `ingestion/parse.py`: `Block.term` set when a `<P>` starts with `<I>` and continues with "means";
  `Section.parent_title` = title of `N.NNN` for subsection `N.NNN-N` (from the same part XML).
- `ingestion/chunk.py`: header gets `— under {parent} {parent_title}`; definition-list sections become
  one unit per term (lead-in paragraph stays with the first), and units are **not packed** together.
  A definition longer than 700 tokens still splits by blocks (existing rule).
- Chunk ids stay deterministic: `2_101--term-simplified-acquisition-threshold` style is tempting but ids
  must be stable under text edits; keep `{section}--{n:03d}`.
- `--index far-chunks-v2` flag on `ingestion.run` (writes a named version; app untouched).
- Alias flip = `PUT /aliases/far-chunks {"indexes":["far-chunks-v2"]}` (infra step 7b with a variable).
  Deleting v1 afterwards needs Aditya's OK (CLAUDE.md: no resource deletes without asking).

## 5. Data flow
Unchanged from 03 (ingest) and 04 (query). New: `evals/retrieval.py` runs hops 4–5 only (embed + search
against a chosen index name, bypassing the alias) for each dev/held-out question.

## 6. High-level design
```
evals/heldout.jsonl          12 new questions (written first, committed, then sealed)
evals/retrieval.py           --index far-chunks-v1|v2 --mode hybrid|bm25|vector --set dev|heldout --k 12
                             → hit@3/5/8, MRR, first-hit rank per question → evals/reports/…-retrieval-<label>.md
ingestion/parse.py, chunk.py E1 (parent title), E2 (definition units), behind flags for A/B builds
ingestion/run.py             --index <name>, --no-parent-title, --no-definition-units (for E1-alone build)
infra/setup.sh step 7b       alias target from a variable
```
Tests: definition detection on 2.101 fixture (235 terms in the real section); one-definition-per-chunk;
parent title present for `6.302-1` (→ "6.302 Circumstances permitting other than full and open
competition"); flags off ⇒ chunks identical to v1 (hash-equal), proving the A/B builds differ only as intended.

## 7. Expected deep-dive questions
1. **How do you know your tuning generalizes?** (dev vs held-out, sealed before tuning, one variable at a
   time, small-n caveats, report losers.)
2. **Why did definitions retrieve badly, and what's the trade-off of one-chunk-per-definition?** (vector
   dilution vs index size and more, shorter chunks competing; why packing helps elsewhere but hurts here.)
3. **How do you ship an index change safely?** (side-by-side v2, alias flip = atomic cutover, rollback,
   storage gate on Free tier, re-embed cost, what you'd do on a bigger corpus: blue/green with partial rebuilds.)

---
## After building
### Results (dev, retrieval-only, 19 answerable; reports in `evals/reports/2026-11-14-retrieval-dev-*.md`)
| # | Index | Query | hit@3 | hit@5 | hit@8 | hit@12 | MRR | Misses (rank) |
|---|---|---|---|---|---|---|---|---|
| E0 | v1 | **hybrid (production)** | 13 | 15 | 16 | 17 | 0.664 | g06 –, g10 –, g15 10 |
| E0 | v1 | BM25 only | 12 | 13 | 13 | 13 | 0.563 | 6 misses |
| E0 | v1 | vector only | 15 | 18 | 18 | 18 | 0.800 | g06 – |
| E0b | v1 | hybrid, vector weight 2 | 14 | 16 | 18 | 18 | 0.696 | g06 – |
| E0b | v1 | hybrid, vector weight 3 | 15 | 16 | 18 | 18 | 0.731 | g06 – |
| E1 | v2 (parent title) | hybrid | 12 | 14 | 16 | 18 | 0.654 | g06 –, g10 12, g15 10 |
| E1 | v2 (parent title) | hybrid, vw 3 | 15 | 16 | 18 | 18 | 0.706 | g06 – |
| E1 | v2 (parent title) | vector | 15 | 17 | 18 | 18 | 0.796 | g06 – |
| E1+E2 | v2 (+ definition chunks) | hybrid | 13 | 14 | 17 | 19 | 0.668 | g10 12, g15 10 |
| **E1+E2** | **v2** | **hybrid, vw 3 (shipped)** | **17** | **18** | **19** | 19 | **0.768** | none |
| E1+E2 | v2 | vector | 17 | 18 | 19 | 19 | 0.890 | none |

What each experiment did:
- **E0 (not predicted):** BM25 was the weak half. Equal-weight RRF let keyword noise on natural-language
  questions push correct vector hits out of the top 8. Vector-only beat hybrid.
- **E0b:** weighting the vector query ×2–3 recovered g10 and g15 while keeping BM25 in the mix.
- **E1 (parent title): neutral.** g10 went from absent to rank 12 under plain hybrid, nothing else moved;
  MRR changes are within noise. Kept because it costs nothing and helps the LLM read split-off chunks,
  but it is **not** a measured retrieval win.
- **E2 (one chunk per definition): the win.** g06 fixed in every mode. Applied to every section with ≥ 5
  defined terms (not just 2.101): 4,068 → 6,442 chunks; incremental rebuild re-embedded only 2,670 (268K tokens).
- **E3 (top_k 12): not run.** With E1+E2+vw3 every dev question hits within 8, so there was nothing for it to fix.

**Pre-registered before opening the held-out set** (commit "pre-register the 'after' config"):
v2 + hybrid with vector weight 3. Not vector-only, despite its higher dev MRR: the dev set has no
exact-identifier questions ("what does 52.219-14 require?"), which is what BM25 is for.

### Results (held-out, before vs after, end to end; `evals/reports/2026-11-14-heldout-{before,after}.md`)
| Held-out (10 answerable + 2 unanswerable) | Before: v1, hybrid | After: v2, hybrid vw 3 |
|---|---|---|
| Retrieval hit@8 (retrieval-only eval) | 7/10, MRR 0.575 | **9/10, MRR 0.772** |
| Expected section cited | 7/10 | **9/10** |
| False "I don't know" | 1/10 | **0/10** |
| Correct "I don't know" | 2/2 | 2/2 |
| Latency p50 / p95 | 3.37 s / 5.98 s | 3.60 s / 6.85 s (within noise) |
| Avg prompt tokens | 3,719 | **3,215** (definition chunks are shorter) |

Remaining held-out miss: h04 (16.301-3 "Limitations" of cost-reimbursement contracts), rank 11.

**Dev end to end with the shipped config** (`2026-11-14-dev-after.md`): retrieval 19/19, citation hit 19/19,
false IDK 0/19, **correct IDK 5/6** (was 6/6). u03 (AFFARS 5306.304 approvals) became a grounded `partial`:
"The provided sources do not include AFFARS 5306.304", followed by the FAR 6.304 approval levels with
citations. Not a hallucination, but it doesn't match the golden label; the label is left for Aditya's
golden-set review rather than changed after seeing the result.

**Shipped:** `rag_vector_weight=3` + image `5eead46`, then alias `far-chunks` → `far-chunks-v2`
(`PUT /aliases` → 204). Live: "What is the simplified acquisition threshold?" → `answered`, $350,000,
`FAR 2.101 ("Simplified acquisition threshold")`. Rollback = `SEARCH_INDEX_VERSION=far-chunks-v1 ./infra/setup.sh 7b`.
`far-chunks-v1` kept for rollback (Search storage 39.2 MB / 50 MB with both); deleting it needs Aditya's OK.

### Trace vs prediction
| Predicted | Observed |
|---|---|
| Hybrid ≥ BM25 and ≥ vector (E0) | **Vector-only beat hybrid** (dev MRR 0.80 vs 0.66). Fixed by weighting, not by dropping BM25 |
| E1 fixes g10 | Neutral; g10 was fixed by the vector weight, not the header |
| E2 adds ~200 chunks for 2.101 + a few sections | +2,374 chunks: many parts have a "Definitions" section with ≥ 5 terms |
| Second index ≈ 35–37 MB total | 39.2 MB (v2 is 22.5 MB: more, shorter chunks) |
| Definition detector: `<I>Term</I> means` | 214/235 at first; aliases ("*Agency head* or *head of the agency* means"), statute cites and "as defined in" forms needed a looser rule → 235/235 |
| Vector index counts toward a quota | Still `null` on Free; vector size 66 MB with two indexes, no error |
### 30-second explanation
-
