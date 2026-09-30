"""ReviewStage 单元测试"""

import asyncio
import pytest

from jy_auto_editor.core.events import reset_event_bus
from jy_auto_editor.core.models import (
    AnalysisResult,
    EditDecision,
    EditDecisionList,
    PipelineContext,
    Segment,
    SubtitleBlock,
    TimeRange,
    Track,
    TrackType,
    VideoAsset,
)
from jy_auto_editor.stages.review import ReviewStage


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_populated_context():
    """创建一个有完整编辑结果的上下文"""
    ctx = PipelineContext()
    ctx.project.name = "测试项目"
    ctx.project.source_videos.append(VideoAsset(path="/fake/video.mp4", name="video"))

    # 视频轨
    video_track = Track(track_type=TrackType.VIDEO)
    video_track.add_segment(Segment(
        segment_id="seg1",
        material_id="mat1",
        source_range=TimeRange(start_us=0, duration_us=10_000_000),
        target_range=TimeRange(start_us=0, duration_us=10_000_000),
    ))
    ctx.project.timeline.add_track(video_track)

    # 文本轨
    text_track = Track(track_type=TrackType.TEXT)
    text_track.add_segment(Segment(
        segment_id="seg2",
        source_range=TimeRange.zero(),
        target_range=TimeRange(start_us=0, duration_us=5_000_000),
    ))
    ctx.project.timeline.add_track(text_track)

    # 字幕
    ctx.project.subtitles.append(SubtitleBlock(
        text="你好",
        time_range=TimeRange(start_us=0, duration_us=2_000_000),
    ))

    # EDL
    ctx.edl = EditDecisionList(decisions=[
        EditDecision(action="cut"),
        EditDecision(action="add_text"),
    ])

    # 分析结果
    ctx.analysis = AnalysisResult(
        transcript="测试文字内容",
        scene_boundaries=[TimeRange(start_us=0, duration_us=5_000_000)],
        highlights=[{"start_second": 0, "end_second": 5}],
        language="zh",
    )

    return ctx


class TestReviewStageMetadata:
    def test_name(self):
        assert ReviewStage.name == "review"

    def test_dependencies(self):
        assert ReviewStage.dependencies == ["edit"]

    def test_can_skip(self):
        assert ReviewStage.can_skip is True

    def test_timeout(self):
        assert ReviewStage.timeout == 3600


class TestShouldSkip:
    def setup_method(self):
        reset_event_bus()

    def test_default_skip(self):
        stage = ReviewStage()
        ctx = PipelineContext()
        assert stage.should_skip(ctx) is True

    def test_enabled_no_skip(self):
        stage = ReviewStage(enabled=True)
        ctx = PipelineContext()
        assert stage.should_skip(ctx) is False

    def test_enable_review_extra(self):
        stage = ReviewStage()
        ctx = PipelineContext(extra={"enable_review": True})
        assert stage.should_skip(ctx) is False

    def test_disabled_with_false_extra(self):
        stage = ReviewStage()
        ctx = PipelineContext(extra={"enable_review": False})
        assert stage.should_skip(ctx) is True


class TestBuildReport:
    def setup_method(self):
        reset_event_bus()

    def test_report_structure(self):
        stage = ReviewStage()
        ctx = _make_populated_context()
        report = stage._build_report(ctx)

        assert report["project_name"] == "测试项目"
        assert report["video_count"] == 1
        assert report["audio_count"] == 0
        assert report["subtitle_count"] == 1
        assert report["track_count"] == 2
        assert report["edl_decision_count"] == 2

    def test_report_tracks_detail(self):
        stage = ReviewStage()
        ctx = _make_populated_context()
        report = stage._build_report(ctx)

        tracks = report["tracks"]
        assert len(tracks) == 2
        types = {t["type"] for t in tracks}
        assert "video" in types
        assert "text" in types

    def test_report_canvas_info(self):
        stage = ReviewStage()
        ctx = _make_populated_context()
        report = stage._build_report(ctx)

        canvas = report["canvas"]
        assert "width" in canvas
        assert "height" in canvas
        assert "ratio" in canvas
        assert "fps" in canvas

    def test_report_analysis_summary(self):
        stage = ReviewStage()
        ctx = _make_populated_context()
        report = stage._build_report(ctx)

        summary = report["analysis_summary"]
        assert summary["transcript_length"] == 6  # len("测试文字内容")
        assert summary["scene_count"] == 1
        assert summary["highlight_count"] == 1
        assert summary["language"] == "zh"

    def test_report_no_analysis(self):
        stage = ReviewStage()
        ctx = _make_populated_context()
        ctx.analysis = None
        report = stage._build_report(ctx)

        assert report["analysis_summary"] == {}

    def test_report_no_edl(self):
        stage = ReviewStage()
        ctx = _make_populated_context()
        ctx.edl = None
        report = stage._build_report(ctx)

        assert report["edl_decision_count"] == 0

    def test_report_duration(self):
        stage = ReviewStage()
        ctx = _make_populated_context()
        report = stage._build_report(ctx)

        assert report["total_duration_seconds"] == 10.0
        assert report["video_duration_seconds"] == 10.0


class TestReviewExecute:
    def setup_method(self):
        reset_event_bus()

    def test_execute_returns_report(self):
        stage = ReviewStage(enabled=True)
        ctx = _make_populated_context()

        result = _run(stage.execute(ctx))

        assert "report" in result
        assert result["status"] == "approved"

    def test_execute_manual_approval(self):
        stage = ReviewStage(enabled=True)
        ctx = _make_populated_context()
        ctx.extra["require_manual_approval"] = True
        ctx.extra["approval_status"] = "approved"

        result = _run(stage.execute(ctx))

        assert result["status"] == "approved"

    def test_execute_manual_rejected(self):
        stage = ReviewStage(enabled=True)
        ctx = _make_populated_context()
        ctx.extra["require_manual_approval"] = True
        ctx.extra["approval_status"] = "rejected"

        result = _run(stage.execute(ctx))

        assert result["status"] == "rejected"


class TestReviewRollback:
    def setup_method(self):
        reset_event_bus()

    def test_rollback_no_crash(self):
        stage = ReviewStage()
        ctx = PipelineContext()
        # rollback 不应抛出异常
        _run(stage.rollback(ctx))
