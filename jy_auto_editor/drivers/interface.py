"""统一驱动接口 — 所有剪映操作的抽象"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..core.models import (
    CanvasConfig,
    ExportConfig,
    ExportResult,
    Segment,
    SubtitleBlock,
    Track,
    TrackType,
    VideoAsset,
    VideoProject,
)


class DriverInterface(ABC):
    """剪映操作的统一抽象

    所有驱动实现（DraftEngine / GUIController / HybridDriver）
    都必须实现此接口，上层业务代码不感知底层实现差异。
    """

    # ──────────────────────────────────────────
    # 项目管理
    # ──────────────────────────────────────────

    @abstractmethod
    async def create_project(
        self, name: str, config: Optional[CanvasConfig] = None
    ) -> str:
        """创建新项目，返回 project_id"""
        ...

    @abstractmethod
    async def open_project(self, project_path: str) -> VideoProject:
        """打开已有项目，返回 VideoProject"""
        ...

    @abstractmethod
    async def save_project(self, project: VideoProject) -> str:
        """保存项目，返回草稿路径"""
        ...

    @abstractmethod
    async def list_projects(self) -> list[dict]:
        """列出所有项目"""
        ...

    # ──────────────────────────────────────────
    # 素材操作
    # ──────────────────────────────────────────

    @abstractmethod
    async def import_media(
        self, project_id: str, file_paths: list[str]
    ) -> list[str]:
        """导入媒体文件，返回 material_id 列表"""
        ...

    @abstractmethod
    async def add_to_timeline(
        self,
        project_id: str,
        material_id: str,
        track_type: TrackType,
        position_us: int = 0,
    ) -> str:
        """将素材添加到时间线，返回 segment_id"""
        ...

    # ──────────────────────────────────────────
    # 编辑操作
    # ──────────────────────────────────────────

    @abstractmethod
    async def split_segment(
        self, project_id: str, segment_id: str, split_point_us: int
    ) -> tuple[str, str]:
        """在指定位置分割片段，返回两个新 segment_id"""
        ...

    @abstractmethod
    async def delete_segment(self, project_id: str, segment_id: str) -> None:
        """删除片段"""
        ...

    @abstractmethod
    async def trim_segment(
        self, project_id: str, segment_id: str, start_us: int, end_us: int
    ) -> None:
        """裁剪片段"""
        ...

    @abstractmethod
    async def set_speed(
        self, project_id: str, segment_id: str, speed: float
    ) -> None:
        """设置片段播放速度"""
        ...

    @abstractmethod
    async def set_volume(
        self, project_id: str, segment_id: str, volume: float
    ) -> None:
        """设置片段音量"""
        ...

    @abstractmethod
    async def add_text(
        self, project_id: str, subtitle: SubtitleBlock
    ) -> str:
        """添加文本/字幕，返回 segment_id"""
        ...

    @abstractmethod
    async def add_effect(
        self, project_id: str, segment_id: str, effect_type: str, params: dict
    ) -> None:
        """为片段添加特效"""
        ...

    @abstractmethod
    async def add_transition(
        self,
        project_id: str,
        segment_id: str,
        transition_type: str,
        duration_us: int = 500_000,
    ) -> None:
        """为片段添加转场"""
        ...

    # ──────────────────────────────────────────
    # 轨道操作
    # ──────────────────────────────────────────

    @abstractmethod
    async def add_track(
        self, project_id: str, track_type: TrackType
    ) -> str:
        """添加轨道，返回 track_id"""
        ...

    @abstractmethod
    async def delete_track(self, project_id: str, track_id: str) -> None:
        """删除轨道"""
        ...

    # ──────────────────────────────────────────
    # 导出
    # ──────────────────────────────────────────

    @abstractmethod
    async def export_video(
        self, project_id: str, config: ExportConfig
    ) -> ExportResult:
        """导出视频"""
        ...

    @abstractmethod
    async def get_export_status(self, task_id: str) -> dict:
        """查询导出状态"""
        ...
