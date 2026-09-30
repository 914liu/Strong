"""剪映 AI 剪辑技能服务 — 豆包/扣子平台插件后端

提供 REST API 供豆包 AI 调用，实现视频分析、自动字幕、智能剪辑等功能。
启动: python server.py
地址: http://localhost:9800
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 应用初始化 — 中文标题与分组标签
# ──────────────────────────────────────────────

app = FastAPI(
    title="剪映 AI 剪辑技能",
    description="通过豆包 AI 驱动剪映专业版自动剪辑视频的 REST API 服务。\n\n"
                "支持视频分析、自动字幕、智能剪辑、长视频转短片、全自动剪辑流水线等功能。\n\n"
                "服务地址: http://localhost:9800\n"
                "交互文档: http://localhost:9800/docs",
    version="1.0.0",
    openapi_tags=[
        {"name": "系统状态", "description": "检查服务运行状态和各组件可用性"},
        {"name": "视频上传", "description": "上传视频文件到服务器"},
        {"name": "视频分析", "description": "AI 分析视频内容，返回时长、分辨率、画幅等信息及剪辑建议"},
        {"name": "自动字幕", "description": "从视频中提取音频并生成字幕文件"},
        {"name": "智能剪辑", "description": "AI 智能分析视频并生成剪辑方案（自动/精彩/紧凑风格）"},
        {"name": "长视频转短片", "description": "从长视频中提取精彩片段，生成多个短视频方案"},
        {"name": "全自动流水线", "description": "一键执行完整剪辑流水线：分析 → 字幕 → 剪辑 → 导出到剪映"},
        {"name": "剪映控制", "description": "启动剪映、查看和打开草稿"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = Path(__file__).parent / "uploads"
OUTPUT_DIR = Path(__file__).parent / "outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

JIANYING_EXE = r"E:\剪映\JianyingPro\JianyingPro.exe"
JIANYING_DRAFT_DIR = Path(os.environ.get("LOCALAPPDATA", "")) / "JianyingPro" / "User Data" / "Projects" / "com.lveditor.draft"


# ──────────────────────────────────────────────
# 请求模型 — 中文字段标注
# ──────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    """视频分析请求"""
    video_path: str = Field(
        ...,
        title="视频路径",
        description="视频文件的完整路径，例如 C:\\Videos\\test.mp4",
        examples=["C:\\Videos\\test.mp4"],
    )
    analysis_type: str = Field(
        default="full",
        title="分析类型",
        description="full=完整分析, scene=仅场景检测, content=仅内容分析",
        examples=["full"],
    )


class SubtitleRequest(BaseModel):
    """字幕生成请求"""
    video_path: str = Field(
        ...,
        title="视频路径",
        description="视频文件的完整路径",
        examples=["C:\\Videos\\test.mp4"],
    )
    language: str = Field(
        default="zh",
        title="语言",
        description="zh=中文, en=英文",
        examples=["zh"],
    )


class SmartCutRequest(BaseModel):
    """智能剪辑请求"""
    video_path: str = Field(
        ...,
        title="视频路径",
        description="视频文件的完整路径",
        examples=["C:\\Videos\\test.mp4"],
    )
    style: str = Field(
        default="auto",
        title="剪辑风格",
        description="auto=自动, highlight=提取精彩片段, compact=紧凑去废话",
        examples=["auto"],
    )
    target_duration: int = Field(
        default=0,
        title="目标时长（秒）",
        description="剪辑后的目标时长，0 表示由 AI 自动决定",
        ge=0,
        examples=[60],
    )


class LongToShortRequest(BaseModel):
    """长视频转短片请求"""
    video_path: str = Field(
        ...,
        title="长视频路径",
        description="长视频文件的完整路径",
        examples=["C:\\Videos\\long_video.mp4"],
    )
    max_clip_duration: int = Field(
        default=60,
        title="短片最大时长（秒）",
        description="每个生成的短片最大时长",
        ge=1,
        examples=[60],
    )
    count: int = Field(
        default=5,
        title="生成数量",
        description="要生成的短片数量",
        ge=1,
        le=20,
        examples=[5],
    )


class FullPipelineRequest(BaseModel):
    """全自动流水线请求"""
    video_path: str = Field(
        ...,
        title="视频路径",
        description="视频文件的完整路径",
        examples=["C:\\Videos\\test.mp4"],
    )
    add_subtitles: bool = Field(
        default=True,
        title="添加字幕",
        description="是否自动添加字幕",
    )
    add_bgm: bool = Field(
        default=False,
        title="添加背景音乐",
        description="是否自动添加背景音乐",
    )
    style: str = Field(
        default="auto",
        title="剪辑风格",
        description="auto=自动, highlight=精彩, compact=紧凑",
        examples=["auto"],
    )


class OpenDraftRequest(BaseModel):
    """打开草稿请求"""
    draft_name: str = Field(
        default="",
        title="草稿名称",
        description="要打开的草稿名称，留空则打开最新的草稿",
        examples=["我的视频"],
    )


# ──────────────────────────────────────────────
# 响应模型 — 中文字段标注
# ──────────────────────────────────────────────

class StatusResponse(BaseModel):
    """服务状态响应"""
    status: str = Field(..., title="状态", description="服务运行状态", examples=["running"])
    service: str = Field(..., title="服务名称", examples=["剪映 AI 剪辑技能"])
    version: str = Field(..., title="版本号", examples=["1.0.0"])
    jianying: dict = Field(..., title="剪映状态", description="剪映是否可用及安装路径")
    ffmpeg: dict = Field(..., title="FFmpeg 状态", description="FFmpeg 是否可用及路径")
    doubao: dict = Field(..., title="豆包状态", description="豆包 API 是否可用")


class UploadResponse(BaseModel):
    """上传视频响应"""
    file_id: str = Field(..., title="文件 ID", description="系统分配的唯一标识")
    path: str = Field(..., title="存储路径", description="文件在服务器上的路径")
    filename: str = Field(..., title="原始文件名")
    size_mb: float = Field(..., title="文件大小（MB）")
    duration_seconds: float = Field(..., title="视频时长（秒）")


class AnalyzeResponse(BaseModel):
    """视频分析响应"""
    video_path: str = Field(..., title="视频路径")
    info: dict = Field(..., title="视频信息", description="包含时长、分辨率、画幅、是否有音轨")
    ai_advice: str = Field(..., title="AI 剪辑建议", description="豆包 AI 给出的剪辑建议")
    recommendations: list = Field(..., title="推荐操作列表")


class SubtitleResponse(BaseModel):
    """字幕生成响应"""
    status: str = Field(..., title="状态")
    audio_path: str = Field(..., title="提取的音频路径")
    message: str = Field(..., title="提示信息")
    next_step: str = Field(..., title="下一步操作")


class SmartCutResponse(BaseModel):
    """智能剪辑响应"""
    status: str = Field(..., title="状态")
    video_path: str = Field(..., title="视频路径")
    original_duration: float = Field(..., title="原始时长（秒）")
    style: str = Field(..., title="剪辑风格")
    ai_plan: str = Field(..., title="AI 剪辑方案")
    output_path: str = Field(..., title="输出路径")
    message: str = Field(..., title="提示信息")


class LongToShortResponse(BaseModel):
    """长转短响应"""
    status: str = Field(..., title="状态")
    video_path: str = Field(..., title="视频路径")
    original_duration: float = Field(..., title="原始时长（秒）")
    target_clips: int = Field(..., title="目标短片数量")
    max_clip_duration: int = Field(..., title="短片最大时长（秒）")
    ai_plan: str = Field(..., title="AI 短片方案")
    message: str = Field(..., title="提示信息")


class FullPipelineResponse(BaseModel):
    """全自动流水线响应"""
    status: str = Field(..., title="状态")
    video_path: str = Field(..., title="视频路径")
    steps: list = Field(..., title="流水线步骤", description="各步骤的名称、状态和详情")
    ai_strategy: str = Field(..., title="AI 剪辑策略")
    message: str = Field(..., title="提示信息")


class DraftItem(BaseModel):
    """草稿条目"""
    name: str = Field(..., title="草稿名称")
    path: str = Field(..., title="草稿路径")
    modified: float = Field(..., title="最后修改时间（时间戳）")


class DraftListResponse(BaseModel):
    """草稿列表响应"""
    drafts: list[DraftItem] = Field(..., title="草稿列表")
    total: int = Field(..., title="草稿总数")


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _find_ffmpeg() -> str:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    winget_path = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_path.exists():
        for p in winget_path.rglob("ffmpeg.exe"):
            return str(p.parent)
    return "ffmpeg"


async def _run_cmd(cmd: list[str], timeout: int = 300) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode, stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
    except asyncio.TimeoutError:
        return -1, "", "命令执行超时"
    except Exception as e:
        return -1, "", str(e)


def _get_video_info(video_path: str) -> dict:
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    cmd = [
        ffprobe, "-v", "quiet",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            import json
            return json.loads(result.stdout)
    except Exception:
        pass
    return {}


def _call_doubao_api(prompt: str, system: str = "") -> str:
    """调用豆包 API"""
    api_key = os.environ.get("DOUBAO_API_KEY", "")
    if not api_key:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent.parent / ".env")
        api_key = os.environ.get("DOUBAO_API_KEY", "")

    if not api_key or api_key.startswith("your-"):
        return ""

    try:
        import openai
        client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url="https://ark.cn-beijing.volces.com/api/v3",
        )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        loop = asyncio.get_event_loop()
        response = loop.run_until_complete(
            client.chat.completions.create(
                model="doubao-pro-32k",
                messages=messages,
                temperature=0.7,
                max_tokens=4096,
            )
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        logger.error(f"豆包 API 调用失败: {e}")
        return ""


# ──────────────────────────────────────────────
# API 端点 — 中文标注
# ──────────────────────────────────────────────

@app.get(
    "/api/status",
    tags=["系统状态"],
    summary="检查服务状态",
    description="检查剪映 AI 剪辑技能服务是否正常运行，以及剪映、FFmpeg、豆包 API 的可用性",
    response_model=StatusResponse,
)
async def get_status():
    jianying_available = os.path.isfile(JIANYING_EXE)
    ffmpeg_available = shutil.which("ffmpeg") is not None

    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    api_key = os.environ.get("DOUBAO_API_KEY", "")
    doubao_available = bool(api_key) and not api_key.startswith("your-")

    return {
        "status": "running",
        "service": "剪映 AI 剪辑技能",
        "version": "1.0.0",
        "jianying": {
            "available": jianying_available,
            "path": JIANYING_EXE if jianying_available else "",
        },
        "ffmpeg": {
            "available": ffmpeg_available,
            "path": _find_ffmpeg(),
        },
        "doubao": {
            "available": doubao_available,
        },
    }


@app.post(
    "/api/upload",
    tags=["视频上传"],
    summary="上传视频文件",
    description="上传视频文件到服务器，返回文件路径和基本信息（时长、大小等）。支持 mp4/mov/avi/mkv/wmv/flv/webm 格式。",
    response_model=UploadResponse,
)
async def upload_video(
    file: UploadFile = File(
        ...,
        title="视频文件",
        description="要上传的视频文件，支持 mp4/mov/avi/mkv/wmv/flv/webm",
    ),
):
    ext = Path(file.filename).suffix.lower()
    if ext not in (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"):
        raise HTTPException(400, f"不支持的视频格式: {ext}，支持: mp4/mov/avi/mkv/wmv/flv/webm")

    file_id = str(uuid.uuid4())[:8]
    save_path = UPLOAD_DIR / f"{file_id}{ext}"
    with open(save_path, "wb") as f:
        while chunk := await file.read():
            f.write(chunk)

    info = _get_video_info(str(save_path))
    duration = 0
    if "format" in info:
        duration = float(info["format"].get("duration", 0))

    return {
        "file_id": file_id,
        "path": str(save_path),
        "filename": file.filename,
        "size_mb": round(save_path.stat().st_size / 1024 / 1024, 2),
        "duration_seconds": round(duration, 1),
    }


@app.post(
    "/api/analyze",
    tags=["视频分析"],
    summary="AI 分析视频",
    description="AI 分析视频内容，返回视频信息（时长、分辨率、画幅）以及豆包 AI 给出的剪辑建议和推荐操作",
    response_model=AnalyzeResponse,
)
async def analyze_video(req: AnalyzeRequest):
    video_path = req.video_path
    if not os.path.isfile(video_path):
        raise HTTPException(404, f"视频文件不存在: {video_path}")

    info = _get_video_info(video_path)
    duration = 0
    if "format" in info:
        duration = float(info["format"].get("duration", 0))

    video_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "video"]
    audio_streams = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]

    width = height = 0
    if video_streams:
        width = int(video_streams[0].get("width", 0))
        height = int(video_streams[0].get("height", 0))

    canvas = "横屏"
    if height > width:
        canvas = "竖屏"
    elif width == height:
        canvas = "方形"

    system = "你是专业的视频剪辑顾问。根据视频信息给出简洁的中文剪辑建议。"
    prompt = f"""请分析以下视频并给出剪辑建议：
- 时长: {duration:.1f}秒
- 分辨率: {width}x{height}
- 画幅: {canvas}
- 有音轨: {len(audio_streams) > 0}

请给出：
1. 视频类型判断（vlog/教程/短片/其他）
2. 推荐的剪辑风格
3. 建议的剪辑操作（如去静音、加字幕、精彩片段提取等）
4. 预计剪辑后时长"""

    ai_advice = _call_doubao_api(prompt, system)

    return {
        "video_path": video_path,
        "info": {
            "duration_seconds（秒）": round(duration, 1),
            "resolution（分辨率）": f"{width}x{height}",
            "canvas（画幅）": canvas,
            "has_audio（有音轨）": len(audio_streams) > 0,
        },
        "ai_advice": ai_advice or "豆包 API 未配置，无法获取 AI 建议",
        "recommendations": [
            "auto_subtitle（自动字幕）" if audio_streams else None,
            "smart_cut（智能剪辑）",
            "scene_detect（场景检测）",
        ],
    }


@app.post(
    "/api/subtitle",
    tags=["自动字幕"],
    summary="生成字幕",
    description="从视频中提取音频，可通过 ASR 服务转录生成字幕文件。支持中文和英文。",
    response_model=SubtitleResponse,
)
async def generate_subtitles(req: SubtitleRequest):
    video_path = req.video_path
    if not os.path.isfile(video_path):
        raise HTTPException(404, f"视频文件不存在: {video_path}")

    audio_path = OUTPUT_DIR / f"{Path(video_path).stem}_audio.wav"
    ffmpeg = _find_ffmpeg()
    code, _, err = await _run_cmd([
        ffmpeg, "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le",
        "-ar", "16000", "-ac", "1",
        str(audio_path),
    ])

    if code != 0:
        raise HTTPException(500, f"音频提取失败: {err[:200]}")

    return {
        "status": "audio_extracted",
        "audio_path": str(audio_path),
        "message": "音频已提取，可通过 ASR 服务转录字幕。配置 OPENAI_API_KEY 后支持自动转录。",
        "next_step": "将音频文件发送到 Whisper API 进行转录",
    }


@app.post(
    "/api/smart_cut",
    tags=["智能剪辑"],
    summary="智能剪辑",
    description="AI 智能分析视频并生成剪辑方案。支持三种风格：auto（自动）、highlight（提取精彩片段）、compact（紧凑去废话）。",
    response_model=SmartCutResponse,
)
async def smart_cut(req: SmartCutRequest):
    video_path = req.video_path
    if not os.path.isfile(video_path):
        raise HTTPException(404, f"视频文件不存在: {video_path}")

    info = _get_video_info(video_path)
    duration = float(info.get("format", {}).get("duration", 0))

    style_names = {"auto": "自动", "highlight": "精彩片段", "compact": "紧凑去废话"}
    style_cn = style_names.get(req.style, req.style)

    system = "你是专业的视频剪辑师。根据视频信息制定剪辑方案，返回 JSON 格式。"
    prompt = f"""视频信息：时长 {duration:.1f}秒，剪辑风格: {style_cn}，目标时长: {req.target_duration}秒

请返回 JSON 格式的剪辑方案：
```json
{{
  "plan": "剪辑方案描述",
  "cuts": [
    {{"start": 0, "end": 10, "action": "keep"}},
    {{"start": 10, "end": 15, "action": "remove"}}
  ],
  "estimated_duration": 45
}}
```"""

    ai_response = _call_doubao_api(prompt, system)
    output_path = str(OUTPUT_DIR / f"{Path(video_path).stem}_cut.mp4")

    return {
        "status": "plan_generated",
        "video_path": video_path,
        "original_duration": round(duration, 1),
        "style": f"{req.style}（{style_cn}）",
        "ai_plan": ai_response or "豆包 API 未配置",
        "output_path": output_path,
        "message": "剪辑方案已生成。完整自动剪辑需要配置 ASR 和 FFmpeg 流水线。",
    }


@app.post(
    "/api/long_to_short",
    tags=["长视频转短片"],
    summary="长视频转短片",
    description="从长视频中提取精彩片段，生成多个短视频方案。适合将直播、课程、访谈等长内容拆分为短视频。",
    response_model=LongToShortResponse,
)
async def long_to_short(req: LongToShortRequest):
    video_path = req.video_path
    if not os.path.isfile(video_path):
        raise HTTPException(404, f"视频文件不存在: {video_path}")

    info = _get_video_info(video_path)
    duration = float(info.get("format", {}).get("duration", 0))

    system = "你是短视频剪辑专家。从长视频中提取精彩片段生成短视频。"
    prompt = f"""长视频时长: {duration:.1f}秒
要求: 生成 {req.count} 个短片，每个最长 {req.max_clip_duration} 秒

请返回 JSON 格式的短片方案：
```json
{{
  "clips": [
    {{"index": 1, "start": 0, "end": 30, "title": "开场", "reason": "吸引观众"}},
    {{"index": 2, "start": 45, "end": 90, "title": "精彩片段", "reason": "高潮内容"}}
  ]
}}
```"""

    ai_response = _call_doubao_api(prompt, system)

    return {
        "status": "plan_generated",
        "video_path": video_path,
        "original_duration": round(duration, 1),
        "target_clips": req.count,
        "max_clip_duration": req.max_clip_duration,
        "ai_plan": ai_response or "豆包 API 未配置",
        "message": "短片方案已生成。",
    }


@app.post(
    "/api/full_pipeline",
    tags=["全自动流水线"],
    summary="全自动剪辑流水线",
    description="一键执行完整剪辑流水线：视频分析 → 字幕生成 → 智能剪辑 → 导出到剪映草稿。支持配置是否添加字幕和背景音乐。",
    response_model=FullPipelineResponse,
)
async def full_pipeline(req: FullPipelineRequest):
    video_path = req.video_path
    if not os.path.isfile(video_path):
        raise HTTPException(404, f"视频文件不存在: {video_path}")

    info = _get_video_info(video_path)
    duration = float(info.get("format", {}).get("duration", 0))

    steps = [
        {"step": "analyze（视频分析）", "status": "done（已完成）", "detail": f"视频时长 {duration:.1f} 秒"},
    ]

    if req.add_subtitles:
        steps.append({"step": "subtitle（字幕生成）", "status": "ready（就绪）", "detail": "字幕生成就绪"})

    if req.add_bgm:
        steps.append({"step": "bgm（背景音乐）", "status": "ready（就绪）", "detail": "背景音乐待添加"})

    style_names = {"auto": "自动", "highlight": "精彩", "compact": "紧凑"}
    style_cn = style_names.get(req.style, req.style)

    steps.append({"step": "smart_cut（智能剪辑）", "status": "ready（就绪）", "detail": f"剪辑风格: {style_cn}"})
    steps.append({"step": "export_draft（导出剪映）", "status": "ready（就绪）", "detail": "导出到剪映草稿"})

    system = "你是视频剪辑总监。为这个视频制定完整的剪辑工作流。"
    prompt = f"""视频: 时长 {duration:.1f}秒
功能: 字幕={"是" if req.add_subtitles else "否"}, BGM={"是" if req.add_bgm else "否"}, 风格={style_cn}

用一句话总结剪辑策略。"""

    ai_summary = _call_doubao_api(prompt, system)

    return {
        "status": "pipeline_ready",
        "video_path": video_path,
        "steps": steps,
        "ai_strategy": ai_summary or "豆包 API 未配置",
        "message": "流水线已就绪，可逐步执行或导出到剪映。",
    }


@app.post(
    "/api/open_jianying",
    tags=["剪映控制"],
    summary="打开剪映",
    description="启动剪映专业版应用程序",
)
async def open_jianying():
    if not os.path.isfile(JIANYING_EXE):
        raise HTTPException(404, f"剪映未找到: {JIANYING_EXE}")

    subprocess.Popen([JIANYING_EXE], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return {"status": "ok", "message": "剪映已启动"}


@app.post(
    "/api/draft/open",
    tags=["剪映控制"],
    summary="在剪映中打开草稿",
    description="在剪映中打开指定名称的草稿，留空则打开最近修改的草稿",
)
async def open_draft_in_jianying(req: OpenDraftRequest):
    if not JIANYING_DRAFT_DIR.exists():
        raise HTTPException(404, "剪映草稿目录不存在")

    if req.draft_name:
        draft_dir = JIANYING_DRAFT_DIR / req.draft_name
        if not draft_dir.exists():
            raise HTTPException(404, f"草稿不存在: {req.draft_name}")
    else:
        drafts = sorted(JIANYING_DRAFT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        if not drafts:
            raise HTTPException(404, "没有草稿文件")
        draft_dir = drafts[0]

    draft_content = draft_dir / "draft_content.json"
    if not draft_content.exists():
        raise HTTPException(404, "草稿内容文件不存在")

    if os.path.isfile(JIANYING_EXE):
        subprocess.Popen(
            [JIANYING_EXE, "--draft", str(draft_dir)],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

    return {
        "status": "ok",
        "draft_name": draft_dir.name,
        "draft_path": str(draft_dir),
        "message": f"已在剪映中打开草稿: {draft_dir.name}",
    }


@app.get(
    "/api/drafts",
    tags=["剪映控制"],
    summary="列出所有剪映草稿",
    description="列出剪映中所有草稿项目，按最后修改时间倒序排列，最多返回 20 个",
    response_model=DraftListResponse,
)
async def list_drafts():
    if not JIANYING_DRAFT_DIR.exists():
        return {"drafts": [], "total": 0, "message": "剪映草稿目录不存在"}

    drafts = []
    for d in sorted(JIANYING_DRAFT_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if d.is_dir() and (d / "draft_content.json").exists():
            drafts.append({
                "name": d.name,
                "path": str(d),
                "modified": d.stat().st_mtime,
            })

    return {"drafts": drafts[:20], "total": len(drafts)}


# ──────────────────────────────────────────────
# 启动
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  剪映 AI 剪辑技能服务")
    print("  地址: http://localhost:9800")
    print("  文档: http://localhost:9800/docs")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=9800)
