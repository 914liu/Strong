"""高光提取插件 — 基于 LLM 分析 + 音频能量"""

from __future__ import annotations

import logging
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin
from ...providers.base_provider import Message

logger = logging.getLogger(__name__)


@register_plugin
class HighlightPlugin(AIPlugin):
    """高光提取插件"""

    plugin_id = "highlight"
    plugin_name = "高光时刻提取"
    version = "0.1.0"
    description = "通过 LLM 分析视频内容，提取最适合短视频的高光片段"
    required_providers = ["llm"]

    input_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": "string"},
            "transcript": {"type": "string", "description": "视频转录文本"},
            "scenes": {"type": "array", "description": "场景信息"},
            "max_clips": {"type": "integer", "default": 3},
            "clip_duration_range": {"type": "array", "default": [15, 60], "description": "片段时长范围(秒)"},
            "platform": {"type": "string", "default": "douyin", "description": "目标平台"},
        },
        "required": ["video_path", "transcript"],
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        transcript = input_data["transcript"]
        scenes = input_data.get("scenes", [])
        max_clips = input_data.get("max_clips", 3)
        duration_range = input_data.get("clip_duration_range", [15, 60])
        platform = input_data.get("platform", "douyin")

        # 构建 LLM prompt
        prompt = f"""你是一个专业的视频编辑专家。请分析以下视频转录文本，从中选出最适合{platform}平台的{max_clips}个高光片段。

要求：
1. 每个片段时长在 {duration_range[0]}-{duration_range[1]} 秒之间
2. 优先选择有完整叙事、情绪高潮、金句或反转的片段
3. 片段之间不要重叠

视频转录文本：
{transcript}

场景信息：
{scenes}

请以 JSON 格式返回，每个片段包含：
- start_second: 起始秒数
- end_second: 结束秒数
- title: 片段标题
- reason: 选择理由
- score: 精彩程度评分 (1-10)
"""

        llm = context.get_provider("llm")
        response = await llm.chat(
            messages=[
                Message(role="system", content="你是专业视频编辑，擅长从长视频中提取高光片段。"),
                Message(role="user", content=prompt),
            ],
            temperature=0.3,
        )

        # 解析 LLM 返回的 JSON
        import json
        try:
            # 尝试从 response 中提取 JSON
            content = response.content
            # 查找 JSON 块
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            highlights = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse LLM response as JSON")
            highlights = []

        return {
            "highlights": highlights,
            "clip_count": len(highlights),
            "raw_response": response.content,
        }
