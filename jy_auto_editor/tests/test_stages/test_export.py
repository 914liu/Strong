"""ExportStage 单元测试"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from jy_auto_editor.core.events import reset_event_bus
from jy_auto_editor.core.models import (
    ExportResult,
    PipelineContext,
    Segment,
    SubtitleBlock,
    TimeRange,
    Track,
    TrackType,
    VideoAsset,
    AudioAsset,
    Effect,
    Transition,
)
from jy_auto_editor.stages.export import ExportStage


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_populated_context(temp_dir=""):
    """创建带时间线内容的上下文"""
    ctx = PipelineContext(temp_dir=temp_dir)
    ctx.project.name = "测试项目"
    ctx.project.project_id = "TEST_PROJECT_001"

    # 视频素材
    ctx.project.source_videos.append(VideoAsset(
        path="/fake/video.mp4", name="video", media_type="video",
    ))
    # 音频素材
    ctx.project.source_audios.append(AudioAsset(
        path="/fake/bgm.wav", name="bgm", duration_us=10_000_000,
    ))

    # 视频轨
    video_track = Track(track_type=TrackType.VIDEO)
    seg = Segment(
        segment_id="seg1",
        material_id="mat1",
        source_range=TimeRange(start_us=0, duration_us=10_000_000),
        target_range=TimeRange(start_us=0, duration_us=10_000_000),
    )
    seg.effects.append(Effect(effect_type="filter", effect_name="blur"))
    seg.transitions.append(Transition(transition_type="dissolve", duration_us=500_000))
    video_track.add_segment(seg)
    ctx.project.timeline.add_track(video_track)

    # 字幕
    ctx.project.subtitles.append(SubtitleBlock(
        text="你好世界",
        time_range=TimeRange(start_us=0, duration_us=2_000_000),
        font_name="微软雅黑",
        font_size=12.0,
    ))

    return ctx


class TestExportStageMetadata:
    def test_name(self):
        assert ExportStage.name == "export"

    def test_dependencies(self):
        assert ExportStage.dependencies == ["edit"]

    def test_timeout(self):
        assert ExportStage.timeout == 600


class TestExportValidate:
    def setup_method(self):
        reset_event_bus()

    def test_no_tracks_returns_false(self):
        stage = ExportStage()
        ctx = PipelineContext()
        assert _run(stage.validate(ctx)) is False

    def test_with_tracks_returns_true(self):
        stage = ExportStage()
        ctx = PipelineContext()
        ctx.project.timeline.add_track(Track(track_type=TrackType.VIDEO))
        assert _run(stage.validate(ctx)) is True


class TestJSONExport:
    def setup_method(self):
        reset_event_bus()

    def test_json_export_creates_file(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        result = _run(stage.execute(ctx))

        assert result["success"] is True
        assert result["status"] == "json_exported"
        assert result["mode"] == "json"

        output_path = Path(result["output_path"])
        assert output_path.exists()
        assert result["file_size"] > 0

    def test_json_export_content(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        result = _run(stage.execute(ctx))

        output_path = Path(result["output_path"])
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert data["project_id"] == "TEST_PROJECT_001"
        assert data["name"] == "测试项目"
        assert len(data["tracks"]) == 1
        assert data["tracks"][0]["type"] == "video"
        assert len(data["tracks"][0]["segments"]) == 1
        assert len(data["subtitles"]) == 1
        assert data["subtitles"][0]["text"] == "你好世界"
        assert data["total_duration_us"] == 10_000_000

    def test_json_export_sets_export_result(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        _run(stage.execute(ctx))

        assert ctx.export_result is not None
        assert ctx.export_result.success is True
        assert ctx.export_result.file_size_bytes > 0

    def test_json_export_includes_canvas(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        result = _run(stage.execute(ctx))

        output_path = Path(result["output_path"])
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "canvas" in data
        assert data["canvas"]["width"] == 1920
        assert data["canvas"]["height"] == 1080

    def test_json_export_includes_metadata(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        result = _run(stage.execute(ctx))

        output_path = Path(result["output_path"])
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert "metadata" in data
        assert data["metadata"]["exporter"] == "jy_auto_editor"

    def test_json_export_source_info(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        result = _run(stage.execute(ctx))

        output_path = Path(result["output_path"])
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assert len(data["source_videos"]) == 1
        assert data["source_videos"][0]["path"] == "/fake/video.mp4"
        assert len(data["source_audios"]) == 1
        assert data["source_audios"][0]["path"] == "/fake/bgm.wav"


class TestDriverExport:
    def setup_method(self):
        reset_event_bus()

    def test_driver_export_success(self, tmp_path):
        mock_driver = AsyncMock()
        mock_driver.save_project = AsyncMock(return_value="/drafts/project")
        mock_driver.export_video = AsyncMock(return_value=ExportResult(
            success=True,
            output_path="/output/video.mp4",
            file_size_bytes=1_000_000,
        ))

        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))
        ctx.extra["driver"] = mock_driver

        result = _run(stage.execute(ctx))

        assert result["success"] is True
        assert result["status"] == "exported"
        assert result["output_path"] == "/output/video.mp4"
        assert result["project_path"] == "/drafts/project"
        assert ctx.export_result.success is True

    def test_driver_save_fails(self, tmp_path):
        mock_driver = AsyncMock()
        mock_driver.save_project = AsyncMock(side_effect=RuntimeError("save failed"))

        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))
        ctx.extra["driver"] = mock_driver

        result = _run(stage.execute(ctx))

        assert result["success"] is False
        assert result["status"] == "save_failed"

    def test_driver_export_fails(self, tmp_path):
        mock_driver = AsyncMock()
        mock_driver.save_project = AsyncMock(return_value="/drafts/project")
        mock_driver.export_video = AsyncMock(side_effect=RuntimeError("export crash"))

        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))
        ctx.extra["driver"] = mock_driver

        result = _run(stage.execute(ctx))

        assert result["success"] is False
        assert result["status"] == "export_failed"
        assert ctx.export_result.success is False


class TestSerializeProject:
    def setup_method(self):
        reset_event_bus()

    def test_serialize_basic(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        data = stage._serialize_project(ctx)

        assert data["project_id"] == "TEST_PROJECT_001"
        assert data["name"] == "测试项目"
        assert isinstance(data["tracks"], list)
        assert isinstance(data["subtitles"], list)

    def test_serialize_segment_details(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        data = stage._serialize_project(ctx)

        seg = data["tracks"][0]["segments"][0]
        assert seg["segment_id"] == "seg1"
        assert seg["material_id"] == "mat1"
        assert seg["source_range"]["start_us"] == 0
        assert seg["source_range"]["duration_us"] == 10_000_000
        assert seg["speed"] == 1.0

    def test_serialize_effects_and_transitions(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        data = stage._serialize_project(ctx)

        seg = data["tracks"][0]["segments"][0]
        assert len(seg["effects"]) == 1
        assert seg["effects"][0]["type"] == "filter"
        assert seg["effects"][0]["name"] == "blur"
        assert len(seg["transitions"]) == 1
        assert seg["transitions"][0]["type"] == "dissolve"

    def test_serialize_subtitle_details(self, tmp_path):
        stage = ExportStage()
        ctx = _make_populated_context(temp_dir=str(tmp_path))

        data = stage._serialize_project(ctx)

        sub = data["subtitles"][0]
        assert sub["text"] == "你好世界"
        assert sub["font_name"] == "微软雅黑"
        assert sub["font_size"] == 12.0


class TestExportRollback:
    def setup_method(self):
        reset_event_bus()

    def test_rollback_clears_export_result(self):
        stage = ExportStage()
        ctx = PipelineContext()
        ctx.export_result = ExportResult(success=True, output_path="/output.mp4")

        _run(stage.rollback(ctx))
        assert ctx.export_result is None
