"""草稿写入器 — 修改并保存 draft_content.json"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Optional

from ...core.exceptions import DraftError
from ...core.models import VideoProject
from .crypto import DraftCrypto
from .schema import (
    CanvasConfigModel,
    ClipTransformModel,
    DraftContentModel,
    DraftMetaInfoModel,
    MaterialsModel,
    PositionModel,
    SegmentModel,
    SizeModel,
    TextMaterialModel,
    TimeRangeModel,
    TrackModel,
    VideoMaterialModel,
)

logger = logging.getLogger(__name__)


class DraftWriter:
    """草稿写入器"""

    def __init__(self, crypto: Optional[DraftCrypto] = None) -> None:
        self._crypto = crypto or DraftCrypto()

    def save(
        self,
        draft: DraftContentModel,
        project_dir: str | Path,
        re_encrypt: bool = True,
    ) -> Path:
        """保存 draft_content.json

        Args:
            draft: 草稿模型
            project_dir: 项目目录
            re_encrypt: 如果原文件是加密的，操作后是否重新加密

        Returns:
            保存后的文件路径
        """
        project_dir = Path(project_dir)
        draft_path = project_dir / "draft_content.json"

        # 检测原始加密状态
        was_encrypted = self._crypto.is_encrypted(draft_path) if draft_path.exists() else False

        try:
            # 写入 JSON
            data = draft.model_dump(exclude_none=True, exclude_defaults=False)
            with open(draft_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # 重新加密
            if was_encrypted and re_encrypt:
                self._crypto.encrypt(draft_path)

            logger.info(f"Saved draft to {draft_path}")
            return draft_path

        except Exception as e:
            raise DraftError(f"Failed to save draft: {e}")

    def save_meta(self, meta: DraftMetaInfoModel, project_dir: str | Path) -> Path:
        """保存 draft_meta_info.json"""
        meta_path = Path(project_dir) / "draft_meta_info.json"
        data = meta.model_dump(exclude_none=True, exclude_defaults=False)
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return meta_path

    def create_new_project(
        self,
        project_dir: str | Path,
        name: str = "未命名项目",
        width: int = 1920,
        height: int = 1080,
    ) -> tuple[DraftContentModel, DraftMetaInfoModel]:
        """创建全新的空白项目

        Args:
            project_dir: 项目目录（会自动创建）
            name: 项目名称
            width: 画布宽度
            height: 画布高度

        Returns:
            (DraftContentModel, DraftMetaInfoModel)
        """
        project_dir = Path(project_dir)
        project_dir.mkdir(parents=True, exist_ok=True)

        now_ts = int(time.time())
        import uuid
        project_id = str(uuid.uuid4()).upper()

        # 创建 draft_content.json
        draft = DraftContentModel(
            id=project_id,
            name=name,
            type="draft",
            canvas_config=CanvasConfigModel(
                width=width,
                height=height,
                ratio=f"{width}:{height}" if width != height else "1:1",
            ),
            create_time=now_ts,
            update_time=now_ts,
            duration=0,
            materials=MaterialsModel(),
            tracks=[],
            version=1,
        )

        # 创建 draft_meta_info.json
        meta = DraftMetaInfoModel(
            draft_id=project_id,
            draft_name=name,
            draft_root_path=str(project_dir),
            tm_draft_create=now_ts,
            tm_draft_modified=now_ts,
            draft_fold_path=str(project_dir),
        )

        self.save(draft, project_dir, re_encrypt=False)
        self.save_meta(meta, project_dir)

        logger.info(f"Created new project: {name} at {project_dir}")
        return draft, meta

    def from_domain_model(
        self,
        project: VideoProject,
        project_dir: str | Path,
    ) -> Path:
        """将领域模型转换回草稿模型并保存"""
        draft = self._domain_to_draft(project)
        return self.save(draft, project_dir)

    def _domain_to_draft(self, project: VideoProject) -> DraftContentModel:
        """将 VideoProject 转换为 DraftContentModel"""
        import uuid

        draft = DraftContentModel(
            id=project.project_id,
            name=project.name,
            canvas_config=CanvasConfigModel(
                width=project.timeline.canvas_config.width,
                height=project.timeline.canvas_config.height,
                ratio=project.timeline.canvas_config.ratio,
            ),
            duration=project.total_duration_us,
            materials=MaterialsModel(),
        )

        # 转换视频素材
        for va in project.source_videos:
            draft.materials.videos.append(VideoMaterialModel(
                id=va.asset_id,
                path=va.path,
                name=va.name,
                type=va.media_type,
            ))

        # 转换轨道
        for track in project.timeline.tracks:
            track_model = TrackModel(
                id=track.track_id,
                type=track.track_type.value,
                render_index=track.render_index,
            )
            for seg in track.segments:
                seg_model = SegmentModel(
                    id=seg.segment_id,
                    material_id=seg.material_id,
                    source_timerange=TimeRangeModel(
                        start=seg.source_range.start_us,
                        duration=seg.source_range.duration_us,
                    ),
                    target_timerange=TimeRangeModel(
                        start=seg.target_range.start_us,
                        duration=seg.target_range.duration_us,
                    ),
                    clip=ClipTransformModel(
                        alpha=seg.alpha,
                        rotation=seg.rotation,
                        scale=SizeModel(width=seg.scale_x, height=seg.scale_y),
                        transform=PositionModel(x=seg.position_x, y=seg.position_y),
                    ),
                    speed=seg.speed,
                    volume=seg.volume,
                )
                track_model.segments.append(seg_model)
            draft.tracks.append(track_model)

        # 转换字幕
        for sub in project.subtitles:
            draft.materials.texts.append(TextMaterialModel(
                id=str(uuid.uuid4()).upper(),
                content=sub.text,
                base_content=sub.text,
                font_name=sub.font_name,
                font_size=sub.font_size,
                alignment={"left": 0, "center": 1, "right": 2}.get(sub.alignment, 1),
            ))

        return draft
