"""字幕生成插件 — 将 ASR 结果格式化为剪映字幕"""

from __future__ import annotations

import logging
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin

logger = logging.getLogger(__name__)


@register_plugin
class SubtitlePlugin(AIPlugin):
    """字幕生成插件"""

    plugin_id = "subtitle"
    plugin_name = "智能字幕生成"
    version = "0.1.0"
    description = "将 ASR 转录结果格式化为剪映字幕轨道"

    input_schema = {
        "type": "object",
        "properties": {
            "subtitles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "start_us": {"type": "integer"},
                        "end_us": {"type": "integer"},
                    },
                },
            },
            "font_name": {"type": "string", "default": "系统默认"},
            "font_size": {"type": "number", "default": 8.0},
            "font_color": {"type": "string", "default": "#FFFFFF"},
            "position_y": {"type": "number", "default": 0.85},
        },
        "required": ["subtitles"],
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        subtitles = input_data["subtitles"]
        font_name = input_data.get("font_name", "系统默认")
        font_size = input_data.get("font_size", 8.0)

        formatted = []
        for sub in subtitles:
            formatted.append({
                "text": sub.get("text", ""),
                "start_us": sub.get("start_us", 0),
                "duration_us": sub.get("end_us", 0) - sub.get("start_us", 0),
                "font_name": font_name,
                "font_size": font_size,
                "font_color": input_data.get("font_color", "#FFFFFF"),
                "position_y": input_data.get("position_y", 0.85),
                "alignment": "center",
            })

        return {
            "formatted_subtitles": formatted,
            "count": len(formatted),
        }
