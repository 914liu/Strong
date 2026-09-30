"""片段操作 — 分割、删除、移动、变速"""

from __future__ import annotations

import uuid
from typing import Optional

from .schema import ClipTransformModel, DraftContentModel, SegmentModel, TimeRangeModel
from .tracks import TrackManager


class SegmentOperator:
    """片段操作器"""

    def __init__(self, draft: DraftContentModel) -> None:
        self._draft = draft
        self._track_mgr = TrackManager(draft)

    def create_segment(
        self,
        material_id: str,
        source_start_us: int = 0,
        source_duration_us: int = 0,
        target_start_us: int = 0,
        target_duration_us: int = 0,
        speed: float = 1.0,
        volume: float = 1.0,
    ) -> SegmentModel:
        """创建新片段（不添加到轨道）"""
        if target_duration_us == 0:
            target_duration_us = int(source_duration_us / speed)

        return SegmentModel(
            id=str(uuid.uuid4()).upper(),
            material_id=material_id,
            source_timerange=TimeRangeModel(
                start=source_start_us,
                duration=source_duration_us,
            ),
            target_timerange=TimeRangeModel(
                start=target_start_us,
                duration=target_duration_us,
            ),
            speed=speed,
            volume=volume,
        )

    def split_segment(
        self, segment_id: str, split_point_us: int
    ) -> tuple[str, str]:
        """在指定位置分割片段

        Args:
            segment_id: 片段 ID
            split_point_us: 分割点在源素材中的位置（微秒）

        Returns:
            (前半段 ID, 后半段 ID)
        """
        track, seg = self._track_mgr.find_segment(segment_id)
        if track is None or seg is None:
            raise ValueError(f"Segment not found: {segment_id}")

        # 计算分割点在 target 中的位置
        split_ratio = (split_point_us - seg.source_timerange.start) / seg.source_timerange.duration
        split_target = seg.target_timerange.start + int(seg.target_timerange.duration * split_ratio)

        # 保存原始时长，后续计算需要
        original_source_duration = seg.source_timerange.duration
        original_target_duration = seg.target_timerange.duration

        # 前半段
        seg1_source_duration = split_point_us - seg.source_timerange.start
        seg1_target_duration = split_target - seg.target_timerange.start
        seg.source_timerange.start = seg.source_timerange.start
        seg.source_timerange.duration = seg1_source_duration
        seg.target_timerange.duration = seg1_target_duration

        # 后半段
        seg2_source_start = split_point_us
        seg2_source_duration = original_source_duration - seg1_source_duration
        seg2 = SegmentModel(
            id=str(uuid.uuid4()).upper(),
            material_id=seg.material_id,
            source_timerange=TimeRangeModel(
                start=seg2_source_start,
                duration=seg2_source_duration,
            ),
            target_timerange=TimeRangeModel(
                start=split_target,
                duration=int(seg2_source_duration / seg.speed),
            ),
            speed=seg.speed,
            volume=seg.volume,
            clip=ClipTransformModel(
                alpha=seg.clip.alpha,
                rotation=seg.clip.rotation,
                scale=seg.clip.scale,
                transform=seg.clip.transform,
            ),
        )

        # 将后半段插入到前半段后面
        idx = track.segments.index(seg)
        track.segments.insert(idx + 1, seg2)

        return seg.id, seg2.id

    def delete_segment(self, segment_id: str) -> bool:
        """删除片段"""
        track, seg = self._track_mgr.find_segment(segment_id)
        if track is None:
            return False
        return self._track_mgr.remove_segment_from_track(track.id, segment_id)

    def move_segment(self, segment_id: str, new_target_start_us: int) -> None:
        """移动片段到新的时间线位置"""
        _, seg = self._track_mgr.find_segment(segment_id)
        if seg is None:
            raise ValueError(f"Segment not found: {segment_id}")
        seg.target_timerange.start = new_target_start_us

    def set_speed(self, segment_id: str, speed: float) -> None:
        """设置片段播放速度"""
        _, seg = self._track_mgr.find_segment(segment_id)
        if seg is None:
            raise ValueError(f"Segment not found: {segment_id}")
        old_speed = seg.speed
        seg.speed = speed
        # 调整 target duration
        seg.target_timerange.duration = int(seg.source_timerange.duration / speed)

    def set_volume(self, segment_id: str, volume: float) -> None:
        """设置片段音量"""
        _, seg = self._track_mgr.find_segment(segment_id)
        if seg is None:
            raise ValueError(f"Segment not found: {segment_id}")
        seg.volume = max(0.0, min(volume, 2.0))

    def trim_segment(
        self, segment_id: str, new_source_start_us: int, new_source_end_us: int
    ) -> None:
        """裁剪片段的源素材范围"""
        _, seg = self._track_mgr.find_segment(segment_id)
        if seg is None:
            raise ValueError(f"Segment not found: {segment_id}")
        new_duration = new_source_end_us - new_source_start_us
        seg.source_timerange.start = new_source_start_us
        seg.source_timerange.duration = new_duration
        seg.target_timerange.duration = int(new_duration / seg.speed)
