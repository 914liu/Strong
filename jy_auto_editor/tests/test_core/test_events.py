"""core/events 单元测试"""

import asyncio
import pytest
from jy_auto_editor.core.events import Event, EventBus, EventType


class TestEventBus:
    def test_on_and_emit(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.on(EventType.LOG, handler)
        event = Event(type=EventType.LOG, data={"msg": "hello"})
        bus.emit(event)
        assert len(received) == 1
        assert received[0].data["msg"] == "hello"

    def test_multiple_handlers(self):
        bus = EventBus()
        count = {"a": 0, "b": 0}

        def handler_a(event: Event):
            count["a"] += 1

        def handler_b(event: Event):
            count["b"] += 1

        bus.on(EventType.STAGE_STARTED, handler_a)
        bus.on(EventType.STAGE_STARTED, handler_b)
        bus.emit(Event(type=EventType.STAGE_STARTED))
        assert count["a"] == 1
        assert count["b"] == 1

    def test_off(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.on(EventType.LOG, handler)
        bus.off(EventType.LOG, handler)
        bus.emit(Event(type=EventType.LOG))
        assert len(received) == 0

    def test_emit_unknown_event_no_error(self):
        bus = EventBus()
        # Should not raise
        bus.emit(Event(type=EventType.LOG))

    def test_async_handler(self):
        bus = EventBus()
        received = []

        async def async_handler(event: Event):
            received.append(event)

        bus.on_async(EventType.PIPELINE_STARTED, async_handler)

        async def run():
            await bus.emit_async(Event(type=EventType.PIPELINE_STARTED))

        asyncio.get_event_loop().run_until_complete(run())
        assert len(received) == 1

    def test_event_types_exist(self):
        assert EventType.PIPELINE_STARTED.value == "pipeline.started"
        assert EventType.PIPELINE_COMPLETED.value == "pipeline.completed"
        assert EventType.PIPELINE_FAILED.value == "pipeline.failed"
        assert EventType.STAGE_STARTED.value == "stage.started"
        assert EventType.STAGE_COMPLETED.value == "stage.completed"
        assert EventType.STAGE_FAILED.value == "stage.failed"

    def test_clear(self):
        bus = EventBus()
        received = []

        def handler(event: Event):
            received.append(event)

        bus.on(EventType.LOG, handler)
        bus.clear()
        bus.emit(Event(type=EventType.LOG))
        assert len(received) == 0

    def test_handler_exception_doesnt_break(self):
        bus = EventBus()
        received = []

        def bad_handler(event: Event):
            raise ValueError("oops")

        def good_handler(event: Event):
            received.append(event)

        bus.on(EventType.LOG, bad_handler)
        bus.on(EventType.LOG, good_handler)
        bus.emit(Event(type=EventType.LOG))
        # good_handler should still be called despite bad_handler raising
        assert len(received) == 1
