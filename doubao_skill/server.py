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

app = FastAPI(
    title="剪映 AI 剪辑技能",
    description="通过豆包 AI 驱动剪映自动剪辑的 REST API 服务",
    version="1.0.0",
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
# 请求/响应模型
# ──────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    video_path: str = Field(description="视频文件路径")
    analysis_type: str = Field(default="full", description="分析类型: full/scene/content")

class SubtitleRequest(BaseModel):
    video_path: str = Field(description="视频文件路径")
    language: str = Field(default="zh", description="语言: zh/en")

class SmartCutRequest(BaseModel):
    video_path: str = Field(description="视频文件路径")
    style: str = Field(default="auto", description="剪辑风格: auto/highlight/compact")
    target_duration: int = Field(default=0, description="目标时长(秒), 0=自动")

class LongToShortRequest(BaseModel):
    video_path: str = Field(description="长视频文件路径")
    max_clip_duration: int = Field(default=60, description="每个短片最大时长(秒)")
    count: int = Field(default=5, description="生成短片数量")

class FullPipelineRequest(BaseModel):
    video_path: str = Field(description="视频文件路径")
    add_subtitles: bool = Field(default=True, description="是否添加字幕")
    add_bgm: bool = Field(default=False, description="是否添加背景音乐")
    style: str = Field(default="auto", description="剪辑风格")

class OpenDraftRequest(BaseModel):
    draft_name: str = Field(default="", description="草稿名称, 空=打开最新草稿")


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
        return -1, "", "Command timed out"
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
        logger.error(f"Doubao API call failed: {e}")
        return ""


# ──────────────────────────────────────────────
# API 端点
# ──────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """检查服务状态和剪映可用性"""
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


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """上传视频文件到服务器"""
    ext = Path(file.filename).suffix.lower()
    if ext not in (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv", ".webm"):
        raise HTTPException(400, f"不支持的视频格式: {ext}")

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


@app.post("/api/analyze")
async def analyze_video(req: AnalyzeRequest):
    """分析视频内容，返回剪辑建议"""
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

    canvas = "horizontal"
    if height > width:
        canvas = "vertical"
    elif width == height:
        canvas = "square"

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
            "duration_seconds": round(duration, 1),
            "resolution": f"{width}x{height}",
            "canvas": canvas,
            "has_audio": len(audio_streams) > 0,
        },
        "ai_advice": ai_advice or "豆包 API 未配置，无法获取 AI 建议",
        "recommendations": [
            "auto_subtitle" if audio_streams else None,
            "smart_cut",
            "scene_detect",
        ],
    }


@app.post("/api/subtitle")
async def generate_subtitles(req: SubtitleRequest):
    """为视频生成字幕"""
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


@app.post("/api/smart_cut")
async def smart_cut(req: SmartCutRequest):
    """智能剪辑"""
    video_path = req.video_path
    if not os.path.isfile(video_path):
        raise HTTPException(404, f"视频文件不存在: {video_path}")

    info = _get_video_info(video_path)
    duration = float(info.get("format", {}).get("duration", 0))

    system = "你是专业的视频剪辑师。根据视频信息制定剪辑方案，返回 JSON 格式。"
    prompt = f"""视频信息：时长 {duration:.1f}秒，剪辑风格: {req.style}，目标时长: {req.target_duration}秒

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
        "style": req.style,
        "ai_plan": ai_response or "豆包 API 未配置",
        "output_path": output_path,
        "message": "剪辑方案已生成。完整自动剪辑需要配置 ASR 和 FFmpeg 流水线。",
    }


@app.post("/api/long_to_short")
async def long_to_short(req: LongToShortRequest):
    """长视频转短片"""
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


@app.post("/api/full_pipeline")
async def full_pipeline(req: FullPipelineRequest):
    """全自动剪辑流水线"""
    video_path = req.video_path
    if not os.path.isfile(video_path):
        raise HTTPException(404, f"视频文件不存在: {video_path}")

    info = _get_video_info(video_path)
    duration = float(info.get("format", {}).get("duration", 0))

    steps = []

    steps.append({"step": "analyze", "status": "done", "detail": f"视频时长 {duration:.1f}s"})

    if req.add_subtitles:
        steps.append({"step": "subtitle", "status": "ready", "detail": "字幕生成就绪"})

    if req.add_bgm:
        steps.append({"step": "bgm", "status": "ready", "detail": "背景音乐待添加"})

    steps.append({"step": "smart_cut", "status": "ready", "detail": f"剪辑风格: {req.style}"})
    steps.append({"step": "export_draft", "status": "ready", "detail": "导出到剪映草稿"})

    system = "你是视频剪辑总监。为这个视频制定完整的剪辑工作流。"
    prompt = f"""视频: 时长 {duration:.1f}秒
功能: 字幕={req.add_subtitles}, BGM={req.add_bgm}, 风格={req.style}

用一句话总结剪辑策略。"""

    ai_summary = _call_doubao_api(prompt, system)

    return {
        "status": "pipeline_ready",
        "video_path": video_path,
        "steps": steps,
        "ai_strategy": ai_summary or "豆包 API 未配置",
        "message": "流水线已就绪，可逐步执行或导出到剪映。",
    }


@app.post("/api/open_jianying")
async def open_jianying():
    """打开剪映"""
    if not os.path.isfile(JIANYING_EXE):
        raise HTTPException(404, f"剪映未找到: {JIANYING_EXE}")

    subprocess.Popen([JIANYING_EXE], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    return {"status": "ok", "message": "剪映已启动"}


@app.post("/api/draft/open")
async def open_draft_in_jianying(req: OpenDraftRequest):
    """在剪映中打开草稿"""
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


@app.get("/api/drafts")
async def list_drafts():
    """列出所有剪映草稿"""
    if not JIANYING_DRAFT_DIR.exists():
        return {"drafts": [], "message": "剪映草稿目录不存在"}

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
