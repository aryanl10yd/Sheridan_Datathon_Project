# Sentinel Orbital investigation agents

The agent subsystem performs defensive, **read-only** investigations. It never accesses the authorization service, approval credentials, interlock controls, exploit code, networks for scanning, or real operational infrastructure. All mission profiles and operations are hypothetical. AI may recommend a hold for review; it cannot approve an operation or establish the status of a separate approval workflow.

## Integration and API

`app.agents` exports `async def investigate(question: str, cve: str | None = None) -> dict` and `model_mode() -> str`. The FastAPI application calls `investigate` from `POST /api/investigate` with JSON `{ "question": "...", "cve": "DEMO-2026-0001" }`; `cve` may be omitted if exactly one CVE/DEMO identifier is in the question. Do not supply multiple identifiers: the result requests one at a time. The data service must be initialized in application startup (the FastAPI startup hook does this); missing source files and unknown records are returned as insufficient evidence, not fabricated results.

Example with the server running:

```bash
curl -s http://127.0.0.1:8000/api/investigate \
  -H 'Content-Type: application/json' \
  -d '{"question":"Investigate exploitation momentum and simulated mission assurance", "cve":"DEMO-2026-0001"}'
```

Python, from an asynchronous context:

```python
from app.agents import investigate, model_mode
result = await investigate("Explain DEMO-2026-0001", "DEMO-2026-0001")
print(result["mode"], result["synthesis"]["summary"])
```

The response has the required top-level fields `mode`, `plan`, `agents`, `synthesis`, `verification`, and `limitations`. A plan contains the chosen roles, tasks, trace ID, timing, and actual supervisor routing-call metrics. Each participating agent returns `name`, `task`, `findings`, `evidence`, `tools`, `duration_ms`, `status`, and model call metadata. Evidence has a stable run-local ID, record ID when applicable, source, method, and original data text (subject to the existing size bounds). `synthesis` contains cautious deterministic highlights and, when available, separately marked model interpretations. `verification` lists mechanically evidence-linked and rejected findings, unresolved conflicts, and the checks' limitations. `status` is `complete`, `partial`, `insufficient_evidence`, or `error`. These are descriptive investigation outputs, not authorization states or chain-of-thought.

## Granite inference configuration

Set all three values as environment variables before starting the server. The endpoint must implement the OpenAI-compatible chat-completions protocol and serve the configured IBM Granite model. Provide a trusted URL ending in `/v1` (the client appends `/chat/completions`) or the complete `/v1/chat/completions` URL. A self-hosted local endpoint is possible; use TLS and trusted infrastructure for remote endpoints because the question and retrieved data are sent there. `GRANITE_API_KEY` is supplied as a Bearer token only to the configured endpoint; it is not included in prompts, logs, or results. For a local server requiring no authentication, use an administrator-supplied placeholder API key if the server accepts one. The application does not obtain or manage IBM IAM tokens; direct watsonx authentication/project-specific request shapes are **not** implemented—use an OpenAI-compatible gateway where appropriate.

```bash
export GRANITE_ENDPOINT='https://your-trusted-granite-host/v1'
export GRANITE_MODEL='ibm-granite/granite-3.3-8b-instruct'
export GRANITE_API_KEY='your-own-key'
export GRANITE_TIMEOUT_SECONDS=20
export GRANITE_MAX_TOKENS=600
export GRANITE_TEMPERATURE=0
export GRANITE_RETRIES=1
```

Defaults are 20 seconds per attempt, 600 output tokens, temperature 0, and one retry. Retries are capped at two and apply to transient/network/invalid-JSON errors; non-transient HTTP errors fail fast. Input context and output are bounded. Configure appropriate provider-side rate, concurrency, retention and network controls; model endpoints and models differ in JSON behavior. This prototype requests JSON in the prompt and validates it with Pydantic; it does **not** assume native JSON-schema or function-calling support. No model-generated tool calls are executed. Calling `model_mode()` reports `granite-configured` when all settings are present, **not** a successful health check or a guarantee of model identity; configure an actual Granite deployment yourself.

- `deterministic-demo`: no complete valid Granite configuration; actual data tools still run, but no model output is claimed. Data may be imported data or fictional DEMO data; inspect source labels independently.
- `granite`: actual configured endpoint calls succeeded for the calls made; model-derived interpretations remain unverified.
- `granite-with-deterministic-fallback`: at least one inference failed; a per-role/supervisor error and fallback are explicitly reported in limitations and metrics. Successful model calls may still be present, separately labelled.
- `deterministic-demo-fallback`: a configured run had no successful model call and no explicit call error, for example when no source evidence was available.

No live Granite credentials or provider endpoint were supplied for development; **real Granite remains untested**. Tests use an HTTP mock and do not certify a particular deployment, model identity, JSON compliance, or inference quality.

## Workflow and role boundaries

1. A deterministic router picks a minimal baseline role set from the question. A configured Granite supervisor can propose additional roles from a validated allowlist; it cannot remove safety-required routes. Unknown scope is reported rather than made up.
2. The language, momentum, statistical discovery, and asset-context specialists independently execute their own fixed, role-specific read-only tool sequences concurrently using asynchronous orchestration. They each have a separate role prompt, tool subset, task and structured result. Fixed tool invocation follows the cookbook's recommendation for predictable safety-sensitive workflows. Mission assurance runs after these specialists so it receives their findings, uncertainty, and status.
3. The verification specialist independently re-reads the target ID, checks evidence IDs and record IDs, checks source-quote and numeric presence, rejects unsupported IDs or quotes and some unrelated claims, and flags simple opposing known-exploitation statements. A missing or mismatched independent record read prevents target-linked claims from being treated as accepted. The supervisor synthesizes cautious, evidence-linked highlights; a separate Granite synthesis call is attempted when configured and is subjected to the same validation.
4. Each Granite specialist, verifier, and supervisor interpretation can use concise original wording. It must cite existing evidence IDs and provide a nonempty, **case-sensitive verbatim quote** from a cited item plus a specific uncertainty. Role findings can cite only their role's evidence; the verifier and supervisor receive shared evidence. Each surfaced item includes its original `model_uncertainty`, `quote`, `evidence_ids`, the label **`MODEL-INFERRED / UNVERIFIED`**, `review_required: true`, and a separate caveat that it is **not verified fact or an official classification**. Confidence is uncalibrated. The original description remains available in the evidence for direct review; a model interpretation is not a substitute for it. In particular, interpreting a description as a possible weakness or behavior is not an official classification or evidence of actual exploitation.

`verification.accepted` means **only that the listed mechanical checks passed**, not that the model's interpretation was accepted as true. The application rejects missing or invalid quotes, nonexistent or inappropriate evidence/record IDs, numerical tokens absent from the quoted span, obvious unrelated prose without meaningful word overlap, assertions of confirmation or authorization, and some instruction-like text. Rejected candidates are removed from findings and synthesis; rejection diagnostics can still identify the rejected claim and IDs. Mechanically rejected specialist findings are not embedded in the mission-assurance aggregation. These conservative checks may reject valid paraphrases or estimates, including numbers expressed differently from the quote.

Most importantly, an exact quote and shared words **cannot prove semantic entailment**: a claim can share terms or numbers with a quote while reversing, exaggerating, or otherwise misrepresenting it. Numeric token presence cannot establish units, arithmetic, scope, or numerical relationships; the checks are not comprehensive for all written quantities, contradictions, data leaks, outdated observations, or temporal leakage. The source itself may be wrong. The label and human-review requirement remain even when all checks pass. Review the original quoted context, applicability, uncertainty and all conclusions manually; do not automatically treat a linked model claim as a fact or an official classification.

Only `app.data.get_vulnerability(id)`, `get_momentum(id)`, `statistics()`, `profiles()`, and bounded `list_vulnerabilities(limit=30, offset=0)` are available to the agents. The statistical specialist reports data-service full-cohort descriptive counts when available and first-page CVSS coverage with sample size and IDs; the page is not random or representative. Descriptive patterns are neither anomalies by default nor causal findings. Momentum uses dated records returned by the data service; a public reference is not proof of a working exploit. Asset matching is case-insensitive product/vendor identity only, including returned affected-product records; versions and actual installations remain unverified.

Each tool result and user question is JSON-encoded into a lower-priority model message as **untrusted data**; it is never a system instruction or a model-authorized executable action. The allowlist, argument construction, bounded calls, deterministic evidence validation, and separation from interlock are code-level controls, not solely prompts or a regex. The model has no tools bound to it and no agent can mutate data. Prompt injection defenses are not a guarantee of accurate model output. Standard logs record trace IDs, role, timings, model-call attempts, errors by class/status, and provider token usage when present; raw prompts, response bodies and secrets are not logged. Logs are not a full distributed tracing service. Tool timeouts stop waiting but cannot forcibly terminate a Python thread already executing a data call.

## Cookbook patterns and evaluation

Reviewed upstream cookbook commit `393166743e92bf4854db0f598af04f1817c02c3b`, including all four guides and the nine requested notebooks. Route-and-Solve informs separated specialists and narrow tool sets; Plan-and-Solve informs a bounded plan followed by execution; Function Calling and ReAct inform a real tool-observation boundary without exposing thoughts, with programmatic fixed tool calls preferred here; ToolRAG informs narrow tool exposure but no embedding/vector tool retriever is warranted for five actions. Agent TDD informs trajectory and answer checks; tracing/NFR inform run ID, latency, attempts and usage; security informs untrusted content, application-enforced allowlists and validation. No cookbook's simulated sandbox is represented as isolation. See `docs/cookbook-notes.md` for notebook paths and important recipe caveats.

Run the isolated regression suite from the project root:

```bash
.venv/bin/python -m pytest tests/test_agents.py -q
```

The suite checks different routes and tool trajectories, raw descriptions and nonverbatim interpretations with exact quotes and preserved uncertainty, mission matching, cohort counts, independent concurrency, unknown and partial data, unsupported numbers/IDs/quotes, unrelated and instruction-like text, contradictory claims, HTTP request shape, token accounting, injection containment, failed inference and bounded fallback. It mocks the Granite provider; production evaluation should add a vetted fixture corpus, real endpoint/model tests, broader claim entailment and contradiction review, prompt-injection adversarial testing, latency/load measurements, and human assessment. The `investigate` function is stateless and multi-turn history is not provided. When a momentum-only investigation is incomplete, the supervisor requests at most one supplemental language-context lookup and explicitly notes that it cannot establish an exploitation trend. Remaining evidence gaps are reported rather than filled with invented facts.
