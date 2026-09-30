# 剪映 AI 自动剪辑插件

> 基于混合驱动 + 插件化 AI + 流水线编排的全自动视频编辑系统

## 功能特性

- **智能字幕** — 基于 ASR 自动识别语音并添加字幕
- **精彩剪辑** — AI 分析内容自动提取高光片段
- **长转短** — 长视频自动裁剪为短视频(抖音/快手/小红书)
- **BGM 推荐** — 根据视频内容智能推荐背景音乐
- **全流程自动化** — 一键完成从分析到导出的完整流水线

## 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                    CLI / Web UI / MCP                     │
├─────────────────────────────────────────────────────────┤
│                   Pipeline Engine (DAG)                   │
│   Ingest → Analyze → Edit → Review → Export              │
├──────────────────────┬──────────────────────────────────┤
│   Drivers Layer      │        AI Layer                   │
│  ┌───────────────┐   │   ┌─────────────────────────┐    │
│  │ Draft Engine  │   │   │  Provider Router         │    │
│  │ GUI Controller│   │   │  ├── OpenAI              │    │
│  │ Hybrid Driver │   │   │  ├── Qwen (DashScope)    │    │
│  └───────────────┘   │   │  └── Ollama (Local)      │    │
│                      │   │  AI Plugins               │    │
│                      │   │  ├── ASR / Subtitle       │    │
│                      │   │  ├── Scene Detect         │    │
│                      │   │  ├── Highlight            │    │
│                      │   │  ├── BGM Recommend        │    │
│                      │   │  └── Long-to-Short        │    │
│                      │   └─────────────────────────┘    │
├──────────────────────┴──────────────────────────────────┤
│              Infrastructure (FFmpeg / Storage)            │
└─────────────────────────────────────────────────────────┘
```

## 快速开始

### 环境要求

- Python 3.11+
- FFmpeg
- 剪映桌面版 (Windows)

### 安装

```bash
# 克隆项目
git clone https://github.com/your-org/jy-auto-editor.git
cd jy-auto-editor

# 安装依赖
pip install -e ".[all]"

# 复制环境变量
cp .env.example .env
# 编辑 .env 填入 API Key
```

### 使用

```bash
# 检查环境
jy-edit check

# 查看草稿信息
jy-edit info /path/to/draft

# 自动添加字幕
jy-edit subtitle /path/to/draft

# 智能剪辑
jy-edit smart-cut /path/to/draft --style highlight

# 长视频转短视频
jy-edit long-to-short /path/to/draft --target-duration 60

# BGM 推荐
jy-edit bgm /path/to/draft --mood auto

# 完整流水线
jy-edit full-pipeline /path/to/draft --export
```

### 配置文件

项目使用 `config/default.yaml` 作为默认配置，支持环境变量引用：

```yaml
ai:
  llm:
    primary: "openai"
    providers:
      openai:
        api_key: "${OPENAI_API_KEY}"
        model: "gpt-4o"
```

## 项目结构

```
jy_auto_editor/
├── core/           # 核心框架 (模型/配置/流水线/事件)
├── drivers/        # 剪映驱动 (草稿引擎/GUI控制/混合驱动)
├── ai/             # AI 服务层 (提供商/插件)
│   ├── providers/  # LLM/ASR/CV 提供商
│   └── plugins/    # 功能插件 (ASR/字幕/高光/BGM等)
├── stages/         # 流水线阶段 (Ingest/Analyze/Edit/Export)
├── infra/          # 基础设施 (FFmpeg/存储/监控/日志)
├── ui/             # 用户界面 (CLI/Web/MCP)
├── config/         # 配置文件
└── tests/          # 测试
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check jy_auto_editor/
mypy jy_auto_editor/
```

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.11+ |
| 异步 | asyncio |
| 数据模型 | Pydantic v2 |
| CLI | Typer + Rich |
| Web | FastAPI (可选) |
| AI | OpenAI / 通义千问 / Ollama |
| ASR | Whisper API / faster-whisper |
| 场景检测 | PySceneDetect |
| GUI自动化 | uiautomation |
| 视频处理 | FFmpeg |

## License

MIT
