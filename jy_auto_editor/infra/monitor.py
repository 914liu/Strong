"""
系统监控 - 资源使用与性能监控

监控 CPU、内存、GPU 使用情况，以及任务执行性能。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class SystemMetrics:
    """系统指标快照"""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0
    gpu_percent: float = 0.0
    gpu_memory_mb: float = 0.0
    disk_read_mb: float = 0.0
    disk_write_mb: float = 0.0
    timestamp: float = 0.0


@dataclass
class TaskMetrics:
    """任务执行指标"""
    task_name: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    status: str = "pending"  # pending / running / completed / failed
    error: Optional[str] = None


class PerformanceMonitor:
    """性能监控器"""

    def __init__(self, interval: float = 5.0):
        """
        Args:
            interval: 采样间隔(秒)
        """
        self.interval = interval
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._metrics_history: list[SystemMetrics] = []
        self._task_metrics: dict[str, TaskMetrics] = {}
        self._callbacks: list[Callable[[SystemMetrics], Awaitable[None]]] = []

    async def start(self) -> None:
        """启动监控"""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Performance monitor started")

    async def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Performance monitor stopped")

    async def _monitor_loop(self) -> None:
        """监控循环"""
        while self._running:
            try:
                metrics = await self._collect_metrics()
                self._metrics_history.append(metrics)

                # 保持最近1000条记录
                if len(self._metrics_history) > 1000:
                    self._metrics_history = self._metrics_history[-500:]

                # 触发回调
                for cb in self._callbacks:
                    try:
                        await cb(metrics)
                    except Exception as e:
                        logger.warning(f"Monitor callback error: {e}")

                await asyncio.sleep(self.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
                await asyncio.sleep(self.interval)

    async def _collect_metrics(self) -> SystemMetrics:
        """收集系统指标"""
        import os

        metrics = SystemMetrics(timestamp=time.time())

        try:
            import psutil
            process = psutil.Process(os.getpid())
            metrics.cpu_percent = process.cpu_percent()
            metrics.memory_mb = process.memory_info().rss / 1024 / 1024
            metrics.memory_percent = process.memory_percent()

            # 磁盘IO
            io = process.io_counters() if hasattr(process, 'io_counters') else None
            if io:
                metrics.disk_read_mb = io.read_bytes / 1024 / 1024
                metrics.disk_write_mb = io.write_bytes / 1024 / 1024
        except ImportError:
            logger.debug("psutil not available, skipping system metrics")
        except Exception as e:
            logger.debug(f"Failed to collect system metrics: {e}")

        # GPU 指标(可选，需要 pynvml)
        try:
            import pynvml
            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            metrics.gpu_percent = util.gpu
            metrics.gpu_memory_mb = mem.used / 1024 / 1024
        except (ImportError, Exception):
            pass  # GPU 监控不可用

        return metrics

    def on_metrics(self, callback: Callable[[SystemMetrics], Awaitable[None]]) -> None:
        """注册指标回调"""
        self._callbacks.append(callback)

    def track_task(self, task_name: str) -> "TaskTracker":
        """
        创建任务跟踪器

        Usage:
            async with monitor.track_task("analyze_stage"):
                await do_work()
        """
        return TaskTracker(self, task_name)

    def get_latest_metrics(self) -> Optional[SystemMetrics]:
        """获取最新指标"""
        return self._metrics_history[-1] if self._metrics_history else None

    def get_task_metrics(self, task_name: str) -> Optional[TaskMetrics]:
        """获取任务指标"""
        return self._task_metrics.get(task_name)

    def get_summary(self) -> dict:
        """获取监控摘要"""
        if not self._metrics_history:
            return {"error": "no metrics collected"}

        cpu_vals = [m.cpu_percent for m in self._metrics_history]
        mem_vals = [m.memory_mb for m in self._metrics_history]

        return {
            "samples": len(self._metrics_history),
            "cpu_avg": sum(cpu_vals) / len(cpu_vals),
            "cpu_max": max(cpu_vals),
            "memory_avg_mb": sum(mem_vals) / len(mem_vals),
            "memory_max_mb": max(mem_vals),
            "tasks_completed": sum(
                1 for t in self._task_metrics.values() if t.status == "completed"
            ),
            "tasks_failed": sum(
                1 for t in self._task_metrics.values() if t.status == "failed"
            ),
        }


class TaskTracker:
    """任务执行跟踪器(异步上下文管理器)"""

    def __init__(self, monitor: PerformanceMonitor, task_name: str):
        self.monitor = monitor
        self.task_name = task_name

    async def __aenter__(self):
        metrics = TaskMetrics(
            task_name=self.task_name,
            start_time=time.time(),
            status="running",
        )
        self.monitor._task_metrics[self.task_name] = metrics
        logger.debug(f"Task started: {self.task_name}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        metrics = self.monitor._task_metrics.get(self.task_name)
        if metrics:
            metrics.end_time = time.time()
            metrics.duration = metrics.end_time - metrics.start_time
            if exc_type:
                metrics.status = "failed"
                metrics.error = str(exc_val)
            else:
                metrics.status = "completed"
            logger.debug(
                f"Task {self.task_name}: {metrics.status} "
                f"({metrics.duration:.2f}s)"
            )
        return False
