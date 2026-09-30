"""EditStage 单元测试"""

import asyncio
import pytest
from unittest.mock import MagicMock

from jy_auto_editor.core.events import reset_event_bus
from jy_auto_editor.core.models import (
    AnalysisResult,
    AudioAsset,
    EditDecision,
    EditDecisionList,
    PipelineContext,
    ProjectInput,
    Segment,
    SubtitleBlock,
    TimeRange,
    Track,
    TrackType,
    VideoAsset,
    MediaInfo,
)
from jy_auto_editor.stages.edit import EditStage


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_context(
    highlights=None,
    subtitles=None,
    scene_boundaries=None,
    video_duration_us=60_000_000,
    extra_params=None,
    source_audios=None,
):
    """创建带分析结果的 PipelineContext"""
    ctx = PipelineContext(
        input=ProjectInput(extra_params=extra_params or {}),
    )
    ctx.project.source_videos.append(VideoAsset(
        asset_id="VIDEO_001",
        path="/fake/video.mp4",
        media_info=MediaInfo(path="/fake/video.mp4", duration_us=video_duration_us),
    ))
    if source_audios:
        for a in source_audios:
            ctx.project.source_audios.append(a)

    ctx.analysis = AnalysisResult(
        highlights=highlights or [],
        subtitles=subtitles or [],
        scene_boundaries=scene_boundaries or [],
    )
    return ctx


class TestEditStageMetadata:
    def test_name(self):
        assert EditStage.name == "edit"

    def test_dependencies(self):
        assert EditStage.dependencies == ["analyze"]

    def test_timeout(self):
        assert EditStage.timeout == 300


class TestEditValidate:
    def setup_method(self):
        reset_event_bus()

    def test_no_analysis_returns_false(self):
        stage = EditStage()
        ctx = PipelineContext()
        ctx.analysis = None
        assert _run(stage.validate(ctx)) is False

    def test_with_analysis_returns_true(self):
        stage = EditStage()
        ctx = PipelineContext()
        ctx.analysis = AnalysisResult()
        assert _run(stage.validate(ctx)) is True


class TestVideoDecisions:
    """测试 EDL 视频决策生成"""

    def setup_method(self):
        reset_event_bus()

    def test_highlight_mode(self):
        """有高光时使用高光模式"""
        stage = EditStage()
        ctx = _make_context(
            highlights=[
                {"start_second": 1.0, "end_second": 5.0, "score": 0.9},
                {"start_second": 10.0, "end_second": 15.0, "score": 0.7},
            ]
        )
        edl = EditDecisionList()
        stage._build_video_decisions(ctx, edl)

        assert len(edl.decisions) == 2
        assert edl.decisions[0].action == "cut"
        assert edl.decisions[0].params["source_start_us"] == 1_000_000
        assert edl.decisions[0].params["source_end_us"] == 5_000_000

    def test_smart_cut_mode(self):
        """有场景边界 + 目标时长时使用智能裁剪"""
        stage = EditStage()
        scenes = [
            TimeRange(start_us=0, duration_us=10_000_000),
            TimeRange(start_us=10_000_000, duration_us=10_000_000),
            TimeRange(start_us=20_000_000, duration_us=10_000_000),
        ]
        ctx = _make_context(
            scene_boundaries=scenes,
            extra_params={"target_duration": 15},  # 15 秒 = 15_000_000 us
        )
        edl = EditDecisionList()
        stage._build_video_decisions(ctx, edl)

        # 应选中足够的场景来接近目标时长
        assert len(edl.decisions) >= 1
        for d in edl.decisions:
            assert d.action == "cut"

    def test_full_video_mode(self):
        """没有高光也没有目标时长时使用完整视频"""
        stage = EditStage()
        ctx = _make_context(video_duration_us=30_000_000)
        edl = EditDecisionList()
        stage._build_video_decisions(ctx, edl)

        assert len(edl.decisions) == 1
        assert edl.decisions[0].params["source_start_us"] == 0
        assert edl.decisions[0].params["source_end_us"] == 30_000_000

    def test_skip_invalid_highlights(self):
        """跳过 end <= start 的高光片段"""
        stage = EditStage()
        ctx = _make_context(
            highlights=[
                {"start_second": 5.0, "end_second": 3.0},  # 无效
                {"start_second": 1.0, "end_second": 4.0},  # 有效
            ]
        )
        edl = EditDecisionList()
        stage._build_video_decisions(ctx, edl)

        assert len(edl.decisions) == 1


class TestSubtitleDecisions:
    def setup_method(self):
        reset_event_bus()

    def test_subtitle_block_input(self):
        stage = EditStage()
        subtitles = [
            SubtitleBlock(text="你好", time_range=TimeRange(start_us=0, duration_us=2_000_000)),
            SubtitleBlock(text="世界", time_range=TimeRange(start_us=2_000_000, duration_us=2_000_000)),
        ]
        ctx = _make_context(subtitles=subtitles)
        edl = EditDecisionList()
        stage._build_subtitle_decisions(ctx, edl)

        assert len(edl.decisions) == 2
        assert edl.decisions[0].action == "add_text"
        assert edl.decisions[0].params["text"] == "你好"

    def test_skip_empty_subtitles(self):
        stage = EditStage()
        subtitles = [
            SubtitleBlock(text="", time_range=TimeRange(start_us=0, duration_us=2_000_000)),
            SubtitleBlock(text="  ", time_range=TimeRange(start_us=2_000_000, duration_us=2_000_000)),
            SubtitleBlock(text="有效", time_range=TimeRange(start_us=4_000_000, duration_us=2_000_000)),
        ]
        ctx = _make_context(subtitles=subtitles)
        edl = EditDecisionList()
        stage._build_subtitle_decisions(ctx, edl)

        assert len(edl.decisions) == 1
        assert edl.decisions[0].params["text"] == "有效"


class TestBGMDecisions:
    def setup_method(self):
        reset_event_bus()

    def test_bgm_from_extra_params(self):
        stage = EditStage()
        ctx = _make_context(extra_params={"bgm_path": "/music/bgm.mp3"})
        edl = EditDecisionList()
        stage._build_bgm_decisions(ctx, edl)

        assert len(edl.decisions) == 1
        assert edl.decisions[0].action == "add_bgm"
        assert edl.decisions[0].params["bgm_path"] == "/music/bgm.mp3"

    def test_bgm_from_source_audios(self):
        stage = EditStage()
        ctx = _make_context(source_audios=[
            AudioAsset(path="/music/a.wav", duration_us=10_000_000),
        ])
        edl = EditDecisionList()
        stage._build_bgm_decisions(ctx, edl)

        assert len(edl.decisions) == 1
        assert edl.decisions[0].params["bgm_path"] == "/music/a.wav"

    def test_no_bgm(self):
        stage = EditStage()
        ctx = _make_context()
        edl = EditDecisionList()
        stage._build_bgm_decisions(ctx, edl)

        assert len(edl.decisions) == 0


class TestEffectDecisions:
    def setup_method(self):
        reset_event_bus()

    def test_transitions_disabled_by_default(self):
        stage = EditStage()
        ctx = _make_context(
            highlights=[{"start_second": 0, "end_second": 5}],
        )
        edl = EditDecisionList()
        stage._build_video_decisions(ctx, edl)
        stage._build_effect_decisions(ctx, edl)

        effect_decisions = [d for d in edl.decisions if d.action == "add_effect"]
        assert len(effect_decisions) == 0

    def test_transitions_enabled(self):
        stage = EditStage()
        ctx = _make_context(
            highlights=[
                {"start_second": 0, "end_second": 5},
                {"start_second": 10, "end_second": 15},
            ],
            extra_params={"enable_transitions": True},
        )
        edl = EditDecisionList()
        stage._build_video_decisions(ctx, edl)
        stage._build_effect_decisions(ctx, edl)

        effect_decisions = [d for d in edl.decisions if d.action == "add_effect"]
        # 2 个视频片段之间应有 1 个转场
        assert len(effect_decisions) == 1
        assert effect_decisions[0].params["effect_type"] == "transition"


class TestApplyCut:
    def setup_method(self):
        reset_event_bus()

    def test_apply_cut_creates_video_track(self):
        stage = EditStage()
        ctx = _make_context()
        decision = EditDecision(
            action="cut",
            target_track=TrackType.VIDEO,
            params={"source_start_us": 0, "source_end_us": 5_000_000},
        )

        stage._apply_cut(ctx, decision)

        video_tracks = ctx.project.timeline.get_tracks_by_type(TrackType.VIDEO)
        assert len(video_tracks) == 1
        assert len(video_tracks[0].segments) == 1

        seg = video_tracks[0].segments[0]
        assert seg.source_range.start_us == 0
        assert seg.source_range.duration_us == 5_000_000
        assert seg.material_id == "VIDEO_001"

    def test_apply_multiple_cuts_sequential(self):
        stage = EditStage()
        ctx = _make_context()

        for start, end in [(0, 5_000_000), (10_000_000, 15_000_000)]:
            decision = EditDecision(
                action="cut",
                target_track=TrackType.VIDEO,
                params={"source_start_us": start, "source_end_us": end},
            )
            stage._apply_cut(ctx, decision)

        video_tracks = ctx.project.timeline.get_tracks_by_type(TrackType.VIDEO)
        assert len(video_tracks[0].segments) == 2
        # 第二个片段应紧接第一个
        assert video_tracks[0].segments[1].target_range.start_us == 5_000_000

    def test_apply_cut_zero_duration_skipped(self):
        stage = EditStage()
        ctx = _make_context()
        decision = EditDecision(
            action="cut",
            target_track=TrackType.VIDEO,
            params={"source_start_us": 5_000_000, "source_end_us": 5_000_000},
        )
        stage._apply_cut(ctx, decision)

        video_tracks = ctx.project.timeline.get_tracks_by_type(TrackType.VIDEO)
        assert len(video_tracks) == 0


class TestApplyAddText:
    def setup_method(self):
        reset_event_bus()

    def test_apply_subtitle(self):
        stage = EditStage()
        ctx = _make_context()
        decision = EditDecision(
            action="add_text",
            target_track=TrackType.TEXT,
            params={
                "text": "你好世界",
                "start_us": 1_000_000,
                "duration_us": 2_000_000,
            },
        )

        stage._apply_add_text(ctx, decision)

        assert len(ctx.project.subtitles) == 1
        assert ctx.project.subtitles[0].text == "你好世界"

        text_tracks = ctx.project.timeline.get_tracks_by_type(TrackType.TEXT)
        assert len(text_tracks) == 1
        assert len(text_tracks[0].segments) == 1

    def test_apply_empty_text_skipped(self):
        stage = EditStage()
        ctx = _make_context()
        decision = EditDecision(
            action="add_text",
            target_track=TrackType.TEXT,
            params={"text": "", "start_us": 0, "duration_us": 2_000_000},
        )
        stage._apply_add_text(ctx, decision)

        text_tracks = ctx.project.timeline.get_tracks_by_type(TrackType.TEXT)
        assert len(text_tracks) == 0


class TestApplyAddBGM:
    def setup_method(self):
        reset_event_bus()

    def test_apply_bgm(self):
        stage = EditStage()
        ctx = _make_context()
        # 先创建视频轨来确定时长
        video_decision = EditDecision(
            action="cut",
            target_track=TrackType.VIDEO,
            params={"source_start_us": 0, "source_end_us": 10_000_000},
        )
        stage._apply_cut(ctx, video_decision)

        bgm_decision = EditDecision(
            action="add_bgm",
            target_track=TrackType.AUDIO,
            params={"bgm_path": "/music/bgm.mp3", "volume": 0.3},
        )
        stage._apply_add_bgm(ctx, bgm_decision)

        audio_tracks = ctx.project.timeline.get_tracks_by_type(TrackType.AUDIO)
        assert len(audio_tracks) == 1
        assert len(audio_tracks[0].segments) == 1
        assert audio_tracks[0].segments[0].volume == 0.3

    def test_bgm_no_video_track_returns_early(self):
        stage = EditStage()
        ctx = _make_context()
        bgm_decision = EditDecision(
            action="add_bgm",
            target_track=TrackType.AUDIO,
            params={"bgm_path": "/music/bgm.mp3", "volume": 0.3},
        )
        stage._apply_add_bgm(ctx, bgm_decision)

        audio_tracks = ctx.project.timeline.get_tracks_by_type(TrackType.AUDIO)
        # 没有视频轨，BGM 不应添加
        assert len(audio_tracks) == 0


class TestSmartCutAlgorithm:
    def setup_method(self):
        reset_event_bus()

    def test_select_scenes_basic(self):
        stage = EditStage()
        scenes = [
            TimeRange(start_us=0, duration_us=10_000_000),
            TimeRange(start_us=10_000_000, duration_us=10_000_000),
            TimeRange(start_us=20_000_000, duration_us=10_000_000),
        ]

        selected = stage._select_scenes_for_duration(scenes, 15_000_000)

        # 应选择至少 1 个场景
        assert len(selected) >= 1
        total = sum(s.duration_us for s in selected)
        assert total <= 15_000_000 * 1.1

    def test_select_scenes_empty(self):
        stage = EditStage()
        selected = stage._select_scenes_for_duration([], 10_000_000)
        assert selected == []

    def test_select_preserves_chronological_order(self):
        stage = EditStage()
        scenes = [
            TimeRange(start_us=30_000_000, duration_us=5_000_000),
            TimeRange(start_us=0, duration_us=10_000_000),
            TimeRange(start_us=10_000_000, duration_us=8_000_000),
        ]

        selected = stage._select_scenes_for_duration(scenes, 20_000_000)

        # 应按时间顺序排列
        for i in range(len(selected) - 1):
            assert selected[i].start_us < selected[i + 1].start_us


class TestFullExecute:
    def setup_method(self):
        reset_event_bus()

    def test_execute_full_pipeline(self):
        stage = EditStage()
        ctx = _make_context(
            highlights=[
                {"start_second": 0, "end_second": 5},
                {"start_second": 10, "end_second": 15},
            ],
            subtitles=[
                SubtitleBlock(text="你好", time_range=TimeRange(start_us=0, duration_us=2_000_000)),
            ],
        )

        result = _run(stage.execute(ctx))

        assert result["total_decisions"] > 0
        assert result["applied"] > 0
        assert result["failed"] == 0
        assert result["timeline_duration_us"] > 0
        assert result["track_count"] >= 1
        assert ctx.edl is not None

    def test_execute_no_analysis_returns_skipped(self):
        stage = EditStage()
        ctx = PipelineContext()
        ctx.analysis = None

        result = _run(stage.execute(ctx))
        assert result["status"] == "skipped"


class TestEditRollback:
    def setup_method(self):
        reset_event_bus()

    def test_rollback_clears_timeline(self):
        stage = EditStage()
        ctx = _make_context()
        ctx.edl = EditDecisionList()
        ctx.project.timeline.add_track(Track(track_type=TrackType.VIDEO))
        ctx.project.subtitles.append(SubtitleBlock(text="test"))

        _run(stage.rollback(ctx))

        assert ctx.edl is None
        assert len(ctx.project.timeline.tracks) == 0
        assert len(ctx.project.subtitles) == 0
