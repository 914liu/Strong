"""插件基类与注册机制"""

from __future__ import annotations

import importlib
import pkgutil
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class PluginDescription:
    """插件描述信息"""
    plugin_id: str
    plugin_name: str
    version: str
    description: str = ""
    author: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    required_providers: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


class PluginContext:
    """插件运行时上下文，提供所有必要的依赖注入"""

    def __init__(
        self,
        config: Any,
        provider_registry: Any = None,
        plugin_registry: Any = None,
        ffmpeg: Any = None,
        temp_dir: str = "",
        cache_dir: str = "",
    ) -> None:
        self._config = config
        self._provider_registry = provider_registry
        self._plugin_registry = plugin_registry
        self._ffmpeg = ffmpeg
        self._temp_dir = temp_dir
        self._cache_dir = cache_dir
        self._cache: dict[str, Any] = {}

    def get_provider(self, provider_type: str) -> Any:
        """获取指定类型的 Provider"""
        if self._provider_registry is None:
            raise RuntimeError("Provider registry not available")
        return self._provider_registry.get_provider(provider_type)

    def get_plugin(self, plugin_id: str) -> AIPlugin:
        """获取另一个插件实例（插件间协作）"""
        if self._plugin_registry is None:
            raise RuntimeError("Plugin registry not available")
        return self._plugin_registry.get_plugin(plugin_id)

    @property
    def config(self) -> Any:
        return self._config

    @property
    def temp_dir(self) -> str:
        return self._temp_dir

    @property
    def cache_dir(self) -> str:
        return self._cache_dir

    def get_temp_path(self, filename: str) -> Path:
        """获取临时文件路径"""
        p = Path(self._temp_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p / filename

    def get_cache(self, key: str) -> Optional[Any]:
        return self._cache.get(key)

    def set_cache(self, key: str, value: Any) -> None:
        self._cache[key] = value


class AIPlugin(ABC):
    """所有 AI 功能插件的基类"""

    plugin_id: str = ""
    plugin_name: str = ""
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
    input_schema: dict[str, Any] = {}
    output_schema: dict[str, Any] = {}
    required_providers: list[str] = []

    @abstractmethod
    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        """执行插件主逻辑

        Args:
            input_data: 输入数据，结构由 input_schema 定义
            context: 插件运行时上下文

        Returns:
            输出数据，结构由 output_schema 定义
        """
        ...

    async def health_check(self) -> bool:
        """健康检查，返回 True 表示插件可用"""
        return True

    async def setup(self, context: PluginContext) -> None:
        """插件初始化钩子（在首次调用 process 前执行）"""
        pass

    async def teardown(self) -> None:
        """插件销毁钩子"""
        pass

    def describe(self) -> PluginDescription:
        """返回插件描述"""
        return PluginDescription(
            plugin_id=self.plugin_id,
            plugin_name=self.plugin_name,
            version=self.version,
            description=self.description,
            author=self.author,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            required_providers=self.required_providers,
        )


# ──────────────────────────────────────────────
# 插件注册表
# ──────────────────────────────────────────────

class PluginRegistry:
    """插件注册中心"""

    def __init__(self) -> None:
        self._plugins: dict[str, AIPlugin] = {}
        self._plugin_classes: dict[str, type[AIPlugin]] = {}

    def register(self, plugin_class: type[AIPlugin]) -> type[AIPlugin]:
        """注册插件类"""
        instance = plugin_class()
        plugin_id = instance.plugin_id
        if not plugin_id:
            raise ValueError(f"Plugin {plugin_class.__name__} has no plugin_id")
        if plugin_id in self._plugins:
            logger.warning(f"Plugin '{plugin_id}' already registered, overwriting")
        self._plugins[plugin_id] = instance
        self._plugin_classes[plugin_id] = plugin_class
        logger.info(f"Registered plugin: {plugin_id} ({instance.plugin_name})")
        return plugin_class

    def register_instance(self, plugin_id: str, instance: AIPlugin) -> None:
        """注册插件实例"""
        self._plugins[plugin_id] = instance
        logger.info(f"Registered plugin instance: {plugin_id}")

    def get_plugin(self, plugin_id: str) -> AIPlugin:
        """获取已注册的插件实例"""
        if plugin_id not in self._plugins:
            raise KeyError(f"Plugin '{plugin_id}' not registered")
        return self._plugins[plugin_id]

    def list_plugins(self) -> list[PluginDescription]:
        """列出所有已注册的插件"""
        return [p.describe() for p in self._plugins.values()]

    def has_plugin(self, plugin_id: str) -> bool:
        return plugin_id in self._plugins

    def scan_directory(self, directory: str) -> int:
        """扫描目录自动发现并注册插件

        每个插件是一个子目录，包含 plugin.py 文件，
        其中定义了继承 AIPlugin 的类。
        """
        count = 0
        plugin_dir = Path(directory)
        if not plugin_dir.exists():
            return count

        for item in plugin_dir.iterdir():
            if not item.is_dir():
                continue
            plugin_file = item / "plugin.py"
            if not plugin_file.exists():
                continue
            try:
                # 动态导入
                module_name = f"plugins.{item.name}.plugin"
                spec = importlib.util.spec_from_file_location(module_name, plugin_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    # 查找 AIPlugin 子类
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (
                            isinstance(attr, type)
                            and issubclass(attr, AIPlugin)
                            and attr is not AIPlugin
                            and attr.plugin_id
                        ):
                            self.register(attr)
                            count += 1
            except Exception as e:
                logger.error(f"Failed to load plugin from {item}: {e}")

        return count


# ──────────────────────────────────────────────
# 装饰器
# ──────────────────────────────────────────────

_global_registry: Optional[PluginRegistry] = None


def get_global_registry() -> PluginRegistry:
    global _global_registry
    if _global_registry is None:
        _global_registry = PluginRegistry()
    return _global_registry


def register_plugin(cls: type[AIPlugin]) -> type[AIPlugin]:
    """装饰器：注册插件到全局注册表"""
    get_global_registry().register(cls)
    return cls
