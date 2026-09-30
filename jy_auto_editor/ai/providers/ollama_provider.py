"""Ollama Provider — 本地模型"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import httpx

from .base_provider import LLMProvider, LLMResponse, Message

logger = logging.getLogger(__name__)


class OllamaLLMProvider(LLMProvider):
    """Ollama 本地 LLM Provider"""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5:14b",
        timeout: int = 120,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def chat(
        self,
        messages: list[Message],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 0,
        **kwargs,
    ) -> LLMResponse:
        model = model or self._model
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        **({"num_predict": max_tokens} if max_tokens else {}),
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return LLMResponse(
                content=data.get("message", {}).get("content", ""),
                model=model,
            )

    async def chat_stream(
        self,
        messages: list[Message],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 0,
        **kwargs,
    ) -> AsyncIterator[str]:
        model = model or self._model
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": m.role, "content": m.content} for m in messages],
                    "stream": True,
                    "options": {"temperature": temperature},
                },
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False
