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

            # 4. 设置输出路径
            await self._set_output_path(export_dialog, output_path)

            # 4.5 设置导出参数（分辨率、编码等）
            await self._set_export_params(export_dialog, config)

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

    async def _set_output_path(self, dialog, output_path: str) -> None:
        """在导出对话框中设置输出路径

        尝试多种 UI 控件类型来定位路径输入框：
        1. 查找 Edit 控件（路径输入框）
        2. 查找 "浏览" 按钮旁的文本框
        3. 通过剪贴板粘贴路径
        """
        try:
            # 尝试查找路径编辑框（多种名称匹配）
            path_edit = None
            for name_hint in ["路径", "输出", "保存", "位置"]:
                try:
                    path_edit = self._finder.find_edit(dialog, name=name_hint, timeout=2)
                    if path_edit is not None:
                        break
                except Exception:
                    continue

            if path_edit is not None:
                await self._executor.input_text(path_edit, output_path, clear_first=True)
                logger.info(f"Set export output path: {output_path}")
                return

            # 回退：尝试查找 "浏览" 按钮，通过文件对话框设置路径
            try:
                browse_btn = self._finder.find_button(dialog, name="浏览", timeout=2)
                if browse_btn is not None:
                    await self._executor.click(browse_btn)
                    await asyncio.sleep(1)

                    # 在文件保存对话框中设置路径
                    try:
                        save_dialog = self._finder.find_element(
                            dialog, name="另存为", timeout=5
                        )
                        file_name_edit = self._finder.find_edit(
                            save_dialog, name="文件名", timeout=3
                        )
                        if file_name_edit is not None:
                            p = Path(output_path)
                            await self._executor.input_text(file_name_edit, p.name, clear_first=True)
                            save_btn = self._finder.find_button(save_dialog, name="保存")
                            if save_btn is not None:
                                await self._executor.click(save_btn)
                                await asyncio.sleep(1)
                                logger.info(f"Set export path via file dialog: {output_path}")
                                return
                    except Exception:
                        pass
            except Exception:
                pass

            logger.warning("Could not find path input control in export dialog")

        except Exception as e:
            logger.warning(f"Failed to set output path in GUI: {e}")

    async def _set_export_params(self, dialog, config: ExportConfig) -> None:
        """设置导出参数（分辨率、编码格式等）

        根据 ExportConfig 在导出对话框中选择对应选项。
        """
        try:
            # 设置分辨率（如果有下拉选择）
            if config.resolution:
                resolution_combo = self._finder.find_element(
                    dialog, name=config.resolution, timeout=3
                )
                if resolution_combo is not None:
                    await self._executor.click(resolution_combo)
                    await asyncio.sleep(0.5)

            # 设置帧率
            if config.fps and config.fps != 30:
                fps_name = str(int(config.fps))
                fps_combo = self._finder.find_element(
                    dialog, name=fps_name, timeout=3
                )
                if fps_combo is not None:
                    await self._executor.click(fps_combo)
                    await asyncio.sleep(0.5)

        except Exception as e:
            logger.debug(f"Export params setting skipped: {e}")
