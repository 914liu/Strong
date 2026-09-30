"""UI 元素定位器 — 基于 uiautomation"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ...core.exceptions import ElementNotFoundError

logger = logging.getLogger(__name__)


class UIElementFinder:
    """UI 元素定位器

    使用多种策略定位剪映界面元素：
    1. AutomationId（最稳定）
    2. Name / ClassName
    3. 图像识别（OpenCV 模板匹配，最后兜底）
    """

    def __init__(self) -> None:
        self._uia = None
        self._init_uiautomation()

    def _init_uiautomation(self) -> None:
        """初始化 uiautomation 库"""
        try:
            import uiautomation as uia
            self._uia = uia
        except ImportError:
            logger.warning(
                "uiautomation not installed. GUI automation disabled. "
                "Install with: pip install uiautomation"
            )

    def find_window(self, name: str = "剪映", timeout: float = 10.0):
        """查找剪映主窗口"""
        if self._uia is None:
            raise ElementNotFoundError("uiautomation not available")

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            window = self._uia.WindowControl(searchDepth=1, Name=name)
            if window.Exists(0, 0):
                return window
            time.sleep(0.5)
        raise ElementNotFoundError(f"JianYing window '{name}' not found within {timeout}s")

    def find_element(
        self,
        parent,
        automation_id: str = "",
        name: str = "",
        class_name: str = "",
        control_type: str = "",
        timeout: float = 5.0,
    ):
        """查找 UI 元素（多策略回退）"""
        if self._uia is None:
            raise ElementNotFoundError("uiautomation not available")

        kwargs = {}
        if automation_id:
            kwargs["AutomationId"] = automation_id
        if name:
            kwargs["Name"] = name
        if class_name:
            kwargs["ClassName"] = class_name
        if control_type:
            kwargs["ControlType"] = getattr(self._uia, control_type, None)

        start = time.monotonic()
        while time.monotonic() - start < timeout:
            element = parent.ElementControl(**kwargs) if kwargs else None
            if element and element.Exists(0, 0):
                return element
            time.sleep(0.3)

        raise ElementNotFoundError(
            f"Element not found: {kwargs}"
        )

    def find_button(self, parent, name: str = "", timeout: float = 5.0):
        """查找按钮"""
        if self._uia is None:
            raise ElementNotFoundError("uiautomation not available")
        return self.find_element(
            parent, name=name, control_type="ButtonControl", timeout=timeout
        )

    def find_edit(self, parent, name: str = "", timeout: float = 5.0):
        """查找输入框"""
        if self._uia is None:
            raise ElementNotFoundError("uiautomation not available")
        return self.find_element(
            parent, name=name, control_type="EditControl", timeout=timeout
        )

    def wait_for_element(
        self,
        parent,
        name: str = "",
        timeout: float = 30.0,
        interval: float = 0.5,
    ):
        """等待元素出现"""
        return self.find_element(parent, name=name, timeout=timeout)
