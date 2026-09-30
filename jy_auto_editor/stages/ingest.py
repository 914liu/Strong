"""Ingest Stage — 素材导入阶段"""

from __future__ import annotations

import logging
from pathlib import Path

from ..core.models import (
    CanvasConfig,
    MediaInfo,
    PipelineContext,
    VideoAsset,
)
from ..core.pipeline import Stage

logger = logging.getLogger(__name__)


class IngestStage(Stage):
    """素材导入阶段

    - 接受视频/音频/图片文件路径
    - 用 FFmpeg 探测媒体信息
    - 生成标准化的 VideoAsset 对象
    """

    name = "ingest"
    dependencies: list[str] = []
    can_skip = False
    timeout = 120

    async def execute(self, context: PipelineContext) -> dict:
        input_data = context.input
        assets = []

        for video_path in input_data.video_paths:
            path = Path(video_path)
            if not path.exists():
                logger.warning(f"File not found: {video_path}")
                continue

            # 探测媒体信息
            media_info = await self._probe_media(str(path))
            asset = VideoAsset(
                path=str(path),
                media_type="video",
                name=path.stem,
                media_info=media_info,
            )
            context.project.source_videos.append(asset)
            assets.append({"path": str(path), "type": "video", "duration_us": media_info.duration_us})
            logger.info(f"Ingested video: {path.name} ({media_info.duration_us / 1e6:.1f}s)")

        for audio_path in input_data.audio_paths:
            path = Path(audio_path)
            if not path.exists():
                continue
            media_info = await self._probe_media(str(path))
            from ..core.models import AudioAsset
            asset = AudioAsset(
                path=str(path),
                name=path.stem,
                duration_us=media_info.duration_us,
            )
            context.project.source_audios.append(asset)
            assets.append({"path": str(path), "type": "audio", "duration_us": media_info.duration_us})

        for image_path in input_data.image_paths:
            path = Path(image_path)
            if not path.exists():
                continue
            asset = VideoAsset(
                path=str(path),
                media_type="image",
                name=path.stem,
            )
            context.project.source_videos.append(asset)
            assets.append({"path": str(path), "type": "image"})

        return {"ingested_assets": assets, "count": len(assets)}

    async def _probe_media(self, file_path: str) -> MediaInfo:
        """用 FFmpeg 探测媒体信息"""
        import asyncio
        info = MediaInfo(path=file_path)
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                file_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                import json
                data = json.loads(stdout)
                fmt = data.get("format", {})
                info.duration_us = int(float(fmt.get("duration", 0)) * 1_000_000)
                info.bitrate = int(fmt.get("bit_rate", 0))
                for stream in data.get("streams", []):
                    if stream.get("codec_type") == "video":
                        info.width = int(stream.get("width", 0))
                        info.height = int(stream.get("height", 0))
                        info.codec = stream.get("codec_name", "")
                        # 解析帧率
                        fps_str = stream.get("r_frame_rate", "30/1")
                        if "/" in fps_str:
                            num, den = fps_str.split("/")
                            info.fps = float(num) / float(den) if float(den) > 0 else 30.0
                    elif stream.get("codec_type") == "audio":
                        info.has_audio = True
        except Exception as e:
            logger.warning(f"ffprobe failed for {file_path}: {e}")
        return info
