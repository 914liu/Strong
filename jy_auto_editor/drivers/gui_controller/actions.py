"""操作执行器 — 点击/拖拽/快捷键"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from ...core.exceptions import GUIControllerError

logger = logging.getLogger(__name__)


class ActionExecutor:
    """GUI 操作执行器，带验证和重试"""

    MAX_RETRIES = 3
    RETRY_DELAYS = [1.0, 2.0, 5.0]

    def __init__(self, finder) -> None:
        self._finder = finder

    async def click(self, element, retries: int = MAX_RETRIES) -> None:
        """点击元素"""
        for attempt in range(retries):
            try:
                element.Click()
                await asyncio.sleep(0.3)
                return
            except Exception as e:
                if attempt < retries - 1:
                    delay = self.RETRY_DELAYS[attempt]
                    logger.warning(f"Click failed (attempt {attempt+1}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    raise GUIControllerError(f"Click failed after {retries} attempts: {e}")

    async def double_click(self, element) -> None:
        """双击元素"""
        element.DoubleClick()
        await asyncio.sleep(0.3)

    async def right_click(self, element) -> None:
        """右键点击"""
        element.RightClick()
        await asyncio.sleep(0.3)

    async def input_text(self, element, text: str, clear_first: bool = True) -> None:
        """输入文本"""
        if clear_first:
            element.SelectAll()
            await asyncio.sleep(0.1)
        element.SendKeys(text)
        await asyncio.sleep(0.2)

    async def press_key(self, key: str) -> None:
        """按下快捷键

        Args:
            key: 按键组合，如 "Ctrl+E", "Ctrl+S", "Delete"
        """
        try:
            import uiautomation as uia
            # 解析组合键
            parts = key.split("+")
            modifiers = []
            main_key = parts[-1].strip()

            for part in parts[:-1]:
                mod = part.strip().lower()
                if mod == "ctrl":
                    modifiers.append(uia.Keys.VK_CONTROL)
                elif mod == "alt":
                    modifiers.append(uia.Keys.VK_MENU)
                elif mod == "shift":
                    modifiers.append(uia.Keys.VK_SHIFT)

            # 发送按键
            uia.SendKey(main_key, waitTime=0.3)
        except ImportError:
            raise GUIControllerError("uiautomation not available for key press")

    async def drag(self, element, x: int, y: int) -> None:
        """拖拽元素"""
        element.Drag(x, y)
        await asyncio.sleep(0.5)

    async def set_value(self, element, value: str) -> None:
        """设置元素值"""
        element.GetValuePattern().SetValue(value)
        await asyncio.sleep(0.2)
