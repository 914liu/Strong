"""应用引导 — 根据配置初始化所有组件并组装运行环境

负责：
1. 根据 config 实例化 LLM / ASR / CV Provider 并注册到 ProviderRouter
2. 创建 ProviderRegistryAdapter 供 PluginContext 使用
3. 扫描并注册所有 AI 插件
4. 创建 FFmpegWrapper、Driver 等基础设施
5. 构建完整的 Pipeline 并返回 Application 上下文
"""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .config import AppConfig, load_config
from .events import EventBus
from .pipeline import Pipeline

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Provider 注册表适配器
# ──────────────────────────────────────────────

class ProviderRegistryAdapter:
    """将 ProviderRouter 适配为 PluginContext 需要的 get_provider(type) 接口

    PluginContext.get_provider("llm")  → router.get_llm()
    PluginContext.get_provider("asr")  → router.get_asr()
    PluginContext.get_provider("cv")   → router.get_cv()
    """

    def __init__(self, router: Any) -> None:
        self._router = router

    def get_provider(self, provider_type: str) -> Any:
        method_map = {
            "llm": self._router.get_llm,
            "asr": self._router.get_asr,
            "cv": self._router.get_cv,
        }
        method = method_map.get(provider_type)
        if method is None:
            raise KeyError(f"Unknown provider type: '{provider_type}'")
        return method()


# ──────────────────────────────────────────────
# Provider 工厂
# ──────────────────────────────────────────────

def _create_llm_providers(config: AppConfig) -> dict[str, Any]:
    """根据配置创建所有 LLM Provider 实例"""
    from ..ai.providers.openai_provider import OpenAILLMProvider
    from ..ai.providers.ollama_provider import OllamaLLMProvider
    from ..ai.providers.qwen_provider import QwenLLMProvider

    factories = {
        "openai": lambda cfg: OpenAILLMProvider(
            api_key=cfg.api_key,
            base_url=cfg.base_url,
            model=cfg.model or "gpt-4o",
            max_tokens=cfg.max_tokens,
            timeout=cfg.timeout,
        ),
        "ollama": lambda cfg: OllamaLLMProvider(
            base_url=cfg.base_url or "http://localhost:11434",
            model=cfg.model or "qwen2.5:14b",
            timeout=cfg.timeout,
        ),
        "qwen": lambda cfg: QwenLLMProvider(
            api_key=cfg.api_key,
            model=cfg.model or "qwen-max",
            max_tokens=cfg.max_tokens,
            timeout=cfg.timeout,
        ),
    }

    providers = {}
    for name, cfg in config.providers.llm_providers.items():
        factory = factories.get(name)
        if factory is None:
            logger.warning(f"Unknown LLM provider: '{name}', skipping")
            continue
        try:
            providers[name] = factory(cfg)
            logger.info(f"Created LLM provider: {name}")
        except Exception as e:
            logger.error(f"Failed to create LLM provider '{name}': {e}")

    return providers


def _create_asr_providers(config: AppConfig) -> dict[str, Any]:
    """根据配置创建所有 ASR Provider 实例"""
    from ..ai.providers.openai_provider import OpenAIASRProvider

    factories = {
        "openai-whisper": lambda cfg: OpenAIASRProvider(
            api_key=getattr(cfg, "extra", {}).get("api_key", "")
            if hasattr(cfg, "extra")
            else "",
            base_url=getattr(cfg, "extra", {}).get("base_url", "")
            if hasattr(cfg, "extra")
            else "",
        ),
    }

    providers = {}
    for name, cfg in config.providers.asr_providers.items():
        factory = factories.get(name)
        if factory is None:
            logger.warning(f"Unknown ASR provider: '{name}', skipping")
            continue
        try:
            # ASR config 结构不同，需要从 cfg 中提取 api_key
            if name == "openai-whisper":
                # 三级 fallback: ASR 自身配置 → LLM Provider 共享 → 环境变量
                api_key = getattr(cfg, "extra", {}).get("api_key", "")
                base_url = getattr(cfg, "extra", {}).get("base_url", "")
                if not api_key and "openai" in config.providers.llm_providers:
                    api_key = config.providers.llm_providers["openai"].api_key
                    base_url = base_url or config.providers.llm_providers["openai"].base_url
                if not api_key:
                    api_key = os.environ.get("OPENAI_API_KEY", "")
                if not api_key:
                    logger.warning(
                        "ASR provider 'openai-whisper' has no API key. "
                        "Set OPENAI_API_KEY in .env or config."
                    )
                providers[name] = OpenAIASRProvider(
                    api_key=api_key,
                    base_url=base_url,
                )
            else:
                providers[name] = factory(cfg)
            logger.info(f"Created ASR provider: {name}")
        except Exception as e:
            logger.error(f"Failed to create ASR provider '{name}': {e}")

    return providers


def _create_cv_provider(config: AppConfig) -> Any:
    """创建 CV Provider（PySceneDetect + FFmpeg）"""
    from ..ai.providers.cv_provider import PySceneDetectCVProvider

    ffmpeg_path = "ffmpeg"
    return PySceneDetectCVProvider(ffmpeg_path=ffmpeg_path)


class _Empty:
    """空占位，避免 KeyError"""
    api_key = ""
    base_url = ""


# ──────────────────────────────────────────────
# Application 上下文
# ──────────────────────────────────────────────

@dataclass
class ApplicationContext:
    """应用运行时的完整上下文"""
    config: AppConfig
    pipeline: Pipeline
    provider_router: Any
    provider_adapter: ProviderRegistryAdapter
    plugin_registry: Any
    ffmpeg: Any
    driver: Any = None


# ──────────────────────────────────────────────
# 主引导函数
# ──────────────────────────────────────────────

def bootstrap(
    config_path: Optional[str] = None,
    config: Optional[AppConfig] = None,
) -> ApplicationContext:
    """应用引导 — 初始化所有组件并返回 ApplicationContext

    Args:
        config_path: 配置文件路径（可选）
        config: 已有配置（可选，优先使用）

    Returns:
        ApplicationContext 包含所有初始化完成的组件
    """
    # 1. 加载配置
    if config is None:
        config = load_config(config_path)

    logger.info("Bootstrapping application...")

    # 2. 创建 Provider Router 并注册 Provider
    from ..ai.providers.base_provider import ProviderRouter

    router = ProviderRouter()

    # LLM
    llm_providers = _create_llm_providers(config)
    for name, provider in llm_providers.items():
        is_default = name == config.providers.llm_default
        router.register_llm(name, provider, default=is_default)

    # ASR
    asr_providers = _create_asr_providers(config)
    for name, provider in asr_providers.items():
        is_default = name == config.providers.asr_default
        router.register_asr(name, provider, default=is_default)

    # CV
    cv_provider = _create_cv_provider(config)
    router.register_cv("pyscenedetect", cv_provider, default=True)

    # 3. 创建适配器
    adapter = ProviderRegistryAdapter(router)

    # 4. 扫描并注册 AI 插件
    from ..core.plugin import PluginRegistry, get_global_registry

    plugin_registry = get_global_registry()
    # 插件通过 @register_plugin 装饰器已自动注册
    # 确保插件模块被导入
    _ensure_plugins_loaded()
    logger.info(f"Registered plugins: {[p.plugin_id for p in plugin_registry.list_plugins()]}")

    # 5. 创建 FFmpeg
    from ..infra.ffmpeg import FFmpegWrapper

    ffmpeg = FFmpegWrapper()

    # 6. 创建 Driver
    driver = _create_driver(config)

    # 7. 构建 Pipeline
    pipeline = _build_pipeline(config, adapter, plugin_registry, ffmpeg, driver)

    logger.info("Bootstrap complete")

    return ApplicationContext(
        config=config,
        pipeline=pipeline,
        provider_router=router,
        provider_adapter=adapter,
        plugin_registry=plugin_registry,
        ffmpeg=ffmpeg,
        driver=driver,
    )


def _ensure_plugins_loaded() -> None:
    """确保所有插件模块已导入（触发 @register_plugin 装饰器）"""
    plugin_modules = [
        "asr.plugin",
        "scene_detect.plugin",
        "highlight.plugin",
        "bgm.plugin",
        "content_rewrite.plugin",
        "cover_gen.plugin",
        "script_gen.plugin",
    ]
    for mod_name in plugin_modules:
        try:
            importlib.import_module(f"jy_auto_editor.ai.plugins.{mod_name}")
        except ImportError as e:
            logger.debug(f"Could not import plugin '{mod_name}': {e}")


def _create_driver(config: AppConfig) -> Any:
    """创建 HybridDriver"""
    try:
        from ..drivers.hybrid_driver import HybridDriver
        from ..core.config import DriverConfig

        driver_config = DriverConfig(
            jianying_path=config.driver.jianying_path,
            draft_root=config.driver.draft_root,
            use_gui_export=config.driver.use_gui_export,
            gui_timeout=config.driver.gui_timeout,
        )
        return HybridDriver(driver_config)
    except Exception as e:
        logger.warning(f"Failed to create driver: {e}")
        return None


def _build_pipeline(
    config: AppConfig,
    adapter: ProviderRegistryAdapter,
    plugin_registry: Any,
    ffmpeg: Any,
    driver: Any,
) -> Pipeline:
    """构建完整的 Pipeline"""
    from ..stages.ingest import IngestStage
    from ..stages.analyze import AnalyzeStage
    from ..stages.edit import EditStage
    from ..stages.review import ReviewStage
    from ..stages.export import ExportStage

    event_bus = EventBus()
    pipeline = Pipeline(event_bus=event_bus, config=config)

    # 将 provider_adapter 和 plugin_registry 注入到 stage 的 extra context
    # 通过 pipeline config 传递
    pipeline._provider_adapter = adapter
    pipeline._plugin_registry = plugin_registry
    pipeline._ffmpeg = ffmpeg
    pipeline._driver = driver

    pipeline.register_stage(IngestStage(ffmpeg=ffmpeg))
    pipeline.register_stage(AnalyzeStage())
    pipeline.register_stage(EditStage())
    pipeline.register_stage(ReviewStage(enabled=False))
    pipeline.register_stage(ExportStage())

    return pipeline
