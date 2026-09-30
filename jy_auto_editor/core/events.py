"""事件总线 — 进度通知、状态变更"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional


class EventType(str, Enum):
    PIPELINE_STARTED = "pipeline.started"
    PIPELINE_COMPLETED = "pipeline.completed"
    PIPELINE_FAILED = "pipeline.failed"
    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"
    STAGE_SKIPPED = "stage.skipped"
    STAGE_PROGRESS = "stage.progress"
    EXPORT_STARTED = "export.started"
    EXPORT_PROGRESS = "export.progress"
    EXPORT_COMPLETED = "export.completed"
    AI_PLUGIN_INVOKED = "ai.plugin.invoked"
    AI_PLUGIN_COMPLETED = "ai.plugin.completed"
    LOG = "log"


@dataclass
class Event:
    """事件"""
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""                   # 事件来源（stage name / plugin id）


# 事件处理器类型
EventHandler = Callable[[Event], Any]
AsyncEventHandler = Callable[[Event], Any]


class EventBus:
    """简单的事件总线，支持同步和异步处理器"""

    def __init__(self) -> None:
        self._handlers: dict[EventType, list[EventHandler]] = {}
        self._async_handlers: dict[EventType, list[AsyncEventHandler]] = {}

    def on(self, event_type: EventType, handler: EventHandler) -> None:
        """注册同步事件处理器"""
        self._handlers.setdefault(event_type, []).append(handler)

    def on_async(self, event_type: EventType, handler: AsyncEventHandler) -> None:
        """注册异步事件处理器"""
        self._async_handlers.setdefault(event_type, []).append(handler)

    def off(self, event_type: EventType, handler: EventHandler) -> None:
        """移除事件处理器"""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    def emit(self, event: Event) -> None:
        """同步发送事件"""
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception:
                pass                 # 事件处理器异常不应影响主流程

    async def emit_async(self, event: Event) -> None:
        """异步发送事件（同时调用同步和异步处理器）"""
        # 同步处理器
        self.emit(event)
        # 异步处理器
        for handler in self._async_handlers.get(event.type, []):
            try:
                await handler(event)
            except Exception:
                pass

    def clear(self) -> None:
        """清除所有处理器"""
        self._handlers.clear()
        self._async_handlers.clear()


# ──────────────────────────────────────────────
# 全局事件总线实例
# ──────────────────────────────────────────────

_global_event_bus: Optional[EventBus] = None


def get_event_bus() -> EventBus:
    """获取全局事件总线"""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def reset_event_bus() -> None:
    """重置全局事件总线（主要用于测试）"""
    global _global_event_bus
    _global_event_bus = None
