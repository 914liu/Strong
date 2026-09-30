"""Analyze Stage — 智能分析阶段

职责：
1. 并行调用 ASR（语音转录）和场景检测
2. 串行调用高光提取（依赖 ASR + 场景检测结果）
3. 可选调用内容标签 / 情绪分析
4. 将分析结果写入 PipelineContext.analysis
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..core.events import Event, EventType, get_event_bus
from ..core.models import AnalysisResult, PipelineContext, SubtitleBlock, TimeRange
from ..core.pipeline import Stage
from ..core.plugin import PluginContext, get_global_registry

logger = logging.getLogger(__name__)


class AnalyzeStage(Stage):
    """智能分析阶段

    并行调用多个分析插件：
    - ASR → 语音转录 + 带时间戳字幕
    - 场景检测 → 场景切换点列表
    - 高光提取 → 精彩片段推荐（依赖前两者）

    可通过实例属性控制各子任务的开关：
        asr_enabled (bool)
        scene_enabled (bool)
        highlight_enabled (bool)
    """

    name = "analyze"
    dependencies = ["ingest"]
    can_skip = False
    timeout = 600

    def __init__(
        self,
        asr_enabled: bool = True,
        scene_enabled: bool = True,
        highlight_enabled: bool = True,
    ) -> None:
        self.asr_enabled = asr_enabled
        self.scene_enabled = scene_enabled
        self.highlight_enabled = highlight_enabled

    async def validate(self, context: PipelineContext) -> bool:
        """校验是否有可分析的素材"""
        return bool(context.project.source_videos)

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        event_bus = get_event_bus()
        analysis = AnalysisResult()
        plugin_registry = get_global_registry()

        # 取第一个视频路径作为主分析目标
        video_path = context.project.source_videos[0].path
        logger.info(f"AnalyzeStage: analyzing {video_path}")

        # ── 并行阶段：ASR + 场景检测 ────────────────
        parallel_tasks: list[asyncio.Task] = []

        if self.asr_enabled and plugin_registry.has_plugin("asr"):
            parallel_tasks.append(
                asyncio.create_task(
                    self._run_asr(plugin_registry, video_path, context, analysis)
                )
            )
        elif not self.asr_enabled:
            logger.info("ASR disabled by configuration")

        if self.scene_enabled and plugin_registry.has_plugin("scene_detect"):
            parallel_tasks.append(
                asyncio.create_task(
                    self._run_scene_detect(plugin_registry, video_path, context, analysis)
                )
            )
        elif not self.scene_enabled:
            logger.info("Scene detection disabled by configuration")

        if parallel_tasks:
            results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
            # 记录并行任务中的异常（不中断流程）
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Parallel analysis task {i} failed: {result}")

        await event_bus.emit_async(Event(
            type=EventType.STAGE_PROGRESS,
            data={"stage": self.name, "progress": 0.5, "phase": "parallel_done"},
            source=self.name,
        ))

        # ── 串行阶段：高光提取（依赖 ASR 结果） ─────
        if self.highlight_enabled and plugin_registry.has_plugin("highlight"):
            if analysis.transcript:
                try:
                    await self._run_highlight(plugin_registry, video_path, context, analysis)
                except Exception as e:
                    logger.error(f"Highlight analysis failed: {e}")
            else:
                logger.warning("Skipping highlight extraction: no transcript available")

        await event_bus.emit_async(Event(
            type=EventType.STAGE_PROGRESS,
            data={"stage": self.name, "progress": 0.8, "phase": "highlight_done"},
            source=self.name,
        ))

        # ── 可选：内容标签 / 情绪分析（未来扩展） ────
        # if plugin_registry.has_plugin("content_tag"):
        #     ...

        # ── 将 ASR 字幕转为 SubtitleBlock ────────────
        # analysis.subtitles 可能已经从 ASR 插件拿到了 dict 列表
        # 确保它们是 SubtitleBlock 对象
        normalized_subtitles = self._normalize_subtitles(analysis.subtitles)
        analysis.subtitles = normalized_subtitles

        context.analysis = analysis

        logger.info(
            f"AnalyzeStage complete: "
            f"{len(analysis.transcript)} chars transcript, "
            f"{len(analysis.subtitles)} subtitles, "
            f"{len(analysis.scene_boundaries)} scenes, "
            f"{len(analysis.highlights)} highlights"
        )

        return {
            "transcript_length": len(analysis.transcript),
            "subtitle_count": len(analysis.subtitles),
            "scene_count": len(analysis.scene_boundaries),
            "highlight_count": len(analysis.highlights),
            "language": analysis.language,
        }

    # ──────────────────────────────────────────────
    # 子任务实现
    # ──────────────────────────────────────────────

    async def _run_asr(
        self,
        registry: Any,
        video_path: str,
        context: PipelineContext,
        analysis: AnalysisResult,
    ) -> None:
        """执行 ASR 语音识别"""
        try:
            asr_plugin = registry.get_plugin("asr")
            plugin_ctx = self._build_plugin_context(context)
            result = await asr_plugin.process(
                {"video_path": video_path},
                plugin_ctx,
            )
            analysis.transcript = result.get("transcript", "")
            analysis.subtitles = result.get("subtitles", [])
            analysis.language = result.get("language", "zh")
            logger.info(f"ASR completed: {len(analysis.transcript)} chars, {len(analysis.subtitles)} segments")
        except Exception as e:
            logger.error(f"ASR failed: {e}")
            raise

    async def _run_scene_detect(
        self,
        registry: Any,
        video_path: str,
        context: PipelineContext,
        analysis: AnalysisResult,
    ) -> None:
        """执行场景检测"""
        try:
            sd_plugin = registry.get_plugin("scene_detect")
            plugin_ctx = self._build_plugin_context(context)

            # 从配置中读取检测阈值
            threshold = 30.0
            if context.extra.get("config"):
                threshold = context.extra["config"].get("scene_threshold", 30.0)

            result = await sd_plugin.process(
                {"video_path": video_path, "threshold": threshold},
                plugin_ctx,
            )
            for scene in result.get("scenes", []):
                analysis.scene_boundaries.append(
                    TimeRange(
                        start_us=scene["start_us"],
                        duration_us=scene["end_us"] - scene["start_us"],
                    )
                )
            logger.info(f"Scene detection completed: {len(analysis.scene_boundaries)} scenes")
        except Exception as e:
            logger.error(f"Scene detection failed: {e}")
            raise

    async def _run_highlight(
        self,
        registry: Any,
        video_path: str,
        context: PipelineContext,
        analysis: AnalysisResult,
    ) -> None:
        """执行高光提取"""
        highlight_plugin = registry.get_plugin("highlight")
        plugin_ctx = self._build_plugin_context(context)

        # 从 extra 参数获取高光配置
        max_clips = context.input.extra_params.get("max_clips", 3)
        platform = context.input.extra_params.get("platform", "douyin")

        result = await highlight_plugin.process({
            "video_path": video_path,
            "transcript": analysis.transcript,
            "scenes": [
                {"start_us": tr.start_us, "end_us": tr.end_us}
                for tr in analysis.scene_boundaries
            ],
            "max_clips": max_clips,
            "platform": platform,
        }, plugin_ctx)

        analysis.highlights = result.get("highlights", [])
        logger.info(f"Highlight extraction completed: {len(analysis.highlights)} clips")

    # ──────────────────────────────────────────────
    # 辅助方法
    # ──────────────────────────────────────────────

    def _build_plugin_context(self, context: PipelineContext) -> PluginContext:
        """构建插件运行时上下文"""
        return PluginContext(
            config=context.extra.get("config"),
            provider_registry=context.extra.get("provider_registry"),
            plugin_registry=get_global_registry(),
            ffmpeg=context.extra.get("ffmpeg"),
            temp_dir=context.temp_dir,
            cache_dir=context.cache_dir,
        )

    def _normalize_subtitles(
        self, raw_subtitles: list[Any]
    ) -> list[SubtitleBlock]:
        """将 ASR 返回的字幕 dict 标准化为 SubtitleBlock 列表"""
        blocks: list[SubtitleBlock] = []
        for sub in raw_subtitles:
            if isinstance(sub, SubtitleBlock):
                blocks.append(sub)
            elif isinstance(sub, dict):
                start_us = sub.get("start_us", 0)
                end_us = sub.get("end_us", 0)
                blocks.append(SubtitleBlock(
                    text=sub.get("text", ""),
                    time_range=TimeRange(
                        start_us=start_us,
                        duration_us=end_us - start_us,
                    ),
                ))
        return blocks

    async def rollback(self, context: PipelineContext) -> None:
        """回滚：清除分析结果"""
        context.analysis = None
        logger.info("AnalyzeStage rolled back: cleared analysis result")
