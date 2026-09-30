"""Bootstrap 和 __main__ 入口单元测试"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from jy_auto_editor.core.config import AppConfig, DriverConfig, ProviderConfig, ProvidersConfig
from jy_auto_editor.core.bootstrap import (
    ApplicationContext,
    ProviderRegistryAdapter,
    _create_cv_provider,
    _create_llm_providers,
    _ensure_plugins_loaded,
    bootstrap,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_config(**overrides) -> AppConfig:
    """构建测试用 AppConfig"""
    config = AppConfig()
    config.providers.llm_providers = {
        "openai": ProviderConfig(
            name="openai",
            api_key="test-key",
            base_url="https://api.test.com/v1",
            model="gpt-4o",
        ),
        "ollama": ProviderConfig(
            name="ollama",
            base_url="http://localhost:11434",
            model="qwen2.5:7b",
        ),
    }
    config.providers.llm_default = "openai"
    return config


# ══════════════════════════════════════════════
# ProviderRegistryAdapter
# ══════════════════════════════════════════════

class TestProviderRegistryAdapter:
    def test_get_provider_llm(self):
        mock_router = MagicMock()
        mock_llm = MagicMock()
        mock_router.get_llm.return_value = mock_llm

        adapter = ProviderRegistryAdapter(mock_router)
        result = adapter.get_provider("llm")

        assert result is mock_llm
        mock_router.get_llm.assert_called_once()

    def test_get_provider_asr(self):
        mock_router = MagicMock()
        mock_asr = MagicMock()
        mock_router.get_asr.return_value = mock_asr

        adapter = ProviderRegistryAdapter(mock_router)
        result = adapter.get_provider("asr")

        assert result is mock_asr

    def test_get_provider_cv(self):
        mock_router = MagicMock()
        mock_cv = MagicMock()
        mock_router.get_cv.return_value = mock_cv

        adapter = ProviderRegistryAdapter(mock_router)
        result = adapter.get_provider("cv")

        assert result is mock_cv

    def test_get_provider_unknown_raises(self):
        mock_router = MagicMock()
        adapter = ProviderRegistryAdapter(mock_router)

        with pytest.raises(KeyError, match="Unknown provider type"):
            adapter.get_provider("unknown_type")

    def test_get_provider_propagates_router_error(self):
        mock_router = MagicMock()
        mock_router.get_llm.side_effect = KeyError("not registered")

        adapter = ProviderRegistryAdapter(mock_router)
        with pytest.raises(KeyError):
            adapter.get_provider("llm")


# ══════════════════════════════════════════════
# Provider 工厂
# ══════════════════════════════════════════════

class TestCreateLLMProviders:
    def test_creates_openai(self):
        config = _make_config()
        providers = _create_llm_providers(config)
        assert "openai" in providers
        assert providers["openai"].provider_name == "openai"

    def test_creates_ollama(self):
        config = _make_config()
        providers = _create_llm_providers(config)
        assert "ollama" in providers
        assert providers["ollama"].provider_name == "ollama"

    def test_skips_unknown_provider(self):
        config = _make_config()
        config.providers.llm_providers["unknown"] = ProviderConfig(name="unknown")
        providers = _create_llm_providers(config)
        assert "unknown" not in providers

    def test_empty_config_returns_empty(self):
        config = AppConfig()
        providers = _create_llm_providers(config)
        assert providers == {}

    def test_multiple_providers(self):
        config = _make_config()
        providers = _create_llm_providers(config)
        assert len(providers) == 2


class TestCreateCVProvider:
    def test_creates_pyscenedetect(self):
        config = AppConfig()
        cv = _create_cv_provider(config)
        assert cv.provider_name == "pyscenedetect"


# ══════════════════════════════════════════════
# _ensure_plugins_loaded
# ══════════════════════════════════════════════

class TestEnsurePluginsLoaded:
    def test_does_not_raise(self):
        _ensure_plugins_loaded()

    def test_plugins_registered(self):
        from jy_auto_editor.core.plugin import get_global_registry
        _ensure_plugins_loaded()
        registry = get_global_registry()
        # 至少应注册 asr, scene_detect, highlight 等核心插件
        plugin_ids = [p.plugin_id for p in registry.list_plugins()]
        assert "asr" in plugin_ids


# ══════════════════════════════════════════════
# bootstrap() 集成
# ══════════════════════════════════════════════

class TestBootstrap:
    def test_bootstrap_returns_context(self):
        config = _make_config()
        ctx = bootstrap(config=config)

        assert isinstance(ctx, ApplicationContext)
        assert ctx.config is config
        assert ctx.pipeline is not None
        assert ctx.provider_router is not None
        assert ctx.provider_adapter is not None
        assert ctx.ffmpeg is not None

    def test_bootstrap_registers_llm_providers(self):
        config = _make_config()
        ctx = bootstrap(config=config)

        # 应能通过 router 获取 LLM
        llm = ctx.provider_router.get_llm()
        assert llm.provider_name == "openai"  # default

    def test_bootstrap_registers_cv_provider(self):
        config = _make_config()
        ctx = bootstrap(config=config)

        cv = ctx.provider_router.get_cv()
        assert cv.provider_name == "pyscenedetect"

    def test_bootstrap_pipeline_has_stages(self):
        config = _make_config()
        ctx = bootstrap(config=config)

        stage_names = [s.name for s in ctx.pipeline.stages]
        assert "ingest" in stage_names
        assert "analyze" in stage_names
        assert "edit" in stage_names
        assert "export" in stage_names

    def test_bootstrap_with_default_config(self):
        """即使没有任何 API key，bootstrap 也不应崩溃"""
        config = AppConfig()
        ctx = bootstrap(config=config)
        assert ctx.pipeline is not None

    def test_bootstrap_adapter_works_with_context(self):
        """验证 adapter 可以正确代理到 router"""
        config = _make_config()
        ctx = bootstrap(config=config)

        # adapter.get_provider("llm") 应该返回默认的 openai LLM
        llm = ctx.provider_adapter.get_provider("llm")
        assert llm.provider_name == "openai"

    def test_bootstrap_driver_created(self):
        config = _make_config()
        ctx = bootstrap(config=config)
        assert ctx.driver is not None

    def test_bootstrap_injects_into_pipeline_context(self):
        """验证 pipeline.run 时 runtime deps 注入到 context.extra"""
        config = _make_config()
        ctx = bootstrap(config=config)

        # 模拟注入
        from jy_auto_editor.core.models import PipelineContext, ProjectInput
        pctx = PipelineContext(input=ProjectInput())
        ctx.pipeline._inject_runtime_deps(pctx)

        assert "provider_registry" in pctx.extra
        assert "ffmpeg" in pctx.extra
        assert "driver" in pctx.extra


# ══════════════════════════════════════════════
# __main__.py 入口
# ══════════════════════════════════════════════

class TestMainEntry:
    def test_main_module_importable(self):
        import jy_auto_editor.__main__  # noqa: F401

    def test_main_function_exists(self):
        from jy_auto_editor.ui.cli.main import main
        assert callable(main)
