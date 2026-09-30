"""CV Provider — 基于 PySceneDetect + FFmpeg 的计算机视觉实现"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from .base_provider import CVProvider, SceneBoundary

logger = logging.getLogger(__name__)


class PySceneDetectCVProvider(CVProvider):
    """基于 PySceneDetect 和 FFmpeg 的 CV Provider

    - 场景检测：优先使用 PySceneDetect，回退到 FFmpeg 帧差分析
    - 关键帧提取：使用 FFmpeg 按间隔截帧
    """

    provider_name = "pyscenedetect"

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        self._ffmpeg = ffmpeg_path
        self._scenedetect_available: Optional[bool] = None

    def _check_scenedetect(self) -> bool:
        """检查 PySceneDetect 是否可用（缓存结果）"""
        if self._scenedetect_available is None:
            try:
                from scenedetect import detect  # noqa: F401
                self._scenedetect_available = True
            except ImportError:
                self._scenedetect_available = False
        return self._scenedetect_available

    async def detect_scenes(
        self, video_path: str, threshold: float = 30.0
    ) -> list[SceneBoundary]:
        """检测场景切换点"""
        if self._check_scenedetect():
            return await self._detect_with_scenedetect(video_path, threshold)
        else:
            return await self._detect_with_ffmpeg(video_path, threshold)

    async def _detect_with_scenedetect(
        self, video_path: str, threshold: float
    ) -> list[SceneBoundary]:
        """使用 PySceneDetect 检测场景"""
        try:
            from scenedetect import detect, ContentDetector

            loop = asyncio.get_event_loop()
            scene_list = await loop.run_in_executor(
                None,
                lambda: detect(video_path, ContentDetector(threshold=threshold)),
            )

            boundaries = []
            for scene in scene_list:
                boundaries.append(SceneBoundary(
                    frame_number=scene[0].get_frames(),
                    time_us=int(scene[0].get_seconds() * 1_000_000),
                    confidence=1.0,
                ))

            logger.info(f"PySceneDetect found {len(boundaries)} scenes")
            return boundaries

        except Exception as e:
            logger.error(f"PySceneDetect detection failed: {e}")
            return []

    async def _detect_with_ffmpeg(
        self, video_path: str, threshold: float
    ) -> list[SceneBoundary]:
        """使用 FFmpeg 的 scene filter 检测场景（回退方案）"""
        # FFmpeg scene detection: 输出帧差超过阈值的帧
        cmd = [
            self._ffmpeg,
            "-i", video_path,
            "-vf", f"select='gt(scene,{threshold / 100})',showinfo",
            "-f", "null",
            "-",
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()
            stderr_text = stderr.decode(errors="replace")

            boundaries = []
            for line in stderr_text.split("\n"):
                if "pts_time:" in line:
                    try:
                        pts_time = float(line.split("pts_time:")[1].split()[0])
                        nframe = 0
                        if "n:" in line:
                            nframe = int(line.split("n:")[1].split()[0])
                        boundaries.append(SceneBoundary(
                            frame_number=nframe,
                            time_us=int(pts_time * 1_000_000),
                            confidence=threshold / 100,
                        ))
                    except (ValueError, IndexError):
                        continue

            logger.info(f"FFmpeg scene detection found {len(boundaries)} scenes")
            return boundaries

        except FileNotFoundError:
            logger.error("FFmpeg not found for scene detection")
            return []
        except Exception as e:
            logger.error(f"FFmpeg scene detection failed: {e}")
            return []

    async def extract_keyframes(
        self, video_path: str, interval_seconds: float = 1.0
    ) -> list[str]:
        """提取关键帧图片"""
        output_dir = Path(video_path).parent / f"{Path(video_path).stem}_keyframes"
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self._ffmpeg,
            "-i", video_path,
            "-vf", f"fps=1/{interval_seconds}",
            "-q:v", "2",
            "-y",
            str(output_dir / "frame_%04d.jpg"),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(f"Keyframe extraction failed: {stderr.decode()}")
                return []

            # 收集生成的帧文件
            frames = sorted(output_dir.glob("frame_*.jpg"))
            frame_paths = [str(f) for f in frames]

            logger.info(f"Extracted {len(frame_paths)} keyframes to {output_dir}")
            return frame_paths

        except FileNotFoundError:
            logger.error("FFmpeg not found for keyframe extraction")
            return []
        except Exception as e:
            logger.error(f"Keyframe extraction failed: {e}")
            return []

    async def is_available(self) -> bool:
        """检查是否可用（FFmpeg 必须，PySceneDetect 可选）"""
        try:
            proc = await asyncio.create_subprocess_exec(
                self._ffmpeg, "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
