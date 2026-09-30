"""长转短插件 — 将长视频自动裁切为多个短视频"""

from __future__ import annotations

import logging
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin

logger = logging.getLogger(__name__)


@register_plugin
class LongToShortPlugin(AIPlugin):
    """长转短插件 — 类似 Opus Clip 的逻辑"""

    plugin_id = "long_to_short"
    plugin_name = "智能长转短"
    version = "0.1.0"
    description = "将长视频自动裁切为多个适合短视频平台的片段"
    required_providers = ["llm"]

    input_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": "string"},
            "transcript": {"type": "string"},
            "scenes": {"type": "array"},
            "target_platform": {"type": "string", "default": "douyin"},
            "max_clips": {"type": "integer", "default": 5},
            "aspect_ratio": {"type": "string", "default": "9:16"},
        },
        "required": ["video_path", "transcript"],
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        video_path = input_data["video_path"]
        transcript = input_data["transcript"]
        scenes = input_data.get("scenes", [])
        platform = input_data.get("target_platform", "douyin")
        max_clips = input_data.get("max_clips", 5)
        aspect_ratio = input_data.get("aspect_ratio", "9:16")

        # 1. 调用高光提取
        highlight_plugin = context.get_plugin("highlight")
        highlight_result = await highlight_plugin.process({
            "video_path": video_path,
            "transcript": transcript,
            "scenes": scenes,
            "max_clips": max_clips,
            "platform": platform,
        }, context)

        highlights = highlight_result.get("highlights", [])

        # 2. 为每个高光片段生成字幕
        subtitle_plugin = context.get_plugin("subtitle")
        # (实际应提取对应时间段的字幕)

        # 3. 推荐 BGM
        bgm_plugin = context.get_plugin("bgm")
        bgm_result = await bgm_plugin.process({
            "video_content": transcript[:500],
            "duration_seconds": 30,
        }, context)

        # 4. 组装短视频规格
        short_videos = []
        for i, h in enumerate(highlights):
            short_videos.append({
                "index": i + 1,
                "title": h.get("title", f"片段{i+1}"),
                "start_second": h.get("start_second", 0),
                "end_second": h.get("end_second", 30),
                "aspect_ratio": aspect_ratio,
                "subtitles": [],
                "bgm": bgm_result.get("recommendations", [{}])[0] if bgm_result.get("recommendations") else {},
                "score": h.get("score", 0),
            })

        return {
            "short_videos": short_videos,
            "clip_count": len(short_videos),
            "source_video": video_path,
        }
