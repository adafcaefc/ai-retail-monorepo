# Azure OpenAI Planner Fix

## Symptoms

The interactive demo waited approximately 45 seconds while the adaptive
planner attempted to obtain a plan, then used the bounded deterministic
acceptance fallback. The SQL and vector work after that decision took only
about 350 ms. The old displayed total also reported only retrieval execution
time and omitted the planner wait.

## Root Cause

The first failing application layer was `AdaptiveQueryPlanner` strict structured
output validation, not DNS, Azure authentication, or SQL/vector retrieval.
The raw Azure request, the OpenAI SDK request, and a simple Pydantic-AI text
request all succeeded. A Pydantic-AI strict tool-output probe also succeeded,
proving that this deployment/API combination supports the structured-output
mechanism.

The adaptive model response itself sometimes contained `null` optional arrays
and a semantic document type/domain combination that disagreed with the
approved catalog mapping. With the old shared `AsyncOpenAI` client, the
planner inherited `max_retries=2` and a large client timeout policy. A failed
structured attempt therefore multiplied into the observed roughly 45-second
wait. The custom no-retry diagnostic exposed the validation failure directly.

The old client construction was also fragile: it used a generic
`AsyncOpenAI` client with a manually duplicated Azure deployment URL,
`api_key="unused"`, an explicit `api-key` header, and an explicit API-version
query. The generic request could succeed, so this was not the proven primary
failure, but the final integration uses the installed SDK's Azure-native client
to make endpoint, deployment, API version, and authentication handling
unambiguous.

## Azure Configuration Path

`src/common/env.py` calls `load_dotenv()` against `backend/.env` and exposes
the application configuration used by the provider. The relevant variable
names are:

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_API_VERSION`
- `AZURE_OPENAI_DEPLOYMENT`

No secret values are recorded here.

## Fix

- `src/llm/model_provider.py` now builds the shared Azure model with
  `AsyncAzureOpenAI(azure_endpoint=..., azure_deployment=..., api_version=...,
  api_key=...)`.
- It exposes a small `create_planner_model()` factory for a separate,
  cached planner client. That client uses the same configured deployment and
  key, a bounded timeout, and `max_retries=0`; unrelated Finance/chat model
  behavior is unchanged.
- `AdaptiveQueryPlanner` caches one planner Agent/model, sets low reasoning
  effort for this bounded planning POC, and permits one Pydantic-AI corrective
  turn only if the strict tool result fails validation. It does not parse free
  form text and it never receives or emits executable SQL.
- Typed catalog-owned normalization converts only nullable empty collections,
  canonicalizes approved document-type/domain mappings, and removes the
  catalog-equivalent `horizon_days=7` decoration from the baked-in
  `demand.forecast_7d` metric. Unknown metrics/dimensions remain unavailable
  and continue through policy/compiler validation.
- Explicitly filtered semantic branches can now force the existing vector
  route during adaptive execution even when their evidence query contains
  planner words such as “forecast” or “compare”. Unfiltered vector overrides
  remain rejected.

## Client Construction

The final shared and planner clients are instances of the installed
`openai 2.53.0` `AsyncAzureOpenAI` class. Pydantic-AI's existing
`OpenAIProvider(openai_client=...)` and `OpenAIChatModel` remain the integration
boundary. The planner factory supplies an `httpx.Timeout` of 15 seconds
(5-second connect cap) and `max_retries=0`. No authorization header is
manually fabricated and no deployment path is concatenated by application
code.

## Structured Output

Pydantic-AI calls the Azure chat-completions endpoint in strict tool mode with
the Pydantic `QueryPlan` schema. The result is validated as `QueryPlan`, then
catalog-normalized, then passed to `QueryPolicy` and
`DeterministicSqlCompiler`. Invalid values still fail closed; there is no
free-form response parsing and no LLM-generated SQL execution.

## Retry / Timeout Policy

The planner transport uses one bounded request (`max_retries=0`). A malformed
strict output may receive one Pydantic-AI corrective turn; this is distinct
from transport retries and remains bounded. The planner timeout is 15 seconds
per request. Existing unrelated model clients retain their prior settings.

## Timing / Observability

Planner events now expose the safe deployment name, strict mode, timeout,
transport retry count, output retry count, model duration, validation duration,
and categorized failure. Categories include `timeout`, `authentication`,
`permission`, `deployment_not_found`, `rate_limited`, `invalid_request`,
`structured_output_validation`, `network`, and `unknown`.

`RetrievalTiming` now separates catalog, planner model, planner validation,
fallback decision, fallback execution, policy, compilation, SQL, embedding,
`VECTOR_DISTANCE`, vector total, evidence aggregation, and gateway wall-clock
time. `ChatRetrievalGateway` measures from entry to final response, including
planner wait and fallback work.

## Validation

Mocked/unit validation:

```bash
cd backend
python -m pytest -q \
  tests/test_adaptive_retrieval.py \
  tests/test_adaptive_retrieval_demo.py \
  tests/test_chat_retrieval_integration.py \
  tests/test_retrieval.py
```

The final focused run passed **96 tests** with **2 existing opt-in skips**.

The live Azure planner regression is opt-in and separate from the unit suite:

```bash
RUN_AZURE_OPENAI_INTEGRATION=1 \
  python -m pytest -q tests/test_azure_openai_planner_integration.py
```

It passed **2 tests** in **20.90 seconds**: the exact forecast prompt and the
new category/inventory prompt each returned a strict `QueryPlan` without the
fallback.

The direct diagnostics recorded a successful raw HTTP request and successful
generic and Azure-native SDK requests when no obsolete `max_tokens` field was
sent. The `max_tokens` probe itself returned Azure HTTP 400 explaining that
this deployment requires `max_completion_tokens`; the application does not
send that obsolete field. A live Pydantic-AI structured-output probe and the
live AdaptiveQueryPlanner tests succeeded.

The full commands required for final repository validation are:

```bash
python -m pytest -q tests
python -m compileall -q src scripts tests
cd ..
git diff --check
```

## Exact Forecast Result

The final exact forecast demo run used the **real Azure planner**, not the
bounded acceptance fallback. It completed planner/model validation, policy,
deterministic compilation, and Azure SQL retrieval, returning `PARTIAL` with
real `demand.forecast_7d` evidence. Forecast basket and backtested MAPE
remained unavailable because neither is an approved catalog metric. The
measured planner time in that run was about **9.2 seconds** and gateway
wall-clock time about **9.7 seconds**.

## New Unseen Query Result

The new query was:

> Rank categories by inventory exposure and explain which categories appear to
> need the most replenishment attention.

It used `PLANNER_REQUIRED`, a real Azure structured plan, policy, deterministic
compiler, SQL, and semantic retrieval with no acceptance fallback. It returned
`PARTIAL`: inventory evidence was available, while category-level aggregation
and the requested time-series rollup remained unavailable in the approved
catalog. One observed run took about **12.2 seconds** in the planner and
**13.4 seconds** gateway wall-clock.

## Remaining Limitations

- Live SQL/vector results depend on Azure SQL reachability and the active
  frozen embedding profile.
- Azure planner latency is still model-dependent; healthy calls observed in
  the final checks were approximately 6–13 seconds.
- Forecast basket, backtested MAPE, category rollups, and time-series fields
  remain unavailable unless approved catalog/source data is added.
- The current Retail chatbot registry remains disabled; this fix does not
  change product/navigation ownership.
- A genuine Azure planner outage still uses the existing bounded acceptance
  fallback only for its exact supported forecast shape.
