"""通义千问 Provider — 阿里云 DashScope"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from .base_provider import LLMProvider, LLMResponse, Message

logger = logging.getLogger(__name__)


class QwenLLMProvider(LLMProvider):
    """通义千问 LLM Provider (DashScope API)"""

    provider_name = "qwen"

    def __init__(
        self,
        api_key: str = "",
        model: str = "qwen-max",
        max_tokens: int = 4096,
        timeout: int = 60,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._timeout = timeout

    async def chat(
        self,
        messages: list[Message],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 0,
        **kwargs,
    ) -> LLMResponse:
        try:
            import dashscope
            from dashscope import Generation
        except ImportError:
            raise RuntimeError("dashscope not installed: pip install dashscope")

        dashscope.api_key = self._api_key
        model = model or self._model
        max_tokens = max_tokens or self._max_tokens

        response = Generation.call(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            max_tokens=max_tokens,
            result_format="message",
        )

        if response.status_code == 200:
            content = response.output.choices[0].message.content
            return LLMResponse(
                content=content,
                model=model,
                usage={
                    "input_tokens": response.usage.get("input_tokens", 0),
                    "output_tokens": response.usage.get("output_tokens", 0),
                },
                finish_reason=response.output.choices[0].finish_reason,
            )
        else:
            logger.error(f"Qwen API error: {response.code} - {response.message}")
            return LLMResponse(content="", finish_reason="error")

    async def chat_stream(
        self,
        messages: list[Message],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 0,
        **kwargs,
    ) -> AsyncIterator[str]:
        try:
            import dashscope
            from dashscope import Generation
        except ImportError:
            raise RuntimeError("dashscope not installed")

        dashscope.api_key = self._api_key
        model = model or self._model

        responses = Generation.call(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
            temperature=temperature,
            stream=True,
            incremental_output=True,
        )

        for response in responses:
            if response.status_code == 200:
                content = response.output.choices[0].message.content
                if content:
                    yield content

    async def is_available(self) -> bool:
        return bool(self._api_key)
