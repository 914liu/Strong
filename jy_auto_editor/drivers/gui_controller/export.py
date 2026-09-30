"""导出触发与监控"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Optional

from ...core.exceptions import ExportError
from ...core.models import ExportConfig, ExportResult

logger = logging.getLogger(__name__)


class ExportTrigger:
    """导出触发器 — 通过 GUI 自动化触发剪映导出"""

    def __init__(self, finder, executor) -> None:
        self._finder = finder
        self._executor = executor

    async def trigger_export(
        self,
        output_path: str,
        config: Optional[ExportConfig] = None,
        timeout: int = 600,
    ) -> ExportResult:
        """触发导出并等待完成

        Args:
            output_path: 输出文件路径
            config: 导出配置
            timeout: 超时秒数

        Returns:
            ExportResult
        """
        config = config or ExportConfig()

        try:
            # 1. 查找主窗口
            window = self._finder.find_window()

            # 2. 点击导出按钮 (Ctrl+E)
            await self._executor.press_key("Ctrl+E")
            await asyncio.sleep(2)

            # 3. 等待导出对话框
            export_dialog = self._finder.find_element(
                window, name="导出", timeout=10
            )

            # 4. 设置输出路径（如果可编辑）
            # 实际实现需要根据剪映版本调整
            # ...

            # 5. 点击"导出"按钮
            export_btn = self._finder.find_button(export_dialog, name="导出")
            await self._executor.click(export_btn)

            # 6. 等待导出完成
            success = await self._wait_for_export(
                Path(output_path), timeout
            )

            if success:
                file_size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
                return ExportResult(
                    success=True,
                    output_path=output_path,
                    file_size_bytes=file_size,
                )
            else:
                return ExportResult(
                    success=False,
                    error_message="Export timed out",
                )

        except Exception as e:
            return ExportResult(
                success=False,
                error_message=str(e),
            )

    async def _wait_for_export(
        self, output_path: Path, timeout: int
    ) -> bool:
        """等待导出完成（通过监控文件是否生成）"""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if output_path.exists() and output_path.stat().st_size > 0:
                # 等待文件写入完成（文件大小不再变化）
                await asyncio.sleep(2)
                size1 = output_path.stat().st_size
                await asyncio.sleep(2)
                size2 = output_path.stat().st_size
                if size1 == size2:
                    logger.info(f"Export completed: {output_path}")
                    return True
            await asyncio.sleep(3)
        return False
