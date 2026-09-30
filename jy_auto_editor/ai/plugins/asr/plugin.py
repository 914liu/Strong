"""ASR 语音识别插件 — 支持 Whisper (本地) / OpenAI API / 阿里云"""

from __future__ import annotations

import logging
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin

logger = logging.getLogger(__name__)


@register_plugin
class ASRPlugin(AIPlugin):
    """语音识别插件"""

    plugin_id = "asr"
    plugin_name = "语音识别与字幕生成"
    version = "0.1.0"
    description = "将视频/音频中的语音转为带时间戳的文本"
    required_providers = ["asr"]

    input_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": "string", "description": "视频/音频文件路径"},
            "language": {"type": "string", "default": "zh", "description": "语言代码"},
        },
        "required": ["video_path"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "transcript": {"type": "string"},
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
            "language": {"type": "string"},
        },
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        from pathlib import Path

        video_path = input_data["video_path"]
        language = input_data.get("language", "zh")

        # 1. 提取音频（使用 FFmpeg）
        audio_path = context.get_temp_path("extracted_audio.wav")
        logger.info(f"Extracting audio from {video_path} -> {audio_path}")

        ffmpeg = context._ffmpeg
        if ffmpeg is None:
            from ....infra.ffmpeg import FFmpegWrapper
            ffmpeg = FFmpegWrapper()

        await ffmpeg.extract_audio(Path(video_path), audio_path)

        # 2. 调用 ASR Provider
        asr_provider = context.get_provider("asr")
        transcript = await asr_provider.transcribe_with_timestamps(str(audio_path), language)

        # 3. 返回结构化结果
        return {
            "transcript": transcript.text,
            "subtitles": transcript.to_subtitle_blocks(),
            "language": transcript.language or language,
        }
