"""Edit Stage — 编辑执行阶段"""

from __future__ import annotations

import logging
from typing import Any

from ..core.models import (
    EditDecision,
    EditDecisionList,
    PipelineContext,
    Segment,
    SubtitleBlock,
    TimeRange,
    Track,
    TrackType,
)
from ..core.pipeline import Stage

logger = logging.getLogger(__name__)


class EditStage(Stage):
    """编辑执行阶段

    根据分析结果和编辑策略，生成 EDL 并通过 Driver 执行编辑操作。
    """

    name = "edit"
    dependencies = ["analyze"]
    can_skip = False
    timeout = 300

    async def execute(self, context: PipelineContext) -> dict:
        analysis = context.analysis
        if analysis is None:
            logger.warning("No analysis result, skipping edit")
            return {"status": "skipped", "reason": "no analysis"}

        edl = EditDecisionList(source_project=context.project)

        # 1. 根据分析结果生成编辑决策
        # 添加字幕
        if analysis.subtitles:
            for sub_data in analysis.subtitles:
                edl.decisions.append(EditDecision(
                    action="add_text",
                    target_track=TrackType.TEXT,
                    params={
                        "text": sub_data.get("text", ""),
                        "start_us": sub_data.get("start_us", 0),
                        "duration_us": sub_data.get("end_us", 0) - sub_data.get("start_us", 0),
                    },
                ))

        # 2. 应用 EDL 到项目
        applied = 0
        for decision in edl.decisions:
            try:
                await self._apply_decision(context, decision)
                applied += 1
            except Exception as e:
                logger.error(f"Failed to apply decision {decision.action}: {e}")

        context.edl = edl
        return {
            "total_decisions": len(edl.decisions),
            "applied": applied,
            "failed": len(edl.decisions) - applied,
        }

    async def _apply_decision(self, context: PipelineContext, decision: EditDecision) -> None:
        """应用单条编辑决策到项目"""
        if decision.action == "add_text":
            subtitle = SubtitleBlock(
                text=decision.params.get("text", ""),
                time_range=TimeRange(
                    start_us=decision.params.get("start_us", 0),
                    duration_us=decision.params.get("duration_us", 0),
                ),
            )
            context.project.subtitles.append(subtitle)
            # 同时添加到时间线文本轨
            text_tracks = context.project.timeline.get_tracks_by_type(TrackType.TEXT)
            if not text_tracks:
                track = Track(track_type=TrackType.TEXT)
                context.project.timeline.add_track(track)
                text_tracks = [track]

            seg = Segment(
                material_id="",
                source_range=TimeRange.zero(),
                target_range=subtitle.time_range,
            )
            text_tracks[0].add_segment(seg)

        elif decision.action == "cut":
            pass  # TODO: 实现智能切片
        elif decision.action == "add_bgm":
            pass  # TODO: 实现 BGM 添加
        elif decision.action == "add_effect":
            pass  # TODO: 实现特效添加
