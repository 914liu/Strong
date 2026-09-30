"""内容改写插件 — 使用 LLM 改写文本/字幕内容"""

from __future__ import annotations

import json
import logging
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin
from ...providers.base_provider import Message

logger = logging.getLogger(__name__)


@register_plugin
class ContentRewritePlugin(AIPlugin):
    """内容改写插件 — 支持多风格改写"""

    plugin_id = "content_rewrite"
    plugin_name = "智能内容改写"
    version = "0.1.0"
    description = "使用 LLM 改写文本/字幕内容，支持多种风格"
    required_providers = ["llm"]

    input_schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "需要改写的原始文本"},
            "style": {
                "type": "string",
                "default": "professional",
                "enum": ["professional", "casual", "humorous", "formal", "creative", "concise"],
                "description": "改写风格",
            },
            "language": {"type": "string", "default": "zh", "description": "目标语言"},
            "preserve_meaning": {"type": "boolean", "default": True, "description": "是否保留原意"},
            "max_length": {"type": "integer", "description": "最大输出长度(字符)"},
            "subtitles": {
                "type": "array",
                "description": "字幕列表（批量改写模式）",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "start_us": {"type": "integer"},
                        "end_us": {"type": "integer"},
                    },
                },
            },
        },
        "required": ["text"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "rewritten_text": {"type": "string"},
            "subtitles": {"type": "array"},
            "style": {"type": "string"},
        },
    }

    STYLE_PROMPTS = {
        "professional": "专业、简洁、权威的风格",
        "casual": "口语化、亲切自然的风格",
        "humorous": "幽默风趣、轻松活泼的风格",
        "formal": "正式、严谨的书面风格",
        "creative": "富有创意、生动形象的风格",
        "concise": "极简精炼、言简意赅的风格",
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        text = input_data["text"]
        style = input_data.get("style", "professional")
        language = input_data.get("language", "zh")
        preserve_meaning = input_data.get("preserve_meaning", True)
        max_length = input_data.get("max_length", 0)
        subtitles = input_data.get("subtitles", [])

        # 批量改写字幕模式
        if subtitles:
            return await self._rewrite_subtitles(subtitles, style, language, context)

        # 单文本改写
        style_desc = self.STYLE_PROMPTS.get(style, style)
        lang_name = "中文" if language == "zh" else "English" if language == "en" else language

        meaning_constraint = "必须保留原文的核心含义和关键信息" if preserve_meaning else "可以适当调整内容"
        length_constraint = f"输出长度不超过 {max_length} 个字符" if max_length else ""

        prompt = f"""请将以下文本改写为{style_desc}的风格。

要求：
1. 使用{lang_name}输出
2. {meaning_constraint}
3. {length_constraint}
4. 只输出改写后的文本，不要添加任何解释或标注

原始文本：
{text}"""

        llm = context.get_provider("llm")
        response = await llm.chat(
            messages=[
                Message(role="system", content="你是专业的文本改写助手，擅长按照指定风格改写文本。"),
                Message(role="user", content=prompt),
            ],
            temperature=0.7,
        )

        rewritten = response.content.strip()

        return {
            "rewritten_text": rewritten,
            "style": style,
            "original_length": len(text),
            "rewritten_length": len(rewritten),
        }

    async def _rewrite_subtitles(
        self,
        subtitles: list[dict],
        style: str,
        language: str,
        context: PluginContext,
    ) -> dict[str, Any]:
        """批量改写字幕文本"""
        style_desc = self.STYLE_PROMPTS.get(style, style)

        # 将所有字幕文本合并，用分隔符分开，一次性改写
        separator = " ||| "
        combined_text = separator.join(sub.get("text", "") for sub in subtitles)

        prompt = f"""请将以下字幕文本逐段改写为{style_desc}的风格。

要求：
1. 保持每段文本的独立性，用 " ||| " 分隔各段
2. 保留原始含义
3. 每段改写后保持相似的篇幅
4. 只输出改写结果，用 " ||| " 连接，不要添加其他内容

原始字幕：
{combined_text}"""

        llm = context.get_provider("llm")
        response = await llm.chat(
            messages=[
                Message(role="system", content="你是专业的字幕改写助手。"),
                Message(role="user", content=prompt),
            ],
            temperature=0.7,
        )

        rewritten_parts = response.content.strip().split("|||")
        rewritten_parts = [p.strip() for p in rewritten_parts]

        # 组装结果
        rewritten_subtitles = []
        for i, sub in enumerate(subtitles):
            new_text = rewritten_parts[i] if i < len(rewritten_parts) else sub.get("text", "")
            rewritten_subtitles.append({
                **sub,
                "text": new_text,
                "original_text": sub.get("text", ""),
            })

        return {
            "rewritten_text": "",
            "subtitles": rewritten_subtitles,
            "style": style,
            "count": len(rewritten_subtitles),
        }
