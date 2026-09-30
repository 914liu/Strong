"""操作结果校验 — 截图对比/状态检查"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class OperationVerifier:
    """操作结果校验器"""

    def verify_element_exists(self, element, timeout: float = 5.0) -> bool:
        """验证元素是否存在"""
        try:
            return element.Exists(0, int(timeout * 1000))
        except Exception:
            return False

    def verify_text_content(self, element, expected: str) -> bool:
        """验证元素文本内容"""
        try:
            actual = element.Name
            return expected in actual
        except Exception:
            return False

    def verify_export_dialog(self, parent) -> bool:
        """验证导出对话框已打开"""
        try:
            # 查找导出对话框的特征元素
            dialog = parent.ElementControl(Name="导出")
            return dialog.Exists(0, 3000)
        except Exception:
            return False

    def take_screenshot(self, path: str = "") -> Optional[str]:
        """截取屏幕（用于调试和状态记录）"""
        try:
            import uiautomation as uia
            bmp = uia.GetScreenAsImage()
            if bmp:
                save_path = path or "screenshot.png"
                bmp.Save(save_path)
                return save_path
        except Exception as e:
            logger.debug(f"Screenshot failed: {e}")
        return None
