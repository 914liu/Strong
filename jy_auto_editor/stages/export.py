"""Export Stage — 导出阶段"""

from __future__ import annotations

import logging
from pathlib import Path

from ..core.models import ExportConfig, PipelineContext
from ..core.pipeline import Stage

logger = logging.getLogger(__name__)


class ExportStage(Stage):
    """导出阶段

    通过 HybridDriver 将编辑结果保存为剪映草稿，
    并可选地通过 GUI 自动化触发导出。
    """

    name = "export"
    dependencies = ["edit"]
    can_skip = False
    timeout = 600

    async def execute(self, context: PipelineContext) -> dict:
        # 1. 保存草稿到剪映项目目录
        driver = context.extra.get("driver")
        if driver is None:
            logger.warning("No driver available, saving draft only")
            return {"status": "draft_saved", "message": "No driver for export"}

        # 2. 保存项目
        project_path = await driver.save_project(context.project)
        logger.info(f"Project saved to: {project_path}")

        # 3. 触发导出
        output_config = context.extra.get("export_config", ExportConfig())
        if not output_config.output_path:
            output_config.output_path = str(
                Path(context.temp_dir) / f"{context.project.name}_output.mp4"
            )

        export_result = await driver.export_video(
            context.project.project_id, output_config
        )

        context.export_result = export_result

        return {
            "success": export_result.success,
            "output_path": export_result.output_path,
            "file_size": export_result.file_size_bytes,
            "error": export_result.error_message,
        }
