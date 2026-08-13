# AI Retail 360 — Current Architecture & Engineering Handoff

**Status date:** 2026-08-13  
**Current project state:** Phases 1–6 complete and frozen for the POC  
**Primary purpose of this file:** Give a new engineer or AI code editor one canonical architecture reference before modifying the repository.

---

## 1. Executive Summary

AI Retail 360 currently has a complete **data + semantic retrieval backend**.

The system has two complementary data layers inside the same Azure SQL Database:

1. **`retail.*`** — authoritative structured business facts for exact/current operational retrieval.
2. **`ai.*`** — semantic documents, deterministic chunks, and native Azure SQL vectors for meaning/context retrieval.

A deterministic Phase 6 router decides whether a question requires:

- `SQL`
- `VECTOR`
- `HYBRID`
- `UNSUPPORTED`

There is **no LLM used for routing** and **no arbitrary text-to-SQL**.

Local embeddings are generated on the Ubuntu VM with:

- Provider: `local_sentence_transformers`
- Model: `BAAI/bge-small-en-v1.5`
- Device: CPU
- Dimension: `384`
- Normalization: L2 normalized
- Active embedding profile: `local-bge-small-en-v1.5-384-v1`

The next intended work is **not another retrieval system**. The existing chatbot/agent framework should consume the Phase 6 `retrieve_context()` service and use the returned evidence when producing agent answers.

---

# 2. Current End-to-End Architecture

```mermaid
flowchart TD
    U[User / Existing Retail Chatbot] --> A[Existing Agent System]
    A --> R[Phase 6 retrieve_context]

    R --> D{Deterministic Router}

    D -->|SQL| S[Allowlisted SQL Capability]
    D -->|VECTOR| V[Semantic Search]
    D -->|HYBRID| H[SQL + Semantic Search]
    D -->|UNSUPPORTED| X[Structured Error / Refusal Metadata]

    S --> DB[(Azure SQL)]
    H --> DB

    V --> BGE[Local BGE Query Embedding\nBAAI/bge-small-en-v1.5\n384-dim CPU]
    H --> BGE

    BGE --> DB

    DB --> RETAIL[retail.*\nExact / current facts]
    DB --> AI[ai.*\nSemantic docs + VECTOR(384)]

    RETAIL --> RESP[RetrievalResponse]
    AI --> RESP

    RESP --> A
    A --> LLM[Existing Agent LLM / Chatbot Process]
    LLM --> U
```

The important architectural boundary is:

> **Phase 6 retrieves trusted evidence. The existing agent/LLM system turns that evidence into the conversational answer.**

Phase 6 itself deliberately does **not** generate natural-language business answers.

---

# 3. Runtime Request Flow

## 3.1 Exact/current operational question

Example:

> What is the current inventory position for GRC-001?

Flow:

```text
User question
    ↓
retrieve_context()
    ↓
Router → SQL
    ↓
Entity resolver → SKU GRC-001
    ↓
Allowlisted capability → sku.inventory_current
    ↓
mssql-python
    ↓
Azure SQL retail.InventorySnapshot + retail.Sku
    ↓
Structured facts + SQL provenance
    ↓
RetrievalResponse
```

No LLM-generated SQL is involved.

---

## 3.2 Semantic/business-meaning question

Example:

> What does Days of Supply mean?

Flow:

```text
User question
    ↓
retrieve_context()
    ↓
Router → VECTOR
    ↓
Intent planner
    ↓
retrieval_domain = business_rule
doc_type = terminology
    ↓
Local BGE query embedding
    ↓
384-dimensional normalized vector
    ↓
Azure SQL VECTOR_DISTANCE('cosine', ...)
    ↓
ai.RetailEmbedding
    ↓
ai.RetailChunk
    ↓
ai.RetailDocument
    ↓
Semantic evidence + citations
    ↓
RetrievalResponse
```

---

## 3.3 Hybrid question

Example:

> Why is GRC-001 at replenishment risk?

Flow:

```text
User question
    ↓
retrieve_context()
    ↓
Router → HYBRID
    ↓
┌───────────────────────────────┐
│ SQL branch                    │
│ current/exact operational data│
│                               │
│ inventory position            │
│ ROP                           │
│ DOS                           │
│ replenishment proposal        │
└───────────────────────────────┘

PLUS

┌───────────────────────────────┐
│ VECTOR branch                 │
│ durable semantic context      │
│                               │
│ definitions                   │
│ formulas                      │
│ business rules                │
│ policy/context                │
└───────────────────────────────┘
    ↓
Independent evidence + citations
    ↓
RetrievalResponse
```

The router does **not** combine those branches into an invented conclusion. That is the agent/LLM layer's responsibility.

If one hybrid branch fails, the response becomes `PARTIAL` and identifies the failed branch explicitly.

---

# 4. Database Connectivity

The Python backend accesses Azure SQL **directly**, not through HTTP.

```text
Python backend
    ↓
mssql-python
    ↓
TDS / TCP 1433
    ↓
Azure SQL Database
```

Current database:

- Database: `free-sql-db-0067773`
- SQL server: `kijangsatuvec.database.windows.net`
- Azure resource group: `William_RG`
- Region: East Asia
- Service objective: `GP_S_Gen5_2`
- Authentication for the POC: SQL authentication

**Never commit or print the SQL password or full connection string.**

The working secret is stored only in:

```text
backend/.env
```

and `backend/.env` is Git-ignored.

The application uses:

```text
AZURE_SQL_CONNECTIONSTRING
```

Do not replace the working SQL driver stack unless there is a proven need.

---

# 5. Structured Data Layer — `retail.*`

`retail.*` is the authority for exact/current business values.

Current validated business-row count:

```text
21,571 rows
```

Current structured objects:

| Table | Rows |
|---|---:|
| `retail.SourceLoad` | 1 |
| `retail.LegalEntity` | 8 |
| `retail.Store` | 160 |
| `retail.Category` | 160 |
| `retail.Vendor` | 8 |
| `retail.Brand` | 12 |
| `retail.Sku` | 800 |
| `retail.TradeAgreement` | 2,400 |
| `retail.Promotion` | 48 |
| `retail.InventorySnapshot` | 800 |
| `retail.StoreSkuSnapshot` | 16,000 |
| `retail.ReplenishmentProposal` | 800 |
| `retail.BrandEvent` | 23 |
| `retail.WorkforceSnapshot` | 160 |
| `retail.MonthlySales` | 192 |

`retail.*` is already validated and should be treated as frozen unless a future source-ingestion phase explicitly changes it.

## 5.1 Structured-vs-semantic rule

The key boundary is:

### Put in SQL

- current inventory position
- reorder point
- days of supply
- current inventory state
- current order quantity
- replenishment proposal
- prices/values when exact/current values matter
- workforce snapshot
- monthly sales
- numeric rankings
- current vendor/service metrics
- current promotion configuration where exact values matter

### Put in semantic retrieval

- terminology
- formulas
- business rules
- product/vendor/store meaning
- durable UOM / pack / supplier relationship context
- D365 mappings
- data-source mappings
- approval rules
- agent responsibilities
- durable business context

### Use HYBRID

When a question requires both current facts and durable business meaning.

---

# 6. Semantic Corpus

The semantic corpus is frozen.

Source artifact:

```text
generated/retail_documents.jsonl
```

Representative sample:

```text
generated/retail_documents_sample.jsonl
```

Current corpus:

```text
1,350 semantic documents
18 document types
8 retrieval domains
```

Every semantic document has exactly:

```text
doc_key
doc_type
retrieval_domain
source_sheet
source_key
content
metadata
content_hash
```

`content_hash` is the SHA-256 hash of canonical semantic `content` only.

Operational values, timestamps, database IDs, vector state, and embedding configuration do not participate in semantic content identity.

---

# 7. Retrieval Domains

Current retrieval domains:

| Domain | Purpose |
|---|---|
| `business_entity` | SKU, store, category, vendor, brand, vertical |
| `business_rule` | formulas, terminology, model parameter definitions |
| `operational_policy` | promotion policy/mechanism |
| `operational_context` | brand-event context |
| `integration` | D365/data-source mapping |
| `governance` | approval rules |
| `agent_configuration` | agent responsibility/configuration |
| `documentation` | workbook overview/documentation |

---

# 8. Phase 5 Embedding Architecture

Azure SQL AI tables:

```text
ai.EmbeddingProfile
ai.RetailDocument
ai.RetailChunk
ai.RetailEmbedding
```

## 8.1 Active profile

```text
profile_key:
local-bge-small-en-v1.5-384-v1

provider:
local_sentence_transformers

model:
BAAI/bge-small-en-v1.5

model revision:
5c38ec7c405ec4b44b94cc5a9bb96e735b38267a

device:
cpu

dimensions:
384

normalization:
true

max sequence length:
512

chunk target:
384 tokens

chunk overlap:
48 tokens
```

## 8.2 Current vector counts

```text
Documents:   1,350
Chunks:      1,361
Embeddings:  1,361
```

Exactly six oversized D365 documents are multi-chunk.

All other documents remain one semantic document → one chunk → one vector.

## 8.3 Chunking rule

Chunking is an **embedding concern**, not a semantic-document concern.

The frozen semantic document remains intact.

```text
RetailDocument
    ↓
RetailChunk (1 or many)
    ↓
RetailEmbedding
```

Only documents over the BGE sequence limit are split.

No silent truncation is allowed.

## 8.4 Incremental embedding rule

An embedding is current only if:

```text
RetailEmbedding.embedded_chunk_hash
==
RetailChunk.chunk_hash
```

and it belongs to the requested embedding profile.

Therefore:

```text
new chunk                 → embed
changed chunk hash        → re-embed
unchanged chunk/profile   → reuse
new embedding profile     → embed all active chunks
metadata-only change      → no re-embed if text/hash unchanged
retail.* operational data → no semantic re-embed by itself
```

The mandatory idempotence test passed:

```text
Document changes:     0
Chunk changes:        0
Embeddings generated: 0
Embeddings reused:    1,361
```

---

# 9. Local BGE Runtime

BGE runs locally on the Ubuntu VM.

Current VM characteristics used during validation:

```text
2 vCPU
4 GiB RAM
CPU-only
no CUDA
```

Do not add GPU/CUDA/NVIDIA/Triton dependencies to this environment.

The working PyTorch stack is CPU-only.

Initial full-corpus BGE benchmark:

```text
1,350 documents
~47 seconds for raw full corpus embedding benchmark
~28.7 docs/sec
```

Phase 6 warm retrieval baseline:

```text
SQL median:     ~280 ms
VECTOR median:  ~306 ms
HYBRID median:  ~457 ms
```

Cold BGE startup is approximately 3.9 seconds total, mostly model loading.

For a long-running backend service, process warm-up is recommended.

---

# 10. Phase 6 Retrieval Layer

Main package:

```text
backend/src/retrieval/
```

Current files:

```text
models.py
routing.py
entities.py
capabilities.py
service.py
authorization.py
observability.py
evaluation.py
api.py
__init__.py
```

The central conceptual service is:

```text
retrieve_context(request) -> RetrievalResponse
```

The agent layer should consume this service rather than directly querying the database.

---

# 11. Retrieval Request Contract

`RetrievalRequest` supports:

```text
query
route_mode
top_k
retrieval_domain
doc_type
entity_hints
agent_context
```

Important limits:

```text
query max length: 1000 characters
top_k default: 5
top_k max: 20
entity hints max: 8
agent_context max: 128 characters
```

Route modes:

```text
auto
sql
vector
hybrid
```

The request explicitly does **not** accept:

```text
SQL text
table names
column names
embedding profile IDs
caller-supplied principals
arbitrary identifiers for database objects
```

---

# 12. Deterministic Router

The router uses no LLM.

Core route meanings:

## SQL

Use for exact/current operational facts.

Signals include:

```text
current
today
now
latest
inventory
position
ROP
reorder point
order quantity
current workforce
counts
totals
rankings
specific exact business record
```

## VECTOR

Use for durable meaning/context.

Examples:

```text
definition
terminology
formula
how calculated
business rule
D365 mapping
data-source mapping
approval policy
agent responsibility
durable entity meaning
```

## HYBRID

Use when the request combines current facts with semantic explanation.

Examples:

```text
why is current X happening
explain current inventory state
current metric + formula
diagnose
recommendation context
current replenishment state + business rule
```

Phase 6 retrieves recommendation evidence but does not generate the recommendation itself.

## UNSUPPORTED

Examples:

```text
delete/update/write requests
arbitrary SQL
unsafe route override
unsupported broad request
unresolvable required entity
```

---

# 13. SQL Capability Catalog

Phase 6 currently exposes 15 fixed, parameterized, bounded capabilities:

```text
sku.lookup
sku.inventory_current
sku.replenishment_current
store.lookup
store_sku.snapshot
vendor.lookup
category.lookup
brand.lookup
legal_entity.lookup
promotion.lookup
workforce.current
sales.monthly
trade_agreement.by_vendor
inventory.at_risk
replenishment.top_candidates
```

Rules:

- explicit column lists
- no `SELECT *`
- fixed SQL templates
- positional parameters
- bounded result sets
- read-only
- user text cannot become executable SQL
- user cannot select arbitrary tables/columns

Do **not** replace this with unrestricted text-to-SQL.

---

# 14. Entity Resolution

Supported entity types:

```text
SKU
store
vendor
legal entity
category
brand
promotion
```

Resolution preference:

```text
1. canonical exact identifier
2. exact typed hint
3. normalized case-insensitive exact source name
```

There is deliberately no uncontrolled fuzzy matching.

If multiple exact matches exist:

```text
AMBIGUOUS_ENTITY
```

If a required entity does not exist:

```text
ENTITY_NOT_FOUND
```

Do not guess.

---

# 15. Vector Intent Filtering

Phase 6 adds intent-aware filtering before reusing the frozen Phase 5 vector search.

Examples:

```text
product / SKU
→ business_entity + sku

definition
→ business_rule + terminology

formula
→ business_rule + formula

D365 / source mapping
→ integration

approval
→ governance + approval_rule

agent responsibility
→ agent_configuration + agent_spec

promotion mechanism/policy
→ operational_policy + promotion
```

This filtering materially improves retrieval quality.

A known regression test is:

```text
"Which product is a perishable fruit?"
```

Without targeted filtering, an SKU first appeared lower in the semantic ranking.

With inferred:

```text
retrieval_domain = business_entity
doc_type = sku
```

a matching SKU ranks first.

---

# 16. Semantic Search

Phase 6 reuses Phase 5 search.

It does not duplicate vector SQL.

Search uses:

```sql
VECTOR_DISTANCE('cosine', stored_vector, query_vector)
```

Lower distance is better.

The service may also expose:

```text
cosine_similarity = 1 - cosine_distance
```

but distance and similarity must be labeled correctly.

Search is strictly scoped to the one `ACTIVE` embedding profile.

Multiple chunks from one document are deduplicated to the parent document using the best matching chunk.

---

# 17. Hybrid Behavior

HYBRID runs independent branches:

```text
HYBRID
├── SQL branch
└── VECTOR branch
```

If both succeed:

```text
status = COMPLETE
```

If exactly one branch succeeds:

```text
status = PARTIAL
```

with an explicit warning/error such as:

```text
HYBRID_SQL_BRANCH_FAILED
HYBRID_VECTOR_BRANCH_FAILED
```

Never use semantic evidence as a substitute for a missing exact SQL fact.

Never use SQL evidence as a substitute for missing semantic context.

---

# 18. Retrieval Response

`RetrievalResponse` returns:

```text
request_id
status
route
routing decision
resolved entities
structured_results
semantic_results
citations
warnings
errors
timing
result counts
```

There is intentionally **no generated natural-language answer field**.

That answer should come from the existing agent/chatbot system.

---

# 19. Provenance / Citations

## SQL evidence

SQL citations include concepts such as:

```text
source_kind = sql
schema = retail
source tables
capability key
business keys
selected contributing fields
source load ID
source sheet
source row
source load timestamp
```

Raw SQL is not returned as citation data.

## Semantic evidence

Semantic citations include:

```text
source_kind = semantic
doc_key
chunk_key
chunk index
retrieval_domain
doc_type
source_sheet
source_key
cosine_distance
cosine_similarity
excerpt
```

These citations should be preserved through the future agent answer layer.

---

# 20. Data Freshness Semantics

The structured dataset has load lineage, but not a universal true business-effective timestamp.

Therefore:

```text
loaded_at / source_load_at
```

means data-load time.

Do not incorrectly label it:

```text
as_of
business effective time
current as of
```

unless the source genuinely supports that meaning.

When freshness cannot be proven, Phase 6 may emit:

```text
BUSINESS_AS_OF_UNAVAILABLE
```

---

# 21. Authorization State

There is currently **no real enterprise authentication / tenant isolation / legal-entity authorization layer** in the backend.

Phase 6 therefore has:

```text
AuthorizationPolicy
InternalPocAuthorizationPolicy
```

but this is only a POC boundary.

The optional HTTP endpoint:

```text
POST /api/retrieval/query
```

is:

```text
internal/dev only
excluded from OpenAPI
disabled by default
```

and requires:

```text
RETAIL_RETRIEVAL_API_ENABLED=true
```

to be enabled.

For agents running inside the same Python backend, prefer a direct Python call:

```text
Agent
  ↓
retrieve_context()
```

rather than:

```text
Agent
  ↓ HTTP
POST /api/retrieval/query
  ↓
retrieve_context()
```

unless the agent and retrieval layers are intentionally deployed as separate services.

---

# 22. Observability

Phase 6 structured logs include:

```text
request_id
query fingerprint
selected route
reason codes
entity-resolution outcome
SQL capability keys
vector filters
result counts
branch timings
total latency
fallback flag
error category
```

The logs deliberately exclude:

```text
full user question by default
SQL connection string
passwords
credentials
full vectors
raw SQL
API keys
environment secrets
```

---

# 23. Current Error Contract

Important machine-readable errors/warnings include:

```text
EMPTY_QUERY
UNSUPPORTED_MUTATION
UNSUPPORTED_INTENT
UNSUPPORTED_STRUCTURED_INTENT
UNSUPPORTED_STRUCTURED_CAPABILITY
ENTITY_NOT_FOUND
AMBIGUOUS_ENTITY
INVALID_FILTER
INVALID_ROUTE_OVERRIDE
ACTIVE_EMBEDDING_PROFILE_UNAVAILABLE
EMBEDDING_PROVIDER_MISMATCH
SQL_UNAVAILABLE
VECTOR_UNAVAILABLE
HYBRID_SQL_BRANCH_FAILED
HYBRID_VECTOR_BRANCH_FAILED
BUSINESS_AS_OF_UNAVAILABLE
RESULT_LIMIT_APPLIED
```

There is no silent fallback.

---

# 24. Current Test/Validation State

Phase 5 final state:

```text
1,350 documents
1,361 chunks
1,361 embeddings
0 stale vectors
0 wrong dimensions
0 non-normalized vectors
0 missing embeddings
```

Phase 6 final state:

```text
Routing evaluation: 43/43 passed
Maintained backend suite: 327 passed, 5 skipped
Consolidated real-BGE/Azure tests: 5 passed
Phase 6 live service/capability subset: 2/2 passed
Semantic quality: 6/6 unfiltered and 6/6 filtered
All 15 SQL capabilities returned bounded live evidence
```

Frozen database invariants:

```text
retail.* tables: 15
business rows: 21,571

ai.* tables: 4
documents: 1,350
chunks: 1,361
embeddings: 1,361

ACTIVE profile:
local-bge-small-en-v1.5-384-v1
```

---

# 25. Important Repository Files

## Historical architecture / build records

```text
plans/retail-data-vector-bootstrap.md
plans/phase-5-vector-embedding-changelog.md
plans/phase-6-retrieval-routing-changelog.md
```

Treat these as historical/frozen implementation records.

## Semantic corpus

```text
generated/retail_documents.jsonl
generated/retail_documents_sample.jsonl
```

## Phase 5 embedding/vector implementation

Key modules include:

```text
backend/src/retail_data_bootstrap/embedding_provider.py
backend/src/retail_data_bootstrap/embedding_config.py
backend/src/retail_data_bootstrap/chunking.py
backend/src/retail_data_bootstrap/vector_store.py
backend/src/retail_data_bootstrap/retrieval_evaluation.py
```

Migration:

```text
sql/ai/001_create_ai_vector_schema.sql
```

Tests:

```text
backend/tests/test_vector_embedding.py
```

## Phase 6 retrieval implementation

```text
backend/src/retrieval/models.py
backend/src/retrieval/routing.py
backend/src/retrieval/entities.py
backend/src/retrieval/capabilities.py
backend/src/retrieval/service.py
backend/src/retrieval/authorization.py
backend/src/retrieval/observability.py
backend/src/retrieval/evaluation.py
backend/src/retrieval/api.py
```

Routing evaluation fixture:

```text
backend/tests/fixtures/retrieval_routing_cases.json
```

Tests:

```text
backend/tests/test_retrieval.py
```

Benchmark:

```text
scripts/benchmark_retrieval.py
```

Backend entry point changed in Phase 6:

```text
backend/main.py
```

---

# 26. Current Environment / POC Runtime

Repository location used during implementation:

```text
~/projects/ai-retail-monorepo
```

Python virtual environment:

```text
.venv
```

Backend secret/config file:

```text
backend/.env
```

Important non-secret configuration names may include:

```text
AZURE_SQL_CONNECTIONSTRING

RETAIL_EMBEDDING_PROVIDER
RETAIL_EMBEDDING_MODEL
RETAIL_EMBEDDING_DIMENSIONS
RETAIL_EMBEDDING_NORMALIZE
RETAIL_EMBEDDING_DEVICE
RETAIL_EMBEDDING_CHUNK_TARGET_TOKENS
RETAIL_EMBEDDING_CHUNK_OVERLAP_TOKENS

RETAIL_RETRIEVAL_API_ENABLED
```

Check:

```text
backend/.env.example
```

for the repository's current configuration contract.

---

# 27. How the Existing Chatbot Should Integrate

The intended next integration is:

```text
existing agent
    ↓
retrieve_context()
    ↓
RetrievalResponse
    ↓
bounded evidence adapter
    ↓
existing agent prompt / LLM
    ↓
answer with citations
```

Conceptually:

```python
request = RetrievalRequest(
    query=user_message,
    route_mode="auto",
    agent_context="replenishment",
)

context = retrieve_context(request)

answer = existing_agent.generate(
    user_message=user_message,
    retrieval_context=context,
)
```

Do not implement another independent retrieval layer inside each agent.

All agents should share the same Phase 6 retrieval service.

---

# 28. Agent Grounding Rules for the Next Engineer

When connecting the existing chatbots, preserve these rules:

1. **Retrieve before answering** for Retail-data factual questions.
2. **SQL is authoritative for current/exact values.**
3. **Semantic evidence is authoritative for durable meaning/rules/context.**
4. **HYBRID gets both evidence types.**
5. A `PARTIAL` retrieval must remain visible to the agent.
6. The LLM must not invent missing operational values.
7. Do not let semantic evidence replace a failed exact SQL branch.
8. Preserve Phase 6 citations in the final answer.
9. Validate that citations used by the generated answer actually exist in the retrieval response.
10. Do not bypass Phase 6 with direct arbitrary database access from individual agents.

---

# 29. What Is Frozen / Do Not Redesign Without Explicit Approval

Treat the following as frozen POC contracts:

```text
retail.* relational schema
21,571 structured business rows

semantic eight-field JSONL contract
1,350 semantic documents

content_hash rules

embedding model/profile contract
BAAI/bge-small-en-v1.5
384 dimensions
normalized
CPU

ai.* four-table vector schema

chunking rules

Phase 5 search behavior

Phase 6 SQL capability catalog

Phase 6 deterministic router

entity-resolution safety rules

no arbitrary text-to-SQL

citation/provenance contracts
```

Changes to these should be deliberate migrations, not incidental refactors.

---

# 30. Known Limitations

Current known limitations:

1. No real enterprise authentication yet.
2. No tenant/legal-entity row-level authorization yet.
3. Azure SQL may occasionally have connection timeouts; retries/latency should remain observable.
4. There is no universal business-effective timestamp.
5. Local BGE has a cold-load penalty on process startup.
6. Exact vector scan is intentional for the small current corpus.
7. The current retrieval layer returns evidence, not a generated answer.
8. Existing agent integration still needs to be wired to `retrieve_context()`.
9. Frontend/user-flow validation after agent integration still needs end-to-end testing.
10. D365 is not yet the live production source adapter; Excel/workbook-derived data remains the POC data foundation.

---

# 31. Recommended Immediate Next Step

Before writing new architecture, inspect the existing chatbot/agent system and locate:

```text
1. where user messages enter the agent
2. where the system prompt is built
3. where model/LLM calls happen
4. where conversation history is stored
5. where streaming is handled
6. where citations can be attached/rendered
7. where agent identity / role is selected
```

Then make the smallest integration:

```text
existing user message
    ↓
retrieve_context()
    ↓
existing LLM prompt builder receives RetrievalResponse
    ↓
existing chatbot answers from grounded evidence
```

Do not build a duplicate chatbot framework.

---

# 32. Recommended Remaining POC Roadmap

Given that the chatbot/agent framework already exists, the remaining POC roadmap can be short:

## Phase 7 — Agent ↔ Retrieval Integration

- connect existing agents to `retrieve_context()`
- build bounded evidence-to-prompt formatting
- preserve SQL vs semantic evidence roles
- validate citations
- handle `PARTIAL`/`FAILED`
- add prompt-injection/evidence-grounding safeguards
- optionally add real auth/legal-entity scoping if required for the handoff environment

## Phase 8 — Nine-Agent + End-to-End Validation

- validate all existing agents against the shared router
- ensure correct agent-specific behavior
- verify UI → agent → retrieval → SQL/vector → answer flow
- run UAT
- measure latency
- validate citation rendering
- validate error behavior
- prepare POC demo/release

After this, the POC can be considered functionally complete.

---

# 33. Production Follow-On Work — Not Yet Part of the POC

Possible later production work:

- live D365/ERP extraction adapter
- incremental source synchronization
- real enterprise identity
- tenant/legal-entity authorization
- network/private-endpoint hardening
- model lifecycle/version migration
- corpus-version atomic promotion
- service monitoring and alerting
- autoscaling/high availability
- disaster recovery
- production observability
- security review
- business-data write/action workflows
- formal governance and audit

Do not mix these into the POC without explicit scope approval.

---

# 34. Mental Model for the New Engineer

Think of the current system as three layers:

```text
LAYER 1 — BUSINESS FACTS
Azure SQL retail.*
Exact/current structured values

LAYER 2 — BUSINESS KNOWLEDGE
Azure SQL ai.*
BGE semantic vectors + durable context

LAYER 3 — RETRIEVAL INTELLIGENCE
Phase 6 retrieve_context()
Decides SQL / VECTOR / HYBRID safely
```

The existing chatbot becomes Layer 4:

```text
LAYER 4 — AGENT / LLM
Consumes RetrievalResponse
Explains, reasons, cites, and converses
```

The engineering goal is now to connect Layer 4 to the already-working Layers 1–3 without bypassing their contracts.

---

# 35. Canonical Engineering Rule

When in doubt:

```text
Exact/current number?
→ SQL / retail.*

Meaning, formula, policy, mapping, terminology?
→ VECTOR / ai.*

Need both current state and explanation?
→ HYBRID

Need to answer conversationally?
→ Existing chatbot/LLM consumes RetrievalResponse

Need arbitrary SQL or write access?
→ Not allowed in the current POC architecture
```

---

# 36. Source-of-Truth Documents

Before making architecture-level changes, read these in order:

```text
1. THIS FILE
2. plans/phase-6-retrieval-routing-changelog.md
3. plans/phase-5-vector-embedding-changelog.md
4. plans/retail-data-vector-bootstrap.md
```

This file describes the current assembled architecture.

The changelogs contain the implementation details, validation history, trade-offs, test results, and frozen phase contracts.

---

**Current handoff state: Phase 6 approved/frozen. The next engineering task is to connect the existing Retail chatbot/agent framework to the shared `retrieve_context()` retrieval service and validate grounded end-to-end responses.**
