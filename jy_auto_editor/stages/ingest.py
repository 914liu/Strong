"""Ingest Stage — 素材导入阶段

职责：
1. 校验输入文件存在性
2. 用 FFprobe 探测所有媒体文件的元信息
3. 生成标准化的 Asset 对象写入 PipelineContext
4. 发出进度事件
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..core.events import Event, EventType, get_event_bus
from ..core.exceptions import ValidationError
from ..core.models import (
    AudioAsset,
    CanvasConfig,
    MediaInfo,
    PipelineContext,
    VideoAsset,
)
from ..core.pipeline import Stage
from ..infra.ffmpeg import FFmpegWrapper

logger = logging.getLogger(__name__)

# 图片默认展示时长（微秒）
DEFAULT_IMAGE_DURATION_US = 5_000_000  # 5 秒


class IngestStage(Stage):
    """素材导入阶段

    - 接受视频/音频/图片文件路径
    - 用 FFprobe 探测媒体信息
    - 生成标准化的 VideoAsset / AudioAsset 对象
    """

    name = "ingest"
    dependencies: list[str] = []
    can_skip = False
    timeout = 120

    def __init__(self, ffmpeg: FFmpegWrapper | None = None) -> None:
        self._ffmpeg = ffmpeg or FFmpegWrapper()

    async def validate(self, context: PipelineContext) -> bool:
        """校验至少有一个输入文件"""
        inp = context.input
        total = len(inp.video_paths) + len(inp.audio_paths) + len(inp.image_paths)
        if total == 0:
            logger.error("IngestStage: no input files provided")
            return False
        return True

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        input_data = context.input
        event_bus = get_event_bus()
        assets: list[dict[str, Any]] = []

        total_files = (
            len(input_data.video_paths)
            + len(input_data.audio_paths)
            + len(input_data.image_paths)
        )
        processed = 0

        # ── 视频文件 ────────────────────────────────
        for video_path in input_data.video_paths:
            path = Path(video_path)
            if not path.exists():
                logger.warning(f"Video file not found, skipping: {video_path}")
                continue

            media_info = await self._probe_media(str(path))
            asset = VideoAsset(
                path=str(path.resolve()),
                media_type="video",
                name=path.stem,
                media_info=media_info,
            )
            context.project.source_videos.append(asset)
            assets.append({
                "path": str(path.resolve()),
                "type": "video",
                "name": path.stem,
                "duration_us": media_info.duration_us,
                "width": media_info.width,
                "height": media_info.height,
            })
            logger.info(
                f"Ingested video: {path.name} "
                f"({media_info.duration_us / 1e6:.1f}s, "
                f"{media_info.width}x{media_info.height})"
            )

            processed += 1
            await event_bus.emit_async(Event(
                type=EventType.STAGE_PROGRESS,
                data={
                    "stage": self.name,
                    "progress": processed / total_files,
                    "current_file": path.name,
                },
                source=self.name,
            ))

        # ── 音频文件 ────────────────────────────────
        for audio_path in input_data.audio_paths:
            path = Path(audio_path)
            if not path.exists():
                logger.warning(f"Audio file not found, skipping: {audio_path}")
                continue

            media_info = await self._probe_media(str(path))
            asset = AudioAsset(
                path=str(path.resolve()),
                name=path.stem,
                duration_us=media_info.duration_us,
            )
            context.project.source_audios.append(asset)
            assets.append({
                "path": str(path.resolve()),
                "type": "audio",
                "name": path.stem,
                "duration_us": media_info.duration_us,
            })
            logger.info(f"Ingested audio: {path.name} ({media_info.duration_us / 1e6:.1f}s)")

            processed += 1
            await event_bus.emit_async(Event(
                type=EventType.STAGE_PROGRESS,
                data={
                    "stage": self.name,
                    "progress": processed / total_files,
                    "current_file": path.name,
                },
                source=self.name,
            ))

        # ── 图片文件 ────────────────────────────────
        for image_path in input_data.image_paths:
            path = Path(image_path)
            if not path.exists():
                logger.warning(f"Image file not found, skipping: {image_path}")
                continue

            media_info = await self._probe_media(str(path))
            asset = VideoAsset(
                path=str(path.resolve()),
                media_type="image",
                name=path.stem,
                media_info=media_info,
            )
            context.project.source_videos.append(asset)
            assets.append({
                "path": str(path.resolve()),
                "type": "image",
                "name": path.stem,
                "duration_us": DEFAULT_IMAGE_DURATION_US,
                "width": media_info.width,
                "height": media_info.height,
            })
            logger.info(f"Ingested image: {path.name} ({media_info.width}x{media_info.height})")

            processed += 1
            await event_bus.emit_async(Event(
                type=EventType.STAGE_PROGRESS,
                data={
                    "stage": self.name,
                    "progress": processed / total_files,
                    "current_file": path.name,
                },
                source=self.name,
            ))

        # ── 自动检测画布配置 ────────────────────────
        if not context.input.canvas_config.width:
            context.input.canvas_config = self._detect_canvas_config(assets)

        return {
            "ingested_assets": assets,
            "count": len(assets),
            "video_count": sum(1 for a in assets if a["type"] == "video"),
            "audio_count": sum(1 for a in assets if a["type"] == "audio"),
            "image_count": sum(1 for a in assets if a["type"] == "image"),
        }

    async def _probe_media(self, file_path: str) -> MediaInfo:
        """用 FFprobe 探测媒体信息"""
        info = MediaInfo(path=file_path)
        try:
            result = await self._ffmpeg.probe(Path(file_path))
            fmt = result.get("format", {})
            info.duration_us = int(float(fmt.get("duration", 0)) * 1_000_000)
            info.bitrate = int(fmt.get("bit_rate", 0))

            for stream in result.get("streams", []):
                codec_type = stream.get("codec_type", "")
                if codec_type == "video":
                    info.width = int(stream.get("width", 0))
                    info.height = int(stream.get("height", 0))
                    info.codec = stream.get("codec_name", "")
                    # 解析帧率 (r_frame_rate 格式为 "30/1")
                    fps_str = stream.get("r_frame_rate", "30/1")
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        info.fps = float(num) / float(den) if float(den) > 0 else 30.0
                    else:
                        info.fps = float(fps_str) if fps_str else 30.0
                elif codec_type == "audio":
                    info.has_audio = True

        except Exception as e:
            logger.warning(f"ffprobe failed for {file_path}: {e}")

        return info

    def _detect_canvas_config(self, assets: list[dict]) -> CanvasConfig:
        """根据第一个视频素材的分辨率自动选择画布配置"""
        for asset in assets:
            w = asset.get("width", 0)
            h = asset.get("height", 0)
            if w > 0 and h > 0:
                ratio = w / h
                if ratio > 1.3:
                    return CanvasConfig.horizontal()
                elif ratio < 0.77:
                    return CanvasConfig.vertical()
                else:
                    return CanvasConfig.square()
        return CanvasConfig.horizontal()

    async def rollback(self, context: PipelineContext) -> None:
        """回滚：清空已导入的素材"""
        context.project.source_videos.clear()
        context.project.source_audios.clear()
        logger.info("IngestStage rolled back: cleared all ingested assets")
