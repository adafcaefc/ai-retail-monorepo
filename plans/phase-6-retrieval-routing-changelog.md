# Phase 6 — Retrieval Service + SQL / Vector / Hybrid Routing

This is the persistent implementation and validation record for Phase 6. Phase 4/4.5 and Phase 5 are frozen inputs and are not modified by this work. Secrets, connection strings, vectors, and complete user-query logs are intentionally excluded.

## 1. Objective

Build a deterministic, agent-ready retrieval service that selects `SQL`, `VECTOR`, `HYBRID`, or `UNSUPPORTED`, executes only allowlisted read-only evidence retrieval, and returns structured facts, semantic evidence, citations, warnings, errors, and timing without generating a natural-language business answer.

## 2. Frozen Inputs

- Structured authority: 15 Azure SQL `retail.*` tables containing 21,571 validated business rows. Exact/current operational values come from this layer. Phase 6 does not migrate, reload, or alter it.
- Semantic authority: the frozen eight-field JSONL contract (`doc_key`, `doc_type`, `retrieval_domain`, `source_sheet`, `source_key`, `content`, `metadata`, `content_hash`). Full corpus checksum remains `f2a04b34a725f1e06a6c547fb7ab4ae1dd294a1365ca0a76c3cf2191008aa567`.
- Vector layer: unchanged `ai.EmbeddingProfile`, `ai.RetailDocument`, `ai.RetailChunk`, and `ai.RetailEmbedding` tables.
- ACTIVE profile: `local-bge-small-en-v1.5-384-v1`; provider `local_sentence_transformers`; model `BAAI/bge-small-en-v1.5`; revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`; 384 dimensions; normalized; CPU.
- Live frozen counts at inspection: 1,350 active documents, 1,361 chunks, and 1,361 embeddings.
- Phase 5 search remains exact Azure SQL `VECTOR_DISTANCE('cosine', ...)`, ACTIVE-profile isolated, optionally domain/type filtered, and parent-document deduplicated using the best chunk.
- The checked-in Phase 5 implementation and existing uncommitted Phase 5 files are treated as approved user-owned state and preserved.

## 3. Retrieval Request Contract

`RetrievalRequest` is a strict Pydantic model (`extra="forbid"`):

| Field | Type/default | Boundary |
|---|---|---|
| `query` | string, required in practical use | Maximum 1,000 characters; whitespace-only is returned as `EMPTY_QUERY` |
| `route_mode` | `auto` | One of `auto`, `sql`, `vector`, `hybrid` |
| `top_k` | `5` | Integer 1–20; also bounds SQL ranking results |
| `retrieval_domain` | null | Must be one of the eight frozen domains |
| `doc_type` | null | Must be one of the 18 frozen types and agree with its frozen domain |
| `entity_hints` | empty list | At most eight exact `{entity_type, value}` hints; value maximum 200 characters |
| `agent_context` | null | Opaque application label, maximum 128 characters; it does not authorize or select data |

The request deliberately has no table, column, SQL, embedding-profile, principal, organization, or legal-entity-scope selector. CLI `--entity TYPE=VALUE` maps to the same typed hints. Invalid/extra fields fail validation rather than being ignored.

`RoutingDecision` returns route, categorical confidence, reason codes, recognized intent/entities, selected allowlisted capabilities, selected semantic filters, `fallback_allowed=false`, and warnings. Confidence is deterministic: supported rules with a concrete semantic intent or SQL capability are `HIGH`; unsafe mutations/empty input are rejected with `HIGH` certainty; unclassified requests are `LOW`. No probability or hidden chain-of-thought is exposed.

`RetrievalResponse` returns request ID, `COMPLETE|PARTIAL|FAILED` status, route/decision, resolved entities, structured results, semantic results, citations, warnings, errors, timing, and result counts. It has no answer or generated-prose field.

## 4. Routing Contract

The router is deterministic and generative-model-free. It normalizes whitespace, applies fixed case-insensitive regular expressions, and uses this precedence:

1. Empty input, mutation verbs, SQL-control phrases, and intentionally broad “tell me everything” input → `UNSUPPORTED`.
2. A fixed ranking capability (`inventory.at_risk` or `replenishment.top_candidates`) → `SQL` even if the word “risk” has semantic meaning.
3. A recognized current capability plus `why`, `diagnose`, `recommend`, `what should`, `explain`, or semantic/current conjunction → `HYBRID`.
4. A durable semantic intent without a current-state signal → `VECTOR`.
5. A recognized current/exact capability → `SQL`.
6. Explicit valid semantic filters with no narrower intent → `VECTOR`.
7. Otherwise → `UNSUPPORTED`.

Current signals include `current`, `today`, `now`, `latest`, `position`, on-hand, ROP/reorder point, workforce/forecast, proposed/highest/ranking/count/total/sum. Semantic signals cover definitions, formulas/calculations, D365/mapping, approvals, agent responsibility, durable SKU/store/category/vendor context, model parameters, promotion policy, brand events, documentation, and business rules. A route override never creates a capability: forced SQL/HYBRID without an allowlisted structured intent is rejected; forced VECTOR without semantic intent or valid filters is rejected. All reason codes are short contract values such as `CURRENT_STATE_INTENT`, `EXACT_ENTITY_LOOKUP`, `DEFINITION_INTENT`, `FORMULA_INTENT`, `INTEGRATION_MAPPING_INTENT`, `GOVERNANCE_INTENT`, `AGENT_CONFIGURATION_INTENT`, and `CURRENT_PLUS_EXPLANATION`.

## 5. Structured SQL Capability Catalog

The live read-only inventory established the queryable fields below. Every eventual capability uses hard-coded SQL structure, explicit columns, positional parameters, deterministic ordering, and a bounded row limit.

| Table | Business key | Queryable business fields | Lineage fields |
|---|---|---|---|
| `retail.LegalEntity` | `legal_entity_id` | name, short name, workforce/sales/season factors, store size | source load/sheet/row, loaded time |
| `retail.Store` | `store_id` | legal entity, name, cluster, size/health/footfall factors, channel | source load/sheet/row, loaded time |
| `retail.Category` | `category_id` | legal entity, name, perishable flag | source load/sheet/row, loaded time |
| `retail.Vendor` | `vendor_account` | code/name/group/currency/terms, lead time, MOQ, service metrics | source load/sheet/row, loaded time |
| `retail.Brand` | `brand_name` | brand identity | source load/sheet/row, loaded time |
| `retail.Sku` | `sku_id` | legal entity/category/item/perishable, price/cost/margin, operational drivers, UOM/pack/channel/vendor/brand | source load/sheet/row, loaded time |
| `retail.TradeAgreement` | SKU/vendor/from/minimum quantity | item, price/currency, lead time/discount/validity/designated flag | source load/sheet/row, loaded time |
| `retail.Promotion` | `promotion_id` | configuration, scope, mechanism, values, dates, D365 construct | source load/sheet/row, loaded time |
| `retail.InventorySnapshot` | `sku_id` | ADS, position, ROP/max, DOS/state, price/value/risk/expiry/order/GMV/margin/funding/open PO | source load/sheet/row, loaded time |
| `retail.StoreSkuSnapshot` | SKU/store | inventory, forecast, order, promotion, contribution, labour measures | source load/sheet/row, loaded time |
| `retail.ReplenishmentProposal` | `sku_id` | reorder flag, order quantities/UOM/value, designated/best vendor prices and saving | source load/sheet/row, loaded time |
| `retail.BrandEvent` | store/event | legal entity and demand lift | source load/sheet/row, loaded time |
| `retail.WorkforceSnapshot` | `store_id` | event, workforce baseline/factors, scheduled/required/gap/surplus/coverage | source load/sheet/row, loaded time |
| `retail.MonthlySales` | period/legal entity | sales amount | source load/sheet/row, loaded time |
| `retail.SourceLoad` | `source_load_id` | workbook/source/load status, load/completion time, row count | load audit only |

The final implemented capability catalog is below. `TOP (?)` limits and all entity values are positional parameters; identifiers and SQL structure are constants in source. Single-record capabilities return at most one row.

| Capability | Intended patterns / required parameters | Sources and joins | Returned fields | Ordering / maximum |
|---|---|---|---|---|
| `sku.lookup` | exact/current SKU master/price lookup; SKU | `Sku` | SKU, item, legal entity, category, perishable, price, cost, margin, sales/buy UOM, pack, channel, vendor, brand | exact key / 1 |
| `sku.inventory_current` | inventory, ROP, DOS, value/risk; SKU | `InventorySnapshot` join `Sku` on SKU | SKU/item/entity/category/vendor/brand plus ADS, position, ROP/max, DOS/state, price/value/risk, expiry/order/GMV/margin/funding/open PO | exact key / 1 |
| `sku.replenishment_current` | proposed replenishment; SKU | `ReplenishmentProposal` join `Sku` | SKU/item, reorder flag, sales/buy quantity/UOM, designated/best vendor prices, amount, saving | exact key / 1 |
| `store.lookup` | exact store details; store | `Store` | store/name/entity/cluster, size/health/footfall factors, channel | exact key / 1 |
| `store_sku.snapshot` | current store/SKU snapshot; SKU + store | `StoreSkuSnapshot` | inventory/ROP/DOS/state/value/risk, forecast/order/pack, promotion margin, contribution, labour | exact composite key / 1 |
| `vendor.lookup` | current vendor service/master values; vendor | `Vendor` | account/code/name/group/currency/terms, lead/MOQ, OTIF/fill/defect/adherence | exact key / 1 |
| `category.lookup` | exact category details; category | `Category` | category/entity/name/perishable | exact key / 1 |
| `brand.lookup` | exact brand details; brand | `Brand` | brand name | exact key / 1 |
| `legal_entity.lookup` | exact legal-entity details; legal entity | `LegalEntity` | ID/name/short name, workforce/sales/peak factors, store size | exact key / 1 |
| `promotion.lookup` | exact promotion configuration; promotion | `Promotion` | ID/name/type/scope/entity/category/season/month/mechanism, discount/value/minimum/funding/uplift/prebuy, validity, D365 construct | exact key / 1 |
| `workforce.current` | current store workforce; store | `WorkforceSnapshot` | store/event/lift, baseline/peak, scheduled/required/gap/surplus/coverage | exact key / 1 |
| `sales.monthly` | monthly history; legal entity | `MonthlySales` | period/entity/sales amount | source row then period descending / 24 |
| `trade_agreement.by_vendor` | exact structured trade terms; vendor | `TradeAgreement` | SKU/vendor/from/minimum, item/price/currency/lead/discount/to/designated | SKU, start descending, minimum / 20 |
| `inventory.at_risk` | highest structured at-risk values | `InventorySnapshot` join `Sku` | SKU/item/state/position/ROP/DOS/risk/inventory value | risk descending then SKU / 20 |
| `replenishment.top_candidates` | highest proposed replenishment quantities | `ReplenishmentProposal` join `Sku`; reorder required only | SKU/item/reorder, sales/buy quantity/UOM, amount | buy quantity descending then SKU / 20 |

Every row also retrieves source load/sheet/row and `loaded_at` solely for provenance. No capability returns raw SQL or uses `SELECT *`.

## 6. Entity Resolution Contract

Resolution supports SKU, store, vendor, legal entity, category, brand, and promotion. It prefers a canonical identifier found in text, then an exact typed hint, then a normalized case-insensitive exact source name present as a whole phrase in the query. Canonical patterns are constrained (for example `AAA-000`, `S000`, `V0000`, `AAA-C00`, and `PRM-0000`); legal entity/brand names use exact database matching. There is no fuzzy, phonetic, edit-distance, or “best candidate” selection.

Multiple exact matches return `AMBIGUOUS_ENTITY` with at most five identifiers/names. Source-name discovery is hard-capped at 1,000 rows per allowlisted entity table. Live data deliberately exercises duplicate category names such as `Accessories` and `Electronics`. A missing entity required by a capability returns `ENTITY_NOT_FOUND`. Either condition prevents SQL execution; a HYBRID vector branch may still return with explicit partial status, but cannot satisfy the missing exact-fact branch. A semantic-only request may continue when an optional structured identifier is absent.

## 7. Vector Retrieval Contract

Phase 6 calls the frozen Phase 5 `semantic_search` function directly; it does not copy or modify its vector SQL. After ranked parents return, Phase 6 performs one bounded parameterized `ai.RetailDocument` lookup for the already-persisted `source_sheet` needed by citations. Ranking, result behavior, chunk/document identity, profile matching, vector storage, and database schema remain unchanged.

| Intent | Inferred filter |
|---|---|
| SKU/product/perishable fruit | `business_entity` + `sku` |
| store/category/vendor durable meaning | `business_entity` + corresponding doc type |
| definition/terminology | `business_rule` + `terminology` |
| formula/calculation | `business_rule` + `formula` |
| model parameter | `business_rule` + `model_parameter` |
| D365/source mapping | `integration` only (several valid integration doc types) |
| approval | `governance` + `approval_rule` |
| agent responsibility | `agent_configuration` + `agent_spec` |
| promotion mechanism/policy | `operational_policy` + `promotion` |
| brand event | `operational_context` + `brand_event` |
| workbook documentation | `documentation` + `workbook_overview` |
| broad business-rule context in HYBRID | `business_rule` only |

Explicit valid filters intersect with inferred filters. A conflicting domain/type is `INVALID_FILTER`, never silently weakened. No filter is forced for genuinely broad semantic input with an explicit valid caller filter. The request cannot name a profile: Phase 5 loads the one ACTIVE profile and verifies it against the frozen local provider configuration. Exact search scans the small 1,361-vector corpus intentionally; Phase 5 candidate oversampling remains `min(max(top_k*10, 50), 1000)`. Lower cosine distance is better; similarity is labeled `1 - cosine_distance`; parent results retain best-chunk deduplication. The CPU model/provider is process-cached and guarded for concurrent sync FastAPI workers.

## 8. Hybrid Retrieval Contract

Hybrid retrieval resolves entities once, executes the selected bounded SQL capability/capabilities, plans semantic filters, and executes Phase 5 search. It returns independent `structured_results` and `semantic_results` plus their citations; it does not concatenate evidence into a conclusion. Branch timing and errors are separate. A failed SQL branch yields semantic evidence only with `PARTIAL` plus `HYBRID_SQL_BRANCH_FAILED`; a failed vector branch yields SQL evidence only with `PARTIAL` plus `HYBRID_VECTOR_BRANCH_FAILED`. When the shared Azure connection is unavailable neither branch is pretended successful. `fallback_allowed` is false in Phase 6.

## 9. Citation / Provenance Contract

SQL citations have deterministic IDs derived from capability, business keys, and lineage. They include `source_kind=sql`, schema `retail`, source table list, capability, business keys, contributing selected fields, source load ID, sheet, row, and `source_load_at`. They never include SQL text. Semantic citation IDs are derived from document key, chunk key, and ACTIVE profile key; citations include domain/type, source sheet/key, chunk index/key, distance, similarity, and bounded excerpt. One Phase 5 parent result retains one best-chunk citation.

`loaded_at` is explicitly labeled load lineage. The schema has no universal business snapshot/effective timestamp, so current/today/latest SQL requests receive `BUSINESS_AS_OF_UNAVAILABLE`; no workbook-relative period is presented as an as-of date.

## 10. Authorization Boundary

Inspection found no application authentication middleware, principal dependency, tenant model, or legal-entity authorization policy in the current FastAPI backend. Phase 6 therefore adds an `AuthorizationPolicy` interface and an `InternalPocAuthorizationPolicy` marker, but does not claim this is authentication or tenant isolation. The read-only `POST /api/retrieval/query` endpoint is internal/dev, excluded from OpenAPI, and disabled by default unless `RETAIL_RETRIEVAL_API_ENABLED=true`. Its principal is server-supplied and cannot be sent in the request. The CLI supplies its own internal POC principal. Enterprise identity, legal-entity entitlements, and tenant row scope remain Phase 7 prerequisites before broader exposure.

## 11. Observability Contract

One structured `retrieval_event` is logged per request with request UUID, 16-hex SHA-256 normalized-query fingerprint (never query text), route/reasons, entity-type outcome, capability keys, vector filters, counts, routing/resolution/SQL/query-embedding/vector-search/total latency, fallback flag, and first error category. An allowlist drops unknown log metadata. Tests prove query text and vector-like payloads are not logged. Connection strings, credentials, environment values, SQL text, full vectors, and complete questions are absent.

Limits are: 1,000 query characters; `top_k` 1–20; SQL capability maxima 1/20/24 with hard global maximum 50; vector candidate maximum 200 under Phase 6’s `top_k` ceiling; Azure connection timeout 30 seconds. `mssql-python` exposes the connection timeout used by the frozen helper but no portable per-command cancellation hook used by this code. The fixed indexed/equality or bounded ranking templates are small POC queries; a framework-level overall deadline is an open hardening item rather than a falsely claimed timeout.

## 12. Fallback / Error Contract

Stable codes include `EMPTY_QUERY`, `UNSUPPORTED_MUTATION`, `UNSUPPORTED_INTENT`, `UNSUPPORTED_STRUCTURED_INTENT`, `UNSUPPORTED_STRUCTURED_CAPABILITY`, `ENTITY_NOT_FOUND`, `AMBIGUOUS_ENTITY`, `INVALID_FILTER`, `INVALID_ROUTE_OVERRIDE`, `ACTIVE_EMBEDDING_PROFILE_UNAVAILABLE`, `EMBEDDING_PROVIDER_MISMATCH`, `SQL_UNAVAILABLE`, `VECTOR_UNAVAILABLE`, `HYBRID_SQL_BRANCH_FAILED`, `HYBRID_VECTOR_BRANCH_FAILED`, `BUSINESS_AS_OF_UNAVAILABLE`, and `RESULT_LIMIT_APPLIED`. Errors expose bounded generic messages rather than SQL/connection internals. Unsupported and single-branch failures are `FAILED`; hybrid evidence with one failed branch is `PARTIAL`; full evidence is `COMPLETE`. There is no silent route fallback and no evidence-type substitution.

## 13. Evaluation Suite

`backend/tests/fixtures/retrieval_routing_cases.json` contains 43 realistic cases: 12 SQL, 11 VECTOR, 8 HYBRID, 8 directly unsupported, and 4 resolution/filter negative cases. Each records route/reason and, where applicable, capability, entity type, domain/type, and error. The deterministic evaluator passes 43/43 (100%). Unit tests additionally cover request boundaries, all capability parameter construction, fixed SQL/injection separation, exact/missing/ambiguous resolution, profile non-selectability, provider reuse, provenance, parent dedup/ranking inherited from Phase 5, hybrid partial behavior, logging redaction, internal API gating, and frozen JSONL leakage.

Live retrieval quality: the six Phase 5 semantic cases passed 6/6 unfiltered and 6/6 filtered. The Phase 6 fruit planner inferred `business_entity/sku`; a matching perishable SKU ranked first (unfiltered Phase 5 rank was 6). SQL, VECTOR, and HYBRID live service cases all returned the expected evidence types. All 15 SQL capabilities returned bounded live rows, and `sku.inventory_current.inventory_position` reconciled with a separate parameterized query.

## 14. Progress Log

- **2026-08-12 09:43 UTC — Stage A inspection completed.** Read `plans/retail-data-vector-bootstrap.md` and `plans/phase-5-vector-embedding-changelog.md` completely. Inspected FastAPI entry points, CLI/config conventions, Azure SQL connection helpers, Phase 5 provider/search code, semantic mappings, tests, and logging/auth patterns. Commands used included segmented `sed`, `rg`, `git status --short`, `sha256sum`, `git check-ignore`, and read-only Python catalog queries.
- **2026-08-12 09:43 UTC — Live Azure inspection.** First connection attempt failed before query execution with the known TCP timeout. The retry succeeded. Confirmed 15 `retail.*` tables and 21,571 business rows (plus one `SourceLoad` audit row); unchanged four-table `ai.*` schema; ACTIVE frozen profile; 1,350 documents, 1,361 chunks, 1,361 embeddings. Bounded sample queries verified `GRC-001`, store `S001`, vendor IDs, legal entities, and duplicate normalized category names for ambiguity testing. No writes or migrations were performed.
- **2026-08-12 09:43 UTC — Safety checks.** Frozen JSONL checksums match Phase 5. `backend/.env` remains Git-ignored. Existing dirty Phase 5/user files were inventoried and preserved. No connection string or credential was printed.
- **2026-08-12 09:43 UTC — Phase 6 record created.** Added this file only; implementation has not yet altered the frozen database or semantic/vector contracts.
- **2026-08-12 09:46–09:56 UTC — Retrieval subsystem implemented.** Added `backend/src/retrieval/` models, router, exact entity resolver, 15-capability SQL catalog/executor, authorization hook, observability, service/hybrid orchestration, evaluation runner, and internal API. Added `retrieve` and `evaluate-retrieval-routing` CLI commands and registered the API router. No migration ran.
- **2026-08-12 09:49 UTC — Routing defect found and fixed.** An early smoke check routed the definition “What does Days of Supply mean?” to SQL because an inventory capability also recognized the phrase. Precedence now selects semantic meaning unless explicit current state is present; the same phrase with current-state explanation becomes HYBRID. Fixed ranking and agent-intent precedence similarly. The 43-case evaluation then passed 43/43.
- **2026-08-12 09:55 UTC — Tests added.** Added `backend/tests/test_retrieval.py` and the 43-case fixture. Updated the Phase 5 fake search row only for the new `source_sheet` output. Targeted result after capability parameterization: 52 passed, 3 opt-in skipped; later Phase 6-only non-live result: 39 passed, 2 deselected.
- **2026-08-12 09:57–10:00 UTC — Live service validation.** Ran the shared CLI for SQL inventory (`GRC-001`), intent-filtered fruit VECTOR, and replenishment-risk HYBRID. All returned `COMPLETE`; SQL had one structured citation, vector had five semantic citations with a perishable SKU rank 1, and hybrid had both branches with six independent citations. Values and full result payloads were not copied into this changelog.
- **2026-08-12 10:00 UTC — Provider lifecycle improvement.** Live timing showed first-query BGE startup. Added one process-cached provider/config with locks for thread-safe query encoding/search; no model/profile/vector state changed.
- **2026-08-12 10:01 UTC — Maintained backend suite.** `python -m pytest -q tests` passed 326 with 4 opt-in skips in 11.01 seconds. A repository-root discovery also collects pre-existing executable `backend/test_retail_tool.py`, which calls D365 at import and fails without `D365_RESOURCE`; this unrelated script is not in the maintained `tests/` suite and was not changed.
- **2026-08-12 10:01 UTC — Opt-in integrations.** With explicit flags, real local BGE plus Azure tests passed 4/4 (326 deselected) in 6.62 seconds. Expanded Phase 6 live tests then passed 2/2: SQL/VECTOR/HYBRID service retrieval and all 15 live SQL capabilities plus direct inventory cross-check.
- **2026-08-12 10:02 UTC — Performance baseline.** Ran `scripts/benchmark_retrieval.py --iterations 10 --top-k 5`. Cold vector total/query embedding were 3,929.7/3,332.1 ms. Warm total median/p95/min/max: SQL 280.3/280.6/280.0/282.0 ms; VECTOR 306.2/306.9/305.2/312.3 ms; HYBRID 457.0/462.1/455.3/480.7 ms. Warm VECTOR query embedding median 23.1 ms and vector search 178.5 ms; HYBRID query embedding 24.9 ms and vector search 151.1 ms. This is a small POC baseline, not an SLA.
- **2026-08-12 10:03 UTC — Retrieval quality rerun.** `evaluate-search --top-k 10` passed all six cases unfiltered and filtered. Formula, terminology, D365 mapping, approval, agent, and fruit expectations were present; inferred SKU filtering moved a matching fruit SKU to rank 1.
- **2026-08-12 10:05 UTC — Final acceptance gate.** Added a 1,000-row cap to exact source-name resolution, reran the maintained suite (327 passed, 5 skipped) and compilation, then ran the consolidated opt-in set (5 passed, 327 deselected). Final read-only Azure check confirmed 15/21,571 structured tables/rows, unchanged four-table AI schema, 1,350/1,361/1,361 document/chunk/embedding counts, and the frozen ACTIVE profile. `git diff --check`, targeted secret/vector scan, JSONL checksums, and `.env` ignore check passed. No migration or database write occurred.
- **2026-08-12 10:07 UTC — Phase 5 freeze audit.** Replaced an interim additive `source_sheet` search-output change with a Phase 6-owned bounded provenance lookup against `ai.RetailDocument`. Phase 5 search code/tests returned to their approved behavior; Phase 6 remains the only owner of the new citation contract.
- **2026-08-12 10:08 UTC — Post-audit verification.** Phase 6 live SQL/VECTOR/HYBRID plus all-capability tests passed 2/2 after the provenance move. The maintained backend suite again passed 327 with 5 opt-in skips in 11.00 seconds; compilation and diff whitespace checks passed.

## 15. Validation Results

- Contracts: strict request/decision/response models implemented; no answer field, profile selector, or SQL identifiers.
- Routing: 43/43 evaluation cases pass; no generative model imported or called by `src.retrieval`.
- SQL: all 15 templates are explicit, positional-parameterized, read-only, and bounded; live results/citations passed and inventory cross-check reconciled.
- Vector: ACTIVE profile only; frozen BGE query prefix/config; lower cosine distance correctly labeled; parent dedup remains; six quality cases passed filtered and unfiltered; fruit SKU rank 1 with inferred filter.
- Hybrid: live complete response contained both independent evidence branches; unit tests prove visible partial failures and no substitution.
- Tests: final maintained suite 327 passed / 5 opt-in skipped; final consolidated opt-in real-model/Azure set 5 passed; the Phase 6 live capability/service subset passed 2/2.
- Performance: warm medians SQL 280.3 ms, VECTOR 306.2 ms, HYBRID 457.0 ms; cold BGE total 3.93 seconds. No retries occurred in this benchmark. The initial Stage A catalog attempt did experience one visible TCP connection timeout before a successful retry.
- Frozen state: final live invariant check is 15 `retail.*` tables / 21,571 business rows and four `ai.*` tables / 1,350 documents / 1,361 chunks / 1,361 embeddings. ACTIVE profile remains `local-bge-small-en-v1.5-384-v1` with the frozen provider/model/revision/dimensions/normalization/status.
- Security/diff: `git diff --check` passed; targeted credential/connection/vector scan returned no matches; `.env` remains ignored; full/sample frozen JSONL checksums remain `f2a04b...a567` and `194368...2f0`; compilation passed. No SQL migration or write command ran in Phase 6.

## 16. Open Questions / Blockers

- Azure SQL connectivity can intermittently time out; retries and their latency must remain visible in the POC benchmark.
- The database provides load lineage but not a universal business-effective timestamp. Freshness claims must emit `BUSINESS_AS_OF_UNAVAILABLE`.
- There is no existing real backend authorization layer. The retrieval API must be described as internal/dev only until enterprise identity and row scoping are implemented.
- The driver path does not provide a Phase 6 portable per-command/overall cancellation mechanism; current safeguards are fixed queries, bounded results, and the existing 30-second connection timeout.
- Cold process startup loads local BGE in about 3.3 seconds on this VM; production process warm-up is recommended before traffic.
- HYBRID semantic relevance is evidence-oriented rather than an answer: for the live replenishment-risk query, relevant ROP/perishable/state formula evidence appeared within top 5, while GMROI ranked first. Future answer-generation evaluation should assess context selection, but Phase 6 must not rerank with an LLM.
- Repository-root pytest discovery has a pre-existing D365 import-time script issue as noted in the progress log; `backend/tests` is green.

## 17. Final Phase 6 Recommendation

Recommend freezing Phase 6 after the final invariant/security check below. The deterministic evidence boundary, allowlisted SQL catalog, intent-filtered Phase 5 reuse, hybrid partial semantics, provenance, internal API gate, and tests meet the POC objective without changing business or vector data.

Recommended Phase 7 scope: integrate `retrieve_context()` into the Retail chat agent behind real authenticated principal/legal-entity authorization; build a bounded evidence-to-prompt adapter; generate grounded natural-language answers with mandatory citation validation and evidence-type rules; add answer faithfulness/refusal evaluation, prompt-injection defenses, and streaming/API tests. Keep business writes/actions, frontend redesign, embedding migration, and arbitrary text-to-SQL out of that phase unless separately approved. Do not start Phase 7 until human review.
