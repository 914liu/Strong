"""Review Stage — 人工审核阶段（可选）

职责：
1. 汇总项目信息生成结构化审核报告
2. 通过事件系统通知外部（CLI 输出 / Web UI 预览）
3. 在 Web UI 模式下可暂停 Pipeline 等待人工确认

此阶段默认跳过，可通过配置启用。
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.events import Event, EventType, get_event_bus
from ..core.models import PipelineContext, TrackType
from ..core.pipeline import Stage

logger = logging.getLogger(__name__)


class ReviewStage(Stage):
    """人工审核阶段

    在 Web UI 模式下生成可交互的时间线预览，
    在 CLI 模式下生成文本报告。

    构造参数：
        enabled: 是否启用审核（默认 False）
    """

    name = "review"
    dependencies = ["edit"]
    can_skip = True
    timeout = 3600  # 等待人工审核可能很长

    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled

    def should_skip(self, context: PipelineContext) -> bool:
        """默认跳过审核，除非明确启用"""
        if self._enabled:
            return False
        return not context.extra.get("enable_review", False)

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        event_bus = get_event_bus()

        # ── 生成审核报告 ─────────────────────────────
        report = self._build_report(context)

        # ── 通过事件通知外部 ─────────────────────────
        await event_bus.emit_async(Event(
            type=EventType.STAGE_PROGRESS,
            data={
                "stage": self.name,
                "progress": 1.0,
                "phase": "report_ready",
                "report": report,
            },
            source=self.name,
        ))

        # ── 日志输出 ─────────────────────────────────
        logger.info("═══ 审核报告 ═══")
        logger.info(f"  项目名称: {report['project_name']}")
        logger.info(f"  总时长: {report['total_duration_seconds']:.1f}s")
        logger.info(f"  视频素材: {report['video_count']} 个")
        logger.info(f"  音频素材: {report['audio_count']} 个")
        logger.info(f"  字幕数量: {report['subtitle_count']} 条")
        logger.info(f"  轨道数量: {report['track_count']} 条")
        for track_info in report.get("tracks", []):
            logger.info(f"    {track_info['type']}: {track_info['segment_count']} 片段")
        logger.info(f"  EDL 决策: {report['edl_decision_count']} 条")
        logger.info("═══════════════")

        # ── Web UI 模式下：等待人工确认 ──────────────
        status = "approved"
        if context.extra.get("require_manual_approval"):
            # 发出等待审核事件（Web UI 可监听此事件展示审核界面）
            await event_bus.emit_async(Event(
                type=EventType.STAGE_PROGRESS,
                data={
                    "stage": self.name,
                    "phase": "awaiting_approval",
                    "report": report,
                },
                source=self.name,
            ))
            # 在实际 Web UI 模式下，这里会暂停等待外部信号
            # CLI 模式下自动通过
            status = context.extra.get("approval_status", "approved")
            logger.info(f"Manual approval status: {status}")

        return {
            "report": report,
            "status": status,
        }

    def _build_report(self, context: PipelineContext) -> dict[str, Any]:
        """构建结构化审核报告"""
        project = context.project
        timeline = project.timeline

        # 轨道详情
        tracks_info = []
        for track in timeline.tracks:
            tracks_info.append({
                "track_id": track.track_id,
                "type": track.track_type.value,
                "segment_count": len(track.segments),
                "duration_us": track.total_duration_us,
                "visible": track.visible,
                "muted": track.muted,
            })

        # 时长统计
        video_tracks = timeline.get_tracks_by_type(TrackType.VIDEO)
        audio_tracks = timeline.get_tracks_by_type(TrackType.AUDIO)
        text_tracks = timeline.get_tracks_by_type(TrackType.TEXT)

        video_duration = max(
            (t.total_duration_us for t in video_tracks),
            default=0,
        )

        # EDL 统计
        edl_count = 0
        if context.edl:
            edl_count = len(context.edl.decisions)

        # 分析摘要
        analysis_summary = {}
        if context.analysis:
            analysis_summary = {
                "transcript_length": len(context.analysis.transcript),
                "scene_count": len(context.analysis.scene_boundaries),
                "highlight_count": len(context.analysis.highlights),
                "language": context.analysis.language,
            }

        return {
            "project_name": project.name,
            "project_id": project.project_id,
            "total_duration_seconds": project.total_duration_seconds,
            "video_duration_seconds": video_duration / 1_000_000,
            "video_count": len(project.source_videos),
            "audio_count": len(project.source_audios),
            "subtitle_count": len(project.subtitles),
            "track_count": len(timeline.tracks),
            "tracks": tracks_info,
            "edl_decision_count": edl_count,
            "analysis_summary": analysis_summary,
            "canvas": {
                "width": timeline.canvas_config.width,
                "height": timeline.canvas_config.height,
                "ratio": timeline.canvas_config.ratio,
                "fps": timeline.canvas_config.fps,
            },
        }

    async def rollback(self, context: PipelineContext) -> None:
        logger.info("ReviewStage rolled back")
