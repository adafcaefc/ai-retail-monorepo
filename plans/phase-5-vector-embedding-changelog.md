# Phase 5 — Local Embedding Pipeline + Azure SQL Vector Storage

## 1. Objective

Persist the approved Phase 4.5 semantic corpus as canonical documents, deterministic embedding chunks, and profile-scoped native Azure SQL vectors. The Phase 5 layer must be reconstructible, incremental, provider-portable, searchable without frontend/agent integration, and must leave the validated `retail.*` relational foundation unchanged.

## 2. Input Contract

The input is the frozen `generated/retail_documents.jsonl` corpus: 1,350 JSON objects with 1,350 deterministic unique `doc_key` values. Every object has exactly these eight required fields and no embedding/vector field:

1. `doc_key`
2. `doc_type`
3. `retrieval_domain`
4. `source_sheet`
5. `source_key`
6. `content`
7. `metadata`
8. `content_hash`

`content_hash` is lowercase SHA-256 of canonical semantic `content` only. Metadata, routing fields, operational SQL state, timestamps, database identifiers, and embedding configuration do not participate in content identity. Phase 5 consumes this contract and does not redesign it.

Baseline frozen artifact checksums:

- Full corpus: `f2a04b34a725f1e06a6c547fb7ab4ae1dd294a1365ca0a76c3cf2191008aa567`
- Representative sample: `194368f80b942933f072b2151500951e03e82d156f27d303d9b695fbb55b22f0`

## 3. Embedding Contract

| Property | Value |
|---|---|
| Provider key | `local_sentence_transformers` |
| Model | `BAAI/bge-small-en-v1.5` |
| Model revision | `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` (resolved from the existing local Hugging Face cache; profile-pinned) |
| Dimensions | 384 |
| Normalization | L2 normalized (`true`) for documents and queries |
| Device | CPU |
| Model maximum sequence length | 512 tokens including tokenizer special tokens |
| Document encoding | Encode canonical chunk semantic text directly; no instruction prefix |
| Query encoding | Prefix short queries, then encode and normalize |
| Query prefix | `Represent this sentence for searching relevant passages: ` |
| Chunk target | 384 tokens including special-token accounting |
| Chunk overlap | 48 content tokens where a split is required |

The provider must count tokens without truncation, reject any over-limit chunk before model inference, validate every output width as exactly 384, and validate finite normalized vectors. Sentence Transformers calls remain behind a provider interface so storage/search orchestration is model-independent.

## 4. Azure SQL AI Schema

Versioned migration: `sql/ai/001_create_ai_vector_schema.sql`. Pre-migration live inspection found no `ai` schema and zero `ai` objects.

Implemented objects:

### `ai.EmbeddingProfile`

- PK: `embedding_profile_id BIGINT IDENTITY`.
- Human identity: unique `profile_key NVARCHAR(128)`.
- Configuration: `provider`, `model_name`, nullable `model_revision`, `dimensions`, `normalization`, `max_sequence_length`, `document_instruction`, `query_instruction`, `chunk_target_tokens`, `chunk_overlap_tokens`, valid `configuration_json`.
- Lifecycle: `status` constrained to `BUILDING`, `ACTIVE`, or `RETIRED`; `created_at`, `activated_at`, `retired_at`.
- Storage checks: dimensions must equal 384, normalization must be true, target/overlap/maximum ordering must be valid, and configuration must be JSON.
- Indexes: unique profile key; filtered unique `UX_ai_EmbeddingProfile_single_active` permits at most one `ACTIVE` row; provider/model/status lookup index.

### `ai.RetailDocument`

- PK: `document_id BIGINT IDENTITY`; unique `doc_key`.
- Frozen contract values: `doc_type`, first-class filterable `retrieval_domain`, `source_sheet`, `source_key`, `content`, valid-object `metadata_json`, 64-character lowercase SHA-256 `content_hash`.
- Lifecycle: `is_active`, `created_at`, `updated_at`.
- No embedding/vector column.
- Indexes: type/active, domain/active, and composite active/domain/type with identity/hash includes.

### `ai.RetailChunk`

- PK: `chunk_id BIGINT IDENTITY`.
- Relationship: `document_id` FK to `RetailDocument` with delete cascade because chunks are reconstructible children.
- Identity: unique `(document_id, chunk_index)` and globally unique deterministic `chunk_key`.
- Content: canonical `content`, lowercase SHA-256 `chunk_hash`, persisted `token_count`, timestamps.
- Checks: non-negative index, 1–512 tokens, valid 64-character lowercase hash.
- Index: document/index join lookup including hash/token count.

### `ai.RetailEmbedding`

- Composite PK: `(embedding_profile_id, chunk_id)`, ordered profile-first for exact profile-scoped scanning.
- Relationships: profile FK to `EmbeddingProfile`; chunk FK to `RetailChunk` with delete cascade.
- Values: native `embedding VECTOR(384)`, exact `embedded_chunk_hash`, `embedded_at`.
- Index: chunk/profile reverse lookup including embedded hash/time.
- Currentness is never inferred from row existence; the persisted embedded hash must equal the current chunk hash.

All three live FKs are enabled/trusted. Live catalog inspection confirmed every PK/unique/index above, including the single-active filtered index.

Azure SQL version `12.0.2000.8` (General Purpose `GP_S_Gen5_2`) successfully evaluated stable `VECTOR_DISTANCE('cosine', ...)`. The catalog currently exposes ordinary clustered/nonclustered indexes and no vector index type. For roughly 1,350–1,400 chunks, Phase 5 therefore uses exact filtered cosine-distance evaluation and does not create or depend on a preview vector index.

## 5. Chunking Strategy

Chunking is an embedding concern and never changes the frozen document. A document whose untruncated token count is at most 512 becomes exactly one chunk containing the full canonical content. Only an oversized document is split.

For oversized text, the implementation deterministically prefers line/paragraph/logical-row boundaries, then sentence boundaries. It greedily packs logical units toward 384 tokens, carries up to 48 content tokens of overlap, and only token-splits a single indivisible unit that cannot safely fit. Overlap is reduced only when needed to keep the next logical unit safe. Token decode/encode safety is verified after construction; no chunk may exceed 512 tokens including special tokens. Chunk keys are `<doc_key>#NNN`; chunk hashes are lowercase SHA-256 of canonical chunk semantic text only.

Realized full-corpus result: 1,361 chunks. Exactly 1,344 documents remain single-chunk and exactly the six known oversized documents become multi-chunk. The largest final chunk is 429 tokens (`d365-field-mapping:time-series-24mo-monthly-sales-per-vertical#000`); it is an intact 429-token document, preserved as one chunk because it fits the 512-token model limit. The largest chunk produced from an oversized document is 384 tokens.

| Oversized document | Source tokens | Final chunks | Chunk token counts |
|---|---:|---:|---|
| `d365-worked-example:grc-092-replenishment` | 1,292 | 4 | 373, 346, 375, 351 |
| `d365-field-mapping:sku-master-item-master-one-row-per-released-product` | 1,065 | 4 | 376, 373, 352, 114 |
| `d365-field-mapping:engine-store-per-sku-per-store-grid-store-dimension-inventdim-inventlocationid` | 886 | 3 | 377, 370, 241 |
| `d365-field-mapping:engine-decision-grid-chain-net-one-row-per-sku` | 691 | 2 | 366, 375 |
| `d365-field-mapping:promotion-discount-detail-retailperiodicdiscount-subtables` | 649 | 2 | 362, 337 |
| `d365-field-mapping:replenishment-detail-line-level-purchase-requisition` | 553 | 2 | 384, 222 |

## 6. Incremental Embedding Rules

An embedding is current only when both conditions hold:

```text
RetailEmbedding.embedded_chunk_hash == RetailChunk.chunk_hash
AND RetailEmbedding.embedding_profile_id == requested_profile_id
```

- New chunk: generate an embedding.
- Changed chunk hash under the same profile: replace that profile's vector and recorded hash.
- Unchanged chunk/hash under the same profile: reuse; do no model work.
- New profile: embed every active chunk under the new profile.
- Metadata-only document change with unchanged chunk text/hash: update the document only; reuse embeddings.
- Changes only under `retail.*`: no embedding work.
- Changed document chunk sets: reconcile transactionally; stale chunks/embeddings for that document are removed because `ai.*` is derived.
- Missing source document: mark the parent inactive and exclude it from search; do not destructively delete it without an explicit future prune operation.

Dry-run computes and reports all document/chunk/embedding actions without opening a write transaction.

The implemented sync transaction upserts documents by `doc_key`, upserts chunks by deterministic `chunk_key`, removes stale chunk members only for incoming changed documents (cascading their derived embeddings), and marks missing source documents inactive. It does not delete documents missing from the source and never reads or writes `retail.*`.

## 7. Search Contract

Search will load the single `ACTIVE` profile, verify it matches the configured provider, embed the query with the profile's query instruction, and search only embeddings belonging to that profile and active parent documents. Optional exact filters are `retrieval_domain` and `doc_type`.

Azure SQL calculates `VECTOR_DISTANCE('cosine', stored_vector, query_vector)`. Lower cosine distance is better. Candidate chunks are ordered ascending by cosine distance, joined to parent documents, and deduplicated by parent in application/service logic using the best matching chunk as the parent score. The service may also return `cosine_similarity = 1 - cosine_distance`, with both fields labelled explicitly. The returned contract includes rank, document identity/type/domain/source key, matched chunk index, and an excerpt. Candidate oversampling prevents duplicate chunks from one parent from starving the requested parent-level `top_k`.

## 8. Provider Portability

Content identity (`content_hash` / `chunk_hash`) and embedding identity (`embedding_profile`) are separate. A vector effectively belongs to `(chunk_hash, embedding_profile)`, not to a document or dimension alone.

Future provider migration:

1. Create the replacement profile as `BUILDING` while the current profile remains `ACTIVE`.
2. Generate replacement embeddings for every active chunk without deleting current vectors.
3. Validate completeness, dimensions, hashes, normalization, and retrieval quality.
4. Atomically switch the single active profile.
5. Retain the old profile temporarily for rollback, then mark it `RETIRED`.

Search never mixes profiles, even when dimensions match. Equal dimensionality does not mean compatible vector spaces.

## 9. Progress Log

### 2026-08-12 08:28:49 UTC — Stage A audit started

- Work completed: read all 619 lines of `plans/retail-data-vector-bootstrap.md`; confirmed the Phase 4.5 freeze, eight-field contract, deterministic content-only hash rule, 1,350-document/18-type/8-domain counts, and validated 21,571-row `retail.*` baseline.
- Files changed: created this persistent Phase 5 plan/changelog.
- Commands run: Git working-tree inspection; repository inventory; segmented full plan read; semantic model/builder/validator/CLI/database/test/migration inspection; local embedding script and benchmark inspection; generated corpus line-count/checksum checks; dependency and local Hugging Face cache inspection; Git ignore verification.
- Results: full/sample checksums match the Phase 4.5 record; `backend/.env` and `generated/` are Git-ignored; installed stack is CPU-only PyTorch (`2.13.0+cpu`), Sentence Transformers `5.7.0`, Transformers `5.15.0`; cached BGE revision is `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`.
- Existing user changes preserved: `scripts/test_local_embedding.py` is modified and `scripts/benchmark_local_embedding.py` is untracked; neither has been overwritten.
- Database migrations performed: none.
- Rows/embeddings: none written/generated by Phase 5 yet.
- Blockers: live Azure SQL `ai.*` catalog and stable vector-distance capability inspection pending.

### 2026-08-12 08:36 UTC — Live Azure SQL preflight completed

- Work completed: inspected the configured database without exposing its connection string; confirmed absence of conflicting `ai.*` objects; tested native cosine vector distance; reconfirmed the `retail.*` table count.
- Files changed: updated Sections 4, 7, 9, and 11 of this changelog.
- Commands run: existing read-only `inspect-database` CLI and a bounded read-only catalog/vector-function query. The first two connection attempts timed out; a retry succeeded.
- Results: `ai` schema absent, `ai` object count 0, `retail` table count 15, native cosine-distance test returned `1.0` for orthogonal vectors, and available index types were `CLUSTERED`, `HEAP`, and `NONCLUSTERED`.
- Database migrations performed: none.
- Rows/embeddings: none written/generated.
- Decision: use stable exact `VECTOR_DISTANCE` over this small POC corpus; do not use preview vector indexing.
- Blockers: none for implementation.

### 2026-08-12 08:47 UTC — Provider, chunker, storage service, migration, and CLI implemented

- Work completed: implemented a lazy provider abstraction and pinned CPU-only local BGE provider; deterministic logical/token chunker; additive four-table Azure SQL migration; embedding-profile registration/lifecycle rules; document/chunk sync planning and transaction; incremental batched embedding; validation; exact cosine search with domain/type filters and parent deduplication; CLI commands; non-secret environment examples.
- Files changed: `backend/src/retail_data_bootstrap/embedding_config.py`, `embedding_provider.py`, `chunking.py`, `vector_store.py`, `cli.py`, `paths.py`, `sql/ai/001_create_ai_vector_schema.sql`, `backend/.env.example`, `backend/requirements.txt`, `backend/pytest.ini`, `backend/tests/test_vector_embedding.py`, and this changelog.
- Commands run: package compilation, CLI help smoke test, diff whitespace check, real cached-tokenizer full-corpus chunk analysis, and focused unit tests.
- Results: the provider now uses the pinned local Hugging Face snapshot in `local_files_only` mode (no HF token/network required); no model is copied into the repository. Full corpus deterministically produces 1,361 safe chunks: 1,344 single-chunk documents and six multi-chunk documents. Maximum final chunk is 429 tokens; zero exceed 512.
- Tests: focused Phase 5 plus bootstrap suites passed **36**, with **3** opt-in integration tests skipped.
- Database migrations performed: none yet.
- Rows/embeddings: none written/generated in Azure SQL yet.
- Blockers: none. Sample-first live workflow is next.

### 2026-08-12 08:59:44 UTC — Migration and sample-first workflow passed

- Work completed: applied the additive migration; verified both schemas; registered the pinned profile as `BUILDING`; ran sample dry-run, live sync, local embedding, persisted-vector validation, and semantic search without activating the partial profile.
- Files changed: added explicit `--allow-building` search mode for sample validation only; normal search still requires `ACTIVE`. Updated CLI, service, tests, and this changelog.
- Commands run: `migrate-vector`, `inspect-vector-database`, `inspect-database`, `register-embedding-profile`, sample `sync-vector-documents --dry-run`, sample live sync, `embed-vectors`, sample `validate-vector-layer`, and sample semantic search.
- Database migrations performed: `sql/ai/001_create_ai_vector_schema.sql`, 5 batches. The first connection attempt timed out before SQL execution; the rerunnable retry succeeded.
- Schema results: 4 new tables (`ai.EmbeddingProfile`, `ai.RetailDocument`, `ai.RetailChunk`, `ai.RetailEmbedding`); `retail.*` remains exactly 15 tables.
- Sample rows: 1 profile, 10 active documents, 10 chunks, 10 embeddings.
- Sample dry run: 10 document inserts, 10 chunk inserts, 10 expected new embeddings, zero writes.
- Sample sync: 10 documents inserted, 10 chunks inserted, database time 0.8290 s.
- Sample embedding: 10 generated, 0 updated, 0 reused, 0 failures; inference 4.2758 s, database 0.6789 s, combined 4.9547 s.
- Sample validation: valid; 10/10 documents, chunks, and vectors reconcile; zero content/chunk hash mismatches, missing/stale embeddings, wrong dimensions, non-normalized vectors, over-limit chunks, or other-profile embeddings. Profile remained `BUILDING`.
- Sample search: unfiltered fruit query ranked `sku:grc-001` first with cosine distance `0.35497159` (similarity `0.64502841`).
- Blockers: none. Full-corpus sync/embedding is now authorized by the passed sample gate.

### 2026-08-12 09:05 UTC — Full corpus embedded, validated, and activated

- Work completed: ran full dry-run and live sync; generated only missing vectors in CPU batches of 32; performed complete pre-activation validation; atomically activated the profile only after validation passed.
- Commands run: full `sync-vector-documents --dry-run`, full live sync, `embed-vectors --batch-size 32`, `validate-vector-layer`, and `activate-vector-profile`.
- Full dry run: 1,340 document inserts plus 10 no-ops; 1,351 chunk inserts plus 10 no-ops; 1,351 new embeddings required and 10 sample embeddings reusable.
- Full sync: 1,350 active documents and 1,361 chunks persisted; database time 87.6383 s.
- Full completion embedding pass: 1,351 generated, 10 reused, 0 updated, 0 failures; inference 64.2168 s, vector database time 98.2358 s, combined 162.4526 s.
- Cumulative fresh-corpus embedding work including the sample: 1,361 generated; inference 68.4926 s, vector database time 98.9147 s, combined 167.4073 s.
- Validation: 1,350/1,350 active documents, 1,361/1,361 chunks, and 1,361/1,361 embeddings reconciled; zero missing/extra rows, content/chunk hash mismatches, stale embedded hashes, wrong dimensions, non-normalized vectors, over-limit chunks, or other-profile embeddings.
- Lifecycle: profile changed from `BUILDING` to `ACTIVE` at `2026-08-12 09:05:05.516 UTC`, after complete validation only.
- Blockers: none.

### 2026-08-12 09:06 UTC — Mandatory idempotence passed

- Work completed: reran full document/chunk synchronization and embedding ingestion against the unchanged frozen corpus.
- Sync result: document inserts 0, updates 0, no-ops 1,350, inactivations 0; chunk inserts 0, updates 0, no-ops 1,361, removals 0; database write time 0.0652 s.
- Embedding result: required 0, generated 0, updated 0, reused 1,361, completed 0, failures 0; inference/database/combined embedding time all 0.0 s. The lazy provider never loaded the model.
- Acceptance result: unchanged data produces zero embedding model work.

### 2026-08-12 09:14:06 UTC — Retrieval, tests, and final live checks completed

- Work completed: added and ran the six-case deterministic/manual evaluation in both unfiltered and domain/type-filtered modes; ran a live multi-chunk deduplication search; ran focused/full/local-model/live-Azure tests; reran the migration; revalidated the ACTIVE profile and relational invariant.
- Files changed: added `retrieval_evaluation.py`, `evaluate-search` CLI, evaluation/top-k documentation, final tests, and this changelog.
- Search results: all 6/6 unfiltered and 6/6 filtered cases passed at top-10. See Section 10 for ranks and filter behavior.
- Multi-chunk result: query for the four-chunk GRC-092 worked example returned its parent once, ranked first, using chunk `#000`; no parent duplication occurred.
- Tests: maintained backend `tests/` suite 288 passed/3 opt-in skipped; focused Phase 5/bootstrap 37 passed/3 skipped; real local-model integration 1 passed; explicit live Azure integrations 2 passed.
- Migration idempotence: the populated migration rerun completed safely in 5 no-op-safe batches and left 4 tables.
- Profile-registration idempotence: rerun returned `created: false` and preserved the existing `ACTIVE` profile and activation timestamp.
- Live rows: 1 profile (`ACTIVE`), 1,350 documents (all active), 1,361 chunks, 1,361 embeddings. No disabled/untrusted `ai` FK. `retail.*` remains 15 tables and exactly 21,571 business rows.
- Security/disk checks: frozen JSONL checksums unchanged; `backend/.env` remains ignored/untracked; CPU-only PyTorch `2.13.0+cpu`, CUDA unavailable, and no NVIDIA/CUDA/Triton packages found; no model cache was added to Git.
- Blockers: none.

## 10. Validation Results

### Frozen input

- Full JSONL: 1,350 lines; SHA-256 `f2a04b34a725f1e06a6c547fb7ab4ae1dd294a1365ca0a76c3cf2191008aa567` (unchanged).
- Sample JSONL: 10 lines; SHA-256 `194368f80b942933f072b2151500951e03e82d156f27d303d9b695fbb55b22f0` (unchanged).
- Eight required fields remain exact; no vector/embedding data leaked into JSONL.

### Azure SQL and profile

| Validation | Result |
|---|---:|
| Active semantic documents | 1,350 / 1,350 |
| Chunks | 1,361 / 1,361 |
| Single-chunk documents | 1,344 |
| Multi-chunk documents | 6 |
| Maximum final chunk tokens | 429 |
| Chunks over 512 | 0 |
| Current profile embeddings | 1,361 / 1,361 |
| Missing embeddings | 0 |
| Stale embedded-hash mismatches | 0 |
| Wrong-dimension vectors | 0 |
| Non-normalized vectors | 0 |
| Other-profile embeddings | 0 |
| Content/chunk hash mismatches | 0 |
| Disabled/untrusted `ai` FKs | 0 |

Profile: `local-bge-small-en-v1.5-384-v1`; `local_sentence_transformers`; `BAAI/bge-small-en-v1.5`; revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`; 384 dimensions; normalized; CPU; 512 maximum; 384/48 chunk configuration; status `ACTIVE`.

### Retrieval quality

The fixed manual evaluation uses top-10 because the unfiltered fruit query correctly ranks the durable Fruit category and Perishable terminology ahead of individual near-duplicate SKU records; the first matching perishable-fruit SKU is rank 6. No hard-coded score threshold is used.

| Case | Expected | Unfiltered | Filtered |
|---|---|---|---|
| Perishable fruit | `business_entity` / `sku` | matching SKUs at ranks 6, 7, 9, 10 | matching SKU rank 1 |
| Days of supply | `terminology:dos` | rank 1 | rank 1 |
| ADS per store | `formula:ads-per-store` | rank 2 (terminology rank 1) | rank 1 |
| D365 demand forecast source | A1 D365 field mapping | rank 1 | rank 1 |
| High-value purchasing approval | `approval-rule:purchase-order` | rank 1 | rank 1 |
| Replenishment agent | `agent-spec:a3-replenishment` | rank 1 | rank 1 |

All 6 unfiltered and all 6 filtered cases passed. Domain and doc-type SQL predicates are exact, the active profile predicate is mandatory, cosine distance is ordered ascending, and parent deduplication uses the best chunk.

### Idempotence and tests

- Second unchanged sync: 0 document changes, 0 chunk changes, 1,350/1,361 no-ops.
- Second unchanged embedding pass: 0 required/generated/updated, 1,361 reused, 0.0 s inference.
- Maintained backend suite: 288 passed, 3 skipped (opt-in markers).
- Real local BGE integration: 1 passed.
- Explicit Azure SQL integrations: 2 passed.
- Compilation and `git diff --check`: passed.

## 11. Open Questions / Blockers

- No Phase 5 implementation blocker remains.
- Exact vector scan is intentionally selected for this small POC. Reassess a stable, generally available Azure SQL vector index only when corpus/latency evidence warrants it; do not adopt a preview feature by default.
- The unfiltered fruit query ranks category/terminology documents above individual SKU documents. This is semantically reasonable and the `doc_type=sku` filter ranks a matching SKU first, but Phase 6 routing should use intent-aware filters when the caller explicitly asks for a product record.
- The current synchronizer can update an ACTIVE profile's documents before its replacement embeddings finish, during which stale rows are excluded from search by hash. For this POC that is safe and explicit; a higher-volume production pipeline should add a corpus-version/build promotion boundary if zero-gap updates are required.

## 12. Final Phase 5 Recommendation

Recommend freezing Phase 5 for this POC. The frozen input is unchanged; the additive native-vector schema, deterministic chunking, profile identity/lifecycle, sample-first/full ingestion, incremental reuse, exact filtered search, parent deduplication, idempotence, retrieval evaluation, and live/local automated tests all pass. The `ACTIVE` profile was promoted only after complete validation.

Recommended Phase 6 scope, after human approval only:

1. Define the backend retrieval service/API contract that wraps this Phase 5 search service without changing storage identities.
2. Implement explicit SQL-vs-vector-vs-hybrid routing using the frozen rule that current operational values come from `retail.*` and durable semantic context comes from `ai.*`.
3. Add authorization, observability, latency/error budgets, and source citations to retrieved chunks/documents.
4. Integrate retrieval into the Retail agent backend first, with evaluation and fallback behavior, before any frontend changes.
5. Keep answer generation, UI integration, and any new embedding provider as separately reviewed workstreams; a provider change must follow the BUILDING/validate/atomic-ACTIVE/rollback workflow in Section 8.

Do not begin Phase 6 automatically.
