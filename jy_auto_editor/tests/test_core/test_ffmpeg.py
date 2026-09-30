"""infra/ffmpeg 单元测试"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import patch, AsyncMock

from jy_auto_editor.infra.ffmpeg import FFmpegWrapper
from jy_auto_editor.core.exceptions import FFmpegError


class TestFFmpegWrapper:
    def test_creation_defaults(self):
        ff = FFmpegWrapper()
        assert ff.ffmpeg == "ffmpeg"
        assert ff.ffprobe == "ffprobe"

    def test_creation_custom_paths(self):
        ff = FFmpegWrapper(ffmpeg_path="/usr/local/bin/ffmpeg",
                           ffprobe_path="/usr/local/bin/ffprobe")
        assert ff.ffmpeg == "/usr/local/bin/ffmpeg"
        assert ff.ffprobe == "/usr/local/bin/ffprobe"

    def test_check_available_returns_bool(self):
        ff = FFmpegWrapper()
        result = asyncio.get_event_loop().run_until_complete(
            ff.check_available()
        )
        # Just verify it returns a bool without crashing
        assert isinstance(result, bool)

    def test_probe_raises_on_failure(self):
        ff = FFmpegWrapper(ffprobe_path="/nonexistent/ffprobe")
        with pytest.raises(FFmpegError):
            asyncio.get_event_loop().run_until_complete(
                ff.probe(Path("/nonexistent/video.mp4"))
            )
