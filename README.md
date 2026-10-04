# VideoBrief V4

把 Bilibili、YouTube、本地视频或字幕转换成可读、可搜、可验证的简体中文知识页。

## 启动

```bash
cd <????>/VideoBrief-MVP
unset PYTHONPATH
.venv/Scripts/python.exe videobrief_server.py
```

打开：http://127.0.0.1:12000/

如需更换端口：

```bash
VIDEOBRIEF_PORT=9000 .venv/Scripts/python.exe videobrief_server.py
```

## 测试

```bash
unset PYTHONPATH
.venv/Scripts/python.exe -m unittest discover -s tests -v
```

## V4 能力

- Bilibili / YouTube / 粘贴字幕 / 本地音视频输入
- FastAPI 后端与后台任务轮询
- 下载、转写、结构化阶段进度
- Whisper tiny / small / medium 三档及进程内模型缓存
- 全链路繁体转简体
- 视频知识指纹：内容类型、信息密度和原视频时长
- 结论优先理解页：直接答案、最多三条非重复关键结论、观看建议和内容边界
- 每条关键结论绑定 Evidence ID；完整类型结构与章节默认折叠、按需展开
- 自动识别依赖画面或实际操作的必看片段，并计算真实阅读节省
- 带时间戳和字幕证据的视频内问答；未找到时明确说明
- 章节时间范围、字幕证据和原片精确跳转
- SQLite 历史记录
- 安全 DOM 渲染（用户内容不直接写入 innerHTML）
- 独立 HTML 下载

## 代码架构

V4 采用**模块化单体 + Ports and Adapters**。仍然只需一条命令启动，不引入微服务、Redis 或 Node 构建链；但领域、用例、来源、智能分析、持久化、Web API 和前端组件已有明确边界。

```text
videobrief/
├── domain/                  # Evidence、Brief、错误与内容类型合同
├── application/             # 统一理解流水线、命令、端口、问答和历史兼容投影
├── infrastructure/
│   ├── sources/             # YouTube、Bilibili、上传、粘贴字幕
│   ├── transcription/       # faster-whisper
│   ├── analysis/            # 本地 semantic-chunking、DeepSeek、证据审计
│   ├── persistence/         # SQLite Repository
│   └── jobs/                # 有界线程安全任务状态
├── api/                     # FastAPI 工厂、DTO、路由与统一错误映射
├── web/                     # 无构建 ES Modules、CSS 和纯 DOM 组件
└── bootstrap.py             # 唯一具体装配入口
```

依赖方向为 `API / Infrastructure → Application → Domain`。`videobrief_service.py`、`videobrief_agent.py`、`videobrief_bilibili.py` 和 `videobrief_server.py` 只保留兼容门面，旧导入、API 路径、默认端口和启动命令不变。

四类输入现在全部进入同一个 `UnderstandingPipeline`：

```text
获取来源 → 规范化 → Evidence Store → 本地结构化
        → 可选智能增强 → 独立证据审计 → decision_brief → SQLite
```

新结果写入 `schema_version: 4`。SQLite 仍保留原始 Brief JSON；读取旧历史时只创建确定性的兼容投影，不覆盖数据库中的原始 payload，也不会改写已有 Evidence ID。前端通过中央 decoder 兼容缺少 `decision_brief` 的旧记录。

## 产品边界

VideoBrief 专注于减少理解视频所需的时间，不提供掌握度、测验、间隔复习或学习打卡。教程里的操作步骤属于原视频内容，可以提取；系统不会额外给用户布置学习任务。

## DeepSeek 智能分析

智能分析使用 OpenAI-compatible 接口，默认配置为：

```text
Provider: deepseek
Base URL: https://api.deepseek.com
Model: deepseek-chat
```

不要把 API Key 写入项目文件或聊天。启动服务前在本机终端设置：

```bash
export VIDEOBRIEF_LLM_API_KEY='你的 DeepSeek API Key'
export VIDEOBRIEF_LLM_PROVIDER='deepseek'
export VIDEOBRIEF_LLM_BASE_URL='https://api.deepseek.com'
export VIDEOBRIEF_LLM_MODEL='deepseek-chat'
.venv/Scripts/python.exe videobrief_server.py
```

若使用 Windows 的 `setx` 持久化环境变量，需要重新打开终端后再启动服务。前端会通过 `/api/agent/status` 显示连接状态，但接口和日志永远不会返回 API Key。

三种分析模式：

- `auto`：有 Key 时使用 DeepSeek；调用失败或未配置时自动退回本地规则引擎。
- `fast`：始终使用本地规则引擎，不产生 API 费用。
- `smart`：强制使用 DeepSeek；未配置或调用失败时明确报错。

智能体采用两阶段闭环：

```text
第一轮：识别核心问题、直接答案、最多三条高价值观点和类型原生结构
第二轮：独立审计每条观点与字幕原文，判定支持、部分支持或拒绝
```

结果页首先生成 `decision_brief`：核心问题、直接答案、最多三条带证据且互不重复的关键结论、观看建议、价值和内容边界。删除任一条不会影响理解的内容不会为了填满版面而进入首屏；信息量低的视频允许只保留一到两条。完整类型结构和章节默认折叠，Evidence ID 作为按需核验脚注，而不是与正文争夺视觉层级。

每条原始字幕会被写入证据库并获得稳定 ID（如 `E0001`）。智能体必须引用真实 `evidence_ids`，不能只引用宽泛章节时间；任意未知 ID 都会使整条观点被丢弃。页面中的直接答案、关键结论、类型结构、章节和问答均可展开显示证据 ID、精确时间及原文，并跳转到对应时间。

智能分析会先判断视频类型，再使用类型专属内容模型；本地极速模式也会生成确定性的降级结构：

| 类型 | 原生结构 |
|---|---|
| 教程 | 目标、前置条件、操作步骤、参数、避坑、完成结果 |
| 访谈 | 核心议题、人物立场、论据、分歧、关键原话、未决问题 |
| 评测 | 评测对象、比较标准、优点、缺点、取舍、最终判断 |
| 知识讲解 | 核心问题、关键概念、关系、案例、结论、适用边界 |
| 观点评论 | 主题、事实、观点、推断、争议、不确定性 |

类型化条目和核心观点使用同一套 `evidence_ids` 与第二轮证据审计。错误类型角色、未知证据 ID、语义不支持的内容都会被过滤，页面和导出 HTML 均保留精确证据。如果智能类型结构通过审计的条目过少，系统不会让残缺的 AI 结构覆盖完整结果，而会保留本地确定性结构并在页面明确标记降级。

智能体只重构标题、核心结论、最多三条关键观点、类型内容模型和章节标题。`decision_brief` 在安全合并后再次生成，确保首屏使用最终审计结果。字幕证据、必看片段和历史记录仍由本地流程控制。

## 内容引擎说明

当前始终保留本地规则引擎 `semantic-chunking` 作为安全降级路径，不冒充大模型分析。知识页会明确显示实际使用的引擎，并为章节保留字幕证据。
