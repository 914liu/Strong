"""core/config 单元测试"""

import os
import pytest
import tempfile
from pathlib import Path

from jy_auto_editor.core.config import (
    AppConfig,
    ProviderConfig,
    ASRProviderConfig,
    DriverConfig,
    ProvidersConfig,
    _resolve_env_vars,
    _detect_jianying_paths,
    load_config,
)


class TestResolveEnvVars:
    def test_simple_env_var(self, monkeypatch):
        monkeypatch.setenv("TEST_KEY", "test_value")
        result = _resolve_env_vars("${TEST_KEY}")
        assert result == "test_value"

    def test_env_var_missing_returns_empty(self, monkeypatch):
        monkeypatch.delenv("MISSING_KEY", raising=False)
        result = _resolve_env_vars("${MISSING_KEY}")
        assert result == ""

    def test_no_env_vars(self):
        result = _resolve_env_vars("plain_string")
        assert result == "plain_string"

    def test_dict_resolution(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "sk-test")
        data = {"api_key": "${API_KEY}", "model": "gpt-4"}
        result = _resolve_env_vars(data)
        assert result["api_key"] == "sk-test"
        assert result["model"] == "gpt-4"

    def test_list_resolution(self, monkeypatch):
        monkeypatch.setenv("ITEM", "hello")
        data = ["${ITEM}", "world"]
        result = _resolve_env_vars(data)
        assert result[0] == "hello"
        assert result[1] == "world"

    def test_nested_resolution(self, monkeypatch):
        monkeypatch.setenv("NESTED", "deep_value")
        data = {"outer": {"inner": "${NESTED}"}}
        result = _resolve_env_vars(data)
        assert result["outer"]["inner"] == "deep_value"


class TestAppConfig:
    def test_defaults(self):
        config = AppConfig()
        assert config.project_name == "jy_auto_editor"
        assert config.debug is False
        assert config.log_level == "INFO"

    def test_driver_defaults(self):
        config = AppConfig()
        assert config.driver.use_gui_export is True
        assert config.driver.auto_decrypt is True
        assert config.driver.gui_timeout == 300


class TestDriverConfig:
    def test_defaults(self):
        config = DriverConfig()
        assert config.jianying_path == ""
        assert config.draft_root == ""
        assert config.use_gui_export is True


class TestProvidersConfig:
    def test_defaults(self):
        config = ProvidersConfig()
        assert config.llm_default == "openai"
        assert config.asr_default == "whisper-local"


class TestLoadConfig:
    def test_load_nonexistent_returns_default(self):
        config = load_config("/nonexistent/config.yaml")
        assert config.project_name == "jy_auto_editor"

    def test_load_from_yaml(self, tmp_path):
        yaml_content = """
debug: true
log_level: "DEBUG"
"""
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(yaml_content, encoding="utf-8")
        config = load_config(str(config_file))
        assert config.debug is True
        assert config.log_level == "DEBUG"

    def test_env_vars_override(self, monkeypatch):
        monkeypatch.setenv("JY_DEBUG", "1")
        monkeypatch.setenv("JY_LOG_LEVEL", "WARNING")
        config = load_config("/nonexistent")
        assert config.debug is True
        assert config.log_level == "WARNING"


class TestDetectJianyingPaths:
    def test_returns_tuple_of_strings(self):
        jianying_path, draft_root = _detect_jianying_paths()
        assert isinstance(jianying_path, str)
        assert isinstance(draft_root, str)
