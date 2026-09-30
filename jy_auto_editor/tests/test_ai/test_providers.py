"""AI Provider 单元测试"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from jy_auto_editor.ai.providers.base_provider import (
    ASRProvider,
    CVProvider,
    LLMProvider,
    LLMResponse,
    Message,
    ProviderRouter,
    SceneBoundary,
    Transcript,
    TranscriptSegment,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ──────────────────────────────────────────────
# Dataclass tests
# ──────────────────────────────────────────────


class TestMessage:
    def test_create_message(self):
        msg = Message(role="user", content="hello")
        assert msg.role == "user"
        assert msg.content == "hello"

    def test_system_message(self):
        msg = Message(role="system", content="you are a bot")
        assert msg.role == "system"


class TestLLMResponse:
    def test_default_values(self):
        resp = LLMResponse()
        assert resp.content == ""
        assert resp.model == ""
        assert resp.usage == {}
        assert resp.finish_reason == ""

    def test_with_values(self):
        resp = LLMResponse(
            content="hello",
            model="gpt-4",
            usage={"total_tokens": 100},
            finish_reason="stop",
        )
        assert resp.content == "hello"
        assert resp.model == "gpt-4"
        assert resp.usage["total_tokens"] == 100


class TestTranscriptSegment:
    def test_default_values(self):
        seg = TranscriptSegment()
        assert seg.text == ""
        assert seg.start_us == 0
        assert seg.end_us == 0
        assert seg.confidence == 0.0

    def test_with_values(self):
        seg = TranscriptSegment(text="hi", start_us=1_000_000, end_us=2_000_000, confidence=0.95)
        assert seg.text == "hi"
        assert seg.start_us == 1_000_000


class TestTranscript:
    def test_default_values(self):
        t = Transcript()
        assert t.text == ""
        assert t.language == ""
        assert t.segments == []
        assert t.duration_us == 0

    def test_to_subtitle_blocks(self):
        t = Transcript(
            text="hello world",
            segments=[
                TranscriptSegment(text="hello", start_us=0, end_us=1_000_000),
                TranscriptSegment(text="world", start_us=1_000_000, end_us=2_000_000),
            ],
        )
        blocks = t.to_subtitle_blocks()
        assert len(blocks) == 2
        assert blocks[0]["text"] == "hello"
        assert blocks[0]["start_us"] == 0
        assert blocks[0]["end_us"] == 1_000_000
        assert blocks[0]["duration_us"] == 1_000_000
        assert blocks[1]["text"] == "world"

    def test_to_subtitle_blocks_empty(self):
        t = Transcript()
        assert t.to_subtitle_blocks() == []

    def test_to_subtitle_blocks_max_chars(self):
        t = Transcript(
            segments=[TranscriptSegment(text="a" * 30, start_us=0, end_us=1_000_000)],
        )
        blocks = t.to_subtitle_blocks(max_chars_per_line=10)
        assert len(blocks) == 1  # max_chars_per_line param is accepted but not enforced in current impl


class TestSceneBoundary:
    def test_default_values(self):
        sb = SceneBoundary()
        assert sb.frame_number == 0
        assert sb.time_us == 0
        assert sb.confidence == 0.0


# ──────────────────────────────────────────────
# ProviderRouter tests
# ──────────────────────────────────────────────


class TestProviderRouter:
    def setup_method(self):
        self.router = ProviderRouter()

    def test_register_and_get_llm(self):
        mock_llm = MagicMock(spec=LLMProvider)
        self.router.register_llm("openai", mock_llm, default=True)
        assert self.router.get_llm("openai") is mock_llm

    def test_get_llm_default(self):
        mock_llm = MagicMock(spec=LLMProvider)
        self.router.register_llm("openai", mock_llm, default=True)
        assert self.router.get_llm() is mock_llm

    def test_get_llm_not_registered_raises(self):
        with pytest.raises(KeyError, match="LLM provider 'unknown' not registered"):
            self.router.get_llm("unknown")

    def test_get_llm_empty_raises(self):
        with pytest.raises(KeyError):
            self.router.get_llm()

    def test_register_and_get_asr(self):
        mock_asr = MagicMock(spec=ASRProvider)
        self.router.register_asr("whisper", mock_asr, default=True)
        assert self.router.get_asr("whisper") is mock_asr

    def test_get_asr_default(self):
        mock_asr = MagicMock(spec=ASRProvider)
        self.router.register_asr("whisper", mock_asr)
        assert self.router.get_asr() is mock_asr

    def test_get_asr_not_registered_raises(self):
        with pytest.raises(KeyError, match="ASR provider"):
            self.router.get_asr("unknown")

    def test_register_and_get_cv(self):
        mock_cv = MagicMock(spec=CVProvider)
        self.router.register_cv("opencv", mock_cv, default=True)
        assert self.router.get_cv("opencv") is mock_cv

    def test_get_cv_not_registered_raises(self):
        with pytest.raises(KeyError, match="CV provider"):
            self.router.get_cv("unknown")

    def test_register_multiple_llm_first_is_default(self):
        mock1 = MagicMock(spec=LLMProvider)
        mock2 = MagicMock(spec=LLMProvider)
        self.router.register_llm("openai", mock1)
        self.router.register_llm("ollama", mock2)
        assert self.router.get_llm() is mock1

    def test_register_multiple_llm_explicit_default(self):
        mock1 = MagicMock(spec=LLMProvider)
        mock2 = MagicMock(spec=LLMProvider)
        self.router.register_llm("openai", mock1)
        self.router.register_llm("ollama", mock2, default=True)
        assert self.router.get_llm() is mock2

    def test_get_available_llm_default_available(self):
        mock_llm = MagicMock(spec=LLMProvider)
        mock_llm.is_available = AsyncMock(return_value=True)
        self.router.register_llm("openai", mock_llm, default=True)
        result = _run(self.router.get_available_llm())
        assert result is mock_llm

    def test_get_available_llm_fallback(self):
        mock1 = MagicMock(spec=LLMProvider)
        mock1.is_available = AsyncMock(return_value=False)
        mock2 = MagicMock(spec=LLMProvider)
        mock2.is_available = AsyncMock(return_value=True)
        self.router.register_llm("openai", mock1, default=True)
        self.router.register_llm("ollama", mock2)
        self.router._llm_fallback = "ollama"
        result = _run(self.router.get_available_llm())
        assert result is mock2

    def test_get_available_llm_all_unavailable_raises(self):
        mock1 = MagicMock(spec=LLMProvider)
        mock1.is_available = AsyncMock(return_value=False)
        self.router.register_llm("openai", mock1, default=True)
        with pytest.raises(RuntimeError, match="No LLM provider available"):
            _run(self.router.get_available_llm())

    def test_get_available_llm_default_exception_tries_fallback(self):
        mock1 = MagicMock(spec=LLMProvider)
        mock1.is_available = AsyncMock(side_effect=ConnectionError("fail"))
        mock2 = MagicMock(spec=LLMProvider)
        mock2.is_available = AsyncMock(return_value=True)
        self.router.register_llm("openai", mock1, default=True)
        self.router.register_llm("ollama", mock2)
        self.router._llm_fallback = "ollama"
        result = _run(self.router.get_available_llm())
        assert result is mock2

    def test_get_available_llm_iterates_all(self):
        mock1 = MagicMock(spec=LLMProvider)
        mock1.is_available = AsyncMock(return_value=False)
        mock2 = MagicMock(spec=LLMProvider)
        mock2.is_available = AsyncMock(return_value=True)
        self.router.register_llm("openai", mock1)
        self.router.register_llm("ollama", mock2)
        result = _run(self.router.get_available_llm())
        assert result is mock2


# ──────────────────────────────────────────────
# OpenAI Provider tests
# ──────────────────────────────────────────────


class TestOpenAILLMProvider:
    def test_is_available_with_key(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider
        p = OpenAILLMProvider(api_key="sk-test")
        assert _run(p.is_available()) is True

    def test_is_available_without_key(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider
        p = OpenAILLMProvider(api_key="")
        assert _run(p.is_available()) is False

    def test_default_base_url(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider
        p = OpenAILLMProvider(api_key="sk-test")
        assert p._base_url == "https://api.openai.com/v1"

    def test_custom_base_url(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider
        p = OpenAILLMProvider(api_key="sk-test", base_url="https://custom.api.com/v1")
        assert p._base_url == "https://custom.api.com/v1"

    def test_default_model(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider
        p = OpenAILLMProvider(api_key="sk-test")
        assert p._model == "gpt-4o"

    def test_provider_name(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider
        assert OpenAILLMProvider.provider_name == "openai"

    def test_chat(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "hello world"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 10
        mock_response.usage.completion_tokens = 20
        mock_response.usage.total_tokens = 30

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        p = OpenAILLMProvider(api_key="sk-test")
        p._client = mock_client

        result = _run(p.chat([Message(role="user", content="hi")]))
        assert result.content == "hello world"
        assert result.model == "gpt-4o"
        assert result.usage["total_tokens"] == 30
        assert result.finish_reason == "stop"

    def test_chat_custom_model(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "resp"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-3.5-turbo"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 0
        mock_response.usage.completion_tokens = 0
        mock_response.usage.total_tokens = 0

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        p = OpenAILLMProvider(api_key="sk-test")
        p._client = mock_client

        _run(p.chat([Message(role="user", content="hi")], model="gpt-3.5-turbo"))
        call_kwargs = mock_client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-3.5-turbo"

    def test_chat_stream(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider

        async def mock_stream():
            chunk1 = MagicMock()
            chunk1.choices = [MagicMock()]
            chunk1.choices[0].delta.content = "hello"
            chunk2 = MagicMock()
            chunk2.choices = [MagicMock()]
            chunk2.choices[0].delta.content = " world"
            yield chunk1
            yield chunk2

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        p = OpenAILLMProvider(api_key="sk-test")
        p._client = mock_client

        chunks = []

        async def collect():
            async for chunk in p.chat_stream([Message(role="user", content="hi")]):
                chunks.append(chunk)

        _run(collect())
        assert chunks == ["hello", " world"]

    def test_get_client_import_error(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAILLMProvider
        p = OpenAILLMProvider(api_key="sk-test")
        p._client = None
        with patch.dict("sys.modules", {"openai": None}):
            with pytest.raises(RuntimeError, match="openai package not installed"):
                p._get_client()


class TestOpenAIASRProvider:
    def test_is_available_with_key(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAIASRProvider
        p = OpenAIASRProvider(api_key="sk-test")
        assert _run(p.is_available()) is True

    def test_is_available_without_key(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAIASRProvider
        p = OpenAIASRProvider(api_key="")
        assert _run(p.is_available()) is False

    def test_provider_name(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAIASRProvider
        assert OpenAIASRProvider.provider_name == "openai-whisper"

    def test_transcribe(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAIASRProvider
        import tempfile, os

        mock_response = MagicMock()
        mock_response.text = "hello world"

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

        p = OpenAIASRProvider(api_key="sk-test")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            tmp_path = f.name

        try:
            with patch.object(p, "_get_client", return_value=mock_client):
                result = _run(p.transcribe(tmp_path, language="en"))
            assert result.text == "hello world"
            assert result.language == "en"
        finally:
            os.unlink(tmp_path)

    def test_transcribe_with_timestamps(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAIASRProvider
        import tempfile, os

        mock_seg = MagicMock()
        mock_seg.text = "hello"
        mock_seg.start = 0.0
        mock_seg.end = 1.5

        mock_response = MagicMock()
        mock_response.text = "hello"
        mock_response.segments = [mock_seg]

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

        p = OpenAIASRProvider(api_key="sk-test")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            tmp_path = f.name

        try:
            with patch.object(p, "_get_client", return_value=mock_client):
                result = _run(p.transcribe_with_timestamps(tmp_path))
            assert result.text == "hello"
            assert len(result.segments) == 1
            assert result.segments[0].text == "hello"
            assert result.segments[0].start_us == 0
            assert result.segments[0].end_us == 1_500_000
        finally:
            os.unlink(tmp_path)

    def test_transcribe_with_timestamps_dict_segments(self):
        from jy_auto_editor.ai.providers.openai_provider import OpenAIASRProvider
        import tempfile, os

        mock_response = MagicMock()
        mock_response.text = "hello"
        mock_response.segments = [{"text": "hi", "start": 0.5, "end": 1.0}]

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create = AsyncMock(return_value=mock_response)

        p = OpenAIASRProvider(api_key="sk-test")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"fake audio")
            tmp_path = f.name

        try:
            with patch.object(p, "_get_client", return_value=mock_client):
                result = _run(p.transcribe_with_timestamps(tmp_path))
            assert result.segments[0].text == "hi"
            assert result.segments[0].start_us == 500_000
            assert result.segments[0].end_us == 1_000_000
        finally:
            os.unlink(tmp_path)


# ──────────────────────────────────────────────
# Ollama Provider tests
# ──────────────────────────────────────────────


class TestOllamaLLMProvider:
    def test_provider_name(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider
        assert OllamaLLMProvider.provider_name == "ollama"

    def test_default_base_url(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider
        p = OllamaLLMProvider()
        assert p._base_url == "http://localhost:11434"

    def test_default_model(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider
        p = OllamaLLMProvider()
        assert p._model == "qwen2.5:14b"

    def test_custom_base_url_trailing_slash(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider
        p = OllamaLLMProvider(base_url="http://localhost:11434/")
        assert p._base_url == "http://localhost:11434"

    def test_chat(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {"content": "hello from ollama"},
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaLLMProvider()

        with patch("jy_auto_editor.ai.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            result = _run(p.chat([Message(role="user", content="hi")]))
        assert result.content == "hello from ollama"
        assert result.model == "qwen2.5:14b"

    def test_chat_custom_model(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"content": "resp"}}
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaLLMProvider()

        with patch("jy_auto_editor.ai.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            _run(p.chat([Message(role="user", content="hi")], model="llama3"))
        call_kwargs = mock_client.post.call_args
        assert call_kwargs.kwargs["json"]["model"] == "llama3"

    def test_chat_stream(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider

        lines = [
            json.dumps({"message": {"content": "hello"}}),
            json.dumps({"message": {"content": " world"}}),
            "",
        ]

        mock_stream_resp = MagicMock()
        mock_stream_resp.aiter_lines = MagicMock(return_value=_async_iter(lines))

        mock_client = AsyncMock()
        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_stream_resp)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaLLMProvider()

        chunks = []

        async def collect():
            async for chunk in p.chat_stream([Message(role="user", content="hi")]):
                chunks.append(chunk)

        with patch("jy_auto_editor.ai.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            _run(collect())
        assert chunks == ["hello", " world"]

    def test_is_available_success(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider

        mock_resp = MagicMock()
        mock_resp.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaLLMProvider()

        with patch("jy_auto_editor.ai.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            assert _run(p.is_available()) is True

    def test_is_available_failure(self):
        from jy_auto_editor.ai.providers.ollama_provider import OllamaLLMProvider

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        p = OllamaLLMProvider()

        with patch("jy_auto_editor.ai.providers.ollama_provider.httpx.AsyncClient", return_value=mock_client):
            assert _run(p.is_available()) is False


# ──────────────────────────────────────────────
# Qwen Provider tests
# ──────────────────────────────────────────────


class TestQwenLLMProvider:
    def test_provider_name(self):
        from jy_auto_editor.ai.providers.qwen_provider import QwenLLMProvider
        assert QwenLLMProvider.provider_name == "qwen"

    def test_is_available_with_key(self):
        from jy_auto_editor.ai.providers.qwen_provider import QwenLLMProvider
        p = QwenLLMProvider(api_key="test-key")
        assert _run(p.is_available()) is True

    def test_is_available_without_key(self):
        from jy_auto_editor.ai.providers.qwen_provider import QwenLLMProvider
        p = QwenLLMProvider(api_key="")
        assert _run(p.is_available()) is False

    def test_default_model(self):
        from jy_auto_editor.ai.providers.qwen_provider import QwenLLMProvider
        p = QwenLLMProvider(api_key="test")
        assert p._model == "qwen-max"

    def test_chat_success(self):
        from jy_auto_editor.ai.providers.qwen_provider import QwenLLMProvider

        mock_choice = MagicMock()
        mock_choice.message.content = "qwen response"
        mock_choice.finish_reason = "stop"

        mock_output = MagicMock()
        mock_output.choices = [mock_choice]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.output = mock_output
        mock_response.usage = {"input_tokens": 5, "output_tokens": 10}

        mock_gen = MagicMock()
        mock_gen.call = MagicMock(return_value=mock_response)

        mock_dashscope = MagicMock()

        p = QwenLLMProvider(api_key="test-key")

        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            with patch("jy_auto_editor.ai.providers.qwen_provider.QwenLLMProvider.chat", new_callable=lambda: _mock_chat_success):
                pass

        # Direct mock approach
        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            with patch("dashscope.Generation", mock_gen):
                result = _run(p.chat([Message(role="user", content="hi")]))
        assert result.content == "qwen response"
        assert result.usage["input_tokens"] == 5

    def test_chat_error_response(self):
        from jy_auto_editor.ai.providers.qwen_provider import QwenLLMProvider

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.code = "invalid_request"
        mock_response.message = "bad request"

        mock_gen = MagicMock()
        mock_gen.call = MagicMock(return_value=mock_response)

        mock_dashscope = MagicMock()

        p = QwenLLMProvider(api_key="test-key")

        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            with patch("dashscope.Generation", mock_gen):
                result = _run(p.chat([Message(role="user", content="hi")]))
        assert result.content == ""
        assert result.finish_reason == "error"

    def test_chat_import_error(self):
        from jy_auto_editor.ai.providers.qwen_provider import QwenLLMProvider

        p = QwenLLMProvider(api_key="test-key")

        with patch.dict("sys.modules", {"dashscope": None}):
            with pytest.raises(RuntimeError, match="dashscope not installed"):
                _run(p.chat([Message(role="user", content="hi")]))

    def test_chat_stream(self):
        from jy_auto_editor.ai.providers.qwen_provider import QwenLLMProvider

        mock_choice = MagicMock()
        mock_choice.message.content = "stream chunk"

        mock_output = MagicMock()
        mock_output.choices = [mock_choice]

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.output = mock_output

        mock_gen = MagicMock()
        mock_gen.call = MagicMock(return_value=iter([mock_resp]))

        mock_dashscope = MagicMock()

        p = QwenLLMProvider(api_key="test-key")

        chunks = []

        async def collect():
            async for chunk in p.chat_stream([Message(role="user", content="hi")]):
                chunks.append(chunk)

        with patch.dict("sys.modules", {"dashscope": mock_dashscope}):
            with patch("dashscope.Generation", mock_gen):
                _run(collect())
        assert chunks == ["stream chunk"]


def _mock_chat_success(self, messages, model="", temperature=0.7, max_tokens=0, **kwargs):
    """Helper for mocking chat success — not used directly, kept for reference"""
    pass


async def _async_iter(items):
    """Helper to create an async iterator from a list"""
    for item in items:
        yield item


# ──────────────────────────────────────────────
# PySceneDetect CV Provider tests
# ──────────────────────────────────────────────


class TestPySceneDetectCVProvider:
    def test_provider_name(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider
        p = PySceneDetectCVProvider()
        assert p.provider_name == "pyscenedetect"

    def test_check_scenedetect_not_available(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider
        p = PySceneDetectCVProvider()
        # Mock import to fail
        with patch.dict("sys.modules", {"scenedetect": None}):
            result = p._check_scenedetect()
            assert result is False
            assert p._scenedetect_available is False

    def test_check_scenedetect_cached(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider
        p = PySceneDetectCVProvider()
        p._scenedetect_available = False
        # Should return cached value without checking import
        result = p._check_scenedetect()
        assert result is False

    def test_detect_with_ffmpeg(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider

        p = PySceneDetectCVProvider(ffmpeg_path="ffmpeg")

        # Mock subprocess
        mock_stderr = b"""
        [showinfo @ 0x5555] n:   0 pts_time:0.000000
        [showinfo @ 0x5555] n:  75 pts_time:2.500000
        [showinfo @ 0x5555] n: 150 pts_time:5.000000
        """

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", mock_stderr))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = _run(p._detect_with_ffmpeg("/tmp/test.mp4", 30.0))

        assert len(result) == 3
        assert result[0].time_us == 0
        assert result[1].time_us == 2_500_000
        assert result[1].frame_number == 75
        assert result[2].time_us == 5_000_000

    def test_detect_with_ffmpeg_no_output(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider

        p = PySceneDetectCVProvider()

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"no scenes"))

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = _run(p._detect_with_ffmpeg("/tmp/test.mp4", 30.0))

        assert result == []

    def test_detect_with_ffmpeg_not_found(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider

        p = PySceneDetectCVProvider(ffmpeg_path="/nonexistent/ffmpeg")

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = _run(p._detect_with_ffmpeg("/tmp/test.mp4", 30.0))

        assert result == []

    def test_extract_keyframes(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider
        import tempfile
        import os

        p = PySceneDetectCVProvider()

        # Create temp directory for output
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "test.mp4")
            output_dir = os.path.join(tmpdir, "test_keyframes")
            os.makedirs(output_dir)

            # Create fake frame files
            for i in range(3):
                frame_path = os.path.join(output_dir, f"frame_{i:04d}.jpg")
                with open(frame_path, "w") as f:
                    f.write("fake image")

            mock_proc = MagicMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_proc.returncode = 0

            with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
                result = _run(p.extract_keyframes(video_path, interval_seconds=2.0))

            assert len(result) == 3
            assert "frame_0000.jpg" in result[0]
            assert "frame_0002.jpg" in result[2]

    def test_extract_keyframes_failure(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider

        p = PySceneDetectCVProvider()

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = _run(p.extract_keyframes("/tmp/test.mp4", 1.0))

        assert result == []

    def test_is_available_success(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider

        p = PySceneDetectCVProvider()

        mock_proc = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"ffmpeg version 4.0", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = _run(p.is_available())

        assert result is True

    def test_is_available_ffmpeg_not_found(self):
        from jy_auto_editor.ai.providers.cv_provider import PySceneDetectCVProvider

        p = PySceneDetectCVProvider(ffmpeg_path="/nonexistent/ffmpeg")

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = _run(p.is_available())

        assert result is False

