"""轨道管理 — 增删改查、排序"""

from __future__ import annotations

import uuid
from typing import Optional

from .schema import DraftContentModel, SegmentModel, TrackModel


class TrackManager:
    """轨道管理器"""

    def __init__(self, draft: DraftContentModel) -> None:
        self._draft = draft

    def add_track(self, track_type: str = "video") -> str:
        """添加轨道，返回 track_id"""
        track_id = str(uuid.uuid4()).upper()
        track = TrackModel(
            id=track_id,
            type=track_type,
            render_index=len(self._draft.tracks),
        )
        self._draft.tracks.append(track)
        return track_id

    def get_track(self, track_id: str) -> Optional[TrackModel]:
        for t in self._draft.tracks:
            if t.id == track_id:
                return t
        return None

    def remove_track(self, track_id: str) -> bool:
        before = len(self._draft.tracks)
        self._draft.tracks = [t for t in self._draft.tracks if t.id != track_id]
        # 重新编号 render_index
        for i, t in enumerate(self._draft.tracks):
            t.render_index = i
        return len(self._draft.tracks) < before

    def get_tracks_by_type(self, track_type: str) -> list[TrackModel]:
        return [t for t in self._draft.tracks if t.type == track_type]

    def get_first_track_by_type(self, track_type: str) -> Optional[TrackModel]:
        for t in self._draft.tracks:
            if t.type == track_type:
                return t
        return None

    def reorder_tracks(self, track_ids: list[str]) -> None:
        """按指定顺序重排轨道"""
        track_map = {t.id: t for t in self._draft.tracks}
        new_order = []
        for tid in track_ids:
            if tid in track_map:
                new_order.append(track_map[tid])
        # 保留未指定的轨道在末尾
        for t in self._draft.tracks:
            if t.id not in track_ids:
                new_order.append(t)
        for i, t in enumerate(new_order):
            t.render_index = i
        self._draft.tracks = new_order

    def add_segment_to_track(
        self,
        track_id: str,
        segment: SegmentModel,
    ) -> str:
        """向轨道添加片段"""
        track = self.get_track(track_id)
        if track is None:
            raise ValueError(f"Track not found: {track_id}")
        track.segments.append(segment)
        return segment.id

    def remove_segment_from_track(self, track_id: str, segment_id: str) -> bool:
        """从轨道中移除片段"""
        track = self.get_track(track_id)
        if track is None:
            return False
        before = len(track.segments)
        track.segments = [s for s in track.segments if s.id != segment_id]
        return len(track.segments) < before

    def find_segment(self, segment_id: str) -> tuple[Optional[TrackModel], Optional[SegmentModel]]:
        """在所有轨道中查找片段"""
        for track in self._draft.tracks:
            for seg in track.segments:
                if seg.id == segment_id:
                    return track, seg
        return None, None

    @property
    def track_count(self) -> int:
        return len(self._draft.tracks)

    @property
    def total_duration(self) -> int:
        """获取时间线总时长（微秒）"""
        max_end = 0
        for track in self._draft.tracks:
            for seg in track.segments:
                end = seg.target_timerange.start + seg.target_timerange.duration
                if end > max_end:
                    max_end = end
        return max_end
