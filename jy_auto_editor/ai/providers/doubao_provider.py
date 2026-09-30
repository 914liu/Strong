"""豆包 Provider — 火山引擎方舟平台 (Ark)

豆包 API 兼容 OpenAI 格式，使用火山引擎的 API Key 认证。
文档: https://www.volcengine.com/docs/82379/1263482
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from .base_provider import LLMProvider, LLMResponse, Message

logger = logging.getLogger(__name__)

DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DOUBAO_DEFAULT_MODEL = "doubao-pro-32k"


class DoubaoLLMProvider(LLMProvider):
    """豆包 LLM Provider（火山引擎方舟）"""

    provider_name = "doubao"

    def __init__(
        self,
        api_key: str = "",
        model: str = "",
        max_tokens: int = 4096,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._model = model or DOUBAO_DEFAULT_MODEL
        self._max_tokens = max_tokens
        self._timeout = timeout
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(
                    api_key=self._api_key,
                    base_url=DOUBAO_BASE_URL,
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
