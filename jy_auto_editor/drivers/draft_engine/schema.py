"""draft_content.json 的 Pydantic 数据模型

完整映射剪映草稿 JSON 结构，用于类型安全的读写操作。
"""

from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# 基础类型
# ──────────────────────────────────────────────

class TimeRangeModel(BaseModel):
    """时间范围（微秒）"""
    start: int = 0
    duration: int = 0


class PositionModel(BaseModel):
    """位置"""
    x: float = 0.0
    y: float = 0.0


class SizeModel(BaseModel):
    """尺寸"""
    width: float = 0.0
    height: float = 0.0


class ColorModel(BaseModel):
    """颜色"""
    r: float = 1.0
    g: float = 1.0
    b: float = 1.0
    a: float = 1.0


# ──────────────────────────────────────────────
# 画布配置
# ──────────────────────────────────────────────

class CanvasConfigModel(BaseModel):
    """画布配置"""
    width: int = 1920
    height: int = 1080
    ratio: str = "16:9"


# ──────────────────────────────────────────────
# 素材模型
# ──────────────────────────────────────────────

class VideoMaterialModel(BaseModel):
    """视频/图片素材"""
    id: str = ""
    type: str = "video"                # video | photo
    path: str = ""
    name: str = ""
    duration: int = 0                  # 微秒
    width: int = 0
    height: int = 0
    fps: float = 30.0
    crop: dict[str, Any] = Field(default_factory=dict)
    extra_type_option: int = 0
    material_url: str = ""
    crop_ratio: str = ""
    video_algorithm: dict[str, Any] = Field(default_factory=dict)


class AudioMaterialModel(BaseModel):
    """音频素材"""
    id: str = ""
    type: str = "music"
    path: str = ""
    name: str = ""
    duration: int = 0                  # 微秒
    query: str = ""
    search_id: str = ""
    effect_id: str = ""
    tone_category_id: str = ""
    tone_category_name: str = ""
    effect_category: str = ""
    source_from: str = ""
    platform: str = ""
    text_id: str = ""
    tts_id: str = ""


class TextMaterialModel(BaseModel):
    """文本/字幕素材"""
    id: str = ""
    content: str = ""                  # 文本内容（可能含 HTML 标签）
    font_path: str = ""
    font_name: str = ""
    font_size: float = 8.0
    font_color: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0, 1.0])
    alignment: int = 1                 # 0=left, 1=center, 2=right
    line_spacing: float = 0.02
    background_color: list[float] = Field(default_factory=list)
    background_alpha: float = 1.0
    bold_width: float = 0.0
    has_shadow: bool = False
    shadow_color: list[float] = Field(default_factory=list)
    shadow_point: PositionModel = Field(default_factory=PositionModel)
    underline: bool = False
    strike_through: bool = False
    italic: float = 0.0
    letter_spacing: float = 0.0
    base_content: str = ""             # 原始文本（不含样式）


class EffectMaterialModel(BaseModel):
    """特效素材"""
    id: str = ""
    name: str = ""
    path: str = ""
    type: str = ""
    value: float = 1.0
    duration: int = 0
    source_platform: str = ""


class StickerMaterialModel(BaseModel):
    """贴纸素材"""
    id: str = ""
    name: str = ""
    path: str = ""
    width: float = 0.0
    height: float = 0.0


# ──────────────────────────────────────────────
# 片段模型
# ──────────────────────────────────────────────

class ClipTransformModel(BaseModel):
    """片段变换"""
    rotation: float = 0.0
    scale: SizeModel = Field(default_factory=lambda: SizeModel(width=1.0, height=1.0))
    transform: PositionModel = Field(default_factory=PositionModel)
    alpha: float = 1.0


class SegmentModel(BaseModel):
    """时间线片段"""
    id: str = ""
    material_id: str = ""
    target_timerange: TimeRangeModel = Field(default_factory=TimeRangeModel)
    source_timerange: TimeRangeModel = Field(default_factory=TimeRangeModel)
    clip: ClipTransformModel = Field(default_factory=ClipTransformModel)
    speed: float = 1.0
    volume: float = 1.0
    extra_material_refs: list[str] = Field(default_factory=list)
    render_index: int = 0
    responsive_layout: dict[str, Any] = Field(default_factory=dict)
    animations: list[dict[str, Any]] = Field(default_factory=list)
    common_keyframes: list[dict[str, Any]] = Field(default_factory=list)
    effects: list[dict[str, Any]] = Field(default_factory=list)
    flags: list[str] = Field(default_factory=list)
    template_id: str = ""
    template_scene: str = "default"


# ──────────────────────────────────────────────
# 轨道模型
# ──────────────────────────────────────────────

class TrackModel(BaseModel):
    """轨道"""
    id: str = ""
    type: str = "video"                # video | audio | text | effect | sticker
    segments: list[SegmentModel] = Field(default_factory=list)
    render_index: int = 0
    attribute: int = 0
    flag: int = 0


# ──────────────────────────────────────────────
# 素材集合
# ──────────────────────────────────────────────

class MaterialsModel(BaseModel):
    """所有素材的集合"""
    videos: list[VideoMaterialModel] = Field(default_factory=list)
    audios: list[AudioMaterialModel] = Field(default_factory=list)
    texts: list[TextMaterialModel] = Field(default_factory=list)
    effects: list[EffectMaterialModel] = Field(default_factory=list)
    stickers: list[StickerMaterialModel] = Field(default_factory=list)
    sounds: list[dict[str, Any]] = Field(default_factory=list)
    fonts: list[dict[str, Any]] = Field(default_factory=list)
    animations: list[dict[str, Any]] = Field(default_factory=list)
    transitions: list[dict[str, Any]] = Field(default_factory=list)
    filters: list[dict[str, Any]] = Field(default_factory=list)
    color_curves: list[dict[str, Any]] = Field(default_factory=list)
    canvases: list[dict[str, Any]] = Field(default_factory=list)
    material_animations: list[dict[str, Any]] = Field(default_factory=list)
    material_colors: list[dict[str, Any]] = Field(default_factory=list)
    hotspots: list[dict[str, Any]] = Field(default_factory=list)
    images: list[dict[str, Any]] = Field(default_factory=list)
    image_animations: list[dict[str, Any]] = Field(default_factory=list)
    vfxs: list[dict[str, Any]] = Field(default_factory=list)
    effects_v2: list[dict[str, Any]] = Field(default_factory=list)


# ──────────────────────────────────────────────
# 顶层草稿模型
# ──────────────────────────────────────────────

class DraftContentModel(BaseModel):
    """draft_content.json 顶层模型"""
    id: str = ""
    name: str = ""
    type: str = "draft"
    canvas_config: CanvasConfigModel = Field(default_factory=CanvasConfigModel)
    config: dict[str, Any] = Field(default_factory=dict)
    create_time: int = 0
    duration: int = 0                  # 微秒
    update_time: int = 0
    materials: MaterialsModel = Field(default_factory=MaterialsModel)
    tracks: list[TrackModel] = Field(default_factory=list)
    keyframe_graph_list: list[dict[str, Any]] = Field(default_factory=list)
    last_nonzero_segment_id: str = ""
    keyframes: dict[str, Any] = Field(default_factory=dict)
    platform: dict[str, Any] = Field(default_factory=dict)
    version: int = 0


class DraftMetaInfoModel(BaseModel):
    """draft_meta_info.json 模型"""
    draft_id: str = ""
    draft_name: str = ""
    draft_root_path: str = ""
    tm_draft_create: int = 0
    tm_draft_modified: int = 0
    tm_duration: int = 0
    draft_fold_path: str = ""
    draft_cloud_last_action_download: bool = False
    draft_is_ai_shorts: bool = False
    draft_is_article_video_draft: bool = False
    draft_is_from_deeplink: str = "false"
    draft_is_invisible: bool = False
    draft_materials_copied: bool = False
    draft_new_version: str = ""
    draft_removable_storage_device: str = ""
    draft_root_path_v2: str = ""
    draft_segment_extra_info: list[dict[str, Any]] = Field(default_factory=list)
    draft_timeline_materials_size_: int = 0
