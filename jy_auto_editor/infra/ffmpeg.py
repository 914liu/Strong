"""
FFmpeg 工具封装 - 音视频处理基础设施

提供 ffprobe 探测、音频提取、视频裁剪等基础能力。
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from jy_auto_editor.core.exceptions import FFmpegError

logger = logging.getLogger(__name__)


class FFmpegWrapper:
    """FFmpeg/FFprobe 封装"""

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        self.ffmpeg = ffmpeg_path
        self.ffprobe = ffprobe_path

    async def probe(self, media_path: Path) -> dict:
        """
        探测媒体文件信息

        Returns:
            ffprobe JSON 输出
        """
        cmd = [
            self.ffprobe,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(media_path),
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        except FileNotFoundError:
            raise FFmpegError(f"ffprobe not found at: {self.ffprobe}")

        if proc.returncode != 0:
            raise FFmpegError(f"ffprobe failed: {stderr.decode()}")

        return json.loads(stdout.decode())

    async def get_duration(self, media_path: Path) -> float:
        """获取媒体时长(秒)"""
        info = await self.probe(media_path)
        return float(info["format"]["duration"])

    async def extract_audio(
        self,
        video_path: Path,
        output_path: Path,
        sample_rate: int = 16000,
        channels: int = 1,
    ) -> Path:
        """
        从视频提取音频(WAV)

        Args:
            video_path: 输入视频路径
            output_path: 输出音频路径
            sample_rate: 采样率
            channels: 声道数

        Returns:
            输出文件路径
        """
        cmd = [
            self.ffmpeg,
            "-i", str(video_path),
            "-vn",                    # 无视频
            "-acodec", "pcm_s16le",   # PCM 16bit
            "-ar", str(sample_rate),
            "-ac", str(channels),
            "-y",                     # 覆盖
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise FFmpegError(f"Audio extraction failed: {stderr.decode()}")

        logger.info(f"Extracted audio: {video_path.name} -> {output_path.name}")
        return output_path

    async def cut_segment(
        self,
        input_path: Path,
        output_path: Path,
        start: float,
        duration: float,
    ) -> Path:
        """
        裁剪视频片段

        Args:
            input_path: 输入视频
            output_path: 输出视频
            start: 开始时间(秒)
            duration: 持续时间(秒)

        Returns:
            输出文件路径
        """
        cmd = [
            self.ffmpeg,
            "-ss", str(start),
            "-i", str(input_path),
            "-t", str(duration),
            "-c", "copy",
            "-y",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise FFmpegError(f"Video cut failed: {stderr.decode()}")

        return output_path

    async def concat_videos(
        self,
        input_paths: list[Path],
        output_path: Path,
    ) -> Path:
        """
        拼接多个视频

        使用 concat demuxer 方式拼接。
        """
        # 创建文件列表
        list_file = output_path.parent / "_concat_list.txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for p in input_paths:
                f.write(f"file '{p.as_posix()}'\n")

        cmd = [
            self.ffmpeg,
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            "-y",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        # 清理临时文件
        list_file.unlink(missing_ok=True)

        if proc.returncode != 0:
            raise FFmpegError(f"Video concat failed: {stderr.decode()}")

        return output_path

    async def check_available(self) -> bool:
        """检查 ffmpeg 是否可用"""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg, "-version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode == 0
        except FileNotFoundError:
            return False
