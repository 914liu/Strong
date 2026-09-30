"""AI 插件基类 — 从 core.plugin 重新导出，并定义 AI 专用接口"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any

from ..core.plugin import AIPlugin, PluginContext, PluginDescription, register_plugin


class AIAnalysisPlugin(AIPlugin):
    """分析类 AI 插件基类

    用于 ASR、场景检测、高光提取等只产出分析结果的插件。
    """

    @abstractmethod
    async def analyze(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        """执行分析

        Returns:
            分析结果字典
        """
        ...

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        """默认实现：直接调用 analyze"""
        return await self.analyze(input_data, context)


class AIGenerationPlugin(AIPlugin):
    """生成类 AI 插件基类

    用于字幕生成、BGM 推荐、脚本生成等产出新内容的插件。
    """

    @abstractmethod
    async def generate(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        """执行生成

        Returns:
            生成结果字典
        """
        ...

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        """默认实现：直接调用 generate"""
        return await self.generate(input_data, context)


class AIEditPlugin(AIPlugin):
    """编辑类 AI 插件基类

    用于智能切片、长转短等直接修改时间线的插件。
    """

    @abstractmethod
    async def edit(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        """执行编辑

        Returns:
            编辑操作结果
        """
        ...

    async def process(self, input_data: dict[str, Any], context: PluginContext) -> dict[str, Any]:
        """默认实现：直接调用 edit"""
        return await self.edit(input_data, context)
