# Current Architecture Audit

## Scope

Inspected on 2026-07-17:

- `videobrief_server.py`
- `videobrief_service.py`
- `videobrief_agent.py`
- `videobrief_bilibili.py`
- `videobrief-app.html`
- `tests/test_*.py`
- SQLite schema and dependency list

## Size and Coupling

| File | Approximate size | Current responsibilities |
|---|---:|---|
| `videobrief_service.py` | 704 lines / 32 KB | URL parsing, subtitles, YouTube, Bilibili bridge, Whisper, semantic chunks, content types, local structures, evidence, decision brief, QA, request orchestration |
| `videobrief_server.py` | 271 lines / 10 KB | config/env, HTTP DTO, FastAPI routes, job store, thread heartbeat, SQLite, uploads, static files, composition root |
| `videobrief_agent.py` | 20 KB | LLM config, status, HTTP, prompts, parsing, audit, evidence-safe merge |
| `videobrief_bilibili.py` | 112 lines / 4 KB | Bilibili API, subtitles, audio download, Whisper fallback |
| `videobrief-app.html` | 29 KB | markup, 9.8 KB CSS, 15.1 KB JS, state, API, components, export, history, QA, search |

## Confirmed Dependency Problems

1. `videobrief_service.py` imports `enhance_brief`; application orchestration therefore depends directly on one infrastructure provider.
2. `videobrief_bilibili.py` imports `get_whisper_model` back from `videobrief_service.py`, producing a reverse/circular ownership relationship.
3. `videobrief_server.py` imports raw functions, owns global job dictionaries, creates the SQLite schema, performs SQL, coordinates threads and defines routes in one module.
4. Text and upload jobs duplicate completion, persistence and error transitions.
5. Upload reads `MAX_UPLOAD + 1` bytes into memory before writing a temporary file; the nominal 500 MB limit therefore also permits a 500 MB process allocation.
6. `_jobs` has no retention policy and grows until process restart.
7. Unknown URL-like input can fall through `source_kind()` as `local`, even when it is not a local path.
8. Background jobs save raw `str(error)` without an error taxonomy or retryability signal.
9. `result_json` has no explicit schema version; old records depend on frontend fallbacks.
10. Frontend has one mutable `current` global and several direct DOM side effects; API payload parsing and rendering are not separated.
11. API routes and legacy test helpers access private `_db`, `_save_result`, `_jobs`, and `_jobs_lock`, making internal movement risky without compatibility facades.

## Existing Contracts That Must Survive

### Observed history generations

A read-only database audit observed 52 records at audit time (the running service was still writing). The payloads fall into four compatibility families:

- `legacy-no-store`: 22 records without `evidence_store`;
- `evidence-store-v1`: 3 records;
- `typed-v2`: 11 records;
- `decision-v3`: 16 records.

Three legacy records reproduce an `IndexError` in question answering because `points=[]` is indexed directly. Compatibility normalization must precede strict domain validation and must not overwrite original JSON.

### Python imports used by tests

- `videobrief_agent`: `_prompt`, `agent_status`, `enhance_brief`
- `videobrief_server`: `app`, `analyse_payload`, `_save_result`, `_jobs`, `_jobs_lock`, `_run_with_live_progress`, `DB_PATH`
- `videobrief_service`: `extract_youtube_id`, `parse_timestamped_transcript`, `source_kind`, `to_simplified`, `yt_dlp_command`, `answer_from_brief`, `make_brief`, `time_to_seconds`

### API paths

- `/api/jobs`
- `/api/jobs/upload`
- `/api/jobs/{job_id}`
- `/api/history`
- `/api/history/{brief_id}`
- `/api/briefs/{brief_id}/ask`
- `/api/agent/status`
- `/api/health`
- `/api/analyse`

### Storage

Current table:

```sql
briefs(
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  title TEXT NOT NULL,
  source TEXT NOT NULL,
  url TEXT NOT NULL,
  result_json TEXT NOT NULL
)
```

## Existing Strengths to Preserve

- Baseline verified on 2026-07-17: `Ran 37 tests in 2.419s`, `OK`.
- Stable Evidence IDs and original quotes.
- DeepSeek analysis/audit separation.
- Unknown evidence rejection and partial-claim narrowing.
- Deterministic `semantic-chunking` fallback.
- Type-native structures for tutorial, interview, review, lecture and commentary.
- No API Key exposure.
- Conclusion-first interface and progressive disclosure.
- SQLite history and simple one-command local startup.
- Current 37-test regression baseline.

## Architecture Conclusion

The codebase does not need more processes or infrastructure. It needs one modular monolith with a stable domain contract, a single application pipeline, explicit ports at external boundaries, a composition root and a modular no-build frontend. Migration must preserve the existing root imports and HTTP contract until all callers are moved.
