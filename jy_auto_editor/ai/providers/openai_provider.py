"""OpenAI Provider — GPT-4o / Whisper / Embeddings"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Optional

from .base_provider import (
    ASRProvider,
    LLMProvider,
    LLMResponse,
    Message,
    Transcript,
    TranscriptSegment,
)

logger = logging.getLogger(__name__)


class OpenAILLMProvider(LLMProvider):
    """OpenAI LLM Provider"""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url or "https://api.openai.com/v1"
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                    timeout=self._timeout,
                )
            except ImportError:
                raise RuntimeError("openai package not installed: pip install openai")
        return self._client

    async def chat(
        self,
        messages: list[Message],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 0,
        **kwargs,
    ) -> LLMResponse:
        client = self._get_client()
        model = model or self._model
        max_tokens = max_tokens or self._max_tokens

        response = await client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )

        return LLMResponse(
            content=response.choices[0].message.content or "",
            model=response.model,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
            finish_reason=response.choices[0].finish_reason,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 0,
        **kwargs,
    ) -> AsyncIterator[str]:
        client = self._get_client()
        model = model or self._model
        max_tokens = max_tokens or self._max_tokens

        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def is_available(self) -> bool:
        return bool(self._api_key)


class OpenAIASRProvider(ASRProvider):
    """OpenAI Whisper API Provider"""

    provider_name = "openai-whisper"

    def __init__(self, api_key: str = "", base_url: str = "") -> None:
        self._api_key = api_key
        self._base_url = base_url

    def _get_client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url or "https://api.openai.com/v1",
        )

    async def transcribe(self, audio_path: str, language: str = "zh") -> Transcript:
        client = self._get_client()
        with open(audio_path, "rb") as f:
            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language,
            )
        return Transcript(
            text=response.text,
            language=language,
        )

    async def transcribe_with_timestamps(
        self, audio_path: str, language: str = "zh"
    ) -> Transcript:
        client = self._get_client()
        with open(audio_path, "rb") as f:
            response = await client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                language=language,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        segments = []
        for seg in getattr(response, "segments", []):
            segments.append(TranscriptSegment(
                text=seg.get("text", "") if isinstance(seg, dict) else seg.text,
                start_us=int((seg.get("start", 0) if isinstance(seg, dict) else seg.start) * 1_000_000),
                end_us=int((seg.get("end", 0) if isinstance(seg, dict) else seg.end) * 1_000_000),
            ))

        return Transcript(
            text=response.text,
            language=language,
            segments=segments,
        )

    async def is_available(self) -> bool:
        return bool(self._api_key)
