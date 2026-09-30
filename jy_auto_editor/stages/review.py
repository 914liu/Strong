"""Review Stage — 人工审核阶段（可选）"""

from __future__ import annotations

import logging

from ..core.models import PipelineContext
from ..core.pipeline import Stage

logger = logging.getLogger(__name__)


class ReviewStage(Stage):
    """人工审核阶段

    在 Web UI 模式下生成预览，CLI 模式下生成报告。
    此阶段默认跳过，可通过配置启用。
    """

    name = "review"
    dependencies = ["edit"]
    can_skip = True
    timeout = 3600         # 等待人工审核可能很长

    def should_skip(self, context: PipelineContext) -> bool:
        """默认跳过审核，除非明确启用"""
        return not context.extra.get("enable_review", False)

    async def execute(self, context: PipelineContext) -> dict:
        # 生成审核报告
        report = {
            "project_name": context.project.name,
            "total_duration_seconds": context.project.total_duration_seconds,
            "video_count": len(context.project.source_videos),
            "subtitle_count": len(context.project.subtitles),
            "track_count": len(context.project.timeline.tracks),
        }

        logger.info(f"Review report: {report}")
        # TODO: Web UI 模式下生成可交互的时间线预览
        # TODO: CLI 模式下输出报告到终端

        return {"report": report, "status": "approved"}
