"""AnalyzeStage 单元测试"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jy_auto_editor.core.events import reset_event_bus
from jy_auto_editor.core.models import (
    AnalysisResult,
    PipelineContext,
    ProjectInput,
    SubtitleBlock,
    TimeRange,
    VideoAsset,
    MediaInfo,
)
from jy_auto_editor.core.plugin import AIPlugin, PluginContext
from jy_auto_editor.stages.analyze import AnalyzeStage


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class MockASRPlugin(AIPlugin):
    plugin_id = "asr"
    plugin_name = "Mock ASR"

    def __init__(self, transcript="测试文字", subtitles=None, language="zh"):
        self._transcript = transcript
        self._subtitles = subtitles or [
            {"text": "测试", "start_us": 0, "end_us": 2_000_000},
            {"text": "文字", "start_us": 2_000_000, "end_us": 4_000_000},
        ]
        self._language = language

    async def process(self, input_data, context):
        return {
            "transcript": self._transcript,
            "subtitles": self._subtitles,
            "language": self._language,
        }


class MockSceneDetectPlugin(AIPlugin):
    plugin_id = "scene_detect"
    plugin_name = "Mock Scene Detect"

    def __init__(self, scenes=None):
        self._scenes = scenes or [
            {"start_us": 0, "end_us": 5_000_000},
            {"start_us": 5_000_000, "end_us": 10_000_000},
        ]

    async def process(self, input_data, context):
        return {"scenes": self._scenes}


class MockHighlightPlugin(AIPlugin):
    plugin_id = "highlight"
    plugin_name = "Mock Highlight"

    def __init__(self, highlights=None):
        self._highlights = highlights or [
            {"start_second": 1.0, "end_second": 5.0, "score": 0.9, "title": "精彩片段"},
        ]

    async def process(self, input_data, context):
        return {"highlights": self._highlights}


def _make_context_with_video():
    """创建带视频素材的 PipelineContext"""
    ctx = PipelineContext(input=ProjectInput())
    ctx.project.source_videos.append(VideoAsset(
        path="/fake/video.mp4",
        media_info=MediaInfo(path="/fake/video.mp4", duration_us=10_000_000),
    ))
    return ctx


def _make_registry(plugins=None):
    """创建 mock 插件注册表"""
    registry = MagicMock()
    registry.has_plugin = MagicMock(side_effect=lambda pid: pid in (plugins or {}))
    registry.get_plugin = MagicMock(side_effect=lambda pid: (plugins or {}).get(pid))
    return registry


class TestAnalyzeStageMetadata:
    def test_name(self):
        stage = AnalyzeStage()
        assert stage.name == "analyze"

    def test_dependencies(self):
        stage = AnalyzeStage()
        assert stage.dependencies == ["ingest"]

    def test_default_flags(self):
        stage = AnalyzeStage()
        assert stage.asr_enabled is True
        assert stage.scene_enabled is True
        assert stage.highlight_enabled is True

    def test_custom_flags(self):
        stage = AnalyzeStage(asr_enabled=False, scene_enabled=False, highlight_enabled=False)
        assert stage.asr_enabled is False
        assert stage.scene_enabled is False
        assert stage.highlight_enabled is False


class TestAnalyzeValidate:
    def setup_method(self):
        reset_event_bus()

    def test_no_videos_returns_false(self):
        stage = AnalyzeStage()
        ctx = PipelineContext()
        assert _run(stage.validate(ctx)) is False

    def test_with_videos_returns_true(self):
        stage = AnalyzeStage()
        ctx = _make_context_with_video()
        assert _run(stage.validate(ctx)) is True


class TestAnalyzeExecute:
    def setup_method(self):
        reset_event_bus()

    @patch("jy_auto_editor.stages.analyze.get_global_registry")
    def test_full_pipeline(self, mock_get_registry):
        asr = MockASRPlugin()
        sd = MockSceneDetectPlugin()
        hl = MockHighlightPlugin()
        registry = _make_registry({"asr": asr, "scene_detect": sd, "highlight": hl})
        mock_get_registry.return_value = registry

        stage = AnalyzeStage()
        ctx = _make_context_with_video()

        result = _run(stage.execute(ctx))

        assert result["transcript_length"] > 0
        assert result["subtitle_count"] == 2
        assert result["scene_count"] == 2
        assert result["highlight_count"] == 1
        assert result["language"] == "zh"
        assert ctx.analysis is not None

    @patch("jy_auto_editor.stages.analyze.get_global_registry")
    def test_asr_disabled(self, mock_get_registry):
        sd = MockSceneDetectPlugin()
        registry = _make_registry({"scene_detect": sd})
        mock_get_registry.return_value = registry

        stage = AnalyzeStage(asr_enabled=False)
        ctx = _make_context_with_video()

        result = _run(stage.execute(ctx))

        assert result["subtitle_count"] == 0
        assert result["transcript_length"] == 0

    @patch("jy_auto_editor.stages.analyze.get_global_registry")
    def test_scene_disabled(self, mock_get_registry):
        asr = MockASRPlugin()
        registry = _make_registry({"asr": asr})
        mock_get_registry.return_value = registry

        stage = AnalyzeStage(scene_enabled=False)
        ctx = _make_context_with_video()

        result = _run(stage.execute(ctx))

        assert result["scene_count"] == 0

    @patch("jy_auto_editor.stages.analyze.get_global_registry")
    def test_highlight_requires_transcript(self, mock_get_registry):
        """高光提取需要 ASR 转录结果"""
        asr = MockASRPlugin(transcript="")  # 空转录
        hl = MockHighlightPlugin()
        registry = _make_registry({"asr": asr, "highlight": hl})
        mock_get_registry.return_value = registry

        stage = AnalyzeStage(scene_enabled=False)
        ctx = _make_context_with_video()

        result = _run(stage.execute(ctx))

        # 没有转录，高光应被跳过
        assert result["highlight_count"] == 0

    @patch("jy_auto_editor.stages.analyze.get_global_registry")
    def test_no_plugins_available(self, mock_get_registry):
        registry = _make_registry({})
        mock_get_registry.return_value = registry

        stage = AnalyzeStage()
        ctx = _make_context_with_video()

        result = _run(stage.execute(ctx))

        assert result["transcript_length"] == 0
        assert result["subtitle_count"] == 0
        assert result["scene_count"] == 0
        assert result["highlight_count"] == 0

    @patch("jy_auto_editor.stages.analyze.get_global_registry")
    def test_asr_failure_doesnt_crash(self, mock_get_registry):
        """ASR 失败时不应中断整个分析"""
        failing_asr = MockASRPlugin()
        failing_asr.process = AsyncMock(side_effect=RuntimeError("ASR crash"))
        registry = _make_registry({"asr": failing_asr})
        mock_get_registry.return_value = registry

        stage = AnalyzeStage(scene_enabled=False, highlight_enabled=False)
        ctx = _make_context_with_video()

        # 不应抛出异常（并行任务中的异常被捕获）
        result = _run(stage.execute(ctx))
        assert result["transcript_length"] == 0


class TestNormalizeSubtitles:
    def setup_method(self):
        reset_event_bus()

    def test_normalize_dicts(self):
        stage = AnalyzeStage()
        raw = [
            {"text": "你好", "start_us": 0, "end_us": 2_000_000},
            {"text": "世界", "start_us": 2_000_000, "end_us": 4_000_000},
        ]
        result = stage._normalize_subtitles(raw)
        assert len(result) == 2
        assert isinstance(result[0], SubtitleBlock)
        assert result[0].text == "你好"
        assert result[0].time_range.start_us == 0
        assert result[0].time_range.duration_us == 2_000_000

    def test_normalize_existing_blocks(self):
        stage = AnalyzeStage()
        block = SubtitleBlock(text="已有", time_range=TimeRange(start_us=0, duration_us=1_000_000))
        result = stage._normalize_subtitles([block])
        assert len(result) == 1
        assert result[0] is block

    def test_normalize_empty_list(self):
        stage = AnalyzeStage()
        result = stage._normalize_subtitles([])
        assert result == []

    def test_normalize_mixed_types(self):
        stage = AnalyzeStage()
        block = SubtitleBlock(text="block", time_range=TimeRange(start_us=0, duration_us=1_000_000))
        raw = [
            block,
            {"text": "dict", "start_us": 1_000_000, "end_us": 3_000_000},
        ]
        result = stage._normalize_subtitles(raw)
        assert len(result) == 2
        assert isinstance(result[0], SubtitleBlock)
        assert isinstance(result[1], SubtitleBlock)


class TestAnalyzeRollback:
    def setup_method(self):
        reset_event_bus()

    def test_rollback_clears_analysis(self):
        stage = AnalyzeStage()
        ctx = PipelineContext()
        ctx.analysis = AnalysisResult(transcript="test")

        _run(stage.rollback(ctx))
        assert ctx.analysis is None
