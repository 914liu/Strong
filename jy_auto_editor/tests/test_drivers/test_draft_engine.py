"""Draft Engine 单元测试 — MaterialManager / TrackManager / SegmentOperator"""

import pytest

from jy_auto_editor.drivers.draft_engine.materials import MaterialManager
from jy_auto_editor.drivers.draft_engine.schema import (
    DraftContentModel,
    MaterialsModel,
    SegmentModel,
    TimeRangeModel,
    TrackModel,
)
from jy_auto_editor.drivers.draft_engine.segments import SegmentOperator
from jy_auto_editor.drivers.draft_engine.tracks import TrackManager


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _make_draft(**kwargs) -> DraftContentModel:
    return DraftContentModel(**kwargs)


@pytest.fixture
def empty_draft():
    return _make_draft()


@pytest.fixture
def material_mgr(empty_draft):
    return MaterialManager(empty_draft)


@pytest.fixture
def track_mgr(empty_draft):
    return TrackManager(empty_draft)


@pytest.fixture
def segment_op(empty_draft):
    return SegmentOperator(empty_draft)


# ══════════════════════════════════════════════
# MaterialManager
# ══════════════════════════════════════════════

class TestMaterialManagerVideo:
    def test_add_video_returns_id(self, material_mgr):
        mid = material_mgr.add_video("/tmp/test.mp4", name="test", duration=10_000_000)
        assert mid
        assert isinstance(mid, str)

    def test_add_video_stores_material(self, material_mgr):
        mid = material_mgr.add_video("/tmp/test.mp4", name="clip1", duration=5_000_000, width=1920, height=1080, fps=60.0)
        video = material_mgr.get_video(mid)
        assert video is not None
        assert video.path == "/tmp/test.mp4"
        assert video.name == "clip1"
        assert video.duration == 5_000_000
        assert video.width == 1920
        assert video.fps == 60.0
        assert video.type == "video"

    def test_add_video_defaults(self, material_mgr):
        mid = material_mgr.add_video("/tmp/a.mp4")
        video = material_mgr.get_video(mid)
        assert video.name == ""
        assert video.duration == 0
        assert video.fps == 30.0

    def test_get_video_not_found(self, material_mgr):
        assert material_mgr.get_video("NONEXISTENT") is None

    def test_remove_video_success(self, material_mgr):
        mid = material_mgr.add_video("/tmp/test.mp4")
        assert material_mgr.remove_video(mid) is True
        assert material_mgr.get_video(mid) is None

    def test_remove_video_not_found(self, material_mgr):
        assert material_mgr.remove_video("NONEXISTENT") is False

    def test_add_image(self, material_mgr):
        mid = material_mgr.add_image("/tmp/img.png", name="photo", width=800, height=600)
        video = material_mgr.get_video(mid)
        assert video is not None
        assert video.type == "photo"
        assert video.duration == 3_000_000  # default 3s
        assert video.width == 800

    def test_add_image_custom_duration(self, material_mgr):
        mid = material_mgr.add_image("/tmp/img.png", duration=5_000_000)
        video = material_mgr.get_video(mid)
        assert video.duration == 5_000_000


class TestMaterialManagerAudio:
    def test_add_audio(self, material_mgr):
        mid = material_mgr.add_audio("/tmp/bgm.mp3", name="bgm", duration=30_000_000)
        audio = material_mgr.get_audio(mid)
        assert audio is not None
        assert audio.path == "/tmp/bgm.mp3"
        assert audio.duration == 30_000_000

    def test_get_audio_not_found(self, material_mgr):
        assert material_mgr.get_audio("NOPE") is None

    def test_add_multiple_audios(self, material_mgr):
        mid1 = material_mgr.add_audio("/tmp/a.mp3")
        mid2 = material_mgr.add_audio("/tmp/b.mp3")
        assert mid1 != mid2
        assert material_mgr.get_audio(mid1) is not None
        assert material_mgr.get_audio(mid2) is not None


class TestMaterialManagerText:
    def test_add_text(self, material_mgr):
        mid = material_mgr.add_text("你好世界", font_name="微软雅黑", font_size=12.0)
        text = material_mgr.get_text(mid)
        assert text is not None
        assert text.content == "你好世界"
        assert text.base_content == "你好世界"
        assert text.font_name == "微软雅黑"
        assert text.font_size == 12.0

    def test_add_text_defaults(self, material_mgr):
        mid = material_mgr.add_text("hello")
        text = material_mgr.get_text(mid)
        assert text.font_size == 8.0
        assert text.alignment == 1

    def test_get_text_not_found(self, material_mgr):
        assert material_mgr.get_text("NOPE") is None


class TestMaterialManagerQuery:
    def test_find_material_video(self, material_mgr):
        mid = material_mgr.add_video("/tmp/v.mp4")
        found = material_mgr.find_material(mid)
        assert found is not None
        assert found.id == mid

    def test_find_material_audio(self, material_mgr):
        mid = material_mgr.add_audio("/tmp/a.mp3")
        found = material_mgr.find_material(mid)
        assert found is not None
        assert found.id == mid

    def test_find_material_text(self, material_mgr):
        mid = material_mgr.add_text("hi")
        found = material_mgr.find_material(mid)
        assert found is not None
        assert found.id == mid

    def test_find_material_not_found(self, material_mgr):
        assert material_mgr.find_material("MISSING") is None

    def test_all_material_ids(self, material_mgr):
        v_id = material_mgr.add_video("/tmp/v.mp4")
        a_id = material_mgr.add_audio("/tmp/a.mp3")
        t_id = material_mgr.add_text("text")
        ids = material_mgr.all_material_ids
        assert v_id in ids
        assert a_id in ids
        assert t_id in ids
        assert len(ids) == 3

    def test_all_material_ids_empty(self, material_mgr):
        assert material_mgr.all_material_ids == []


# ══════════════════════════════════════════════
# TrackManager
# ══════════════════════════════════════════════

class TestTrackManagerAddRemove:
    def test_add_track(self, track_mgr):
        tid = track_mgr.add_track("video")
        assert tid
        track = track_mgr.get_track(tid)
        assert track is not None
        assert track.type == "video"

    def test_add_track_render_index(self, track_mgr):
        t1 = track_mgr.add_track("video")
        t2 = track_mgr.add_track("audio")
        assert track_mgr.get_track(t1).render_index == 0
        assert track_mgr.get_track(t2).render_index == 1

    def test_remove_track(self, track_mgr):
        tid = track_mgr.add_track("video")
        assert track_mgr.remove_track(tid) is True
        assert track_mgr.get_track(tid) is None

    def test_remove_track_not_found(self, track_mgr):
        assert track_mgr.remove_track("NOPE") is False

    def test_remove_track_reindexes(self, track_mgr):
        t1 = track_mgr.add_track("video")
        t2 = track_mgr.add_track("audio")
        t3 = track_mgr.add_track("text")
        track_mgr.remove_track(t2)
        assert track_mgr.get_track(t1).render_index == 0
        assert track_mgr.get_track(t3).render_index == 1

    def test_track_count(self, track_mgr):
        assert track_mgr.track_count == 0
        track_mgr.add_track("video")
        assert track_mgr.track_count == 1
        track_mgr.add_track("audio")
        assert track_mgr.track_count == 2


class TestTrackManagerQuery:
    def test_get_tracks_by_type(self, track_mgr):
        track_mgr.add_track("video")
        track_mgr.add_track("video")
        track_mgr.add_track("audio")
        videos = track_mgr.get_tracks_by_type("video")
        assert len(videos) == 2
        audios = track_mgr.get_tracks_by_type("audio")
        assert len(audios) == 1

    def test_get_tracks_by_type_empty(self, track_mgr):
        assert track_mgr.get_tracks_by_type("video") == []

    def test_get_first_track_by_type(self, track_mgr):
        t1 = track_mgr.add_track("video")
        track_mgr.add_track("video")
        first = track_mgr.get_first_track_by_type("video")
        assert first is not None
        assert first.id == t1

    def test_get_first_track_by_type_none(self, track_mgr):
        assert track_mgr.get_first_track_by_type("video") is None


class TestTrackManagerReorder:
    def test_reorder_tracks(self, track_mgr):
        t1 = track_mgr.add_track("video")
        t2 = track_mgr.add_track("audio")
        t3 = track_mgr.add_track("text")
        track_mgr.reorder_tracks([t3, t1])
        tracks = track_mgr._draft.tracks
        assert tracks[0].id == t3
        assert tracks[0].render_index == 0
        assert tracks[1].id == t1
        assert tracks[1].render_index == 1
        # t2 was not specified, goes to end
        assert tracks[2].id == t2
        assert tracks[2].render_index == 2


class TestTrackManagerSegments:
    def test_add_segment_to_track(self, track_mgr):
        tid = track_mgr.add_track("video")
        seg = SegmentModel(id="SEG1", material_id="MAT1")
        seg_id = track_mgr.add_segment_to_track(tid, seg)
        assert seg_id == "SEG1"
        track = track_mgr.get_track(tid)
        assert len(track.segments) == 1

    def test_add_segment_to_nonexistent_track(self, track_mgr):
        seg = SegmentModel(id="SEG1")
        with pytest.raises(ValueError, match="Track not found"):
            track_mgr.add_segment_to_track("NOPE", seg)

    def test_remove_segment_from_track(self, track_mgr):
        tid = track_mgr.add_track("video")
        seg = SegmentModel(id="SEG1")
        track_mgr.add_segment_to_track(tid, seg)
        assert track_mgr.remove_segment_from_track(tid, "SEG1") is True
        track = track_mgr.get_track(tid)
        assert len(track.segments) == 0

    def test_remove_segment_not_found(self, track_mgr):
        tid = track_mgr.add_track("video")
        assert track_mgr.remove_segment_from_track(tid, "NOPE") is False

    def test_remove_segment_nonexistent_track(self, track_mgr):
        assert track_mgr.remove_segment_from_track("NOPE", "SEG1") is False

    def test_find_segment(self, track_mgr):
        tid = track_mgr.add_track("video")
        seg = SegmentModel(id="SEG1", material_id="MAT1")
        track_mgr.add_segment_to_track(tid, seg)
        found_track, found_seg = track_mgr.find_segment("SEG1")
        assert found_track is not None
        assert found_track.id == tid
        assert found_seg is not None
        assert found_seg.id == "SEG1"

    def test_find_segment_not_found(self, track_mgr):
        track, seg = track_mgr.find_segment("NOPE")
        assert track is None
        assert seg is None

    def test_total_duration(self, track_mgr):
        tid = track_mgr.add_track("video")
        seg1 = SegmentModel(
            id="S1",
            target_timerange=TimeRangeModel(start=0, duration=5_000_000),
        )
        seg2 = SegmentModel(
            id="S2",
            target_timerange=TimeRangeModel(start=5_000_000, duration=3_000_000),
        )
        track_mgr.add_segment_to_track(tid, seg1)
        track_mgr.add_segment_to_track(tid, seg2)
        assert track_mgr.total_duration == 8_000_000

    def test_total_duration_empty(self, track_mgr):
        assert track_mgr.total_duration == 0


# ══════════════════════════════════════════════
# SegmentOperator
# ══════════════════════════════════════════════

class TestSegmentOperatorCreate:
    def test_create_segment(self, segment_op):
        seg = segment_op.create_segment(
            material_id="MAT1",
            source_start_us=0,
            source_duration_us=10_000_000,
            target_start_us=0,
            target_duration_us=10_000_000,
        )
        assert seg.id
        assert seg.material_id == "MAT1"
        assert seg.source_timerange.start == 0
        assert seg.source_timerange.duration == 10_000_000
        assert seg.speed == 1.0
        assert seg.volume == 1.0

    def test_create_segment_auto_target_duration(self, segment_op):
        """target_duration_us=0 时自动根据 speed 计算"""
        seg = segment_op.create_segment(
            material_id="MAT1",
            source_duration_us=10_000_000,
            target_duration_us=0,
            speed=2.0,
        )
        # 2x speed → target duration = source / speed = 5_000_000
        assert seg.target_timerange.duration == 5_000_000

    def test_create_segment_custom_speed_volume(self, segment_op):
        seg = segment_op.create_segment(
            material_id="MAT1",
            source_duration_us=10_000_000,
            speed=0.5,
            volume=0.8,
        )
        assert seg.speed == 0.5
        assert seg.volume == 0.8
        # 0.5x speed → target = 10_000_000 / 0.5 = 20_000_000
        assert seg.target_timerange.duration == 20_000_000


class TestSegmentOperatorSplit:
    def _setup_segment(self, segment_op):
        """Helper: create a draft with a track and segment"""
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(
            id="S1",
            material_id="M1",
            source_timerange=TimeRangeModel(start=0, duration=10_000_000),
            target_timerange=TimeRangeModel(start=0, duration=10_000_000),
            speed=1.0,
        )
        track.segments.append(seg)
        draft.tracks.append(track)
        return "S1"

    def test_split_segment(self, segment_op):
        seg_id = self._setup_segment(segment_op)
        s1, s2 = segment_op.split_segment(seg_id, 5_000_000)
        assert s1 == seg_id  # first half keeps original id
        assert s2 != s1

        track = segment_op._track_mgr.get_track("T1")
        assert len(track.segments) == 2

        first = track.segments[0]
        second = track.segments[1]
        assert first.source_timerange.duration == 5_000_000
        assert second.source_timerange.start == 5_000_000
        assert second.source_timerange.duration == 5_000_000

    def test_split_segment_not_found(self, segment_op):
        with pytest.raises(ValueError, match="Segment not found"):
            segment_op.split_segment("NOPE", 5_000_000)

    def test_split_preserves_speed_volume(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(
            id="S1",
            material_id="M1",
            source_timerange=TimeRangeModel(start=0, duration=10_000_000),
            target_timerange=TimeRangeModel(start=0, duration=5_000_000),
            speed=2.0,
            volume=0.5,
        )
        track.segments.append(seg)
        draft.tracks.append(track)

        segment_op.split_segment("S1", 5_000_000)
        second = track.segments[1]
        assert second.speed == 2.0
        assert second.volume == 0.5


class TestSegmentOperatorDelete:
    def test_delete_segment(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(id="S1")
        track.segments.append(seg)
        draft.tracks.append(track)

        assert segment_op.delete_segment("S1") is True
        assert len(track.segments) == 0

    def test_delete_segment_not_found(self, segment_op):
        assert segment_op.delete_segment("NOPE") is False


class TestSegmentOperatorMove:
    def test_move_segment(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(
            id="S1",
            target_timerange=TimeRangeModel(start=0, duration=5_000_000),
        )
        track.segments.append(seg)
        draft.tracks.append(track)

        segment_op.move_segment("S1", 10_000_000)
        assert seg.target_timerange.start == 10_000_000

    def test_move_segment_not_found(self, segment_op):
        with pytest.raises(ValueError, match="Segment not found"):
            segment_op.move_segment("NOPE", 0)


class TestSegmentOperatorSpeed:
    def test_set_speed(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(
            id="S1",
            source_timerange=TimeRangeModel(start=0, duration=10_000_000),
            target_timerange=TimeRangeModel(start=0, duration=10_000_000),
            speed=1.0,
        )
        track.segments.append(seg)
        draft.tracks.append(track)

        segment_op.set_speed("S1", 2.0)
        assert seg.speed == 2.0
        assert seg.target_timerange.duration == 5_000_000

    def test_set_speed_not_found(self, segment_op):
        with pytest.raises(ValueError, match="Segment not found"):
            segment_op.set_speed("NOPE", 1.0)


class TestSegmentOperatorVolume:
    def test_set_volume(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(id="S1", volume=1.0)
        track.segments.append(seg)
        draft.tracks.append(track)

        segment_op.set_volume("S1", 0.5)
        assert seg.volume == 0.5

    def test_set_volume_clamped_high(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(id="S1", volume=1.0)
        track.segments.append(seg)
        draft.tracks.append(track)

        segment_op.set_volume("S1", 5.0)
        assert seg.volume == 2.0

    def test_set_volume_clamped_low(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(id="S1", volume=1.0)
        track.segments.append(seg)
        draft.tracks.append(track)

        segment_op.set_volume("S1", -1.0)
        assert seg.volume == 0.0

    def test_set_volume_not_found(self, segment_op):
        with pytest.raises(ValueError, match="Segment not found"):
            segment_op.set_volume("NOPE", 1.0)


class TestSegmentOperatorTrim:
    def test_trim_segment(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(
            id="S1",
            source_timerange=TimeRangeModel(start=0, duration=10_000_000),
            target_timerange=TimeRangeModel(start=0, duration=10_000_000),
            speed=1.0,
        )
        track.segments.append(seg)
        draft.tracks.append(track)

        segment_op.trim_segment("S1", 2_000_000, 8_000_000)
        assert seg.source_timerange.start == 2_000_000
        assert seg.source_timerange.duration == 6_000_000
        assert seg.target_timerange.duration == 6_000_000

    def test_trim_segment_with_speed(self, segment_op):
        draft = segment_op._draft
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(
            id="S1",
            source_timerange=TimeRangeModel(start=0, duration=10_000_000),
            target_timerange=TimeRangeModel(start=0, duration=5_000_000),
            speed=2.0,
        )
        track.segments.append(seg)
        draft.tracks.append(track)

        segment_op.trim_segment("S1", 2_000_000, 8_000_000)
        assert seg.source_timerange.duration == 6_000_000
        # target = source / speed = 6_000_000 / 2.0 = 3_000_000
        assert seg.target_timerange.duration == 3_000_000

    def test_trim_segment_not_found(self, segment_op):
        with pytest.raises(ValueError, match="Segment not found"):
            segment_op.trim_segment("NOPE", 0, 1_000_000)
