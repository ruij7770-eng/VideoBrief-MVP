# Database Guidelines

> SQLite persistence and history compatibility conventions for VideoBrief.

---

## Storage Model

VideoBrief uses SQLite through `SQLiteBriefRepository`. The `briefs` table retains the original six-column shape and stores the complete Brief JSON in `result_json`.

New JSON payloads contain `schema_version: 4`. The database table is not rebuilt merely to version JSON.

## Query Rules

- SQL is allowed only in `videobrief/infrastructure/persistence/`.
- Always name insert columns explicitly:

```sql
INSERT INTO briefs (id, created_at, title, source, url, result_json)
VALUES (?, ?, ?, ?, ?, ?)
```

- Never use `INSERT INTO briefs VALUES (...)`; adding a column would break every writer.
- Use one short-lived connection per repository operation.
- Configure `busy_timeout=5000` and WAL mode for the local concurrent workload.
- Parameterize every value. Never format user input into SQL.

## Historical JSON

Observed history contains four generations: `legacy-no-store`, `evidence-store-v1`, `typed-v2`, and `decision-v3`.

Read flow:

```text
stored JSON -> detect generation -> deterministic read projection -> current API
```

Rules:

- Never pass raw legacy JSON directly to strict current Pydantic models.
- Never overwrite a historical payload as a side effect of reading it.
- Preserve existing Evidence IDs byte-for-byte.
- For records without Evidence IDs, generate deterministic `L...` IDs only in the read projection.
- Projection must be idempotent: normalizing the same payload twice returns equal results.
- Ask/export/history endpoints consume the projected form; `get_raw()` remains available for audits.

## Migration Safety

Before any future DDL or batch rewrite:

1. create a SQLite backup with the SQLite backup API;
2. verify `PRAGMA integrity_check = ok`;
3. run compatibility tests across every record;
4. prove the migration is idempotent;
5. document and test restore steps.

Do not test migrations against the user's live `videobrief.db`; use a temporary database or backup snapshot.

## Common Mistakes

- Applying a strict new schema directly to legacy rows.
- Regenerating modern `E0001...` IDs during reads.
- Adding a table column before replacing positional inserts.
- Opening one global SQLite connection across worker threads.
- Treating a successful JSON decode as evidence that Evidence references are valid.
