# VideoBrief Architecture Redesign

## 1. Architecture Style

采用**模块化单体 + Ports and Adapters**，而不是微服务。

理由：

- 产品是本地单机应用，FastAPI、SQLite、Whisper 和静态前端共享同一生命周期；拆成微服务只会增加部署、端口和故障面。
- 当前真正的问题是职责和依赖方向混乱，不是进程数量不足。
- Ports 只用于确实存在替换需求的边界：来源、转写、分析器、Brief 仓储、任务仓储。纯文本处理和决策摘要保持普通纯函数，避免过度抽象。

### Dependency Rule

```text
web assets ────────> HTTP API DTO
                         │
api routes ─────────> application services ─────────> domain models
                         │        │
                         │        └──────────────> ports (Protocols)
                         │                              ▲
                         └──────────────────────────────┤
                                                infrastructure adapters
```

- `domain` 不导入 FastAPI、requests、SQLite、Whisper 或浏览器概念。
- `application` 只依赖 `domain` 与 `ports`。
- `infrastructure` 实现 ports，可依赖 requests、SQLite、yt-dlp、Whisper 和 DeepSeek。
- `api` 负责装配依赖、HTTP DTO、异常映射和静态资源。
- 根目录旧模块只做兼容转发，不再拥有业务逻辑。

## 2. Target Directory Structure

```text
VideoBrief-MVP/
├── videobrief/
│   ├── __init__.py
│   ├── config.py
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── errors.py
│   ├── application/
│   │   ├── __init__.py
│   │   ├── ports.py
│   │   ├── pipeline.py
│   │   ├── decision.py
│   │   ├── question_answering.py
│   │   └── compatibility.py
│   ├── infrastructure/
│   │   ├── sources/
│   │   │   ├── registry.py
│   │   │   ├── pasted.py
│   │   │   ├── youtube.py
│   │   │   ├── bilibili.py
│   │   │   └── upload.py
│   │   ├── transcription/
│   │   │   └── whisper.py
│   │   ├── analysis/
│   │   │   ├── semantic.py
│   │   │   └── deepseek.py
│   │   ├── persistence/
│   │   │   └── sqlite.py
│   │   └── jobs/
│   │       └── memory.py
│   ├── api/
│   │   ├── app.py
│   │   ├── dependencies.py
│   │   ├── schemas.py
│   │   └── routes/
│   │       ├── jobs.py
│   │       ├── briefs.py
│   │       └── system.py
│   └── web/
│       ├── index.html
│       └── assets/
│           ├── css/app.css
│           └── js/
│               ├── app.js
│               ├── api.js
│               ├── state.js
│               ├── dom.js
│               ├── export.js
│               └── components/
│                   ├── decision.js
│                   ├── structure.js
│                   ├── evidence.js
│                   ├── chapters.js
│                   └── tools.js
├── videobrief_server.py       # compatibility composition entry
├── videobrief_service.py      # compatibility exports
├── videobrief_agent.py        # compatibility exports
├── videobrief_bilibili.py     # compatibility exports
└── tests/
    ├── unit/
    ├── integration/
    ├── contract/
    └── browser/
```

目录按**变化原因**而不是文件类型拆分。实现过程中若某个目录只有一个很小的使用者，不继续拆成更多抽象层。

## 3. Domain Contract

新生成和已规范化的内部领域模型使用 Pydantic v2，因为项目已经依赖 Pydantic，且同一模型需要：

- 边界校验；
- 稳定 JSON 序列化；
- API Schema；
- 历史数据读取时的默认值和兼容升级。

严格模型绝不直接解析原始历史 JSON。历史数据先经过版本检测和兼容投影，再进入模型；对旧调用方，兼容门面统一返回 `model_dump(mode="json")`，现有 dict 合同不变。

### Core Models

```text
TranscriptRow
  time: str
  seconds: int
  end_seconds: int
  text: str

Evidence
  evidence_id: str
  time: str
  seconds: int
  end_seconds: int
  quote: str
  source: str

Insight
  title: str
  detail: str
  evidence_ids: list[str]
  claim_type: video_explicit | context_summary | system_inference
  audit_status: supported | partial | local
  confidence: high | medium | low

DecisionBrief
  question: str
  answer: str
  takeaways: list[Insight]  # max_length=3
  value: str
  watch_verdict: required | recommended | not_required
  watch_reason: str
  watch_seconds: int
  limitation: str

Brief
  schema_version: int
  title, summary, source, url
  content_type
  evidence_store
  chapters
  key_insights
  content_model
  must_watch_segments
  decision_brief
  metrics
  agent
```

### Invariants

1. Evidence ID 只由字幕规范化阶段分配，按原始顺序稳定生成 `E0001...`。
2. 所有 `evidence_ids` 必须存在于同一个 Brief 的 Evidence Store。
3. 智能分析不能改写 `evidence_store`、原始时间或必看片段。
4. `decision_brief.takeaways` 最多三条，不能复述 `answer`，不能使用开场介绍填充。
5. 派生字段可在历史读取时重建，事实字段不得猜测或覆盖。

## 4. Application Pipeline

### Command

`AnalyseCommand` 统一描述四类输入：

```text
url | transcript | upload_path
analysis_mode: auto | fast | smart
whisper_model: tiny | small | medium
original_filename
```

入口校验保证三种输入载荷中恰有一个有效来源。HTTP DTO 到 Command 的转换只发生在 API 层。

### Stages

```text
QUEUED
  → ACQUIRING      解析来源、获取字幕或准备上传文件
  → TRANSCRIBING   仅当需要 Whisper
  → NORMALIZING    简繁转换、时间规范化、Evidence ID
  → STRUCTURING    本地确定性分析和类型原生结构
  → ENHANCING      可选 DeepSeek 第一轮理解
  → AUDITING       可选 DeepSeek 第二轮证据审计
  → FINALIZING     decision_brief、metrics、schema_version
  → PERSISTING     保存 Brief
  → COMPLETED
```

`UnderstandingPipeline.run(command, progress_callback)` 返回领域 `Brief`。它不认识 FastAPI、后台线程或 SQLite。应用层 `JobRunner` 负责把阶段事件写入任务仓储并在成功后调用 Brief 仓储。

文本和上传任务只在 Source Adapter 不同；后续完整流水线相同。

`FINALIZING` 是所有派生字段的唯一写入点。智能增强后必须统一重建 `decision_brief`、metrics 和 fingerprint 投影；这同时修复当前上传路径没有重新生成智能 `decision_brief` 的差异。

## 5. Ports and Adapters

### Ports

- `SourceAdapter.supports(command) -> bool`
- `SourceAdapter.acquire(command, progress) -> AcquisitionResult`
- `Transcriber.transcribe(path, model_size) -> list[TranscriptRow]`
- `LocalAnalyzer.analyse(evidence_store) -> BriefDraft`
- `SmartAnalyzer.enhance(rows, draft, mode) -> BriefDraft`
- `BriefRepository.save/get/list`
- `JobRepository.create/update/get/prune`

### Source Registry

`SourceRegistry` 按明确优先级选择适配器：

1. pasted transcript；
2. upload path；
3. Bilibili URL；
4. YouTube URL；
5. 不支持的 URL 抛出 `UnsupportedSourceError`。

不再把未知字符串默认为 `local`，避免错误进入后续流程。

来源层同时修复已审计缺陷：验证真实 yt-dlp 可执行文件后再调用；YouTube CLI 失败仍能进入 transcript API 回退；Bilibili 使用精确域名白名单、先解析 `b23.tv` 短链，并区分 BV/AV 参数。

### Whisper

`WhisperTranscriber` 独占模型缓存与锁。Bilibili 音频回退也依赖同一个 Transcriber port，不再反向导入 `videobrief_service.get_whisper_model`。

### DeepSeek

`DeepSeekAnalyzer` 拆为四个内部协作者但不拆进程：

- `DeepSeekClient`：配置、HTTP、超时和 JSON 解析；
- `AnalysisPrompt`：第一轮结构化理解；
- `AuditPrompt`：只发送实际引用证据；
- `EvidenceMergePolicy`：白名单角色、未知 ID 拒绝、partial 收窄、最多三条。

审计策略必须 fail-closed：缺失 `summary_status` 不得默认 supported；`partial` 没有有效收窄文本时回退本地表述。标题和章节重写要么进入第二轮审计，要么在本轮保持本地结果。

`fast` 永不调用客户端；`smart` 不可用时返回明确错误；`auto` 记录降级元数据后使用本地结果。

## 6. Persistence and History Compatibility

### SQLite

保留现有 `briefs` 表，避免破坏性迁移：

```sql
briefs(id, created_at, title, source, url, result_json)
```

`SQLiteBriefRepository` 每次使用独立连接，并配置：

```text
PRAGMA journal_mode=WAL
PRAGMA busy_timeout=5000
```

### Schema Version

新结果顶层写入 `schema_version`。`BriefCompatibility.upgrade(raw)` 在读取历史时执行：

1. 按字段结构识别 `legacy-no-store`、`evidence-store-v1`、`typed-v2`、`decision-v3`，不按日期猜测；
2. 保留现代记录原始 Evidence Store、ID、时间和原文；
3. 对没有 Evidence Store 的旧记录，按章节序号、证据序号、时间和 quote hash 确定性生成只读投影 ID，并标记 `source=legacy_chapter_projection`；
4. 补缺失默认字段，并安全处理 `points=[]`；
5. 若旧记录缺 `decision_brief`，仅从现有 summary/key_insights/content_model 重新派生；
6. 不修改数据库中的旧 JSON，除非未来提供显式迁移命令。

本机数据库已观察到四代 payload；任何 Pydantic 严格校验都只能作用于兼容投影，不能直接作用于原始行。

### Jobs

首版任务仍为进程内：

- 线程安全；
- 每次更新返回快照，避免外部持有内部 dict；
- 最多保留 100 个终态任务或 24 小时；
- 服务重启后任务丢失是公开行为；Brief 历史不丢失。

## 7. API Design

### Compatibility

保持现有路径和主要成功响应：

- `POST /api/jobs`
- `POST /api/jobs/upload`
- `GET /api/jobs/{job_id}`
- `GET /api/history`
- `GET /api/history/{brief_id}`
- `POST /api/briefs/{brief_id}/ask`
- `GET /api/agent/status`
- `GET /api/health`
- `POST /api/analyse`

### Error Contract

新错误同时保留 FastAPI 兼容的 `detail`，并提供机器可读字段：

```json
{
  "detail": "无法获取该视频字幕。",
  "error": {
    "code": "SOURCE_UNAVAILABLE",
    "message": "无法获取该视频字幕。",
    "retryable": true
  }
}
```

路由只捕获应用异常并交给全局异常处理器；后台任务写入同样的 error code/message，不泄露堆栈或密钥。

### Upload

上传改为分块流式写入临时文件并同步累计大小，不再一次性把最多 500 MB 读入内存。异常与取消路径都删除临时文件。

## 8. Frontend Architecture

采用**无构建 ES Modules**。原因：

- 本地产品不需要 Node 运行时或构建步骤；
- 浏览器原生模块已经足以支撑当前组件规模；
- 通过 JSDoc typedef、中央 decoder 和 reducer 获得大部分类型与状态收益；
- 若未来复杂度超过阈值，可在 API/领域合同稳定后迁移 Vite，而不影响后端。

### Data Flow

```text
DOM event → action → reducer/store → effect(api.js) → action → state → render
```

唯一 Store 状态：

```text
view: create | processing | result | error
job
brief
history
question
searchQuery
agentStatus
```

API 响应只在 `api.js` 中解码/规范化；组件不直接解析未知 payload。

### Components

- `decision.js`：首屏唯一权威摘要；
- `structure.js`：五类类型原生结构，逐项折叠；
- `evidence.js`：Evidence ID、原文和原片跳转；
- `chapters.js`：完整章节与搜索；
- `tools.js`：问答、历史和导出工具。

组件返回 DOM 节点，不使用用户内容拼接 `innerHTML`。只有导出 HTML 使用集中 `escapeHtml`。

### Progressive Disclosure

- Level 1：核心答案、1–3 条关键结论、观看建议、限制、时间节省；
- Level 2：唯一类型原生结构；
- Level 3：证据、完整章节、审计元数据和工具。

桌面维持内容主栏 + 轻量导航/工具；390px 下主内容单列，工具移至正文后，顶部仅保留主操作。

## 9. Migration Strategy

采用 Strangler Fig 渐进替换：

1. 建立新包、领域模型和兼容序列化，不改变运行路径。
2. 先迁移纯函数：字幕解析、时间、Evidence、decision_brief、问答。
3. 迁移本地语义分析和五类内容模型。
4. 迁移来源与 Whisper，消除 Bilibili 反向导入。
5. 迁移 DeepSeek 客户端、Prompt、审计和合并。
6. 迁移 SQLite 仓储、任务仓储、统一 Pipeline 和 JobRunner。
7. 将 FastAPI 路由切到新应用层；根入口继续导出同一个 `app`。
8. 拆分前端静态模块并切换静态资源服务。
9. 迁移测试目录和文档；确认无调用后删除旧实现体，仅保留门面。

每一步都要求旧测试、该切片新测试和真实启动检查通过。切换点通过兼容门面或单个 composition root 控制，回滚只需恢复上一实现绑定，不回滚数据库。

## 10. Testing Strategy

### Unit

- 领域模型与 Evidence invariant；
- 字幕规范化和 stable ID；
- decision_brief 去重、少于三条和限制；
- 内容类型结构；
- Prompt、审计和 merge policy；
- repository/job store。

### Integration

- 四种 Source Adapter 使用 fixture/fake transport；
- Pipeline 使用 fake adapter/analyzer/repository 验证阶段顺序；
- SQLite 旧 JSON 读取兼容；
- FastAPI TestClient 验证成功/错误合同和流式上传限制。

### Contract

- 根目录旧模块导入和函数签名；
- 现有 API 路径和关键字段；
- 前端 API decoder 与后端 Brief fixture；
- 历史记录 round-trip。

### Browser

- 桌面：创建、进度、结果、证据、问答、历史、导出；
- 390×844：无横向溢出、首屏顺序正确、工具可访问；
- 控制台无 JS error。

## 11. Rollback and Operational Safety

- 开始前保留当前 37 项测试绿灯和可运行服务作为基线。
- 不更改 `.env`、API Key 或数据库路径。
- 不对现有 SQLite 执行破坏性 DDL。
- 每个切片只在合同测试通过后切换 composition binding。
- 若来源或智能层迁移失败，恢复门面导入；历史数据无需恢复。
- 若前端模块化失败，根路由可临时继续服务旧 `videobrief-app.html`。

## 12. Trade-offs

- **选择 ES Modules 而非 React/Vite**：放弃编译期类型和成熟组件生态，换取零构建、低运行复杂度和可直接调试。
- **保留 dict 兼容门面**：短期存在一次 model↔dict 转换，换取测试和第三方脚本不被一次性打断。
- **任务不持久化**：服务重启会丢在途任务，但避免为了本地 MVP 引入复杂恢复机制；完成的 Brief 仍持久化。
- **SQLite JSON 整体存储**：查询能力有限，但目前主要访问模式是保存/列出/按 ID 读取，拆表收益不足以证明复杂度。
