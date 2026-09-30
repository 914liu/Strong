"""插件注册中心 — AI 插件专用注册表"""

from __future__ import annotations

from ..core.plugin import PluginRegistry

# AI 层使用全局的 PluginRegistry
ai_registry = PluginRegistry()
