"""场景检测插件 — 基于 PySceneDetect"""

from __future__ import annotations

import logging
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin

logger = logging.getLogger(__name__)


@register_plugin
class SceneDetectPlugin(AIPlugin):
    """场景检测插件"""

    plugin_id = "scene_detect"
    plugin_name = "场景检测"
    version = "0.1.0"
    description = "检测视频中的场景切换点"
    required_providers = ["cv"]

    input_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": "string"},
            "threshold": {"type": "number", "default": 30.0, "description": "检测阈值"},
        },
        "required": ["video_path"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_us": {"type": "integer"},
                        "end_us": {"type": "integer"},
                        "frame_number": {"type": "integer"},
                    },
                },
            },
            "scene_count": {"type": "integer"},
        },
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        video_path = input_data["video_path"]
        threshold = input_data.get("threshold", 30.0)

        try:
            from scenedetect import detect, ContentDetector

            scene_list = detect(video_path, ContentDetector(threshold=threshold))
            scenes = []
            for scene in scene_list:
                scenes.append({
                    "start_us": int(scene[0].get_seconds() * 1_000_000),
                    "end_us": int(scene[1].get_seconds() * 1_000_000),
                })
            return {"scenes": scenes, "scene_count": len(scenes)}

        except ImportError:
            logger.warning("PySceneDetect not installed, using fallback")
            # 回退到 CV Provider
            cv_provider = context.get_provider("cv")
            boundaries = await cv_provider.detect_scenes(video_path, threshold)
            scenes = [
                {"start_us": 0, "end_us": b.time_us, "frame_number": b.frame_number}
                for b in boundaries
            ]
            return {"scenes": scenes, "scene_count": len(scenes)}
