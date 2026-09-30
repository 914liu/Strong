"""智能配乐推荐插件"""

from __future__ import annotations

import logging
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin
from ...providers.base_provider import Message

logger = logging.getLogger(__name__)


@register_plugin
class BGMPlugin(AIPlugin):
    """智能配乐推荐插件"""

    plugin_id = "bgm"
    plugin_name = "智能配乐推荐"
    version = "0.1.0"
    description = "根据视频内容和情绪推荐合适的背景音乐"
    required_providers = ["llm"]

    input_schema = {
        "type": "object",
        "properties": {
            "video_content": {"type": "string", "description": "视频内容描述或转录文本"},
            "duration_seconds": {"type": "number", "description": "视频时长"},
            "mood": {"type": "string", "description": "期望情绪 (可选)"},
            "genre": {"type": "string", "description": "音乐风格 (可选)"},
        },
        "required": ["video_content"],
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        content = input_data["video_content"]
        duration = input_data.get("duration_seconds", 60)
        mood = input_data.get("mood", "")
        genre = input_data.get("genre", "")

        prompt = f"""根据以下视频内容，推荐3首适合的背景音乐。

视频内容：{content}
视频时长：{duration}秒
{"期望情绪：" + mood if mood else ""}
{"音乐风格：" + genre if genre else ""}

请返回 JSON 格式，每首音乐包含：
- name: 音乐名称
- style: 风格
- bpm: 节奏 (BPM)
- mood: 情绪
- reason: 推荐理由
"""

        llm = context.get_provider("llm")
        response = await llm.chat(
            messages=[Message(role="user", content=prompt)],
            temperature=0.7,
        )

        import json
        try:
            bgm_list = json.loads(response.content)
        except json.JSONDecodeError:
            bgm_list = []

        return {
            "recommendations": bgm_list if isinstance(bgm_list, list) else [],
            "raw_response": response.content,
        }
