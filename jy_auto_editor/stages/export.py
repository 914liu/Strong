"""Export Stage — 导出阶段

职责：
1. 将项目时间线通过 Driver 保存为剪映草稿
2. 可选地通过 GUI 自动化触发视频导出
3. 无 Driver 时回退为 JSON 时间线导出
4. 记录导出结果到 PipelineContext
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..core.events import Event, EventType, get_event_bus
from ..core.models import ExportConfig, ExportResult, PipelineContext
from ..core.pipeline import Stage

logger = logging.getLogger(__name__)


class ExportStage(Stage):
    """导出阶段

    通过 HybridDriver 将编辑结果保存为剪映草稿，
    并可选地通过 GUI 自动化触发导出。

    当没有 Driver 可用时会回退到 JSON 导出模式。
    """

    name = "export"
    dependencies = ["edit"]
    can_skip = False
    timeout = 600

    async def validate(self, context: PipelineContext) -> bool:
        """校验时间线是否有内容可导出"""
        return bool(context.project.timeline.tracks)

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        event_bus = get_event_bus()
        driver = context.extra.get("driver")

        await event_bus.emit_async(Event(
            type=EventType.STAGE_PROGRESS,
            data={"stage": self.name, "progress": 0.1, "phase": "starting"},
            source=self.name,
        ))

        # ── 模式 A: 有 Driver → 保存剪映草稿 ─────────
        if driver is not None:
            return await self._export_with_driver(context, driver, event_bus)

        # ── 模式 B: 无 Driver → JSON 导出 ────────────
        return await self._export_as_json(context, event_bus)

    async def _export_with_driver(
        self,
        context: PipelineContext,
        driver: Any,
        event_bus: Any,
    ) -> dict[str, Any]:
        """通过 Driver 保存草稿并导出"""

        # 1. 保存项目草稿
        try:
            project_path = await driver.save_project(context.project)
            logger.info(f"Project saved to: {project_path}")
        except Exception as e:
            logger.error(f"Failed to save project: {e}")
            return {
                "success": False,
                "status": "save_failed",
                "error": str(e),
            }

        await event_bus.emit_async(Event(
            type=EventType.STAGE_PROGRESS,
            data={"stage": self.name, "progress": 0.5, "phase": "project_saved"},
            source=self.name,
        ))

        # 2. 触发视频导出
        output_config = context.extra.get("export_config")
        if output_config is None:
            output_config = ExportConfig(
                output_path=str(
                    Path(context.temp_dir or ".") / f"{context.project.name}_output.mp4"
                ),
            )
        elif not output_config.output_path:
            output_config.output_path = str(
                Path(context.temp_dir or ".") / f"{context.project.name}_output.mp4"
            )

        try:
            await event_bus.emit_async(Event(
                type=EventType.EXPORT_STARTED,
                data={
                    "project_id": context.project.project_id,
                    "output_path": output_config.output_path,
                },
                source=self.name,
            ))

            export_result = await driver.export_video(
                context.project.project_id,
                output_config,
            )
            context.export_result = export_result

            await event_bus.emit_async(Event(
                type=EventType.EXPORT_COMPLETED,
                data={
                    "success": export_result.success,
                    "output_path": export_result.output_path,
                    "file_size": export_result.file_size_bytes,
                },
                source=self.name,
            ))

            logger.info(
                f"Export completed: success={export_result.success}, "
                f"path={export_result.output_path}"
            )

            return {
                "success": export_result.success,
                "status": "exported",
                "output_path": export_result.output_path,
                "file_size": export_result.file_size_bytes,
                "error": export_result.error_message,
                "project_path": project_path,
            }

        except Exception as e:
            logger.error(f"Export failed: {e}")
            error_result = ExportResult(
                success=False,
                output_path=output_config.output_path,
                error_message=str(e),
            )
            context.export_result = error_result

            await event_bus.emit_async(Event(
                type=EventType.EXPORT_COMPLETED,
                data={
                    "success": False,
                    "error": str(e),
                },
                source=self.name,
            ))

            return {
                "success": False,
                "status": "export_failed",
                "error": str(e),
                "project_path": project_path,
            }

    async def _export_as_json(
        self,
        context: PipelineContext,
        event_bus: Any,
    ) -> dict[str, Any]:
        """无 Driver 时回退为 JSON 导出

        将时间线和项目数据序列化为 JSON 文件。
        """
        output_dir = Path(context.temp_dir or ".")
        output_dir.mkdir(parents=True, exist_ok=True)

        project_name = context.project.name or "untitled"
        output_path = output_dir / f"{project_name}_timeline.json"

        # 序列化项目数据
        project_data = self._serialize_project(context)

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(project_data, f, ensure_ascii=False, indent=2)

            file_size = output_path.stat().st_size
            logger.info(f"Timeline exported as JSON: {output_path} ({file_size} bytes)")

            export_result = ExportResult(
                success=True,
                output_path=str(output_path),
                file_size_bytes=file_size,
                duration_us=context.project.total_duration_us,
            )
            context.export_result = export_result

            await event_bus.emit_async(Event(
                type=EventType.EXPORT_COMPLETED,
                data={
                    "success": True,
                    "output_path": str(output_path),
                    "mode": "json",
                },
                source=self.name,
            ))

            return {
                "success": True,
                "status": "json_exported",
                "output_path": str(output_path),
                "file_size": file_size,
                "mode": "json",
            }

        except Exception as e:
            logger.error(f"JSON export failed: {e}")
            return {
                "success": False,
                "status": "json_export_failed",
                "error": str(e),
            }

    def _serialize_project(self, context: PipelineContext) -> dict[str, Any]:
        """将项目数据序列化为可 JSON 化的字典"""
        project = context.project
        timeline = project.timeline

        tracks_data = []
        for track in timeline.tracks:
            segments_data = []
            for seg in track.segments:
                segments_data.append({
                    "segment_id": seg.segment_id,
                    "material_id": seg.material_id,
                    "source_range": {
                        "start_us": seg.source_range.start_us,
                        "duration_us": seg.source_range.duration_us,
                    },
                    "target_range": {
                        "start_us": seg.target_range.start_us,
                        "duration_us": seg.target_range.duration_us,
                    },
                    "speed": seg.speed,
                    "volume": seg.volume,
                    "effects": [
                        {"type": e.effect_type, "name": e.effect_name, "params": e.params}
                        for e in seg.effects
                    ],
                    "transitions": [
                        {"type": t.transition_type, "duration_us": t.duration_us}
                        for t in seg.transitions
                    ],
                })
            tracks_data.append({
                "track_id": track.track_id,
                "type": track.track_type.value,
                "render_index": track.render_index,
                "visible": track.visible,
                "muted": track.muted,
                "segments": segments_data,
            })

        subtitles_data = [
            {
                "text": sub.text,
                "start_us": sub.time_range.start_us,
                "duration_us": sub.time_range.duration_us,
                "font_name": sub.font_name,
                "font_size": sub.font_size,
                "font_color": sub.font_color,
                "position_y": sub.position_y,
            }
            for sub in project.subtitles
        ]

        return {
            "project_id": project.project_id,
            "name": project.name,
            "canvas": {
                "width": timeline.canvas_config.width,
                "height": timeline.canvas_config.height,
                "ratio": timeline.canvas_config.ratio,
                "fps": timeline.canvas_config.fps,
            },
            "tracks": tracks_data,
            "subtitles": subtitles_data,
            "total_duration_us": project.total_duration_us,
            "source_videos": [
                {"path": v.path, "name": v.name, "media_type": v.media_type}
                for v in project.source_videos
            ],
            "source_audios": [
                {"path": a.path, "name": a.name, "duration_us": a.duration_us}
                for a in project.source_audios
            ],
            "metadata": {
                "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "exporter": "jy_auto_editor",
                "version": "0.1.0",
            },
        }

    async def rollback(self, context: PipelineContext) -> None:
        """回滚：清除导出结果"""
        context.export_result = None
        logger.info("ExportStage rolled back: cleared export result")
