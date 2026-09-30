"""混合驱动 — 结合 Draft Engine 和 GUI Controller

优先使用 Draft Engine 进行快速无头编辑操作，
仅在需要导出时启动 GUI Controller。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from ..core.config import AppConfig, DriverConfig
from ..core.exceptions import DriverError
from ..core.models import (
    CanvasConfig,
    ExportConfig,
    ExportResult,
    Segment,
    SubtitleBlock,
    TimeRange,
    Track,
    TrackType,
    VideoAsset,
    VideoProject,
)
from .draft_engine.crypto import DraftCrypto
from .draft_engine.materials import MaterialManager
from .draft_engine.reader import DraftReader
from .draft_engine.schema import DraftContentModel, SegmentModel, TimeRangeModel
from .draft_engine.segments import SegmentOperator
from .draft_engine.tracks import TrackManager
from .draft_engine.writer import DraftWriter
from .gui_controller.actions import ActionExecutor
from .gui_controller.export import ExportTrigger
from .gui_controller.finder import UIElementFinder
from .gui_controller.process import JianYingProcess
from .interface import DriverInterface

logger = logging.getLogger(__name__)


class HybridDriver(DriverInterface):
    """混合驱动实现

    策略：
    - 所有编辑操作通过 Draft Engine（快速、无头）
    - 导出操作通过 GUI Controller（必须启动剪映）
    """

    def __init__(self, config: Optional[DriverConfig] = None) -> None:
        self._config = config or DriverConfig()
        self._crypto = DraftCrypto()
        self._reader = DraftReader(self._crypto)
        self._writer = DraftWriter(self._crypto)

        # 当前操作的项目
        self._current_draft: Optional[DraftContentModel] = None
        self._current_project_dir: Optional[Path] = None
        self._current_project: Optional[VideoProject] = None

        # GUI 组件（延迟初始化）
        self._process: Optional[JianYingProcess] = None
        self._finder: Optional[UIElementFinder] = None
        self._executor: Optional[ActionExecutor] = None
        self._export_trigger: Optional[ExportTrigger] = None

        # 导出任务跟踪
        self._export_tasks: dict[str, dict] = {}

    def _ensure_gui(self) -> None:
        """延迟初始化 GUI 组件"""
        if self._process is None:
            self._process = JianYingProcess(self._config.jianying_path)
            self._finder = UIElementFinder()
            self._executor = ActionExecutor(self._finder)
            self._export_trigger = ExportTrigger(self._finder, self._executor)

    def _get_material_mgr(self) -> MaterialManager:
        if self._current_draft is None:
            raise DriverError("No project open")
        return MaterialManager(self._current_draft)

    def _get_track_mgr(self) -> TrackManager:
        if self._current_draft is None:
            raise DriverError("No project open")
        return TrackManager(self._current_draft)

    def _get_segment_op(self) -> SegmentOperator:
        if self._current_draft is None:
            raise DriverError("No project open")
        return SegmentOperator(self._current_draft)

    # ──────────────────────────────────────────
    # 项目管理
    # ──────────────────────────────────────────

    async def create_project(
        self, name: str, config: Optional[CanvasConfig] = None
    ) -> str:
        config = config or CanvasConfig.horizontal()
        draft_root = Path(self._config.draft_root)
        if not draft_root.exists():
            draft_root.mkdir(parents=True, exist_ok=True)

        project_dir = draft_root / f"{name}_{int(time.time())}"
        draft, meta = self._writer.create_new_project(
            project_dir, name, config.width, config.height
        )
        self._current_draft = draft
        self._current_project_dir = project_dir
        logger.info(f"Created project '{name}' at {project_dir}")
        return draft.id

    async def open_project(self, project_path: str) -> VideoProject:
        self._current_project_dir = Path(project_path)
        self._current_draft = self._reader.read(self._current_project_dir)
        self._current_project = self._reader.to_domain_model(self._current_draft)
        return self._current_project

    async def save_project(self, project: VideoProject) -> str:
        if self._current_project_dir is None:
            raise DriverError("No project directory set")
        self._writer.from_domain_model(project, self._current_project_dir)
        return str(self._current_project_dir)

    async def list_projects(self) -> list[dict]:
        draft_root = Path(self._config.draft_root)
        if not draft_root.exists():
            return []
        projects = []
        for item in draft_root.iterdir():
            if item.is_dir() and (item / "draft_content.json").exists():
                try:
                    meta = self._reader.read_meta(item)
                    projects.append({
                        "path": str(item),
                        "name": meta.draft_name,
                        "id": meta.draft_id,
                        "modified": meta.tm_draft_modified,
                    })
                except Exception:
                    projects.append({
                        "path": str(item),
                        "name": item.name,
                        "id": "",
                        "modified": 0,
                    })
        return projects

    # ──────────────────────────────────────────
    # 素材操作
    # ──────────────────────────────────────────

    async def import_media(
        self, project_id: str, file_paths: list[str]
    ) -> list[str]:
        mgr = self._get_material_mgr()
        ids = []
        for fp in file_paths:
            p = Path(fp)
            suffix = p.suffix.lower()
            if suffix in (".mp4", ".mov", ".avi", ".mkv", ".wmv", ".flv"):
                mid = mgr.add_video(path=str(p), name=p.stem)
            elif suffix in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
                mid = mgr.add_image(path=str(p), name=p.stem)
            elif suffix in (".mp3", ".wav", ".aac", ".flac", ".m4a"):
                mid = mgr.add_audio(path=str(p), name=p.stem)
            else:
                mid = mgr.add_video(path=str(p), name=p.stem)
            ids.append(mid)
        return ids

    async def add_to_timeline(
        self,
        project_id: str,
        material_id: str,
        track_type: TrackType,
        position_us: int = 0,
    ) -> str:
        mgr = self._get_material_mgr()
        track_mgr = self._get_track_mgr()
        seg_op = self._get_segment_op()

        # 查找或创建轨道
        tracks = track_mgr.get_tracks_by_type(track_type.value)
        if not tracks:
            track_id = track_mgr.add_track(track_type.value)
            track = track_mgr.get_track(track_id)
        else:
            track = tracks[0]

        # 获取素材时长
        material = mgr.find_material(material_id)
        duration = getattr(material, "duration", 0) if material else 0

        # 创建片段
        seg = seg_op.create_segment(
            material_id=material_id,
            source_start_us=0,
            source_duration_us=duration,
            target_start_us=position_us,
            target_duration_us=duration,
        )
        track_mgr.add_segment_to_track(track.id, seg)
        return seg.id

    # ──────────────────────────────────────────
    # 编辑操作
    # ──────────────────────────────────────────

    async def split_segment(
        self, project_id: str, segment_id: str, split_point_us: int
    ) -> tuple[str, str]:
        return self._get_segment_op().split_segment(segment_id, split_point_us)

    async def delete_segment(self, project_id: str, segment_id: str) -> None:
        self._get_segment_op().delete_segment(segment_id)

    async def trim_segment(
        self, project_id: str, segment_id: str, start_us: int, end_us: int
    ) -> None:
        self._get_segment_op().trim_segment(segment_id, start_us, end_us)

    async def set_speed(
        self, project_id: str, segment_id: str, speed: float
    ) -> None:
        self._get_segment_op().set_speed(segment_id, speed)

    async def set_volume(
        self, project_id: str, segment_id: str, volume: float
    ) -> None:
        self._get_segment_op().set_volume(segment_id, volume)

    async def add_text(
        self, project_id: str, subtitle: SubtitleBlock
    ) -> str:
        mgr = self._get_material_mgr()
        track_mgr = self._get_track_mgr()

        # 添加文本素材
        text_id = mgr.add_text(
            content=subtitle.text,
            font_name=subtitle.font_name,
            font_size=subtitle.font_size,
        )

        # 添加到文本轨道
        tracks = track_mgr.get_tracks_by_type("text")
        if not tracks:
            track_id = track_mgr.add_track("text")
            track = track_mgr.get_track(track_id)
        else:
            track = tracks[0]

        seg = SegmentModel(
            id=str(__import__("uuid").uuid4()).upper(),
            material_id=text_id,
            source_timerange=TimeRangeModel(start=0, duration=3_000_000),
            target_timerange=TimeRangeModel(
                start=subtitle.time_range.start_us,
                duration=subtitle.time_range.duration_us,
            ),
        )
        track_mgr.add_segment_to_track(track.id, seg)
        return seg.id

    async def add_effect(
        self, project_id: str, segment_id: str, effect_type: str, params: dict
    ) -> None:
        """为片段添加特效

        在 materials.effects 中创建 EffectMaterialModel，
        并将其 ID 关联到 segment.effects 列表。
        """
        import uuid

        mgr = self._get_material_mgr()
        track_mgr = self._get_track_mgr()

        # 创建特效素材
        effect_id = str(uuid.uuid4()).upper()
        effect_material = {
            "id": effect_id,
            "name": effect_type,
            "type": effect_type,
            "path": params.get("path", ""),
            "value": params.get("value", 1.0),
            "duration": params.get("duration", 0),
        }
        self._current_draft.materials.effects.append(effect_material)

        # 查找目标片段并关联特效
        track, seg = track_mgr.find_segment(segment_id)
        if track is not None and seg is not None:
            seg.effects.append({
                "effect_id": effect_id,
                "effect_type": effect_type,
                "params": params,
            })
            # 添加素材引用
            if effect_id not in seg.extra_material_refs:
                seg.extra_material_refs.append(effect_id)

        logger.info(f"Added effect '{effect_type}' ({effect_id}) to segment {segment_id}")

    async def add_transition(
        self,
        project_id: str,
        segment_id: str,
        transition_type: str,
        duration_us: int = 500_000,
    ) -> None:
        """为片段添加转场

        在 materials.transitions 中创建转场条目，
        并记录在片段上。
        """
        import uuid

        track_mgr = self._get_track_mgr()

        # 创建转场素材
        transition_id = str(uuid.uuid4()).upper()
        transition_material = {
            "id": transition_id,
            "type": transition_type,
            "duration": duration_us,
            "name": transition_type,
        }
        self._current_draft.materials.transitions.append(transition_material)

        # 查找目标片段并关联转场
        track, seg = track_mgr.find_segment(segment_id)
        if track is not None and seg is not None:
            seg.animations.append({
                "animation_id": transition_id,
                "type": "transition",
                "transition_type": transition_type,
                "duration_us": duration_us,
            })
            if transition_id not in seg.extra_material_refs:
                seg.extra_material_refs.append(transition_id)

        logger.info(f"Added transition '{transition_type}' ({transition_id}) to segment {segment_id}")

    # ──────────────────────────────────────────
    # 轨道操作
    # ──────────────────────────────────────────

    async def add_track(
        self, project_id: str, track_type: TrackType
    ) -> str:
        return self._get_track_mgr().add_track(track_type.value)

    async def delete_track(self, project_id: str, track_id: str) -> None:
        self._get_track_mgr().remove_track(track_id)

    # ──────────────────────────────────────────
    # 导出
    # ──────────────────────────────────────────

    async def export_video(
        self, project_id: str, config: ExportConfig
    ) -> ExportResult:
        import uuid

        # 1. 先保存草稿
        if self._current_project and self._current_project_dir:
            await self.save_project(self._current_project)

        task_id = str(uuid.uuid4()).upper()

        if not self._config.use_gui_export:
            self._export_tasks[task_id] = {
                "task_id": task_id,
                "status": "failed",
                "error": "GUI export disabled. Open project in JianYing manually.",
                "output_path": config.output_path,
            }
            return ExportResult(
                success=False,
                error_message="GUI export disabled. Open project in JianYing manually.",
            )

        # 2. 通过 GUI 触发导出
        self._ensure_gui()
        if not self._process.is_running():
            self._process.launch(wait=True)

        self._export_tasks[task_id] = {
            "task_id": task_id,
            "status": "exporting",
            "output_path": config.output_path,
        }

        result = await self._export_trigger.trigger_export(
            output_path=config.output_path,
            config=config,
            timeout=self._config.gui_timeout,
        )

        self._export_tasks[task_id] = {
            "task_id": task_id,
            "status": "completed" if result.success else "failed",
            "output_path": result.output_path,
            "file_size_bytes": result.file_size_bytes,
            "error": result.error_message,
        }

        return result

    async def get_export_status(self, task_id: str) -> dict:
        """查询导出任务状态"""
        if task_id in self._export_tasks:
            return self._export_tasks[task_id]
        return {"task_id": task_id, "status": "not_found"}
