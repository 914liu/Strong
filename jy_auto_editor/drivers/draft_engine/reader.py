"""草稿读取器 — 读取并解析 draft_content.json"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from ...core.exceptions import DraftError
from ...core.models import (
    AudioAsset,
    CanvasConfig,
    Segment,
    SubtitleBlock,
    TimeRange,
    Track,
    TrackType,
    VideoAsset,
    VideoProject,
)
from .crypto import DraftCrypto
from .schema import DraftContentModel, DraftMetaInfoModel

logger = logging.getLogger(__name__)


class DraftReader:
    """草稿读取器"""

    def __init__(self, crypto: Optional[DraftCrypto] = None) -> None:
        self._crypto = crypto or DraftCrypto()

    def read(self, project_dir: str | Path) -> DraftContentModel:
        """读取并解析 draft_content.json

        Args:
            project_dir: 剪映项目文件夹路径

        Returns:
            解析后的 DraftContentModel
        """
        project_dir = Path(project_dir)
        draft_path = project_dir / "draft_content.json"

        if not draft_path.exists():
            raise DraftError(f"Draft file not found: {draft_path}")

        # 透明处理加密
        draft_path, was_encrypted = self._crypto.ensure_decrypted(draft_path)

        try:
            with open(draft_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return DraftContentModel.model_validate(raw)
        except json.JSONDecodeError as e:
            raise DraftError(f"Invalid JSON in draft: {e}")
        except Exception as e:
            # 如果是我们解密后产生的错误，尝试恢复
            if was_encrypted:
                self._crypto.restore_encrypted_backup(
                    project_dir / "draft_content.json"
                )
            raise DraftError(f"Failed to read draft: {e}")

    def read_meta(self, project_dir: str | Path) -> DraftMetaInfoModel:
        """读取 draft_meta_info.json"""
        meta_path = Path(project_dir) / "draft_meta_info.json"
        if not meta_path.exists():
            raise DraftError(f"Meta file not found: {meta_path}")

        with open(meta_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return DraftMetaInfoModel.model_validate(raw)

    def to_domain_model(self, draft: DraftContentModel) -> VideoProject:
        """将草稿模型转换为领域模型 (VideoProject)"""
        project = VideoProject(
            project_id=draft.id,
            name=draft.name,
        )

        # 画布配置
        project.timeline.canvas_config = CanvasConfig(
            width=draft.canvas_config.width,
            height=draft.canvas_config.height,
            ratio=draft.canvas_config.ratio,
        )

        # 转换素材
        for vm in draft.materials.videos:
            project.source_videos.append(VideoAsset(
                asset_id=vm.id,
                path=vm.path,
                media_type=vm.type,
                name=vm.name,
            ))

        for am in draft.materials.audios:
            project.source_audios.append(AudioAsset(
                asset_id=am.id,
                path=am.path,
                name=am.name,
                duration_us=am.duration,
            ))

        # 转换轨道和片段
        for tm in draft.tracks:
            track_type = self._parse_track_type(tm.type)
            track = Track(
                track_id=tm.id,
                track_type=track_type,
                render_index=tm.render_index,
            )
            for sm in tm.segments:
                segment = Segment(
                    segment_id=sm.id,
                    material_id=sm.material_id,
                    source_range=TimeRange(
                        start_us=sm.source_timerange.start,
                        duration_us=sm.source_timerange.duration,
                    ),
                    target_range=TimeRange(
                        start_us=sm.target_timerange.start,
                        duration_us=sm.target_timerange.duration,
                    ),
                    speed=sm.speed,
                    volume=sm.volume,
                    alpha=sm.clip.alpha,
                    rotation=sm.clip.rotation,
                    scale_x=sm.clip.scale.width,
                    scale_y=sm.clip.scale.height,
                    position_x=sm.clip.transform.x,
                    position_y=sm.clip.transform.y,
                )
                track.segments.append(segment)
            project.timeline.add_track(track)

        # 转换文本素材为字幕
        for text_m in draft.materials.texts:
            subtitle = SubtitleBlock(
                text=text_m.base_content or text_m.content,
                font_name=text_m.font_name,
                font_size=text_m.font_size,
            )
            project.subtitles.append(subtitle)

        return project

    @staticmethod
    def _parse_track_type(type_str: str) -> TrackType:
        mapping = {
            "video": TrackType.VIDEO,
            "audio": TrackType.AUDIO,
            "text": TrackType.TEXT,
            "effect": TrackType.EFFECT,
            "sticker": TrackType.STICKER,
        }
        return mapping.get(type_str.lower(), TrackType.VIDEO)

    def read_project(self, project_dir: str | Path) -> VideoProject:
        """一步完成：读取草稿 → 转换为领域模型"""
        draft = self.read(project_dir)
        return self.to_domain_model(draft)
