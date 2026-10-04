# Directory Structure

> The actual backend organization used by VideoBrief V4.

---

## Architecture

VideoBrief is a modular monolith using Ports and Adapters. Dependencies point inward:

```text
API / infrastructure -> application -> domain
```

The domain and application packages must not import FastAPI, SQLite, Requests, source adapters, or LLM adapters. Concrete implementations are assembled only in `videobrief/bootstrap.py` and `videobrief/api/dependencies.py`.

## Directory Layout

```text
videobrief/
├── domain/                  # Models, error taxonomy, content taxonomy
├── application/             # Commands, ports, pipeline, projections, QA, jobs
├── infrastructure/
│   ├── sources/             # YouTube, Bilibili, upload, pasted transcript
│   ├── transcription/       # faster-whisper adapter
│   ├── analysis/            # Local analysis, DeepSeek, prompts, audit merge
│   ├── persistence/         # SQLite repository
│   └── jobs/                # In-memory job repository
├── api/                     # App factory, DTOs, route modules, error mapping
├── web/                     # Static no-build ES Modules and CSS
├── bootstrap.py             # Concrete pipeline assembly
└── config.py                # Runtime settings
```

## Module Rules

- Pure Evidence and Brief invariants belong in `domain/`.
- Use-case orchestration belongs in `application/` and depends on protocols from `application/ports.py`.
- External I/O belongs in `infrastructure/`.
- FastAPI routes only decode requests, invoke application services, and encode responses.
- `videobrief_service.py`, `videobrief_agent.py`, `videobrief_bilibili.py`, and `videobrief_server.py` are compatibility facades. Never add new business logic there.
- All input types must enter `UnderstandingPipeline`; do not create source-specific analysis flows.

## Naming

- Domain and application names describe product concepts (`Evidence`, `Brief`, `AnalyseCommand`).
- Adapters describe the external technology (`YouTubeSource`, `DeepSeekAnalyzer`, `SQLiteBriefRepository`).
- User-facing messages and UI text use Simplified Chinese; code and project specifications use English.

## Reference Implementations

- Pipeline: `videobrief/application/pipeline.py`
- Composition: `videobrief/bootstrap.py`
- Source selection: `videobrief/infrastructure/sources/registry.py`
- API factory: `videobrief/api/app.py`
