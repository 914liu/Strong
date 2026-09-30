"""AI Plugin 单元测试"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jy_auto_editor.ai.providers.base_provider import (
    LLMResponse,
    Message,
    Transcript,
    TranscriptSegment,
)
from jy_auto_editor.core.plugin import PluginContext


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────


def _make_plugin_context(
    provider_registry=None,
    plugin_registry=None,
    temp_dir="/tmp/test_ai_plugins",
):
    """构建测试用 PluginContext"""
    return PluginContext(
        config={},
        provider_registry=provider_registry,
        plugin_registry=plugin_registry,
        ffmpeg=None,
        temp_dir=temp_dir,
        cache_dir="/tmp/test_ai_plugins_cache",
    )


def _make_mock_provider_registry(providers: dict):
    """构建模拟 ProviderRegistry"""
    registry = MagicMock()
    registry.get_provider = MagicMock(side_effect=lambda t: providers.get(t))
    return registry


def _make_mock_plugin_registry(plugins: dict):
    """构建模拟 PluginRegistry"""
    registry = MagicMock()
    registry.get_plugin = MagicMock(side_effect=lambda pid: plugins.get(pid))
    return registry


# ──────────────────────────────────────────────
# ASR Plugin tests
# ──────────────────────────────────────────────


class TestASRPlugin:
    def test_plugin_metadata(self):
        from jy_auto_editor.ai.plugins.asr.plugin import ASRPlugin
        p = ASRPlugin()
        assert p.plugin_id == "asr"
        assert p.plugin_name == "语音识别与字幕生成"
        assert p.version == "0.1.0"
        assert "asr" in p.required_providers

    def test_input_schema(self):
        from jy_auto_editor.ai.plugins.asr.plugin import ASRPlugin
        p = ASRPlugin()
        assert "video_path" in p.input_schema["properties"]
        assert "video_path" in p.input_schema["required"]

    def test_output_schema(self):
        from jy_auto_editor.ai.plugins.asr.plugin import ASRPlugin
        p = ASRPlugin()
        assert "transcript" in p.output_schema["properties"]
        assert "subtitles" in p.output_schema["properties"]

    def test_process_success(self):
        from jy_auto_editor.ai.plugins.asr.plugin import ASRPlugin

        transcript = Transcript(
            text="测试文字内容",
            language="zh",
            segments=[
                TranscriptSegment(text="测试", start_us=0, end_us=1_000_000),
                TranscriptSegment(text="文字内容", start_us=1_000_000, end_us=3_000_000),
            ],
        )

        mock_asr = MagicMock()
        mock_asr.transcribe_with_timestamps = AsyncMock(return_value=transcript)

        registry = _make_mock_provider_registry({"asr": mock_asr})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = ASRPlugin()
        result = _run(plugin.process({"video_path": "/tmp/test.mp4", "language": "zh"}, ctx))

        assert result["transcript"] == "测试文字内容"
        assert result["language"] == "zh"
        assert len(result["subtitles"]) == 2
        assert result["subtitles"][0]["text"] == "测试"
        assert result["subtitles"][0]["start_us"] == 0
        assert result["subtitles"][0]["end_us"] == 1_000_000

    def test_process_default_language(self):
        from jy_auto_editor.ai.plugins.asr.plugin import ASRPlugin

        transcript = Transcript(text="hi", language="en")
        mock_asr = MagicMock()
        mock_asr.transcribe_with_timestamps = AsyncMock(return_value=transcript)

        registry = _make_mock_provider_registry({"asr": mock_asr})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = ASRPlugin()
        result = _run(plugin.process({"video_path": "/tmp/test.mp4"}, ctx))
        assert result["language"] == "en"

    def test_process_no_provider_raises(self):
        from jy_auto_editor.ai.plugins.asr.plugin import ASRPlugin

        registry = _make_mock_provider_registry({})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = ASRPlugin()
        with pytest.raises(Exception):
            _run(plugin.process({"video_path": "/tmp/test.mp4"}, ctx))


# ──────────────────────────────────────────────
# Scene Detect Plugin tests
# ──────────────────────────────────────────────


class TestSceneDetectPlugin:
    def test_plugin_metadata(self):
        from jy_auto_editor.ai.plugins.scene_detect.plugin import SceneDetectPlugin
        p = SceneDetectPlugin()
        assert p.plugin_id == "scene_detect"
        assert p.plugin_name == "场景检测"
        assert "cv" in p.required_providers

    def test_process_with_pyscenedetect(self):
        from jy_auto_editor.ai.plugins.scene_detect.plugin import SceneDetectPlugin

        mock_scene0 = MagicMock()
        mock_scene0.get_seconds.return_value = 0.0
        mock_scene1 = MagicMock()
        mock_scene1.get_seconds.return_value = 5.5

        mock_scenedetect = MagicMock()
        mock_scenedetect.detect = MagicMock(return_value=[(mock_scene0, mock_scene1)])
        mock_scenedetect.ContentDetector = MagicMock()

        plugin = SceneDetectPlugin()
        with patch.dict("sys.modules", {"scenedetect": mock_scenedetect}):
            result = _run(plugin.process({"video_path": "/tmp/test.mp4"}, _make_plugin_context()))

        assert result["scene_count"] == 1
        assert result["scenes"][0]["start_us"] == 0
        assert result["scenes"][0]["end_us"] == 5_500_000

    def test_process_pyscenedetect_import_error_fallback(self):
        from jy_auto_editor.ai.plugins.scene_detect.plugin import SceneDetectPlugin
        from jy_auto_editor.ai.providers.base_provider import SceneBoundary

        mock_cv = MagicMock()
        mock_cv.detect_scenes = AsyncMock(return_value=[
            SceneBoundary(frame_number=150, time_us=5_000_000, confidence=0.9),
            SceneBoundary(frame_number=300, time_us=10_000_000, confidence=0.85),
        ])

        registry = _make_mock_provider_registry({"cv": mock_cv})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = SceneDetectPlugin()
        with patch.dict("sys.modules", {"scenedetect": None}):
            result = _run(plugin.process({"video_path": "/tmp/test.mp4", "threshold": 30.0}, ctx))

        assert result["scene_count"] == 2
        assert result["scenes"][0]["end_us"] == 5_000_000
        assert result["scenes"][0]["frame_number"] == 150

    def test_process_custom_threshold(self):
        from jy_auto_editor.ai.plugins.scene_detect.plugin import SceneDetectPlugin

        mock_scenedetect = MagicMock()
        mock_scenedetect.detect = MagicMock(return_value=[])

        plugin = SceneDetectPlugin()
        with patch.dict("sys.modules", {"scenedetect": mock_scenedetect}):
            _run(plugin.process({"video_path": "/tmp/test.mp4", "threshold": 50.0}, _make_plugin_context()))
            mock_scenedetect.ContentDetector.assert_called_once_with(threshold=50.0)


# ──────────────────────────────────────────────
# Highlight Plugin tests
# ──────────────────────────────────────────────


class TestHighlightPlugin:
    def test_plugin_metadata(self):
        from jy_auto_editor.ai.plugins.highlight.plugin import HighlightPlugin
        p = HighlightPlugin()
        assert p.plugin_id == "highlight"
        assert p.plugin_name == "高光时刻提取"
        assert "llm" in p.required_providers

    def test_process_success(self):
        from jy_auto_editor.ai.plugins.highlight.plugin import HighlightPlugin

        highlights = [
            {"start_second": 10, "end_second": 40, "title": "精彩片段", "reason": "情绪高潮", "score": 9},
        ]
        llm_response = LLMResponse(content=json.dumps(highlights))

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = HighlightPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "这是一段测试文字",
            "scenes": [{"start_us": 0, "end_us": 60_000_000}],
            "max_clips": 3,
            "platform": "douyin",
        }, ctx))

        assert result["clip_count"] == 1
        assert result["highlights"][0]["title"] == "精彩片段"
        assert result["highlights"][0]["score"] == 9

    def test_process_json_in_code_block(self):
        from jy_auto_editor.ai.plugins.highlight.plugin import HighlightPlugin

        highlights = [{"start_second": 5, "end_second": 20, "title": "test", "reason": "good", "score": 8}]
        content = f"一些说明文字\n```json\n{json.dumps(highlights)}\n```"
        llm_response = LLMResponse(content=content)

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = HighlightPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "test",
        }, ctx))

        assert result["clip_count"] == 1

    def test_process_json_parse_failure(self):
        from jy_auto_editor.ai.plugins.highlight.plugin import HighlightPlugin

        llm_response = LLMResponse(content="not valid json at all {{{")

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = HighlightPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "test",
        }, ctx))

        assert result["highlights"] == []
        assert result["clip_count"] == 0

    def test_process_default_params(self):
        from jy_auto_editor.ai.plugins.highlight.plugin import HighlightPlugin

        llm_response = LLMResponse(content="[]")
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = HighlightPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "test",
        }, ctx))

        # Verify LLM was called with default platform and max_clips
        call_args = mock_llm.chat.call_args
        prompt = call_args.kwargs["messages"][1].content
        assert "douyin" in prompt
        assert "3" in prompt

    def test_process_custom_platform(self):
        from jy_auto_editor.ai.plugins.highlight.plugin import HighlightPlugin

        llm_response = LLMResponse(content="[]")
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = HighlightPlugin()
        _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "test",
            "platform": "bilibili",
            "max_clips": 5,
        }, ctx))

        call_args = mock_llm.chat.call_args
        prompt = call_args.kwargs["messages"][1].content
        assert "bilibili" in prompt
        assert "5" in prompt


# ──────────────────────────────────────────────
# Subtitle Plugin tests
# ──────────────────────────────────────────────


class TestSubtitlePlugin:
    def test_plugin_metadata(self):
        from jy_auto_editor.ai.plugins.subtitle.plugin import SubtitlePlugin
        p = SubtitlePlugin()
        assert p.plugin_id == "subtitle"
        assert p.plugin_name == "智能字幕生成"

    def test_process_success(self):
        from jy_auto_editor.ai.plugins.subtitle.plugin import SubtitlePlugin

        plugin = SubtitlePlugin()
        result = _run(plugin.process({
            "subtitles": [
                {"text": "hello", "start_us": 0, "end_us": 1_000_000},
                {"text": "world", "start_us": 1_000_000, "end_us": 2_000_000},
            ],
        }, _make_plugin_context()))

        assert result["count"] == 2
        assert result["formatted_subtitles"][0]["text"] == "hello"
        assert result["formatted_subtitles"][0]["start_us"] == 0
        assert result["formatted_subtitles"][0]["duration_us"] == 1_000_000
        assert result["formatted_subtitles"][0]["font_color"] == "#FFFFFF"
        assert result["formatted_subtitles"][0]["alignment"] == "center"

    def test_process_custom_style(self):
        from jy_auto_editor.ai.plugins.subtitle.plugin import SubtitlePlugin

        plugin = SubtitlePlugin()
        result = _run(plugin.process({
            "subtitles": [{"text": "hi", "start_us": 0, "end_us": 500_000}],
            "font_name": "Arial",
            "font_size": 12.0,
            "font_color": "#FF0000",
            "position_y": 0.9,
        }, _make_plugin_context()))

        sub = result["formatted_subtitles"][0]
        assert sub["font_name"] == "Arial"
        assert sub["font_size"] == 12.0
        assert sub["font_color"] == "#FF0000"
        assert sub["position_y"] == 0.9

    def test_process_empty_subtitles(self):
        from jy_auto_editor.ai.plugins.subtitle.plugin import SubtitlePlugin

        plugin = SubtitlePlugin()
        result = _run(plugin.process({"subtitles": []}, _make_plugin_context()))
        assert result["count"] == 0
        assert result["formatted_subtitles"] == []

    def test_process_missing_fields_defaults(self):
        from jy_auto_editor.ai.plugins.subtitle.plugin import SubtitlePlugin

        plugin = SubtitlePlugin()
        result = _run(plugin.process({
            "subtitles": [{"text": "hi"}],
        }, _make_plugin_context()))

        sub = result["formatted_subtitles"][0]
        assert sub["start_us"] == 0
        assert sub["duration_us"] == 0


# ─────────────────────────────────────────────
# BGM Plugin tests
# ──────────────────────────────────────────────


class TestBGMPlugin:
    def test_plugin_metadata(self):
        from jy_auto_editor.ai.plugins.bgm.plugin import BGMPlugin
        p = BGMPlugin()
        assert p.plugin_id == "bgm"
        assert p.plugin_name == "智能配乐推荐"
        assert "llm" in p.required_providers

    def test_process_success(self):
        from jy_auto_editor.ai.plugins.bgm.plugin import BGMPlugin

        recommendations = [
            {"name": "Song A", "style": "pop", "bpm": 120, "mood": "happy", "reason": "fits well"},
        ]
        llm_response = LLMResponse(content=json.dumps(recommendations))

        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = BGMPlugin()
        result = _run(plugin.process({
            "video_content": "这是一个快乐的视频",
            "duration_seconds": 30,
        }, ctx))

        assert len(result["recommendations"]) == 1
        assert result["recommendations"][0]["name"] == "Song A"

    def test_process_with_mood_and_genre(self):
        from jy_auto_editor.ai.plugins.bgm.plugin import BGMPlugin

        llm_response = LLMResponse(content="[]")
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = BGMPlugin()
        _run(plugin.process({
            "video_content": "test",
            "mood": "sad",
            "genre": "classical",
        }, ctx))

        call_args = mock_llm.chat.call_args
        prompt = call_args.kwargs["messages"][0].content
        assert "sad" in prompt
        assert "classical" in prompt

    def test_process_json_parse_failure(self):
        from jy_auto_editor.ai.plugins.bgm.plugin import BGMPlugin

        llm_response = LLMResponse(content="not json")
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = BGMPlugin()
        result = _run(plugin.process({"video_content": "test"}, ctx))
        assert result["recommendations"] == []

    def test_process_non_list_response(self):
        from jy_auto_editor.ai.plugins.bgm.plugin import BGMPlugin

        llm_response = LLMResponse(content=json.dumps({"not": "a list"}))
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = BGMPlugin()
        result = _run(plugin.process({"video_content": "test"}, ctx))
        assert result["recommendations"] == []

    def test_process_default_duration(self):
        from jy_auto_editor.ai.plugins.bgm.plugin import BGMPlugin

        llm_response = LLMResponse(content="[]")
        mock_llm = MagicMock()
        mock_llm.chat = AsyncMock(return_value=llm_response)

        registry = _make_mock_provider_registry({"llm": mock_llm})
        ctx = _make_plugin_context(provider_registry=registry)

        plugin = BGMPlugin()
        _run(plugin.process({"video_content": "test"}, ctx))

        call_args = mock_llm.chat.call_args
        prompt = call_args.kwargs["messages"][0].content
        assert "60" in prompt  # default duration


# ──────────────────────────────────────────────
# Long to Short Plugin tests
# ──────────────────────────────────────────────


class TestLongToShortPlugin:
    def test_plugin_metadata(self):
        from jy_auto_editor.ai.plugins.long_to_short.plugin import LongToShortPlugin
        p = LongToShortPlugin()
        assert p.plugin_id == "long_to_short"
        assert p.plugin_name == "智能长转短"
        assert "llm" in p.required_providers

    def test_process_success(self):
        from jy_auto_editor.ai.plugins.long_to_short.plugin import LongToShortPlugin

        highlights = [
            {"start_second": 10, "end_second": 40, "title": "片段1", "score": 9},
            {"start_second": 60, "end_second": 90, "title": "片段2", "score": 7},
        ]

        mock_highlight = MagicMock()
        mock_highlight.process = AsyncMock(return_value={
            "highlights": highlights,
            "clip_count": 2,
        })

        mock_bgm = MagicMock()
        mock_bgm.process = AsyncMock(return_value={
            "recommendations": [{"name": "BGM1", "style": "pop"}],
        })

        plugin_registry = _make_mock_plugin_registry({
            "highlight": mock_highlight,
            "bgm": mock_bgm,
        })
        ctx = _make_plugin_context(plugin_registry=plugin_registry)

        plugin = LongToShortPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "这是一段很长的视频内容" * 10,
            "scenes": [],
            "target_platform": "douyin",
            "max_clips": 5,
        }, ctx))

        assert result["clip_count"] == 2
        assert len(result["short_videos"]) == 2
        assert result["short_videos"][0]["title"] == "片段1"
        assert result["short_videos"][0]["start_second"] == 10
        assert result["short_videos"][0]["end_second"] == 40
        assert result["short_videos"][0]["aspect_ratio"] == "9:16"
        assert result["short_videos"][0]["bgm"]["name"] == "BGM1"
        assert result["source_video"] == "/tmp/test.mp4"

    def test_process_no_highlights(self):
        from jy_auto_editor.ai.plugins.long_to_short.plugin import LongToShortPlugin

        mock_highlight = MagicMock()
        mock_highlight.process = AsyncMock(return_value={"highlights": [], "clip_count": 0})

        mock_bgm = MagicMock()
        mock_bgm.process = AsyncMock(return_value={"recommendations": []})

        plugin_registry = _make_mock_plugin_registry({
            "highlight": mock_highlight,
            "bgm": mock_bgm,
        })
        ctx = _make_plugin_context(plugin_registry=plugin_registry)

        plugin = LongToShortPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "test",
        }, ctx))

        assert result["clip_count"] == 0
        assert result["short_videos"] == []

    def test_process_no_bgm_recommendations(self):
        from jy_auto_editor.ai.plugins.long_to_short.plugin import LongToShortPlugin

        highlights = [{"start_second": 0, "end_second": 30, "title": "片段1", "score": 8}]

        mock_highlight = MagicMock()
        mock_highlight.process = AsyncMock(return_value={"highlights": highlights})

        mock_bgm = MagicMock()
        mock_bgm.process = AsyncMock(return_value={"recommendations": []})

        plugin_registry = _make_mock_plugin_registry({
            "highlight": mock_highlight,
            "bgm": mock_bgm,
        })
        ctx = _make_plugin_context(plugin_registry=plugin_registry)

        plugin = LongToShortPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "test",
        }, ctx))

        assert result["short_videos"][0]["bgm"] == {}

    def test_process_custom_aspect_ratio(self):
        from jy_auto_editor.ai.plugins.long_to_short.plugin import LongToShortPlugin

        mock_highlight = MagicMock()
        mock_highlight.process = AsyncMock(return_value={"highlights": [{"start_second": 0, "end_second": 30, "title": "t", "score": 5}]})

        mock_bgm = MagicMock()
        mock_bgm.process = AsyncMock(return_value={"recommendations": [{"name": "bgm"}]})

        plugin_registry = _make_mock_plugin_registry({
            "highlight": mock_highlight,
            "bgm": mock_bgm,
        })
        ctx = _make_plugin_context(plugin_registry=plugin_registry)

        plugin = LongToShortPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "test",
            "aspect_ratio": "16:9",
        }, ctx))

        assert result["short_videos"][0]["aspect_ratio"] == "16:9"

    def test_process_default_platform(self):
        from jy_auto_editor.ai.plugins.long_to_short.plugin import LongToShortPlugin

        mock_highlight = MagicMock()
        mock_highlight.process = AsyncMock(return_value={"highlights": []})

        mock_bgm = MagicMock()
        mock_bgm.process = AsyncMock(return_value={"recommendations": []})

        plugin_registry = _make_mock_plugin_registry({
            "highlight": mock_highlight,
            "bgm": mock_bgm,
        })
        ctx = _make_plugin_context(plugin_registry=plugin_registry)

        plugin = LongToShortPlugin()
        result = _run(plugin.process({
            "video_path": "/tmp/test.mp4",
            "transcript": "test",
        }, ctx))

        # Verify highlight plugin was called with default platform
        call_args = mock_highlight.process.call_args
        assert call_args.args[0]["platform"] == "douyin"


# ──────────────────────────────────────────────
# PluginContext tests
# ──────────────────────────────────────────────


class TestPluginContext:
    def test_get_temp_path(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            ctx = PluginContext(config={}, temp_dir=tmpdir)
            path = ctx.get_temp_path("test.wav")
            assert path.name == "test.wav"
            assert str(path).startswith(tmpdir)

    def test_cache_operations(self):
        ctx = PluginContext(config={})
        ctx.set_cache("key1", "value1")
        assert ctx.get_cache("key1") == "value1"
        assert ctx.get_cache("nonexistent") is None

    def test_get_provider_no_registry(self):
        ctx = PluginContext(config={})
        with pytest.raises(RuntimeError, match="Provider registry not available"):
            ctx.get_provider("llm")

    def test_get_plugin_no_registry(self):
        ctx = PluginContext(config={})
        with pytest.raises(RuntimeError, match="Plugin registry not available"):
            ctx.get_plugin("asr")

    def test_properties(self):
        ctx = PluginContext(config={"key": "val"}, temp_dir="/tmp/t", cache_dir="/tmp/c")
        assert ctx.config == {"key": "val"}
        assert ctx.temp_dir == "/tmp/t"
        assert ctx.cache_dir == "/tmp/c"
