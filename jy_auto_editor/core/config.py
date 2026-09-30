"""配置管理 — YAML + 环境变量 + .env"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .exceptions import ConfigError


@dataclass
class ProviderConfig:
    """单个 AI Provider 的配置"""
    name: str = ""
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 4096
    timeout: int = 60
    retry: int = 3
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ASRProviderConfig:
    """ASR Provider 配置"""
    name: str = "whisper-local"
    model: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    language: str = "zh"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvidersConfig:
    """所有 AI Provider 的配置"""
    llm_default: str = "openai"
    llm_fallback: str = ""
    llm_providers: dict[str, ProviderConfig] = field(default_factory=dict)

    asr_default: str = "whisper-local"
    asr_fallback: str = ""
    asr_providers: dict[str, ASRProviderConfig] = field(default_factory=dict)


@dataclass
class DriverConfig:
    """驱动层配置"""
    jianying_path: str = ""            # 剪映安装路径（自动检测）
    draft_root: str = ""               # 草稿根目录（自动检测）
    use_gui_export: bool = True        # 是否使用 GUI 自动化导出
    gui_timeout: int = 300             # GUI 操作超时秒数
    auto_decrypt: bool = True          # 自动处理加密草稿


@dataclass
class AppConfig:
    """应用顶层配置"""
    project_name: str = "jy_auto_editor"
    debug: bool = False
    log_level: str = "INFO"
    temp_dir: str = ""
    cache_dir: str = ""
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    driver: DriverConfig = field(default_factory=DriverConfig)
    extra: dict[str, Any] = field(default_factory=dict)


def _resolve_env_vars(value: Any) -> Any:
    """递归解析配置值中的环境变量引用 ${ENV_VAR}"""
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            env_key = value[2:-1]
            return os.environ.get(env_key, "")
        return value
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    return value


def _detect_jianying_paths() -> tuple[str, str]:
    """自动检测剪映安装路径和草稿目录"""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return "", ""

    jianying_path = os.path.join(local_app_data, "JianyingPro")
    draft_root = os.path.join(
        local_app_data,
        "JianyingPro", "User Data", "Projects", "com.lveditor.draft",
    )
    return jianying_path, draft_root


def load_config(config_path: Optional[str] = None) -> AppConfig:
    """加载配置文件

    优先级: 环境变量 > 指定配置文件 > 默认配置
    """
    # 0. 加载 .env 文件（如果存在）
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    config = AppConfig()

    # 1. 自动检测剪映路径
    jianying_path, draft_root = _detect_jianying_paths()
    config.driver.jianying_path = jianying_path
    config.driver.draft_root = draft_root

    # 2. 加载 YAML 配置文件
    if config_path is None:
        # 包内默认配置（始终可用）
        _pkg_config = Path(__file__).parent.parent / "config" / "default.yaml"
        # 按优先级搜索配置文件
        search_paths = [
            _pkg_config,                                     # 包内默认（最低优先级）
            Path("config.yaml"),                             # CWD 用户覆盖
            Path.home() / ".jy_auto_editor" / "config.yaml", # 用户全局配置
        ]
        for p in search_paths:
            if p.exists():
                config_path = str(p)
                break

    if config_path and Path(config_path).exists():
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw = _resolve_env_vars(raw)
        config = _merge_config(config, raw)

    # 3. 环境变量覆盖（最高优先级）
    if os.environ.get("JY_DEBUG"):
        config.debug = True
    if os.environ.get("JY_LOG_LEVEL"):
        config.log_level = os.environ["JY_LOG_LEVEL"]
    if os.environ.get("JY_TEMP_DIR"):
        config.temp_dir = os.environ["JY_TEMP_DIR"]
    if os.environ.get("JY_CACHE_DIR"):
        config.cache_dir = os.environ["JY_CACHE_DIR"]

    return config


def _merge_config(config: AppConfig, raw: dict[str, Any]) -> AppConfig:
    """将 YAML 原始字典合并到 AppConfig"""
    if "debug" in raw:
        config.debug = bool(raw["debug"])
    if "log_level" in raw:
        config.log_level = str(raw["log_level"])
    if "temp_dir" in raw:
        config.temp_dir = str(raw["temp_dir"])
    if "cache_dir" in raw:
        config.cache_dir = str(raw["cache_dir"])

    # Provider 配置
    providers_raw = raw.get("providers", {})
    if "llm" in providers_raw:
        llm_raw = providers_raw["llm"]
        config.providers.llm_default = llm_raw.get("default", "openai")
        config.providers.llm_fallback = llm_raw.get("fallback", "")
        for name, p_raw in llm_raw.items():
            if name in ("default", "fallback", "strategy"):
                continue
            if isinstance(p_raw, dict):
                config.providers.llm_providers[name] = ProviderConfig(
                    name=name,
                    api_key=p_raw.get("api_key", ""),
                    base_url=p_raw.get("base_url", ""),
                    model=p_raw.get("model", ""),
                    max_tokens=p_raw.get("max_tokens", 4096),
                    timeout=p_raw.get("timeout", 60),
                    retry=p_raw.get("retry", 3),
                )

    if "asr" in providers_raw:
        asr_raw = providers_raw["asr"]
        config.providers.asr_default = asr_raw.get("default", "whisper-local")
        config.providers.asr_fallback = asr_raw.get("fallback", "")
        for name, p_raw in asr_raw.items():
            if name in ("default", "fallback"):
                continue
            if isinstance(p_raw, dict):
                config.providers.asr_providers[name] = ASRProviderConfig(
                    name=name,
                    model=p_raw.get("model", "large-v3"),
                    device=p_raw.get("device", "cuda"),
                    compute_type=p_raw.get("compute_type", "float16"),
                    language=p_raw.get("language", "zh"),
                    extra={
                        "api_key": p_raw.get("api_key", ""),
                        "base_url": p_raw.get("base_url", ""),
                    },
                )

    # Driver 配置
    driver_raw = raw.get("driver", {})
    if "use_gui_export" in driver_raw:
        config.driver.use_gui_export = bool(driver_raw["use_gui_export"])
    if "gui_timeout" in driver_raw:
        config.driver.gui_timeout = int(driver_raw["gui_timeout"])
    if "auto_decrypt" in driver_raw:
        config.driver.auto_decrypt = bool(driver_raw["auto_decrypt"])

    return config
