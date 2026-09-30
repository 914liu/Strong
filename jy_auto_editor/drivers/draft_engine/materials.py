"""素材管理 — 视频/音频/文本素材 CRUD"""

from __future__ import annotations

import uuid
from typing import Optional

from .schema import (
    AudioMaterialModel,
    DraftContentModel,
    TextMaterialModel,
    VideoMaterialModel,
)


class MaterialManager:
    """素材管理器"""

    def __init__(self, draft: DraftContentModel) -> None:
        self._draft = draft

    # ──────────────────────────────────────────
    # 视频素材
    # ──────────────────────────────────────────

    def add_video(
        self,
        path: str,
        name: str = "",
        duration: int = 0,
        width: int = 0,
        height: int = 0,
        fps: float = 30.0,
    ) -> str:
        """添加视频素材，返回 material_id"""
        material_id = str(uuid.uuid4()).upper()
        self._draft.materials.videos.append(VideoMaterialModel(
            id=material_id,
            type="video",
            path=path,
            name=name,
            duration=duration,
            width=width,
            height=height,
            fps=fps,
        ))
        return material_id

    def add_image(
        self,
        path: str,
        name: str = "",
        width: int = 0,
        height: int = 0,
        duration: int = 3_000_000,     # 默认 3 秒
    ) -> str:
        """添加图片素材，返回 material_id"""
        material_id = str(uuid.uuid4()).upper()
        self._draft.materials.videos.append(VideoMaterialModel(
            id=material_id,
            type="photo",
            path=path,
            name=name,
            duration=duration,
            width=width,
            height=height,
        ))
        return material_id

    def get_video(self, material_id: str) -> Optional[VideoMaterialModel]:
        for v in self._draft.materials.videos:
            if v.id == material_id:
                return v
        return None

    def remove_video(self, material_id: str) -> bool:
        before = len(self._draft.materials.videos)
        self._draft.materials.videos = [
            v for v in self._draft.materials.videos if v.id != material_id
        ]
        return len(self._draft.materials.videos) < before

    # ──────────────────────────────────────────
    # 音频素材
    # ──────────────────────────────────────────

    def add_audio(
        self,
        path: str,
        name: str = "",
        duration: int = 0,
    ) -> str:
        """添加音频素材，返回 material_id"""
        material_id = str(uuid.uuid4()).upper()
        self._draft.materials.audios.append(AudioMaterialModel(
            id=material_id,
            path=path,
            name=name,
            duration=duration,
        ))
        return material_id

    def get_audio(self, material_id: str) -> Optional[AudioMaterialModel]:
        for a in self._draft.materials.audios:
            if a.id == material_id:
                return a
        return None

    # ──────────────────────────────────────────
    # 文本素材
    # ──────────────────────────────────────────

    def add_text(
        self,
        content: str,
        font_name: str = "",
        font_size: float = 8.0,
        alignment: int = 1,
    ) -> str:
        """添加文本素材，返回 material_id"""
        material_id = str(uuid.uuid4()).upper()
        self._draft.materials.texts.append(TextMaterialModel(
            id=material_id,
            content=content,
            base_content=content,
            font_name=font_name,
            font_size=font_size,
            alignment=alignment,
        ))
        return material_id

    def get_text(self, material_id: str) -> Optional[TextMaterialModel]:
        for t in self._draft.materials.texts:
            if t.id == material_id:
                return t
        return None

    # ──────────────────────────────────────────
    # 通用查询
    # ──────────────────────────────────────────

    def find_material(self, material_id: str) -> Optional[object]:
        """在素材集合中查找指定 ID 的素材"""
        for collection in [
            self._draft.materials.videos,
            self._draft.materials.audios,
            self._draft.materials.texts,
            self._draft.materials.effects,
        ]:
            for item in collection:
                if hasattr(item, "id") and item.id == material_id:
                    return item
        return None

    @property
    def all_material_ids(self) -> list[str]:
        """获取所有素材 ID"""
        ids = []
        for v in self._draft.materials.videos:
            ids.append(v.id)
        for a in self._draft.materials.audios:
            ids.append(a.id)
        for t in self._draft.materials.texts:
            ids.append(t.id)
        return ids
