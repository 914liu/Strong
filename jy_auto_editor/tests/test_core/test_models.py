"""core/models 单元测试"""

import pytest
from jy_auto_editor.core.models import (
    TimeRange,
    VideoAsset,
    AudioAsset,
    SubtitleBlock,
    Segment,
    Track,
    TrackType,
    Timeline,
    VideoProject,
    ProjectInput,
    AnalysisResult,
    EditDecision,
    EditDecisionList,
    ExportConfig,
    CanvasConfig,
    PipelineContext,
    MICROSECONDS_PER_SECOND,
    generate_id,
)


class TestTimeRange:
    def test_basic_creation(self):
        tr = TimeRange(start_us=0, duration_us=1_000_000)
        assert tr.start_us == 0
        assert tr.duration_us == 1_000_000

    def test_end_us(self):
        tr = TimeRange(start_us=500_000, duration_us=1_000_000)
        assert tr.end_us == 1_500_000

    def test_duration_seconds(self):
        tr = TimeRange(start_us=0, duration_us=2_500_000)
        assert tr.duration_seconds == 2.5

    def test_start_seconds(self):
        tr = TimeRange(start_us=1_500_000, duration_us=1_000_000)
        assert tr.start_seconds == 1.5

    def test_overlaps(self):
        tr1 = TimeRange(start_us=0, duration_us=10_000_000)
        tr2 = TimeRange(start_us=5_000_000, duration_us=10_000_000)
        tr3 = TimeRange(start_us=20_000_000, duration_us=5_000_000)
        assert tr1.overlaps(tr2)
        assert not tr1.overlaps(tr3)

    def test_from_seconds(self):
        tr = TimeRange.from_seconds(1.5, 2.0)
        assert tr.start_us == 1_500_000
        assert tr.duration_us == 2_000_000

    def test_zero(self):
        tr = TimeRange.zero()
        assert tr.start_us == 0
        assert tr.duration_us == 0


class TestGenerateId:
    def test_returns_uppercase_uuid(self):
        id1 = generate_id()
        assert id1 == id1.upper()
        assert len(id1) == 36  # UUID format

    def test_unique_ids(self):
        ids = {generate_id() for _ in range(100)}
        assert len(ids) == 100


class TestVideoAsset:
    def test_creation(self):
        asset = VideoAsset(
            asset_id="test-id",
            path="/path/to/video.mp4",
            name="test_video",
        )
        assert asset.asset_id == "test-id"
        assert asset.media_type == "video"

    def test_default_id_generated(self):
        asset = VideoAsset(path="/p.mp4")
        assert asset.asset_id != ""


class TestAudioAsset:
    def test_creation(self):
        asset = AudioAsset(
            asset_id="audio-1",
            path="/path/to/audio.wav",
            name="bgm",
            duration_us=5_000_000,
        )
        assert asset.asset_id == "audio-1"
        assert asset.duration_us == 5_000_000


class TestSegment:
    def test_creation(self):
        seg = Segment(
            segment_id="seg-1",
            material_id="mat-1",
            source_range=TimeRange(start_us=0, duration_us=5_000_000),
            target_range=TimeRange(start_us=0, duration_us=5_000_000),
        )
        assert seg.speed == 1.0
        assert seg.volume == 1.0
        assert seg.alpha == 1.0


class TestTrack:
    def test_add_segment(self):
        track = Track(track_id="t1", track_type=TrackType.VIDEO)
        seg = Segment(
            segment_id="s1",
            material_id="m1",
            source_range=TimeRange(start_us=0, duration_us=1_000_000),
            target_range=TimeRange(start_us=0, duration_us=1_000_000),
        )
        track.add_segment(seg)
        assert len(track.segments) == 1
        assert track.segments[0].segment_id == "s1"

    def test_total_duration_us(self):
        track = Track(track_id="t1", track_type=TrackType.VIDEO)
        seg = Segment(
            segment_id="s1",
            material_id="m1",
            source_range=TimeRange(start_us=0, duration_us=5_000_000),
            target_range=TimeRange(start_us=1_000_000, duration_us=5_000_000),
        )
        track.add_segment(seg)
        assert track.total_duration_us == 6_000_000


class TestTimeline:
    def test_add_track(self):
        timeline = Timeline()
        track = Track(track_id="t1", track_type=TrackType.VIDEO)
        timeline.add_track(track)
        assert len(timeline.tracks) == 1
        assert track.render_index == 0

    def test_total_duration_us(self):
        timeline = Timeline()
        track = Track(track_id="t1", track_type=TrackType.VIDEO)
        seg = Segment(
            segment_id="s1",
            material_id="m1",
            source_range=TimeRange(start_us=0, duration_us=5_000_000),
            target_range=TimeRange(start_us=1_000_000, duration_us=5_000_000),
        )
        track.add_segment(seg)
        timeline.add_track(track)
        assert timeline.total_duration_us == 6_000_000

    def test_get_tracks_by_type(self):
        timeline = Timeline()
        v_track = Track(track_type=TrackType.VIDEO)
        a_track = Track(track_type=TrackType.AUDIO)
        timeline.add_track(v_track)
        timeline.add_track(a_track)
        videos = timeline.get_tracks_by_type(TrackType.VIDEO)
        assert len(videos) == 1


class TestVideoProject:
    def test_creation_defaults(self):
        project = VideoProject()
        assert project.name == "未命名项目"
        assert project.timeline.canvas_config.width == 1920

    def test_custom_timeline(self):
        timeline = Timeline(canvas_config=CanvasConfig(width=1080, height=1920, ratio="9:16"))
        project = VideoProject(timeline=timeline)
        assert project.timeline.canvas_config.width == 1080


class TestEditDecisionList:
    def test_empty_edl(self):
        edl = EditDecisionList()
        assert len(edl.decisions) == 0

    def test_add_decisions(self):
        edl = EditDecisionList()
        edl.decisions.append(EditDecision(action="cut"))
        edl.decisions.append(EditDecision(action="trim"))
        assert len(edl.decisions) == 2


class TestExportConfig:
    def test_defaults(self):
        config = ExportConfig()
        assert config.resolution == "1920x1080"
        assert config.fps == 30
        assert config.format == "mp4"


class TestPipelineContext:
    def test_defaults(self):
        ctx = PipelineContext()
        assert ctx.project.name == "未命名项目"
        assert ctx.analysis is None
        assert ctx.edl is None
