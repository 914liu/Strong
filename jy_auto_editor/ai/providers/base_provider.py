"""Provider 抽象基类 — LLM / ASR / CV 统一接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional


# ──────────────────────────────────────────────
# LLM 相关
# ──────────────────────────────────────────────

@dataclass
class Message:
    """LLM 消息"""
    role: str                        # system | user | assistant
    content: str


@dataclass
class LLMResponse:
    """LLM 响应"""
    content: str = ""
    model: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """LLM 统一接口"""

    provider_name: str = ""

    @abstractmethod
    async def chat(
        self,
        messages: list[Message],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> LLMResponse:
        """同步对话"""
        ...

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[Message],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
        **kwargs,
    ) -> AsyncIterator[str]:
        """流式对话"""
        ...
        # 需要 yield，这里用 AsyncIterator 标记
        yield ""

    async def embeddings(
        self, texts: list[str], model: str = ""
    ) -> list[list[float]]:
        """文本向量化（可选实现）"""
        raise NotImplementedError(f"{self.provider_name} does not support embeddings")

    @abstractmethod
    async def is_available(self) -> bool:
        """检查 Provider 是否可用"""
        ...


# ──────────────────────────────────────────────
# ASR 相关
# ──────────────────────────────────────────────

@dataclass
class TranscriptSegment:
    """ASR 转录片段"""
    text: str = ""
    start_us: int = 0                # 起始时间（微秒）
    end_us: int = 0                  # 结束时间（微秒）
    confidence: float = 0.0


@dataclass
class Transcript:
    """ASR 转录结果"""
    text: str = ""
    language: str = ""
    segments: list[TranscriptSegment] = field(default_factory=list)
    duration_us: int = 0

    def to_subtitle_blocks(self, max_chars_per_line: int = 20) -> list[dict]:
        """转换为字幕块列表"""
        blocks = []
        for seg in self.segments:
            blocks.append({
                "text": seg.text,
                "start_us": seg.start_us,
                "end_us": seg.end_us,
                "duration_us": seg.end_us - seg.start_us,
            })
        return blocks


class ASRProvider(ABC):
    """语音识别统一接口"""

    provider_name: str = ""

    @abstractmethod
    async def transcribe(
        self, audio_path: str, language: str = "zh"
    ) -> Transcript:
        """转录音频文件"""
        ...

    @abstractmethod
    async def transcribe_with_timestamps(
        self, audio_path: str, language: str = "zh"
    ) -> Transcript:
        """转录并返回时间戳"""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


# ──────────────────────────────────────────────
# CV 相关
# ──────────────────────────────────────────────

@dataclass
class SceneBoundary:
    """场景切换点"""
    frame_number: int = 0
    time_us: int = 0                 # 切换发生的微秒时间
    confidence: float = 0.0


class CVProvider(ABC):
    """计算机视觉统一接口"""

    provider_name: str = ""

    @abstractmethod
    async def detect_scenes(
        self, video_path: str, threshold: float = 30.0
    ) -> list[SceneBoundary]:
        """检测场景切换点"""
        ...

    @abstractmethod
    async def extract_keyframes(
        self, video_path: str, interval_seconds: float = 1.0
    ) -> list[str]:
        """提取关键帧图片路径列表"""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        ...


# ──────────────────────────────────────────────
# Provider 路由器
# ──────────────────────────────────────────────

class ProviderRouter:
    """Provider 路由器 — 支持主备切换、负载均衡"""

    def __init__(self) -> None:
        self._llm_providers: dict[str, LLMProvider] = {}
        self._asr_providers: dict[str, ASRProvider] = {}
        self._cv_providers: dict[str, CVProvider] = {}
        self._llm_default: str = ""
        self._llm_fallback: str = ""
        self._asr_default: str = ""
        self._cv_default: str = ""

    def register_llm(self, name: str, provider: LLMProvider, default: bool = False) -> None:
        self._llm_providers[name] = provider
        if default or not self._llm_default:
            self._llm_default = name

    def register_asr(self, name: str, provider: ASRProvider, default: bool = False) -> None:
        self._asr_providers[name] = provider
        if default or not self._asr_default:
            self._asr_default = name

    def register_cv(self, name: str, provider: CVProvider, default: bool = False) -> None:
        self._cv_providers[name] = provider
        if default or not self._cv_default:
            self._cv_default = name

    def get_llm(self, name: str = "") -> LLMProvider:
        name = name or self._llm_default
        if name not in self._llm_providers:
            raise KeyError(f"LLM provider '{name}' not registered")
        return self._llm_providers[name]

    def get_asr(self, name: str = "") -> ASRProvider:
        name = name or self._asr_default
        if name not in self._asr_providers:
            raise KeyError(f"ASR provider '{name}' not registered")
        return self._asr_providers[name]

    def get_cv(self, name: str = "") -> CVProvider:
        name = name or self._cv_default
        if name not in self._cv_providers:
            raise KeyError(f"CV provider '{name}' not registered")
        return self._cv_providers[name]

    async def get_available_llm(self) -> LLMProvider:
        """获取可用的 LLM Provider（自动降级）"""
        # 尝试默认
        try:
            provider = self.get_llm()
            if await provider.is_available():
                return provider
        except Exception:
            pass
        # 尝试 fallback
        if self._llm_fallback:
            try:
                provider = self.get_llm(self._llm_fallback)
                if await provider.is_available():
                    return provider
            except Exception:
                pass
        # 遍历所有
        for name, provider in self._llm_providers.items():
            if await provider.is_available():
                return provider
        raise RuntimeError("No LLM provider available")
