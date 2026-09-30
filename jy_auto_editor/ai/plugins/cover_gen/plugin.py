"""封面生成插件 — 从视频提取关键帧并用 LLM 选择最佳封面"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ....core.plugin import AIPlugin, PluginContext, register_plugin
from ...providers.base_provider import Message

logger = logging.getLogger(__name__)


@register_plugin
class CoverGenPlugin(AIPlugin):
    """封面生成插件 — 智能选取/生成视频封面"""

    plugin_id = "cover_gen"
    plugin_name = "智能封面生成"
    version = "0.1.0"
    description = "从视频中提取关键帧，结合 LLM 分析选择最佳封面"
    required_providers = ["llm"]

    input_schema = {
        "type": "object",
        "properties": {
            "video_path": {"type": "string", "description": "视频文件路径"},
            "transcript": {"type": "string", "description": "视频转录文本（可选）"},
            "num_candidates": {"type": "integer", "default": 5, "description": "候选封面数量"},
            "interval_seconds": {"type": "number", "default": 2.0, "description": "关键帧采样间隔(秒)"},
            "style": {
                "type": "string",
                "default": "auto",
                "enum": ["auto", "eye_catching", "clean", "dramatic", "informative"],
                "description": "封面风格",
            },
            "add_title": {"type": "boolean", "default": False, "description": "是否在封面上添加标题文字"},
            "title_text": {"type": "string", "description": "封面标题文字"},
        },
        "required": ["video_path"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "cover_path": {"type": "string", "description": "最终封面图片路径"},
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "frame_path": {"type": "string"},
                        "timestamp_us": {"type": "integer"},
                        "score": {"type": "number"},
                        "reason": {"type": "string"},
                    },
                },
            },
            "title_overlay": {"type": "object", "description": "标题叠加信息"},
        },
    }

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        video_path = input_data["video_path"]
        transcript = input_data.get("transcript", "")
        num_candidates = input_data.get("num_candidates", 5)
        interval = input_data.get("interval_seconds", 2.0)
        style = input_data.get("style", "auto")
        add_title = input_data.get("add_title", False)
        title_text = input_data.get("title_text", "")

        # 1. 提取关键帧
        keyframes = await self._extract_keyframes(video_path, interval, context)

        if not keyframes:
            return {
                "cover_path": "",
                "candidates": [],
                "error": "No keyframes could be extracted",
            }

        # 2. 用 LLM 分析选择最佳封面
        candidates = await self._select_best_covers(
            keyframes, transcript, num_candidates, style, context
        )

        # 3. 选择得分最高的作为最终封面
        best_cover = ""
        if candidates:
            best_cover = candidates[0].get("frame_path", "")

        # 4. 可选：添加标题叠加
        title_overlay = {}
        if add_title and title_text and best_cover:
            title_overlay = await self._add_title_overlay(
                best_cover, title_text, style, context
            )
            if title_overlay.get("output_path"):
                best_cover = title_overlay["output_path"]

        return {
            "cover_path": best_cover,
            "candidates": candidates,
            "candidate_count": len(candidates),
            "title_overlay": title_overlay,
        }

    async def _extract_keyframes(
        self, video_path: str, interval: float, context: PluginContext
    ) -> list[dict]:
        """提取关键帧"""
        keyframes = []

        # 优先使用 CV Provider
        try:
            cv_provider = context.get_provider("cv")
            if cv_provider is None:
                raise RuntimeError("CV provider not registered")
            frame_paths = await cv_provider.extract_keyframes(video_path, interval)
            for i, fp in enumerate(frame_paths):
                keyframes.append({
                    "frame_path": fp,
                    "timestamp_us": int(i * interval * 1_000_000),
                    "index": i,
                })
            return keyframes
        except (RuntimeError, KeyError):
            logger.info("CV provider not available, using FFmpeg fallback")

        # 回退：使用 FFmpeg 按间隔截帧
        try:
            ffmpeg = context._ffmpeg
            if ffmpeg is None:
                from ....infra.ffmpeg import FFmpegWrapper
                ffmpeg = FFmpegWrapper()

            temp_dir = context.get_temp_path("keyframes")
            temp_dir.mkdir(parents=True, exist_ok=True)

            duration = await ffmpeg.get_duration(Path(video_path))
            t = 0.0
            idx = 0
            while t < duration:
                output = temp_dir / f"frame_{idx:04d}.jpg"
                # 使用 ffmpeg 截取单帧
                import asyncio
                cmd = [
                    ffmpeg.ffmpeg,
                    "-ss", str(t),
                    "-i", video_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y",
                    str(output),
                ]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()

                if output.exists() and output.stat().st_size > 0:
                    keyframes.append({
                        "frame_path": str(output),
                        "timestamp_us": int(t * 1_000_000),
                        "index": idx,
                    })
                    idx += 1
                t += interval
        except Exception as e:
            logger.error(f"Keyframe extraction failed: {e}")

        return keyframes

    async def _select_best_covers(
        self,
        keyframes: list[dict],
        transcript: str,
        num_candidates: int,
        style: str,
        context: PluginContext,
    ) -> list[dict]:
        """使用 LLM 从关键帧中选择最佳封面候选"""
        if not keyframes:
            return []

        # 构建帧信息列表
        frame_info = "\n".join(
            f"帧 {kf['index']}: 时间戳 {kf['timestamp_us'] / 1_000_000:.1f}s, 路径 {kf['frame_path']}"
            for kf in keyframes
        )

        style_hints = {
            "auto": "选择视觉吸引力最强、内容最具代表性的帧",
            "eye_catching": "选择色彩鲜明、视觉冲击力强的帧",
            "clean": "选择画面简洁、构图清晰的帧",
            "dramatic": "选择情绪张力强、有戏剧性的帧",
            "informative": "选择最能传达视频主题和内容的帧",
        }
        hint = style_hints.get(style, style_hints["auto"])

        prompt = f"""你是一个视频封面选择专家。请从以下关键帧中选出最适合作为视频封面的 {num_candidates} 个候选。

视频转录文本：
{transcript if transcript else "（无转录文本）"}

关键帧列表：
{frame_info}

选择标准：{hint}

请以 JSON 数组格式返回，每个候选包含：
- frame_index: 帧索引
- score: 评分 (1-10)
- reason: 选择理由
"""

        llm = context.get_provider("llm")
        response = await llm.chat(
            messages=[
                Message(role="system", content="你是专业的视频封面选择专家。"),
                Message(role="user", content=prompt),
            ],
            temperature=0.3,
        )

        # 解析 LLM 返回
        try:
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            selections = json.loads(content)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse LLM cover selection, using first frames")
            selections = [
                {"frame_index": kf["index"], "score": 5.0, "reason": "默认选择"}
                for kf in keyframes[:num_candidates]
            ]

        # 组装候选列表
        candidates = []
        kf_map = {kf["index"]: kf for kf in keyframes}
        for sel in selections[:num_candidates]:
            idx = sel.get("frame_index", 0)
            kf = kf_map.get(idx)
            if kf:
                candidates.append({
                    "frame_path": kf["frame_path"],
                    "timestamp_us": kf["timestamp_us"],
                    "score": sel.get("score", 5.0),
                    "reason": sel.get("reason", ""),
                })

        # 按分数降序排列
        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates

    async def _add_title_overlay(
        self,
        cover_path: str,
        title_text: str,
        style: str,
        context: PluginContext,
    ) -> dict:
        """在封面上叠加标题文字（使用 FFmpeg drawtext）"""
        import asyncio

        output_path = str(context.get_temp_path("cover_with_title.jpg"))

        # 根据风格设置字体参数
        font_size = 48 if style != "clean" else 36
        font_color = "white"
        border_color = "black"

        cmd = [
            "ffmpeg",
            "-i", cover_path,
            "-vf", (
                f"drawtext=text='{title_text}'"
                f":fontsize={font_size}"
                f":fontcolor={font_color}"
                f":borderw=2"
                f":bordercolor={border_color}"
                f":x=(w-text_w)/2"
                f":y=(h-text_h)/2"
            ),
            "-y",
            output_path,
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if Path(output_path).exists():
                return {
                    "output_path": output_path,
                    "title": title_text,
                    "font_size": font_size,
                }
        except Exception as e:
            logger.error(f"Title overlay failed: {e}")

        return {}
