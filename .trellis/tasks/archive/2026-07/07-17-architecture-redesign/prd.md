# VideoBrief 整体架构重构

## Goal

把当前由四个大型 Python 文件和一个内联 HTML 文件组成的 VideoBrief，重构为职责清晰、可独立测试、可渐进迁移的产品架构；在不破坏现有输入方式、历史数据、证据链和本地启动体验的前提下，持续降低“形成准确理解所需的时间”。

## Background

- 当前核心链路已经可用：Bilibili、YouTube、粘贴字幕和本地音视频均可生成简体中文知识页。
- `videobrief_service.py` 同时承担来源识别、字幕解析、YouTube/Bilibili 获取、Whisper、语义分块、内容分类、结构生成、决策摘要和问答，职责高度耦合。
- `videobrief_server.py` 同时承担配置加载、FastAPI 路由、请求校验、任务状态、线程心跳、SQLite 建表/读写和静态文件服务。
- `videobrief_agent.py` 同时承担 Provider 配置、Prompt、HTTP 客户端、第一轮分析、第二轮审计和安全合并。
- `videobrief-app.html` 内联全部 HTML、CSS、状态、API 调用、渲染、导出、历史、搜索和问答逻辑。
- 现有稳定外部合同包括 `/api/jobs`、`/api/jobs/upload`、`/api/jobs/{id}`、`/api/history`、`/api/history/{id}`、`/api/briefs/{id}/ask`、`/api/agent/status`、`/api/health` 和兼容接口 `/api/analyse`。
- 当前 SQLite `briefs.result_json` 保存完整结果；历史记录必须继续可读。
- 结果页已经采用“核心答案 → 最多三条高价值结论 → 观看建议 → 按需展开证据”的产品结构。

## Requirements

### R1. 单一可观察理解流水线

- 所有输入方式必须进入同一条应用流水线：输入解析 → 来源获取/转写 → 字幕规范化 → Evidence Store → 本地结构 → 可选智能增强 → 证据审计 → `decision_brief` → 持久化。
- 文本任务与上传任务不得分别维护两套结果组装逻辑。
- 流水线阶段必须产生可供任务进度展示的稳定阶段事件。

### R2. 明确的领域合同

- 为字幕行、证据、章节、关键结论、类型原生结构、观看片段、决策摘要、完整 Brief、任务状态定义统一模型。
- Evidence ID、精确秒数、原始引用和来源是不可变事实层；智能模型不得改写。
- `decision_brief` 是首屏唯一权威理解摘要，最多三条非重复、带证据的关键结论；信息量低时允许少于三条。

### R3. 可替换来源与转写适配器

- 粘贴字幕、YouTube、Bilibili、本地上传必须作为独立适配器实现统一端口。
- Whisper 模型缓存与音视频转写从内容结构化逻辑中分离。
- YouTube 与 Bilibili 的字幕优先、音频回退策略必须保留，错误信息必须可行动。

### R4. 本地分析与智能分析解耦

- 本地确定性分析必须始终可用，并保持 `semantic-chunking` 披露。
- DeepSeek 使用独立 Provider 客户端、分析 Prompt、审计 Prompt 和安全合并策略。
- `auto`、`fast`、`smart` 三种模式及降级语义保持不变。
- API Key 只从环境变量或 `.env` 读取，不进入前端、数据库、日志或 Git。

### R5. API、任务与持久化分层

- FastAPI 路由只处理 HTTP 校验、状态码和 DTO 转换，不直接操作 SQLite、线程字典或领域算法。
- 任务仓储和 Brief 仓储通过明确接口访问；首版仍使用进程内任务仓储与 SQLite Brief 仓储。
- 现有 API 路径和主要响应字段保持兼容；新增版本字段用于未来迁移。
- 历史 `result_json` 在读取时补齐当前派生字段，不要求破坏性数据库迁移。

### R6. 结论优先前端架构

- 前端拆分为静态入口、样式、API 客户端、状态管理、页面编排和可复用渲染组件。
- 首屏只突出核心答案、最多三条关键结论、观看建议、边界和真实节省。
- 完整类型结构、章节和 Evidence ID 默认折叠；问答、搜索、历史和导出继续可用。
- 不重新引入独立“核心观点”“内容地图”等重复模块。
- 用户提供的内容必须继续使用 DOM `textContent` 等安全方式渲染。

### R7. 兼容迁移与回滚

- 根目录现有 `videobrief_server.py`、`videobrief_service.py`、`videobrief_agent.py`、`videobrief_bilibili.py` 暂时保留为兼容门面，内部委托新包。
- 每个迁移切片完成后均可独立运行现有测试和本地服务；不得用一次性 Big Bang 替换造成长时间不可用。
- 旧实现仅在所有调用方迁移和合同测试通过后删除。

### R8. 测试与质量

- 新领域模型、流水线、来源端口、仓储、任务阶段、智能安全合并和前端模块均须有专项测试。
- 现有回归测试继续通过；兼容门面需要合同测试。
- 至少完成一次真实本地 API 任务、一次桌面浏览器验收和一次精确移动视口验收。
- 不得把静态 HTML 检查冒充真实浏览器验收。

### R9. 产品边界与语言

- 所有界面、错误信息和生成内容保持简体中文。
- 产品只帮助用户快速、准确理解视频，不添加测验、掌握度、间隔复习、打卡或课程管理。
- 任何新增运行时依赖都必须直接改善当前产品能力，并保留单命令本地启动体验。

## Acceptance Criteria

- [ ] AC1：用户可在 `http://127.0.0.1:12000/` 完成粘贴字幕、链接和本地上传三类主路径。
- [ ] AC2：所有输入通过同一应用流水线，并产出一致的 Brief 领域合同。
- [ ] AC3：Evidence Store 中每条原始字幕具有稳定 ID、时间、秒数和原文；关键结论全部可追溯。
- [ ] AC4：`decision_brief` 最多三条非重复关键结论，不使用开场介绍或核心答案复述填充版面。
- [ ] AC5：`auto`、`fast`、`smart` 行为与安全降级保持兼容，智能分析仍执行独立证据审计。
- [ ] AC6：现有 API 路径和 SQLite 历史数据可继续读取；旧记录能在读取时补齐当前派生字段。
- [ ] AC7：FastAPI 路由不直接包含 SQLite SQL、领域分析或来源抓取逻辑。
- [ ] AC8：前端不再是单一内联文件；API、状态、组件和样式可独立测试与维护。
- [ ] AC9：完整自动化套件通过，新增架构合同测试通过，真实本地 API 闭环通过。
- [ ] AC10：桌面和真实 390px 移动视口无横向溢出、重叠或关键内容截断。
- [ ] AC11：DeepSeek Key 不出现在响应、数据库、日志、静态资源和版本控制中。
- [ ] AC12：README、架构文档、启动方式和故障排查与新结构一致。

## Constraints

- 固定项目路径：`D:\workspace\VideoBrief-MVP`。
- Windows/Git Bash 下运行 Python 前使用 `unset PYTHONPATH`。
- 默认端口保持 `12000`。
- 首版保持单进程本地应用、SQLite、FastAPI、faster-whisper 和 OpenAI-compatible DeepSeek。
- 迁移期间必须保留当前可运行版本和回滚点。

## Out of Scope

- 多用户账户、权限系统和云端部署。
- 视频学习管理、测验、复习和掌握度功能。
- 当前重构中引入完整画面理解、OCR 或关键帧模型；这些只保留扩展端口。

## Product and Architecture Decisions

- 前端采用无构建静态 ES Modules：不增加 Node 运行依赖，通过中央 API decoder、reducer/store 和独立组件提高可维护性。
- 重构采用渐进式兼容迁移，不做一次性 Big Bang 替换。
- SQLite 继续整体保存 Brief JSON，并在 JSON 内加入 `schema_version`；旧数据在读取时升级派生字段。
- 保持模块化单体，不引入微服务、远程缓存或消息队列。