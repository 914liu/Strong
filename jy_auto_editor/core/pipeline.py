"""Pipeline 引擎 — Stage 编排、DAG 执行、断点续跑"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from .events import Event, EventType, get_event_bus
from .exceptions import PipelineError, StageFailedError, StageTimeoutError
from .models import PipelineContext, ProjectInput

logger = logging.getLogger(__name__)


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PipelineStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


@dataclass
class StageResult:
    """Stage 执行结果"""
    stage_name: str
    status: StageStatus
    output: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""
    duration_seconds: float = 0.0
    started_at: str = ""
    completed_at: str = ""


class Stage(ABC):
    """Pipeline 阶段基类"""

    name: str = ""
    dependencies: list[str] = []       # 依赖的前置 Stage 名称
    can_skip: bool = False             # 是否可跳过
    timeout: int = 600                 # 超时秒数（默认 10 分钟）

    @abstractmethod
    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        """执行阶段逻辑

        Args:
            context: Pipeline 上下文

        Returns:
            阶段输出数据，会存入 StageResult.output 并更新 context
        """
        ...

    async def validate(self, context: PipelineContext) -> bool:
        """执行前校验，返回 False 则跳过此 Stage"""
        return True

    async def rollback(self, context: PipelineContext) -> None:
        """失败时回滚清理"""
        pass

    def should_skip(self, context: PipelineContext) -> bool:
        """判断是否应跳过"""
        return False


class Pipeline:
    """Pipeline 引擎"""

    def __init__(
        self,
        name: str = "default",
        stages: Optional[list[Stage]] = None,
        db_path: str = "",
        event_bus: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> None:
        self.name = name
        self.stages: list[Stage] = stages or []
        self.status = PipelineStatus.IDLE
        self.stage_results: dict[str, StageResult] = {}
        self._db_path = db_path
        self._current_stage: Optional[str] = None
        self._event_bus = event_bus or get_event_bus()
        self._config = config

    @property
    def event_bus(self) -> Any:
        """暴露事件总线，供外部订阅事件"""
        return self._event_bus

    @property
    def config(self) -> Any:
        """暴露配置"""
        return self._config

    def add_stage(self, stage: Stage) -> None:
        """添加 Stage"""
        self.stages.append(stage)

    def register_stage(self, stage: Stage) -> None:
        """注册 Stage（带校验）

        - 检查 name 非空
        - 检查重名覆盖
        """
        if not stage.name:
            raise PipelineError(f"Stage class {type(stage).__name__} has no name")
        # 覆盖同名 Stage（允许后注册覆盖先注册）
        self.stages = [s for s in self.stages if s.name != stage.name]
        self.stages.append(stage)
        logger.debug(f"Registered stage: {stage.name}")

    def get_stage(self, name: str) -> Stage:
        """按名称获取 Stage 实例"""
        for stage in self.stages:
            if stage.name == name:
                return stage
        raise PipelineError(f"Stage '{name}' not found in pipeline")

    def _resolve_execution_order(self) -> list[Stage]:
        """根据依赖关系解析执行顺序（拓扑排序）"""
        stage_map = {s.name: s for s in self.stages}
        visited: set[str] = set()
        order: list[Stage] = []
        visiting: set[str] = set()       # 检测循环依赖

        def visit(name: str) -> None:
            if name in visiting:
                raise PipelineError(f"Circular dependency detected involving stage '{name}'")
            if name in visited:
                return
            visiting.add(name)
            stage = stage_map.get(name)
            if stage is None:
                raise PipelineError(f"Unknown stage dependency: '{name}'")
            for dep in stage.dependencies:
                visit(dep)
            visiting.discard(name)
            visited.add(name)
            order.append(stage)

        for stage in self.stages:
            visit(stage.name)

        return order

    def _get_parallel_groups(self) -> list[list[Stage]]:
        """将 Stage 分组，同组内的 Stage 可并行执行"""
        stage_map = {s.name: s for s in self.stages}
        completed: set[str] = set()
        groups: list[list[Stage]] = []
        remaining = set(s.name for s in self.stages)

        while remaining:
            # 找出所有依赖都已完成的 Stage
            ready = []
            for name in list(remaining):
                stage = stage_map[name]
                if all(dep in completed for dep in stage.dependencies):
                    ready.append(stage)
            if not ready:
                raise PipelineError("Cannot resolve execution order — possible circular dependency")
            groups.append(ready)
            for stage in ready:
                remaining.discard(stage.name)
                completed.add(stage.name)

        return groups

    async def run(
        self,
        input_data: ProjectInput,
        context: Optional[PipelineContext] = None,
        resume_from_checkpoint: bool = False,
    ) -> PipelineContext:
        """执行完整 Pipeline

        Args:
            input_data: 项目输入数据
            context: 可选的已有上下文（用于断点续跑）
            resume_from_checkpoint: 是否从上次中断处继续
        """
        if context is None:
            context = PipelineContext(input=input_data)

        self.status = PipelineStatus.RUNNING
        await self._event_bus.emit_async(Event(
            type=EventType.PIPELINE_STARTED,
            data={"pipeline": self.name, "input": str(input_data)},
            source="pipeline",
        ))

        # 初始化 SQLite 状态存储
        if resume_from_checkpoint:
            self._init_db()

        execution_order = self._get_parallel_groups()

        try:
            for group in execution_order:
                # 同组内的 Stage 并行执行
                tasks = []
                for stage in group:
                    # 检查断点续跑
                    if resume_from_checkpoint and self._is_stage_completed(stage.name):
                        logger.info(f"Stage '{stage.name}' already completed, skipping (resume)")
                        continue
                    tasks.append(self._run_stage(stage, context))

                if tasks:
                    await asyncio.gather(*tasks)

            self.status = PipelineStatus.COMPLETED
            await self._event_bus.emit_async(Event(
                type=EventType.PIPELINE_COMPLETED,
                data={"pipeline": self.name},
                source="pipeline",
            ))

        except Exception as e:
            self.status = PipelineStatus.FAILED
            await self._event_bus.emit_async(Event(
                type=EventType.PIPELINE_FAILED,
                data={"pipeline": self.name, "error": str(e)},
                source="pipeline",
            ))
            raise

        return context

    async def _run_stage(self, stage: Stage, context: PipelineContext) -> StageResult:
        """执行单个 Stage"""
        self._current_stage = stage.name
        started_at = datetime.now().isoformat()

        await self._event_bus.emit_async(Event(
            type=EventType.STAGE_STARTED,
            data={"stage": stage.name},
            source=stage.name,
        ))

        # 校验是否应跳过
        if stage.can_skip and (not await stage.validate(context) or stage.should_skip(context)):
            result = StageResult(
                stage_name=stage.name,
                status=StageStatus.SKIPPED,
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
            )
            self.stage_results[stage.name] = result
            self._save_stage_result(result)
            await self._event_bus.emit_async(Event(
                type=EventType.STAGE_SKIPPED,
                data={"stage": stage.name, "reason": "skipped by condition"},
                source=stage.name,
            ))
            return result

        start_time = time.monotonic()
        try:
            output = await asyncio.wait_for(
                stage.execute(context),
                timeout=stage.timeout,
            )
            duration = time.monotonic() - start_time

            result = StageResult(
                stage_name=stage.name,
                status=StageStatus.COMPLETED,
                output=output,
                duration_seconds=duration,
                started_at=started_at,
                completed_at=datetime.now().isoformat(),
            )
            self.stage_results[stage.name] = result
            self._save_stage_result(result)

            await self._event_bus.emit_async(Event(
                type=EventType.STAGE_COMPLETED,
                data={"stage": stage.name, "duration": duration},
                source=stage.name,
            ))
            return result

        except asyncio.TimeoutError:
            await stage.rollback(context)
            await self._event_bus.emit_async(Event(
                type=EventType.STAGE_FAILED,
                data={"stage": stage.name, "error": f"timeout after {stage.timeout}s"},
                source=stage.name,
            ))
            raise StageTimeoutError(stage.name, stage.timeout)
        except Exception as e:
            await stage.rollback(context)
            await self._event_bus.emit_async(Event(
                type=EventType.STAGE_FAILED,
                data={"stage": stage.name, "error": str(e)},
                source=stage.name,
            ))
            raise StageFailedError(stage.name, e)

    def get_status(self) -> dict[str, Any]:
        """获取 Pipeline 当前状态"""
        return {
            "pipeline": self.name,
            "status": self.status.value,
            "current_stage": self._current_stage,
            "stages": {
                name: {
                    "status": r.status.value,
                    "duration": r.duration_seconds,
                    "error": r.error_message,
                }
                for name, r in self.stage_results.items()
            },
        }

    # ──────────────────────────────────────────
    # SQLite 持久化（断点续跑）
    # ──────────────────────────────────────────

    def _init_db(self) -> None:
        if not self._db_path:
            return
        conn = sqlite3.connect(self._db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stage_results (
                pipeline TEXT,
                stage TEXT,
                status TEXT,
                output TEXT,
                duration REAL,
                started_at TEXT,
                completed_at TEXT,
                PRIMARY KEY (pipeline, stage)
            )
        """)
        conn.commit()
        conn.close()

    def _save_stage_result(self, result: StageResult) -> None:
        if not self._db_path:
            return
        conn = sqlite3.connect(self._db_path)
        conn.execute(
            """INSERT OR REPLACE INTO stage_results
               (pipeline, stage, status, output, duration, started_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                self.name,
                result.stage_name,
                result.status.value,
                json.dumps(result.output, ensure_ascii=False),
                result.duration_seconds,
                result.started_at,
                result.completed_at,
            ),
        )
        conn.commit()
        conn.close()

    def _is_stage_completed(self, stage_name: str) -> bool:
        if not self._db_path:
            return False
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT status FROM stage_results WHERE pipeline=? AND stage=?",
                (self.name, stage_name),
            ).fetchone()
            conn.close()
            return row is not None and row[0] == StageStatus.COMPLETED.value
        except Exception:
            return False
