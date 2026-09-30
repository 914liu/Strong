"""脚本生成插件 — 使用 LLM 根据视频分析结果生成剪辑脚本"""

from __future__ import annotations

import json
import logging
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin
from ...providers.base_provider import Message

logger = logging.getLogger(__name__)


@register_plugin
class ScriptGenPlugin(AIPlugin):
    """脚本生成插件 — 自动生成视频剪辑脚本"""

    plugin_id = "script_gen"
    plugin_name = "智能脚本生成"
    version = "0.1.0"
    description = "根据视频分析数据（转录、场景、高光等）自动生成剪辑脚本"
    required_providers = ["llm"]

    input_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": "string", "description": "源视频文件路径"},
            "transcript": {"type": "string", "description": "视频转录文本"},
            "scenes": {
                "type": "array",
                "description": "场景检测结果",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_us": {"type": "integer"},
                        "end_us": {"type": "integer"},
                    },
                },
            },
            "highlights": {
                "type": "array",
                "description": "高光片段信息",
            },
            "target_duration": {"type": "integer", "description": "目标时长(秒)"},
            "target_platform": {
                "type": "string",
                "default": "douyin",
                "enum": ["douyin", "kuaishou", "xiaohongshu", "bilibili", "youtube"],
                "description": "目标发布平台",
            },
            "video_type": {
                "type": "string",
                "default": "short",
                "enum": ["short", "narrative", "tutorial", "vlog", "commercial"],
                "description": "视频类型",
            },
            "extra_instructions": {"type": "string", "description": "额外的剪辑指令"},
        },
        "required": ["video_path", "transcript"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "script": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "segments": {"type": "array"},
                    "transitions": {"type": "array"},
                    "bgm_suggestion": {"type": "string"},
                    "subtitle_style": {"type": "string"},
                },
            },
            "total_duration": {"type": "number"},
            "segment_count": {"type": "integer"},
        },
    }

    PLATFORM_SPECS = {
        "douyin": {"aspect_ratio": "9:16", "max_duration": 60, "style": "节奏快、开头抓眼球"},
        "kuaishou": {"aspect_ratio": "9:16", "max_duration": 120, "style": "真实接地气"},
        "xiaohongshu": {"aspect_ratio": "3:4", "max_duration": 180, "style": "精致美观、有调性"},
        "bilibili": {"aspect_ratio": "16:9", "max_duration": 600, "style": "内容深度、有梗"},
        "youtube": {"aspect_ratio": "16:9", "max_duration": 1200, "style": "专业、结构清晰"},
    }

    VIDEO_TYPE_PROMPTS = {
        "short": "快节奏短视频，开头3秒必须抓住注意力",
        "narrative": "叙事型视频，注重故事线和情感节奏",
        "tutorial": "教程型视频，步骤清晰、重点突出",
        "vlog": "Vlog 风格，自然真实、有代入感",
        "commercial": "商业宣传视频，突出卖点、节奏紧凑",
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        video_path = input_data["video_path"]
        transcript = input_data["transcript"]
        scenes = input_data.get("scenes", [])
        highlights = input_data.get("highlights", [])
        target_duration = input_data.get("target_duration", 0)
        platform = input_data.get("target_platform", "douyin")
        video_type = input_data.get("video_type", "short")
        extra_instructions = input_data.get("extra_instructions", "")

        platform_spec = self.PLATFORM_SPECS.get(platform, self.PLATFORM_SPECS["douyin"])
        type_prompt = self.VIDEO_TYPE_PROMPTS.get(video_type, self.VIDEO_TYPE_PROMPTS["short"])

        if target_duration <= 0:
            target_duration = platform_spec["max_duration"]

        # 构建 LLM prompt
        scenes_json = json.dumps(scenes, ensure_ascii=False, indent=2) if scenes else "无"
        highlights_json = json.dumps(highlights, ensure_ascii=False, indent=2) if highlights else "无"
        extra_section = f"## 额外指令\n{extra_instructions}" if extra_instructions else ""

        prompt = f"""你是一个专业的视频剪辑师。请根据以下视频分析数据，生成一份完整的剪辑脚本。

## 视频信息
- 源文件: {video_path}
- 目标平台: {platform}（{platform_spec['style']}）
- 目标画幅: {platform_spec['aspect_ratio']}
- 目标时长: {target_duration}秒
- 视频类型: {type_prompt}

## 转录文本
{transcript}

## 场景检测结果
{scenes_json}

## 高光片段
{highlights_json}

{extra_section}

## 请生成剪辑脚本，JSON 格式包含：
- title: 视频标题
- segments: 片段数组，每个片段包含：
  - action: "keep" | "cut" | "trim" | "reorder"
  - start_us: 起始微秒
  - end_us: 结束微秒
  - purpose: 该片段的叙事目的
  - notes: 剪辑备注
- transitions: 转场数组，每个包含：
  - after_segment: 在第几个片段后
  - type: 转场类型 (cut/dissolve/fade/slide/zoom)
  - duration_us: 转场时长(微秒)
- bgm_suggestion: 背景音乐建议
- subtitle_style: 字幕风格建议
- opening_hook: 开头吸引策略
"""

        llm = context.get_provider("llm")
        response = await llm.chat(
            messages=[
                Message(
                    role="system",
                    content="你是专业的视频剪辑师，擅长根据内容分析数据制定剪辑方案。输出必须是合法的 JSON。",
                ),
                Message(role="user", content=prompt),
            ],
            temperature=0.4,
        )

        # 解析 LLM 返回的脚本
        script = self._parse_script(response.content)

        # 计算总时长
        total_duration = 0.0
        for seg in script.get("segments", []):
            start = seg.get("start_us", 0)
            end = seg.get("end_us", 0)
            total_duration += (end - start) / 1_000_000

        return {
            "script": script,
            "total_duration": total_duration,
            "segment_count": len(script.get("segments", [])),
            "target_platform": platform,
            "target_duration": target_duration,
            "raw_response": response.content,
        }

    def _parse_script(self, content: str) -> dict:
        """解析 LLM 返回的脚本 JSON"""
        try:
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            script = json.loads(content)
            if isinstance(script, dict):
                return script
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse script JSON from LLM response")

        # 返回空脚本结构
        return {
            "title": "",
            "segments": [],
            "transitions": [],
            "bgm_suggestion": "",
            "subtitle_style": "",
            "opening_hook": "",
        }
