# Quality Guidelines

> Quality gates for the VideoBrief modular monolith.

---

## Forbidden Patterns

- Domain or application imports from `videobrief.infrastructure` or `videobrief.api`.
- SQL, HTTP requests, Whisper loading, or analysis logic inside FastAPI routes.
- New business logic in the four root compatibility modules.
- Separate analysis pipelines for URL, pasted transcript, and upload input.
- Unknown or mixed-validity Evidence IDs in accepted claims.
- More than three first-screen takeaways or filler created to reach three.
- Direct `innerHTML` rendering of API/user content.
- API keys in source, browser responses, SQLite, logs, exports, or Git.
- Reading and rewriting historical JSON in the same operation.

## Required Patterns

- Every source enters `UnderstandingPipeline`.
- `decision_brief` is finalized after optional smart enhancement and evidence audit.
- The Evidence Store is created before any claim-producing analysis.
- DeepSeek output is merged fail-closed: missing audit status is not approval.
- Source hosts use exact allowlists; suffix checks such as `endswith("bilibili.com")` are forbidden.
- Uploads are streamed in bounded chunks and rejected once the configured byte limit is crossed.
- Static frontend data is decoded centrally before components receive it.
- Components construct safe DOM nodes and receive callbacks; they do not fetch APIs directly.
- Job reads return snapshots, and completed/failed jobs are bounded by TTL/count.

## Testing Requirements

Canonical full suite:

```bash
unset PYTHONPATH
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

Changes must add the narrowest relevant test first, then run the full suite. Required coverage areas:

- domain and Evidence invariants;
- application pipeline finalization order;
- source fallback and host allowlists;
- smart audit fail-closed behavior;
- old/new SQLite payload projection;
- API paths, status codes, error envelope and upload limits;
- dependency direction and thin facades;
- frontend module separation, safe DOM and CSS media-rule structure.

Also run:

```bash
.venv/Scripts/python.exe -m compileall -q videobrief
node --check <each JS module>
git diff --check
```

For cross-layer changes, exercise a real FastAPI job and inspect the browser console. Responsive changes require an exact `390 x 844` CSS-viewport overflow check.

## Review Checklist

- Does any dependency point outward from domain/application?
- Do all accepted claims reference known Evidence IDs?
- Is `decision_brief` based on the final audited Brief?
- Are old API paths, JSON fields, root imports and port 12000 still compatible?
- Can all observed history generations be read without mutation?
- Does an unavailable DeepSeek provider safely fall back or return the correct error for the selected mode?
- Do frontend components avoid direct network and unsafe HTML rendering?
- Are desktop and mobile layouts free of overflow and console errors?
- Are new runtime dependencies necessary for current product value?
