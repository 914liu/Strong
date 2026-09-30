"""IngestStage 单元测试"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from jy_auto_editor.core.events import reset_event_bus
from jy_auto_editor.core.models import (
    AudioAsset,
    CanvasConfig,
    MediaInfo,
    PipelineContext,
    ProjectInput,
    VideoAsset,
)
from jy_auto_editor.infra.ffmpeg import FFmpegWrapper
from jy_auto_editor.stages.ingest import IngestStage, DEFAULT_IMAGE_DURATION_US


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_ffprobe_result(
    duration=10.0,
    width=1920,
    height=1080,
    codec="h264",
    has_audio=True,
    fps="30/1",
):
    """构造 ffprobe JSON 输出"""
    streams = []
    if width > 0:
        streams.append({
            "codec_type": "video",
            "width": width,
            "height": height,
            "codec_name": codec,
            "r_frame_rate": fps,
        })
    if has_audio:
        streams.append({
            "codec_type": "audio",
            "codec_name": "aac",
        })
    return {
        "format": {
            "duration": str(duration),
            "bit_rate": "5000000",
        },
        "streams": streams,
    }


class TestIngestStageMetadata:
    def test_name(self):
        stage = IngestStage()
        assert stage.name == "ingest"

    def test_dependencies_empty(self):
        stage = IngestStage()
        assert stage.dependencies == []

    def test_cannot_skip(self):
        assert IngestStage.can_skip is False

    def test_timeout(self):
        assert IngestStage.timeout == 120

    def test_custom_ffmpeg(self):
        ff = MagicMock(spec=FFmpegWrapper)
        stage = IngestStage(ffmpeg=ff)
        assert stage._ffmpeg is ff


class TestIngestValidate:
    def setup_method(self):
        reset_event_bus()

    def test_no_inputs_returns_false(self):
        stage = IngestStage()
        ctx = PipelineContext(input=ProjectInput())
        result = _run(stage.validate(ctx))
        assert result is False

    def test_with_video_path_returns_true(self):
        stage = IngestStage()
        ctx = PipelineContext(input=ProjectInput(video_paths=["/fake/video.mp4"]))
        result = _run(stage.validate(ctx))
        assert result is True

    def test_with_audio_only_returns_true(self):
        stage = IngestStage()
        ctx = PipelineContext(input=ProjectInput(audio_paths=["/fake/audio.wav"]))
        result = _run(stage.validate(ctx))
        assert result is True

    def test_with_image_only_returns_true(self):
        stage = IngestStage()
        ctx = PipelineContext(input=ProjectInput(image_paths=["/fake/img.png"]))
        result = _run(stage.validate(ctx))
        assert result is True


class TestIngestExecute:
    def setup_method(self):
        reset_event_bus()

    def test_ingest_video(self, tmp_path):
        video_file = tmp_path / "test.mp4"
        video_file.write_bytes(b"\x00" * 100)

        mock_ffmpeg = MagicMock(spec=FFmpegWrapper)
        mock_ffmpeg.probe = AsyncMock(return_value=_make_ffprobe_result(
            duration=15.0, width=1920, height=1080,
        ))

        stage = IngestStage(ffmpeg=mock_ffmpeg)
        ctx = PipelineContext(input=ProjectInput(video_paths=[str(video_file)]))

        result = _run(stage.execute(ctx))

        assert result["count"] == 1
        assert result["video_count"] == 1
        assert result["audio_count"] == 0
        assert result["image_count"] == 0
        assert len(ctx.project.source_videos) == 1

        asset = ctx.project.source_videos[0]
        assert asset.media_type == "video"
        assert asset.name == "test"
        assert asset.media_info is not None
        assert asset.media_info.duration_us == 15_000_000
        assert asset.media_info.width == 1920
        assert asset.media_info.height == 1080

    def test_ingest_audio(self, tmp_path):
        audio_file = tmp_path / "bgm.wav"
        audio_file.write_bytes(b"\x00" * 100)

        mock_ffmpeg = MagicMock(spec=FFmpegWrapper)
        mock_ffmpeg.probe = AsyncMock(return_value=_make_ffprobe_result(
            duration=30.0, width=0, height=0, has_audio=True,
        ))

        stage = IngestStage(ffmpeg=mock_ffmpeg)
        ctx = PipelineContext(input=ProjectInput(audio_paths=[str(audio_file)]))

        result = _run(stage.execute(ctx))

        assert result["count"] == 1
        assert result["audio_count"] == 1
        assert len(ctx.project.source_audios) == 1

        asset = ctx.project.source_audios[0]
        assert asset.name == "bgm"
        assert asset.duration_us == 30_000_000

    def test_ingest_image(self, tmp_path):
        img_file = tmp_path / "cover.png"
        img_file.write_bytes(b"\x00" * 100)

        mock_ffmpeg = MagicMock(spec=FFmpegWrapper)
        mock_ffmpeg.probe = AsyncMock(return_value=_make_ffprobe_result(
            duration=0, width=1080, height=1920, has_audio=False,
        ))

        stage = IngestStage(ffmpeg=mock_ffmpeg)
        ctx = PipelineContext(input=ProjectInput(image_paths=[str(img_file)]))

        result = _run(stage.execute(ctx))

        assert result["count"] == 1
        assert result["image_count"] == 1
        assert len(ctx.project.source_videos) == 1

        asset = ctx.project.source_videos[0]
        assert asset.media_type == "image"
        # 图片使用默认时长
        assert result["ingested_assets"][0]["duration_us"] == DEFAULT_IMAGE_DURATION_US

    def test_missing_file_skipped(self, tmp_path):
        mock_ffmpeg = MagicMock(spec=FFmpegWrapper)
        stage = IngestStage(ffmpeg=mock_ffmpeg)

        ctx = PipelineContext(input=ProjectInput(
            video_paths=[str(tmp_path / "nonexistent.mp4")],
        ))
        result = _run(stage.execute(ctx))

        assert result["count"] == 0
        mock_ffmpeg.probe.assert_not_called()

    def test_mixed_inputs(self, tmp_path):
        video_file = tmp_path / "clip.mp4"
        video_file.write_bytes(b"\x00" * 100)
        audio_file = tmp_path / "music.wav"
        audio_file.write_bytes(b"\x00" * 100)

        mock_ffmpeg = MagicMock(spec=FFmpegWrapper)
        mock_ffmpeg.probe = AsyncMock(side_effect=[
            _make_ffprobe_result(duration=10.0, width=1920, height=1080),
            _make_ffprobe_result(duration=20.0, width=0, height=0, has_audio=True),
        ])

        stage = IngestStage(ffmpeg=mock_ffmpeg)
        ctx = PipelineContext(input=ProjectInput(
            video_paths=[str(video_file)],
            audio_paths=[str(audio_file)],
        ))

        result = _run(stage.execute(ctx))

        assert result["count"] == 2
        assert result["video_count"] == 1
        assert result["audio_count"] == 1
        assert len(ctx.project.source_videos) == 1
        assert len(ctx.project.source_audios) == 1

    def test_ffprobe_failure_returns_zero_info(self, tmp_path):
        video_file = tmp_path / "broken.mp4"
        video_file.write_bytes(b"\x00" * 100)

        mock_ffmpeg = MagicMock(spec=FFmpegWrapper)
        mock_ffmpeg.probe = AsyncMock(side_effect=Exception("ffprobe crash"))

        stage = IngestStage(ffmpeg=mock_ffmpeg)
        ctx = PipelineContext(input=ProjectInput(video_paths=[str(video_file)]))

        result = _run(stage.execute(ctx))

        # 即使 ffprobe 失败，仍应返回资产（只是信息为空）
        assert result["count"] == 1
        asset = ctx.project.source_videos[0]
        assert asset.media_info.duration_us == 0


class TestCanvasDetection:
    def setup_method(self):
        reset_event_bus()

    def test_horizontal_detection(self):
        stage = IngestStage()
        assets = [{"width": 1920, "height": 1080}]
        config = stage._detect_canvas_config(assets)
        assert config.ratio == "16:9"

    def test_vertical_detection(self):
        stage = IngestStage()
        assets = [{"width": 1080, "height": 1920}]
        config = stage._detect_canvas_config(assets)
        assert config.ratio == "9:16"

    def test_square_detection(self):
        stage = IngestStage()
        assets = [{"width": 1080, "height": 1080}]
        config = stage._detect_canvas_config(assets)
        assert config.ratio == "1:1"

    def test_no_dimensions_defaults_horizontal(self):
        stage = IngestStage()
        assets = [{"width": 0, "height": 0}]
        config = stage._detect_canvas_config(assets)
        assert config.ratio == "16:9"

    def test_empty_assets_defaults_horizontal(self):
        stage = IngestStage()
        config = stage._detect_canvas_config([])
        assert config.ratio == "16:9"


class TestIngestRollback:
    def setup_method(self):
        reset_event_bus()

    def test_rollback_clears_assets(self):
        stage = IngestStage()
        ctx = PipelineContext()
        ctx.project.source_videos.append(VideoAsset(path="/fake.mp4"))
        ctx.project.source_audios.append(AudioAsset(path="/fake.wav"))

        _run(stage.rollback(ctx))

        assert len(ctx.project.source_videos) == 0
        assert len(ctx.project.source_audios) == 0
