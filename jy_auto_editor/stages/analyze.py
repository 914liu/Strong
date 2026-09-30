"""Analyze Stage — 智能分析阶段"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..core.models import AnalysisResult, PipelineContext
from ..core.pipeline import Stage
from ..core.plugin import PluginContext, get_global_registry

logger = logging.getLogger(__name__)


class AnalyzeStage(Stage):
    """智能分析阶段

    并行调用多个分析插件：
    - ASR → 语音转录
    - 场景检测 → 场景切换点
    - 高光提取 → 精彩片段
    - 内容分类 → 标签/情绪
    """

    name = "analyze"
    dependencies = ["ingest"]
    can_skip = False
    timeout = 600

    async def execute(self, context: PipelineContext) -> dict:
        analysis = AnalysisResult()
        plugin_registry = get_global_registry()

        # 获取第一个视频路径
        video_path = ""
        if context.project.source_videos:
            video_path = context.project.source_videos[0].path

        if not video_path:
            logger.warning("No video files to analyze")
            return {"analysis": "skipped", "reason": "no video files"}

        tasks = []

        # ASR 分析
        if plugin_registry.has_plugin("asr"):
            tasks.append(self._run_asr(plugin_registry, video_path, context, analysis))

        # 场景检测
        if plugin_registry.has_plugin("scene_detect"):
            tasks.append(self._run_scene_detect(plugin_registry, video_path, context, analysis))

        # 并行执行所有分析任务
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # 高光提取（依赖 ASR 和场景检测结果）
        if plugin_registry.has_plugin("highlight") and analysis.transcript:
            try:
                highlight_plugin = plugin_registry.get_plugin("highlight")
                plugin_ctx = PluginContext(
                    config=context.extra.get("config"),
                    temp_dir=context.temp_dir,
                    cache_dir=context.cache_dir,
                )
                result = await highlight_plugin.process({
                    "video_path": video_path,
                    "transcript": analysis.transcript,
                    "scenes": [{"start_us": tr.start_us, "end_us": tr.end_us} for tr in analysis.scene_boundaries],
                }, plugin_ctx)
                analysis.highlights = result.get("highlights", [])
            except Exception as e:
                logger.error(f"Highlight analysis failed: {e}")

        context.analysis = analysis
        return {
            "transcript_length": len(analysis.transcript),
            "subtitle_count": len(analysis.subtitles),
            "scene_count": len(analysis.scene_boundaries),
            "highlight_count": len(analysis.highlights),
        }

    async def _run_asr(self, registry, video_path, context, analysis):
        try:
            asr_plugin = registry.get_plugin("asr")
            plugin_ctx = PluginContext(
                config=context.extra.get("config"),
                temp_dir=context.temp_dir,
                cache_dir=context.cache_dir,
            )
            result = await asr_plugin.process({"video_path": video_path}, plugin_ctx)
            analysis.transcript = result.get("transcript", "")
            analysis.subtitles = result.get("subtitles", [])
            analysis.language = result.get("language", "zh")
            logger.info(f"ASR completed: {len(analysis.transcript)} chars")
        except Exception as e:
            logger.error(f"ASR failed: {e}")

    async def _run_scene_detect(self, registry, video_path, context, analysis):
        try:
            sd_plugin = registry.get_plugin("scene_detect")
            plugin_ctx = PluginContext(
                config=context.extra.get("config"),
                temp_dir=context.temp_dir,
                cache_dir=context.cache_dir,
            )
            result = await sd_plugin.process({"video_path": video_path}, plugin_ctx)
            from ..core.models import TimeRange
            for scene in result.get("scenes", []):
                analysis.scene_boundaries.append(
                    TimeRange(start_us=scene["start_us"], duration_us=scene["end_us"] - scene["start_us"])
                )
            logger.info(f"Scene detection completed: {len(analysis.scene_boundaries)} scenes")
        except Exception as e:
            logger.error(f"Scene detection failed: {e}")
