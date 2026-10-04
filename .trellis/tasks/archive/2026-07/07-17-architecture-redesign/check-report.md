# Architecture Redesign Check Report

Date: 2026-07-17
Task: `07-17-architecture-redesign`
Result: PASS

## Delivered architecture

- Modular monolith with Ports and Adapters.
- Dependency direction guarded by tests: API / infrastructure -> application -> domain.
- One `UnderstandingPipeline` for pasted transcripts, URLs and uploads.
- Source adapters for YouTube, Bilibili, local upload and pasted transcript.
- Separate deterministic analysis, DeepSeek client, prompts and fail-closed evidence merge.
- Canonical Pydantic domain contracts for Evidence, Insight, DecisionBrief and Brief.
- FastAPI application factory with split routes and Chinese error envelopes.
- SQLite repository with explicit-column inserts and read-time historical projection.
- Bounded, thread-safe in-memory job repository.
- No-build static ES Modules with central API decoder, reducer/store and pure DOM components.
- Thin compatibility facades retained at all four original root Python modules.

## Compatibility evidence

- Existing API paths and default port `12000` remain available.
- Original startup command remains valid.
- New payloads carry `schema_version: 4`.
- A read-only SQLite backup scan covered all 52 pre-migration records:
  - `legacy-no-store`: 22
  - `evidence-store-v1`: 3
  - `typed-v2`: 11
  - `decision-v3`: 16
- `PRAGMA integrity_check = ok`.
- Every record produced a deterministic read projection and safe question-answering result.
- No dangling Evidence references were found.
- Snapshot SHA-256 was unchanged before/after the scan.
- Existing modern Evidence IDs remained unchanged; legacy IDs are generated only in the read projection.

## Automated verification

Canonical command:

```bash
unset PYTHONPATH
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Result:

```text
Ran 74 tests in 10.147s
OK
```

Additional gates:

```text
PYTHON_COMPILE_OK
JS_MODULE_SYNTAX_OK
GIT_DIFF_CHECK_OK
ENV_GITIGNORE_OK
```

The suite now includes domain, application, source, smart-audit, repository, API, dependency-direction, frontend-module and legacy compatibility contracts.

## Runtime verification

Fresh final service:

```json
{"status":"ok","version":"4.0","schema_version":4,"port":12000}
```

Fast API / static frontend end-to-end result:

```text
AD_HOC_V4_E2E_PASS
```

Verified health, module HTML, CSS/JS assets, safe provider status, error envelope, job completion, canonical result, Evidence integrity and history round-trip.

## Real DeepSeek verification

Three real `smart` jobs completed against the configured OpenAI-compatible DeepSeek endpoint:

| Requested case | Actual template | Evidence | First-screen takeaways | Result |
|---|---:|---:|---:|---|
| tutorial | tutorial | 5 | 2 | PASS |
| interview | interview | 4 | 2 | PASS |
| commentary | commentary | 4 | 1 | PASS |

Every case verified:

- `schema_version == 4`;
- two model calls;
- `agent-evidence-first` engine;
- only known Evidence IDs;
- only native roles for the final template;
- non-empty `decision_brief.answer`;
- no more than three first-screen takeaways.

Marker:

```text
AD_HOC_REAL_DEEPSEEK_V4_PASS
```

All ten records created by API, browser, responsive and DeepSeek verification were then removed by explicit UUID in one SQLite transaction. The database returned from 62 to the original 52 records, `PRAGMA integrity_check` remained `ok`, and no pre-existing row was selected by title or time range.

## Browser and responsive verification

Desktop browser:

- ES Modules loaded successfully.
- Demo fast job completed.
- Conclusion-first hero, up to three takeaways, watch advice, native structure and chapters rendered.
- Type structure and chapters were collapsed by default.
- Browser console contained zero JavaScript errors.

Exact `390 x 844` CSS viewport:

```text
AD_HOC_MOBILE_390_PASS
```

Verified:

- no horizontal overflow;
- left rail collapsed;
- result shell and decision answer visible;
- one to three takeaways;
- type items and chapters collapsed;
- no visible failure state.

This check found and fixed a missing closing brace in `.metrics` that had prevented both media queries from entering CSSOM. A regression contract now checks balanced braces and both top-level media rules.

## Intentional constraints retained

- Jobs remain process-local and the service should run with one worker.
- SQLite remains the persistence layer.
- Frontend remains no-build ES Modules.
- DeepSeek remains optional; `auto` safely falls back to deterministic analysis.
- No Redis, Celery, Kafka, Node build pipeline or microservices were introduced.
