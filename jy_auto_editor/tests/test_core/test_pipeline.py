"""core/pipeline 单元测试"""

import asyncio
import pytest
from typing import Any

from jy_auto_editor.core.pipeline import Pipeline, Stage, StageStatus, PipelineStatus
from jy_auto_editor.core.models import ProjectInput, PipelineContext
from jy_auto_editor.core.exceptions import StageFailedError, PipelineError
from jy_auto_editor.core.events import reset_event_bus


class MockStage(Stage):
    """测试用模拟阶段"""
    name = "mock_stage"

    def __init__(self, should_fail: bool = False):
        self.should_fail = should_fail
        self.executed = False

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        self.executed = True
        if self.should_fail:
            raise RuntimeError("Stage failed intentionally")
        return {"status": "ok"}


class OrderStage(Stage):
    """记录执行顺序的阶段"""

    def __init__(self, name: str, order_list: list):
        self.name = name
        self.order_list = order_list

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        self.order_list.append(self.name)
        return {}


class TestPipeline:
    def setup_method(self):
        reset_event_bus()

    def test_create_pipeline(self):
        pipeline = Pipeline(name="test")
        assert pipeline.name == "test"
        assert pipeline.status == PipelineStatus.IDLE
        assert len(pipeline.stages) == 0

    def test_add_stage(self):
        pipeline = Pipeline()
        stage = MockStage()
        pipeline.add_stage(stage)
        assert len(pipeline.stages) == 1

    def test_run_executes_stages(self):
        reset_event_bus()
        pipeline = Pipeline(name="test")
        order = []
        pipeline.add_stage(OrderStage("first", order))
        pipeline.add_stage(OrderStage("second", order))

        project_input = ProjectInput()
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.run(project_input)
        )
        assert isinstance(result, PipelineContext)
        assert "first" in order
        assert "second" in order

    def test_run_stops_on_failure(self):
        reset_event_bus()
        pipeline = Pipeline(name="test")
        pipeline.add_stage(MockStage(should_fail=True))

        project_input = ProjectInput()
        with pytest.raises(StageFailedError):
            asyncio.get_event_loop().run_until_complete(
                pipeline.run(project_input)
            )
        assert pipeline.status == PipelineStatus.FAILED

    def test_run_empty_pipeline(self):
        reset_event_bus()
        pipeline = Pipeline(name="empty")
        project_input = ProjectInput()
        result = asyncio.get_event_loop().run_until_complete(
            pipeline.run(project_input)
        )
        assert result is not None
        assert pipeline.status == PipelineStatus.COMPLETED

    def test_get_status(self):
        reset_event_bus()
        pipeline = Pipeline(name="test")
        pipeline.add_stage(MockStage())
        project_input = ProjectInput()
        asyncio.get_event_loop().run_until_complete(
            pipeline.run(project_input)
        )
        status = pipeline.get_status()
        assert status["pipeline"] == "test"
        assert status["status"] == "completed"

    def test_skip_stage(self):
        reset_event_bus()

        class SkippableStage(Stage):
            name = "skippable"
            can_skip = True

            async def execute(self, context):
                return {}

            async def validate(self, context):
                return False  # 校验不通过，应跳过

        pipeline = Pipeline(name="test")
        pipeline.add_stage(SkippableStage())
        project_input = ProjectInput()
        asyncio.get_event_loop().run_until_complete(
            pipeline.run(project_input)
        )
        result = pipeline.stage_results.get("skippable")
        assert result is not None
        assert result.status == StageStatus.SKIPPED
