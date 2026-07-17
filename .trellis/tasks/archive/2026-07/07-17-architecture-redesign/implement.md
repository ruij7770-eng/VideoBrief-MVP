# VideoBrief Architecture Redesign Implementation Plan

## Preconditions

- Task artifacts `prd.md`, `design.md`, and this plan have been reviewed.
- User explicitly approves implementation.
- Current dirty worktree is preserved as the migration baseline; no unrelated user file is reverted.
- Baseline command succeeds before the first architecture edit:

```bash
unset PYTHONPATH
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Expected baseline: 37 tests, `OK`.

## Global Rules

- Work in vertical, independently testable slices.
- Every behavior change follows RED → GREEN → REFACTOR.
- Root compatibility modules remain importable until final verification.
- No destructive SQLite migration.
- After every slice, run its focused tests and the full suite.
- If a slice cannot pass compatibility tests, restore only that slice's composition binding; do not delete working legacy code.

---

## Task 1 — Package Skeleton, Settings, Errors and Domain Models

**Objective:** Establish the dependency direction and canonical Brief contract without changing runtime behavior.

**Create:**

- `videobrief/__init__.py`
- `videobrief/config.py`
- `videobrief/domain/__init__.py`
- `videobrief/domain/errors.py`
- `videobrief/domain/models.py`
- `tests/unit/test_domain_models.py`
- `tests/unit/test_config.py`

**Steps:**

1. Write failing tests proving:
   - `DecisionBrief.takeaways` rejects more than three items;
   - an Insight rejects empty evidence IDs;
   - a Brief validates that referenced Evidence IDs exist;
   - settings load port, DB path and LLM metadata but never serialize API Key through public status.
2. Run:
   ```bash
   unset PYTHONPATH
   .venv/Scripts/python.exe -m unittest tests.unit.test_domain_models tests.unit.test_config -v
   ```
   Expected: import failures.
3. Implement `Settings` as a frozen dataclass and domain models as Pydantic v2 models.
4. Add domain errors:
   `InputValidationError`, `UnsupportedSourceError`, `SourceUnavailableError`, `TranscriptionError`, `AnalysisUnavailableError`, `BriefNotFoundError`.
5. Keep serialization aliases compatible with current dict keys (`body`/`quote` where required at adapters only).
6. Run focused tests and full suite.

**Rollback point:** New package is additive; delete new files if the contract cannot coexist.

---

## Task 2 — Transcript, Evidence, Decision and QA Pure Services

**Objective:** Move deterministic pure logic first and make legacy functions delegate to it.

**Create:**

- `videobrief/application/__init__.py`
- `videobrief/application/transcript.py`
- `videobrief/application/decision.py`
- `videobrief/application/question_answering.py`
- `videobrief/application/compatibility.py`
- `tests/unit/test_transcript_service.py`
- `tests/unit/test_decision_service.py`
- `tests/unit/test_question_answering.py`
- `tests/contract/test_legacy_service_facade.py`

**Modify:**

- `videobrief_service.py`

**Steps:**

1. Write failing tests for VTT/SRT/bracket parsing, simplified Chinese, long timestamps, stable Evidence IDs and exact original quotes.
2. Write failing decision tests for:
   - answer/takeaway deduplication;
   - 1–3 takeaways based on information value;
   - removal of opening-intro filler;
   - generic-title replacement;
   - watch verdict and exact watch seconds.
3. Write failing QA tests proving best evidence selection and explicit not-found behavior.
4. Implement pure services by moving existing tested logic, not rewriting algorithms at the same time.
5. Replace the corresponding root functions with thin imports/wrappers. Preserve function signatures and dict return types.
6. Run:
   ```bash
   unset PYTHONPATH
   .venv/Scripts/python.exe -m unittest \
     tests.unit.test_transcript_service \
     tests.unit.test_decision_service \
     tests.unit.test_question_answering \
     tests.contract.test_legacy_service_facade -v
   ```
7. Run full suite.

**Rollback point:** Change facade imports back to the legacy implementation; new pure modules remain unused.

---

## Task 3 — Local Semantic Analyzer and Brief Assembly

**Objective:** Give deterministic analysis one owner and return a canonical Brief draft.

**Create:**

- `videobrief/infrastructure/__init__.py`
- `videobrief/infrastructure/analysis/__init__.py`
- `videobrief/infrastructure/analysis/semantic.py`
- `tests/unit/test_semantic_analyzer.py`

**Modify:**

- `videobrief_service.py`
- `tests/test_v3.py` only where imports should target the canonical module in addition to facade contracts.

**Steps:**

1. Add fixture-based failing tests covering tutorial, interview, review, lecture and commentary role order.
2. Add an Evidence conservation test: every source Evidence ID appears unchanged after semantic chunking.
3. Move title, summary, chunks, content type, local content model, content map, must-watch and metrics logic into `SemanticAnalyzer` plus small pure helpers.
4. Build `Brief` through one assembler and call `DecisionService` last.
5. Keep `make_brief(rows)` facade returning the legacy dict representation.
6. Run focused tests and full suite.

**Rollback point:** Rebind `make_brief` to legacy code.

---

## Task 4 — Source Registry and Whisper Transcription

**Objective:** Isolate external acquisition and remove the Bilibili→service reverse import.

**Create:**

- `videobrief/application/ports.py`
- `videobrief/infrastructure/sources/__init__.py`
- `videobrief/infrastructure/sources/registry.py`
- `videobrief/infrastructure/sources/pasted.py`
- `videobrief/infrastructure/sources/youtube.py`
- `videobrief/infrastructure/sources/bilibili.py`
- `videobrief/infrastructure/sources/upload.py`
- `videobrief/infrastructure/transcription/__init__.py`
- `videobrief/infrastructure/transcription/whisper.py`
- `tests/unit/test_source_registry.py`
- `tests/integration/test_source_adapters.py`
- `tests/contract/test_legacy_source_facades.py`

**Modify:**

- `videobrief_service.py`
- `videobrief_bilibili.py`

**Steps:**

1. Define only the ports needed by multiple implementations: `SourceAdapter`, `Transcriber`, `LocalAnalyzer`, `SmartAnalyzer`, `BriefRepository`, `JobRepository`.
2. Add failing registry tests for exact priority and unsupported URL rejection.
3. Add adapter tests with fake requests/subprocess/transcriber; no live web dependency in automated tests.
4. Move Whisper cache into `WhisperTranscriber`.
5. Inject the same Transcriber into Bilibili audio fallback and upload adapter.
6. Keep `get_whisper_model`, `fetch_youtube_transcript`, `fetch_bilibili_transcript`, `transcribe_local_video` and `bilibili_transcribe` facades.
7. Run focused tests and full suite.

**Rollback point:** Facades can point back to old acquisition functions without touching domain or DB.

---

## Task 5 — DeepSeek Client, Prompts, Audit and Merge Policy

**Objective:** Separate provider I/O from evidence policy while preserving two-stage behavior.

**Create:**

- `videobrief/infrastructure/analysis/deepseek.py`
- `videobrief/infrastructure/analysis/prompts.py`
- `videobrief/infrastructure/analysis/audit.py`
- `tests/unit/test_deepseek_client.py`
- `tests/unit/test_evidence_merge_policy.py`
- `tests/contract/test_legacy_agent_facade.py`

**Modify:**

- `videobrief_agent.py`

**Steps:**

1. Re-express all current `tests/test_agent.py` cases against the new collaborators before moving code.
2. Add tests for provider timeout, invalid JSON, unknown Evidence ID, partial narrowing, wrong type role, sparse structure fallback and max-three page insights.
3. Move config/HTTP into `DeepSeekClient`; never expose `api_key` from status.
4. Move first- and second-pass prompt construction to `prompts.py`.
5. Move merge rules to `EvidenceMergePolicy`, independent of HTTP.
6. Implement `DeepSeekAnalyzer.enhance()` and mode behavior.
7. Make root `_prompt`, `agent_status`, `enhance_brief` facades preserve test imports and transport injection.
8. Run focused tests and full suite.

**Optional real check:** One user-authorized `smart` sample only after fake-transport tests pass.

**Rollback point:** Rebind root agent facade to legacy implementation.

---

## Task 6 — SQLite Repository, Job Store and Unified Pipeline

**Objective:** Replace global SQL/job/orchestration logic with application services.

**Create:**

- `videobrief/application/pipeline.py`
- `videobrief/application/jobs.py`
- `videobrief/infrastructure/persistence/__init__.py`
- `videobrief/infrastructure/persistence/sqlite.py`
- `videobrief/infrastructure/jobs/__init__.py`
- `videobrief/infrastructure/jobs/memory.py`
- `tests/unit/test_job_store.py`
- `tests/integration/test_sqlite_repository.py`
- `tests/integration/test_pipeline.py`
- `tests/integration/test_history_compatibility.py`

**Modify:**

- `videobrief_server.py` compatibility helpers only after new tests pass.

**Steps:**

1. Add failing repository tests using temporary SQLite files:
   - create schema idempotently;
   - save/get/list round-trip;
   - read an old JSON fixture without `schema_version`/`decision_brief`;
   - preserve evidence facts.
2. Add failing job-store tests for snapshots, legal transitions, retention and missing IDs.
3. Add fake-port pipeline tests asserting exact stage order and a single code path for text/upload after acquisition.
4. Configure WAL and busy timeout per connection.
5. Implement `BriefCompatibility.upgrade(raw)` on read only.
6. Implement `JobRunner` to persist success and standardize failure code/message.
7. Keep `_db`, `_save_result`, `_jobs`, `_jobs_lock`, `_run_with_live_progress` compatibility surfaces until old tests migrate.
8. Run focused tests and full suite.

**Rollback point:** API still points at old server functions until Task 7 switches the composition root.

---

## Task 7 — FastAPI Composition Root and Routes

**Objective:** Make HTTP a thin boundary and switch runtime to the new pipeline.

**Create:**

- `videobrief/api/__init__.py`
- `videobrief/api/app.py`
- `videobrief/api/dependencies.py`
- `videobrief/api/schemas.py`
- `videobrief/api/routes/__init__.py`
- `videobrief/api/routes/jobs.py`
- `videobrief/api/routes/briefs.py`
- `videobrief/api/routes/system.py`
- `tests/contract/test_api_contract_v3.py`
- `tests/integration/test_upload_streaming.py`

**Modify:**

- `videobrief_server.py`
- `tests/test_server.py`

**Steps:**

1. Freeze current API success fixtures and add failing new error-contract tests.
2. Implement dependency construction in one cached application container; tests can override ports/repositories.
3. Move routes by area; no SQL, source acquisition or analysis imports inside route modules.
4. Stream uploads to a temporary file in chunks, enforce 500 MB while writing and clean every exit path.
5. Install application-error handlers returning both `detail` and structured `error`.
6. Make root `videobrief_server.app` import the new app; retain tested helper wrappers.
7. Verify every existing path and the old synchronous `/api/analyse` route.
8. Run focused tests and full suite.
9. Start server and verify `/api/health`, `/api/agent/status`, one fast pasted transcript job and one history read.

**Rollback point:** Restore the single `app` binding in `videobrief_server.py`.

---

## Task 8 — Modular Conclusion-First Frontend

**Objective:** Replace inline UI with maintainable static modules without changing the product hierarchy.

**Create:**

- `videobrief/web/index.html`
- `videobrief/web/assets/css/app.css`
- `videobrief/web/assets/js/app.js`
- `videobrief/web/assets/js/api.js`
- `videobrief/web/assets/js/state.js`
- `videobrief/web/assets/js/dom.js`
- `videobrief/web/assets/js/export.js`
- `videobrief/web/assets/js/components/decision.js`
- `videobrief/web/assets/js/components/structure.js`
- `videobrief/web/assets/js/components/evidence.js`
- `videobrief/web/assets/js/components/chapters.js`
- `videobrief/web/assets/js/components/tools.js`
- `tests/contract/test_frontend_assets.py`
- `tests/browser/test_decision_first_flow.py` if the selected browser runner is available; otherwise keep browser execution as an explicit manual/automation command outside unittest.

**Modify:**

- `videobrief/api/app.py` for static mount.
- `videobrief-app.html` becomes a small compatibility entry or redirect, with no inline app implementation.
- `tests/test_ui_contract.py` migrates from string presence checks to asset and behavior contracts.

**Steps:**

1. Add failing asset tests proving index references external CSS/ES Modules and all static paths return 200.
2. Implement centralized `api.js` decoder and errors.
3. Implement reducer/store with explicit `idle/processing/ready/error` view transitions.
4. Move DOM helpers and Evidence rendering first.
5. Move decision, type structure, chapters and tools components.
6. Move export to one escaping boundary.
7. Preserve demo, polling, source jump, search, QA, history and export.
8. Keep first-screen hierarchy exactly: answer → 1–3 takeaways → watch decision/boundary → metrics.
9. Run static/contract tests and full suite.
10. Browser verify desktop and 390×844; console must contain zero uncaught errors.

**Rollback point:** Root route can serve the previous `videobrief-app.html` while assets remain additive.

---

## Task 9 — Compatibility Cleanup, Documentation and Architecture Specs

**Objective:** Remove duplicate implementation bodies only after all consumers use the new package.

**Modify:**

- `videobrief_service.py`
- `videobrief_agent.py`
- `videobrief_bilibili.py`
- `videobrief_server.py`
- `README.md`
- `.trellis/spec/backend/directory-structure.md`
- `.trellis/spec/backend/database-guidelines.md`
- `.trellis/spec/backend/error-handling.md`
- `.trellis/spec/backend/quality-guidelines.md`
- `.trellis/spec/backend/logging-guidelines.md`

**Steps:**

1. Search all imports/references to legacy implementation symbols.
2. Keep only required compatibility exports; remove unreachable duplicate bodies.
3. Document actual package boundaries, repository conventions, error taxonomy, tests and secrets rules in English per the spec requirement.
4. Rewrite README startup, architecture, API, environment and troubleshooting sections.
5. Add `docs/architecture.md` only if README would become too large; do not duplicate the same source of truth.
6. Run full suite, ad-hoc focused architecture verification and server/browser checks.
7. Review git diff for secrets, DB files, temporary uploads, generated caches and unrelated changes.

---

## Final Validation Gate

### Automated

```bash
unset PYTHONPATH
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Expected: all tests `OK`.

### API

- `/api/health` returns current version and `status=ok`.
- `/api/agent/status` contains no `api_key`.
- Fast pasted transcript job completes and returns canonical `schema_version`, `evidence_store`, `decision_brief`, `content_model` and `brief_id`.
- Old SQLite history item loads with current derived fields.
- QA returns exact timestamp and Evidence ID.

### Browser

Desktop:

- Create form, progress, result, evidence, QA, history and export work.
- No repeated insight/map modules.
- Console has no uncaught error.

390×844:

- No horizontal overflow or overlap.
- Answer and first takeaway appear before secondary metadata.
- Tools remain reachable after main content.

### Security

- Search tracked files and response payloads for Key patterns.
- `.env`, database, uploads and caches remain ignored.
- Errors do not include request headers, environment values or stack traces.

## Commit and Finish

After the final check passes:

```bash
git add <reviewed architecture files only>
git commit -m "refactor: redesign VideoBrief architecture"
```

Then update Trellis session/spec records and archive the task according to the project workflow.
