# 剪映 AI 全自动剪辑插件 — 系统架构设计文档

## 一、系统架构总览

### 1.1 设计哲学

本系统采用 **"混合驱动 + 插件化 AI + 流水线编排"** 三位一体的架构理念：

- **混合驱动层**：草稿 JSON 直接操作（快速、无头）与 GUI 自动化（可触发导出）互补，通过统一适配器屏蔽底层差异
- **插件化 AI 层**：所有 AI 能力（语音识别、场景检测、高光提取、文案生成、配乐推荐等）以插件形式注册，通过统一接口调用，支持多 Provider 热切换
- **流水线编排层**：将完整的视频编辑流程抽象为可编排的 Pipeline，每个阶段（Ingest → Analyze → Edit → Review → Export）由可组合的 Stage 组成

### 1.2 组件架构图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户界面层 (UI Layer)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │
│  │   CLI 模式    │  │  Web UI 模式  │  │  MCP Server 模式 (Agent) │  │
│  │   (Typer)    │  │ (FastAPI+Vue) │  │  (MCP Protocol/JSON-RPC) │  │
│  └──────┬───────┘  └──────┬───────┘  └────────────┬─────────────┘  │
└─────────┼──────────────────┼──────────────────────┼────────────────┘
          │                  │                      │
          ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     编排引擎层 (Orchestrator)                        │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Pipeline Engine: Ingest → Analyze → Edit → Review → Export │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌────────┐ ┌────────┐ │   │
│  │  │ Ingest  │→│ Analyze │→│  Edit   │→│ Review │→│ Export │ │   │
│  │  │ Stage   │ │ Stage   │ │ Stage   │ │ Stage  │ │ Stage  │ │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └────────┘ └────────┘ │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌──────────────────┐  ┌──────────────────────────────────────┐   │
│  │  Task Scheduler  │  │  Event Bus (状态通知 / 进度回调)       │   │
│  └──────────────────┘  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
          │                  │                      │
          ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       AI 服务抽象层 (AI Layer)                       │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  AI Service Registry (插件注册中心)                          │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │   │
│  │  │ ASR 插件  │ │ 场景检测  │ │ 高光提取  │ │ 文案/脚本生成  │  │   │
│  │  │(Whisper等)│ │(PyScene) │ │(LLM/CV)  │ │(GPT/Qwen等)  │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────────────┐  │   │
│  │  │ BGM 推荐  │ │ 字幕翻译  │ │ 封面生成  │ │ 自定义插件... │  │   │
│  │  │(音频分析) │ │(LLM+NLP) │ │(DALL-E等)│ │  (扩展槽)     │  │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └───────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  Provider Adapter (多供应商适配)                              │   │
│  │  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────┐ │   │
│  │  │ OpenAI │ │ 通义千问│ │ 文心一言│ │ 本地LLM│ │ Custom   │ │   │
│  │  │(GPT-4o)│ │(Qwen)  │ │(ERNIE) │ │(Ollama)│ │ Provider │ │   │
│  │  └────────┘ └────────┘ └────────┘ └────────┘ └──────────┘ │   │
│  └─────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
          │                  │                      │
          ▼                  ▼                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    剪映驱动层 (JianYing Driver)                      │
│  ┌────────────────────┐  ┌────────────────────────────────────┐    │
│  │  Draft Engine       │  │  GUI Controller                   │    │
│  │  ┌──────────────┐  │  │  ┌────────────────────────────┐   │    │
│  │  │ DraftReader  │  │  │  │ JianYingProcessManager     │   │    │
│  │  │ DraftWriter  │  │  │  │ UIElementFinder            │   │    │
│  │  │ DraftCrypto  │  │  │  │ ActionExecutor             │   │    │
│  │  │ (jy-draftc)  │  │  │  │ ExportTrigger              │   │    │
│  │  └──────────────┘  │  │  └────────────────────────────┘   │    │
│  │  ┌──────────────┐  │  │  ┌────────────────────────────┐   │    │
│  │  │ MaterialMgr  │  │  │  │ ScreenCapture (状态校验)    │   │    │
│  │  │ TrackBuilder │  │  │  │ WaitForCompletion          │   │    │
│  │  │ SegmentOps   │  │  │  └────────────────────────────┘   │    │
│  │  └──────────────┘  │  └────────────────────────────────────┘    │
│  └────────────────────┘                                            │
│  ┌────────────────────────────────────────────────────────────┐    │
│  │  Unified Driver Interface (统一驱动接口)                     │    │
│  │  open_project() | save_draft() | export_video() | ...      │    │
│  └────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      基础设施层 (Infrastructure)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐│
│  │ FFmpeg   │ │ 配置管理  │ │ 日志系统  │ │ 缓存管理  │ │ 资源监控  ││
│  │ Wrapper  │ │ (YAML)   │ │(structlog)│ │ (SQLite) │ │(CPU/GPU) ││
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

### 1.3 核心设计原则

| 原则 | 说明 |
|------|------|
| **驱动无关** | 上层业务逻辑不感知底层是 JSON 操作还是 GUI 自动化，通过 `DriverInterface` 抽象 |
| **AI 可插拔** | 每个 AI 能力是独立插件，通过 `AIPlugin` 基类注册，支持运行时热加载 |
| **Provider 可切换** | LLM/ASR/CV 等 Provider 通过统一适配器模式接入，配置文件切换，零代码改动 |
| **流水线可编排** | Pipeline 的每个 Stage 可独立运行、跳过、重排，支持条件分支和并行执行 |
| **版本兼容** | 自动检测剪映版本和草稿加密状态，透明处理加解密 |

---

## 二、技术背景：剪映草稿格式

### 2.1 核心文件

剪映项目存储在磁盘上的文件夹中，路径通常为：

```
%LOCALAPPDATA%\JianyingPro\User Data\Projects\com.lveditor.draft\<项目名>\
```

每个项目文件夹至少包含：

- `draft_content.json` — 主项目文件，包含所有编辑数据
- `draft_meta_info.json` — 元数据（项目名、时间戳、UUID）

### 2.2 draft_content.json 结构

| 字段 | 说明 |
|------|------|
| `id` | 项目唯一标识 |
| `name` | 项目名称 |
| `canvas_config` | 分辨率（宽/高）、帧率 |
| `duration` | 总时长，单位为**微秒** |
| `materials` | 所有素材数组（视频/音频/文本/特效/画布/字体等） |
| `tracks` | 时间线轨道数组（视频轨/音频轨/文本轨/特效轨） |

### 2.3 关键细节

- **时间单位**：微秒（1 秒 = 1,000,000 微秒）
- **UUID 引用**：`material_id` 将 track 中的 segment 关联到 materials 中的素材
- **加密**：剪映 v6.0+ 的 `draft_content.json` 使用 AES 加密，需通过 `jy-draftc` 工具解密

### 2.4 已有开源工具

| 项目 | 说明 |
|------|------|
| [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft) | Python 库，读写 draft_content.json（PyPI 可用） |
| [capcut-mate](https://github.com/Hommy-master/capcut-mate) | FastAPI + Electron + uiautomation 全自动化框架 |
| [jy-draftc](https://github.com/wenshui330/jy-draftc) | 剪映 v6.0+ 草稿加解密工具 |
| [cutcli](https://github.com/xuliang2024/cutcli-cookbook) | CLI 草稿生成工具 |
| [JianYing MCP Server](https://www.claudemarketplace.org/mcp/jianying-mcp) | AI Agent 通过 MCP 协议控制剪映 |

---

## 三、模块分解与项目结构

```
jy_auto_editor/
├── core/                    # 核心框架（不依赖任何 AI 或剪映特定逻辑）
│   ├── pipeline.py          # Pipeline 引擎：Stage 编排、DAG 执行
│   ├── plugin.py            # 插件基类与注册机制
│   ├── config.py            # 配置管理（YAML + 环境变量 + .env）
│   ├── events.py            # 事件总线（进度通知、状态变更）
│   ├── models.py            # 领域模型（VideoProject, Segment, Timeline 等）
│   └── exceptions.py        # 统一异常体系
│
├── drivers/                 # 剪映驱动层
│   ├── interface.py         # 统一驱动接口 (ABC)
│   ├── draft_engine/        # 草稿 JSON 操作引擎
│   │   ├── reader.py        # 读取 draft_content.json
│   │   ├── writer.py        # 写入/修改 draft_content.json
│   │   ├── crypto.py        # 加解密适配（集成 jy-draftc）
│   │   ├── materials.py     # 素材管理（视频/音频/文本素材 CRUD）
│   │   ├── tracks.py        # 轨道管理（增删改查、排序）
│   │   ├── segments.py      # 片段操作（分割、删除、移动、变速）
│   │   └── schema.py        # draft_content.json 的 Pydantic 模型
│   ├── gui_controller/      # GUI 自动化控制器
│   │   ├── process.py       # 剪映进程管理（启动/关闭/检测）
│   │   ├── finder.py        # UI 元素定位（基于 uiautomation）
│   │   ├── actions.py       # 操作执行器（点击/拖拽/快捷键）
│   │   ├── export.py        # 导出触发与监控
│   │   └── verifier.py      # 操作结果校验（截图对比/状态检查）
│   └── hybrid_driver.py     # 混合驱动：自动选择最优策略
│
├── ai/                      # AI 服务抽象层
│   ├── base.py              # AIPlugin 基类与接口定义
│   ├── registry.py          # 插件注册中心
│   ├── providers/           # Provider 适配器
│   │   ├── base_provider.py # Provider 抽象基类
│   │   ├── openai_provider.py
│   │   ├── qwen_provider.py     # 通义千问
│   │   ├── ernie_provider.py    # 文心一言
│   │   ├── ollama_provider.py   # 本地模型
│   │   └── custom_provider.py   # 用户自定义 Provider
│   └── plugins/             # AI 功能插件
│       ├── asr/             # 语音识别（Whisper / 阿里云ASR / 讯飞）
│       ├── scene_detect/    # 场景检测（PySceneDetect / 自研CV）
│       ├── highlight/       # 高光提取（LLM + 音频能量分析）
│       ├── subtitle/        # 字幕生成与翻译
│       ├── bgm/             # 智能配乐推荐
│       ├── script_gen/      # 文案/脚本生成
│       ├── cover_gen/       # 封面生成
│       ├── long_to_short/   # 长转短（Opus Clip 类逻辑）
│       └── content_rewrite/ # 内容改写/洗稿
│
├── stages/                  # Pipeline 阶段实现
│   ├── ingest.py            # 素材导入阶段
│   ├── analyze.py           # 智能分析阶段
│   ├── edit.py              # 编辑执行阶段
│   ├── review.py            # 人工审核阶段（可选）
│   └── export.py            # 导出阶段
│
├── ui/                      # 用户界面
│   ├── cli/                 # CLI 模式
│   │   ├── main.py          # Typer 入口
│   │   └── commands.py      # 子命令定义
│   ├── web/                 # Web UI 模式
│   │   ├── api/             # FastAPI 后端
│   │   │   ├── routes.py
│   │   │   ├── websocket.py # 实时进度推送
│   │   │   └── schemas.py
│   │   └── frontend/        # Vue 3 前端
│   └── mcp/                 # MCP Server 模式
│       ├── server.py        # MCP 协议实现
│       └── tools.py         # MCP 工具定义
│
├── infra/                   # 基础设施
│   ├── ffmpeg.py            # FFmpeg 封装（抽帧/转码/音频提取）
│   ├── storage.py           # 本地文件管理（临时文件/缓存清理）
│   ├── monitor.py           # 资源监控（GPU/CPU/内存）
│   └── logging.py           # 结构化日志
│
└── config/                  # 配置文件
    ├── default.yaml         # 默认配置
    ├── providers.yaml       # AI Provider 配置
    └── pipelines.yaml       # 预定义 Pipeline 模板
```

---

## 四、核心模块设计

### 4.1 Pipeline 引擎 (`core/pipeline.py`)

Pipeline 引擎是整个系统的调度中枢，支持：

- **DAG 执行**：Stage 之间声明依赖关系，无依赖的 Stage 并行执行
- **条件分支**：根据上一阶段结果决定后续路径（如：检测到无人声则跳过 ASR）
- **断点续跑**：中间结果持久化到 SQLite，失败后可从上次成功的 Stage 继续
- **回滚机制**：每个 Stage 实现 `rollback()`，失败时清理已产生的中间文件

```python
class Stage(ABC):
    name: str
    dependencies: list[str]     # 依赖的前置 Stage
    can_skip: bool              # 是否可跳过
    timeout: int                # 超时秒数

    async def execute(self, context: PipelineContext) -> StageResult: ...
    async def validate(self, context: PipelineContext) -> bool: ...
    async def rollback(self, context: PipelineContext) -> None: ...

class Pipeline:
    stages: list[Stage]

    async def run(self, input: ProjectInput) -> PipelineResult: ...
    async def run_stage(self, stage_name: str) -> StageResult: ...
    def get_status(self) -> PipelineStatus: ...
```

### 4.2 AI 插件基类 (`ai/base.py`)

```python
class AIPlugin(ABC):
    """所有 AI 功能插件的基类"""
    plugin_id: str                    # 唯一标识，如 "asr.whisper"
    plugin_name: str                  # 显示名称
    version: str
    input_schema: dict                # JSON Schema，描述输入参数
    output_schema: dict               # JSON Schema，描述输出格式
    required_providers: list[str]     # 需要的 Provider 类型

    @abstractmethod
    async def process(self, input_data: dict, context: PluginContext) -> dict: ...

    async def health_check(self) -> bool: ...
    async def describe(self) -> PluginDescription: ...
```

### 4.3 统一驱动接口 (`drivers/interface.py`)

```python
class DriverInterface(ABC):
    """剪映操作的统一抽象"""

    # 项目管理
    async def create_project(self, name: str, config: CanvasConfig) -> str: ...
    async def open_project(self, project_path: str) -> VideoProject: ...
    async def save_project(self, project: VideoProject) -> str: ...

    # 素材操作
    async def import_media(self, project_id: str, file_paths: list[str]) -> list[str]: ...
    async def add_to_timeline(self, project_id: str, material_id: str,
                               track_type: TrackType, position_us: int) -> str: ...

    # 编辑操作
    async def split_segment(self, project_id: str, segment_id: str,
                            split_point_us: int) -> tuple[str, str]: ...
    async def delete_segment(self, project_id: str, segment_id: str) -> None: ...
    async def set_speed(self, project_id: str, segment_id: str, speed: float) -> None: ...
    async def add_text(self, project_id: str, text: SubtitleBlock) -> str: ...
    async def add_effect(self, project_id: str, segment_id: str, effect: Effect) -> None: ...

    # 导出
    async def export_video(self, project_id: str, config: ExportConfig) -> ExportResult: ...
    async def get_export_status(self, task_id: str) -> ExportStatus: ...
```

### 4.4 混合驱动策略 (`drivers/hybrid_driver.py`)

```python
class HybridDriver(DriverInterface):
    """混合驱动：优先用 Draft Engine，仅在必须时启动 GUI"""

    async def export_video(self, project_id, config):
        # 1. 用 Draft Engine 完成所有编辑操作（快、稳定）
        # 2. 保存草稿到剪映项目目录
        # 3. 启动 GUI Controller 打开剪映、加载项目、触发导出
        # 4. 等待导出完成，返回结果
```

### 4.5 领域模型 (`core/models.py`)

与剪映草稿格式解耦的中间表示（IR），通过 Driver 层的 Converter 与 `draft_content.json` 互转：

```python
class VideoProject:
    project_id: str
    source_videos: list[VideoAsset]
    timeline: Timeline
    metadata: ProjectMetadata

class Timeline:
    tracks: list[Track]
    total_duration_us: int         # 微秒
    canvas_config: CanvasConfig

class Track:
    track_id: str
    track_type: TrackType          # VIDEO / AUDIO / TEXT / EFFECT
    segments: list[Segment]
    render_index: int

class Segment:
    segment_id: str
    material_id: str               # 关联素材 ID
    source_range: TimeRange        # 源素材的时间范围（微秒）
    target_range: TimeRange        # 在时间线上的目标位置
    speed: float
    volume: float
    effects: list[Effect]
    transitions: list[Transition]
```

---

## 五、AI 服务抽象层设计

### 5.1 两层抽象

**第一层：Provider Adapter（供应商适配）**

```python
class LLMProvider(ABC):
    """LLM 统一接口"""
    async def chat(self, messages: list[Message], **kwargs) -> LLMResponse: ...
    async def chat_stream(self, messages: list[Message], **kwargs) -> AsyncIterator[str]: ...
    async def embeddings(self, texts: list[str]) -> list[list[float]]: ...
    async def is_available(self) -> bool: ...

class ASRProvider(ABC):
    """语音识别统一接口"""
    async def transcribe(self, audio_path: str, language: str) -> Transcript: ...
    async def transcribe_with_timestamps(self, audio_path: str) -> TimestampedTranscript: ...

class CVProvider(ABC):
    """计算机视觉统一接口"""
    async def detect_scenes(self, video_path: str) -> list[SceneBoundary]: ...
    async def extract_features(self, frame: np.ndarray) -> FeatureVector: ...
```

**第二层：AI Plugin（功能插件）**

每个 AI 功能是一个独立插件，内部通过 Provider Adapter 调用 AI 服务。插件间可互相调用（如 `highlight` 插件内部调用 `asr` 插件获取文本，再用 LLM 分析高光时刻）。

### 5.2 Provider 配置示例

```yaml
# config/providers.yaml
providers:
  llm:
    strategy: primary-fallback    # primary-fallback | round-robin | cost-optimal
    openai:
      api_key: "${OPENAI_API_KEY}"
      model: gpt-4o
      max_tokens: 4096
      timeout: 60
      retry: 3
    qwen:
      api_key: "${DASHSCOPE_API_KEY}"
      model: qwen-max
    ollama:
      base_url: http://localhost:11434
      model: qwen2.5:14b

  asr:
    default: whisper-local
    whisper-local:
      model: large-v3
      compute_type: float16
      device: cuda
    aliyun-asr:
      access_key: "${ALIYUN_AK}"
      secret_key: "${ALIYUN_SK}"

  cv:
    default: local
    local:
      scene_detect_threshold: 30.0
```

### 5.3 插件注册方式

```python
# 方式 1: 装饰器注册（内置插件）
@register_plugin
class MyPlugin(AIPlugin):
    plugin_id = "my_plugin"
    ...

# 方式 2: 配置文件注册（第三方插件）
# config/plugins.yaml
plugins:
  enabled:
    - asr
    - scene_detect
    - highlight
    - my_custom_plugin
  paths:
    - ./plugins/
    - ~/jy_plugins/

# 方式 3: pip 安装注册（发布到 PyPI 的插件）
# pip install jy-plugin-xxx
# 通过 setuptools entry_points 自动发现
```

### 5.4 插件间协作示例：长转短

```
LongToShortPlugin.process():
  │
  ├─→ 调用 ASRPlugin → 获取带时间戳的完整文本
  │
  ├─→ 调用 SceneDetectPlugin → 获取场景切换点
  │
  ├─→ 调用 LLMProvider.chat(
  │       prompt: "根据以下视频转录文本和场景信息，
  │               选出最适合短视频平台的3个高光片段，
  │               每个片段15-60秒...",
  │       context: {transcript, scenes}
  │    )
  │    → 获取 LLM 选择的高光区间
  │
  ├─→ 调用 SubtitlePlugin → 为每个短视频片段生成字幕
  │
  ├─→ 调用 BGMPlugin → 推荐并匹配背景音乐
  │
  └─→ 返回: list[ShortVideoSpec]  (每个短视频的 EDL)
```

---

## 六、数据流：从视频导入到最终导出

```
用户输入（视频文件 + 编辑指令）
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: INGEST (素材导入)                                   │
│                                                             │
│  输入文件 → FFmpeg Probe → VideoAsset 元数据                 │
│                                  │                          │
│                            注册到 Driver                    │
│                                  │                          │
│                            创建/打开剪映项目                  │
└──────────────────────────────────┼──────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: ANALYZE (智能分析) ── 并行执行 ──┐                  │
│                                          │                  │
│  ┌──────────┐  ┌──────────┐  ┌─────────┐│  ┌────────────┐  │
│  │ ASR 分析  │  │ 场景检测  │  │ 高光提取 ││  │ 内容分类    │  │
│  │ (Whisper) │  │(PyScene) │  │(LLM+CV) ││  │ (LLM)      │  │
│  └────┬─────┘  └────┬─────┘  └────┬────┘│  └─────┬──────┘  │
│       │              │             │      │        │         │
│       └──────────────┴─────────────┴──────┴────────┘         │
│                          │                                   │
│                    AnalysisResult                            │
│              (文本+场景+高光+分类+情感)                       │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: EDIT (编辑执行)                                     │
│                                                             │
│  AnalysisResult + 编辑策略 → EDL (编辑决策列表)               │
│                                     │                       │
│                              ┌──────┴──────┐                │
│                              │ Draft Engine │                │
│                              │              │                │
│                              │ 1. 创建轨道   │                │
│                              │ 2. 放置视频段  │                │
│                              │ 3. 智能切片   │                │
│                              │ 4. 添加字幕   │                │
│                              │ 5. 添加 BGM   │                │
│                              │ 6. 添加转场   │                │
│                              │ 7. 保存草稿   │                │
│                              └──────┬──────┘                │
│                                     │                       │
│                           draft_content.json                 │
│                           (写入剪映项目目录)                  │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 4: REVIEW (可选审核)                                    │
│                                                             │
│  Web UI: 时间线预览 → 用户调整 → 确认                        │
│  CLI:    编辑报告 → 用户确认                                  │
│  MCP:    返回 Agent → Agent 决策                              │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 5: EXPORT (导出)                                       │
│                                                             │
│  HybridDriver:                                              │
│    1. 启动剪映进程 (如未运行)                                 │
│    2. 打开项目                                               │
│    3. GUI 触发导出 (Ctrl+E → 设置参数 → 导出)                │
│    4. 轮询等待导出完成                                       │
│    5. 验证输出文件                                           │
│    6. 后处理 (重命名/移动/上传)                              │
│                                                             │
│  输出: 最终视频文件 (.mp4)                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 七、技术栈推荐

| 层次 | 技术选型 | 理由 |
|------|---------|------|
| **语言** | Python 3.11+ | AI 生态最完善，asyncio 支持好 |
| **异步框架** | asyncio + anyio | 原生协程，适合 IO 密集的 Pipeline |
| **草稿操作** | pyJianYingDraft (PyPI) | 成熟的剪映草稿读写库 |
| **草稿加解密** | jy-draftc | 唯一可用的加解密工具（调用 videoeditor.dll） |
| **GUI 自动化** | uiautomation + pywinauto | Windows UI 自动化标准方案 |
| **视频处理** | FFmpeg (ffmpeg-python) | 工业级视频处理 |
| **场景检测** | PySceneDetect | 开源场景检测标准库 |
| **语音识别** | faster-whisper (本地) + 阿里云ASR (云端) | 本地免费 + 云端兜底 |
| **LLM** | openai SDK + dashscope SDK + ollama | 覆盖国内外 + 本地模型 |
| **数据模型** | Pydantic v2 | 类型安全、序列化性能好 |
| **CLI** | Typer | 类型提示友好、自动生成帮助 |
| **Web 后端** | FastAPI | 异步、自动 OpenAPI 文档 |
| **Web 前端** | Vue 3 + Element Plus | 国内生态好、组件丰富 |
| **实时通信** | WebSocket | Pipeline 进度实时推送 |
| **MCP 协议** | mcp (Python SDK) | 标准 MCP Server 实现 |
| **数据库** | SQLite | 存储 Pipeline 状态、缓存分析结果 |
| **配置管理** | PyYAML + pydantic-settings | YAML 配置 + 环境变量覆盖 |
| **日志** | structlog | 结构化日志 |
| **重试** | tenacity | 优雅的重试/降级策略 |
| **测试** | pytest + pytest-asyncio | 标准异步测试方案 |

---

## 八、关键实现考量

### 8.1 剪映版本兼容性

```python
class DraftCrypto:
    """自动处理草稿加解密"""

    async def detect_encryption(self, draft_path: Path) -> bool:
        """检测草稿是否加密：读取首字节，'{' = 明文，否则加密"""
        first_byte = draft_path.read_bytes()[:1]
        return first_byte != b'{'

    async def ensure_decrypted(self, draft_path: Path) -> Path:
        """确保草稿已解密，返回可操作的 JSON 文件路径"""
        if not await self.detect_encryption(draft_path):
            return draft_path
        decrypted = await self._call_jy_draftc_decrypt(draft_path)
        return decrypted

    async def re_encrypt(self, draft_path: Path):
        """操作完成后回加密（仅对加密版本草稿）"""
        if self._was_originally_encrypted:
            await self._call_jy_draftc_encrypt(draft_path)
```

**版本兼容策略**：

- 启动时自动检测剪映版本
- v5.9.x 及以下：直接读写 JSON
- v6.0+：自动调用 jy-draftc 解密 → 操作 → 回加密
- 如果 jy-draftc 不可用：提示用户降级剪映或使用 GUI 模式

### 8.2 时间单位与 UUID 管理

```python
MICROSECONDS_PER_SECOND = 1_000_000

class TimeRange:
    """统一时间范围表示，内部存储微秒"""
    start_us: int
    duration_us: int

    @classmethod
    def from_seconds(cls, start: float, duration: float) -> 'TimeRange':
        return cls(
            start_us=int(start * MICROSECONDS_PER_SECOND),
            duration_us=int(duration * MICROSECONDS_PER_SECOND)
        )

# UUID 生成：所有 material_id / segment_id 使用 uuid4
def generate_id() -> str:
    return str(uuid.uuid4()).upper()
```

### 8.3 GUI 自动化稳定性

- **多层元素定位**：优先 AutomationId → Name/ClassName → 图像识别（OpenCV 模板匹配）
- **操作验证**：每次操作后截图对比或检查 UI 状态
- **重试机制**：失败自动重试 3 次，指数退避（1s → 2s → 5s）

### 8.4 并发与资源管理

- **GPU 资源**：ASR（Whisper）和 CV 任务共享 GPU，通过 `ResourceLock` 协调
- **API 限流**：每个 Provider 独立 RateLimiter
- **文件清理**：Pipeline 完成后自动清理临时文件
- **大文件处理**：视频文件使用符号链接或绝对路径引用，不复制

---

## 九、开发阶段规划

### Phase 1: MVP — 基础能力验证（4-6 周）

**目标**：跑通 "导入视频 → 自动加字幕 → 导出" 的最小闭环

- 搭建项目骨架（core/ + drivers/draft_engine/ + infra/）
- 实现 DraftEngine：读写 draft_content.json（基于 pyJianYingDraft）
- 实现 DraftCrypto：自动检测和处理加密草稿
- 实现 ASR 插件（faster-whisper 本地模式）
- 实现字幕写入：ASR 结果 → 文本轨 → draft_content.json
- 实现 CLI 模式（Typer）：`jy-edit subtitle <video_path>`
- 手动在剪映中打开草稿并导出（验证全流程）

**交付物**：可运行的 CLI 工具，输入视频文件，输出带字幕的剪映草稿

### Phase 2: 核心功能完善（6-8 周）

**目标**：补齐智能切片、高光提取、BGM 推荐，实现全自动导出

- 实现场景检测插件（PySceneDetect）
- 实现智能切片：按场景/静音点自动分割
- 实现高光提取插件（LLM 分析 + 音频能量）
- 实现 BGM 推荐插件（基于视频情绪匹配）
- 实现 GUI Controller：自动导出功能
- 实现 HybridDriver：草稿编辑 + GUI 导出
- 实现 Provider 多供应商支持（OpenAI + 通义千问 + Ollama）
- 实现 Pipeline 断点续跑

**交付物**：CLI 工具支持 `jy-edit smart-cut`、`jy-edit highlight`、`jy-edit full-pipeline`

### Phase 3: 长转短 + Web UI（6-8 周）

**目标**：实现长视频转短视频的核心场景，提供 Web 管理界面

- 实现长转短插件（Opus Clip 类逻辑）
- 实现文案/脚本生成插件
- 实现 Web 后端（FastAPI + WebSocket 进度推送）
- 实现 Web 前端（Vue 3：项目管理、Pipeline 配置、进度监控、预览）
- 实现批量处理能力（多视频队列）
- 实现内容改写插件

**交付物**：Web 应用，支持上传视频、选择模板、预览时间线、一键导出

### Phase 4: 生态与高级功能（持续迭代）

- 插件 SDK 文档与示例
- 插件市场（第三方插件发布/安装）
- MCP Server 模式（让 AI Agent 直接调用）
- 封面生成插件（DALL-E / Stable Diffusion）
- 多语言字幕翻译插件
- 模板系统（预设编辑风格：Vlog、教程、新闻、带货等）
- 性能优化：GPU Pipeline 并行、分布式任务队列

---

## 十、风险与缓解策略

| 风险 | 影响 | 缓解策略 |
|------|------|---------|
| 剪映更新导致草稿格式变更 | 草稿操作失败 | schema.py 版本化 + 自动检测 + 回退到 GUI 模式 |
| jy-draftc 加密算法变更 | 无法读写加密草稿 | 监控 jy-draftc 更新 + 保留降级到 v5.9.x 的选项 |
| GUI 自动化因 UI 变更失效 | 无法触发导出 | 多层元素定位 + 图像识别兜底 + 版本适配层 |
| AI Provider API 不可用 | 分析功能中断 | 主备 Provider 自动切换 + 本地模型兜底 |
| GPU 内存不足 | ASR 崩溃 | 自动检测显存，选择合适模型大小 + 分段处理 |
| 法律风险 | 合规问题 | 仅操作用户自己的草稿文件，不修改剪映程序本身 |
