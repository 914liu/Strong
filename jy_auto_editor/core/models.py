"""领域模型 — 与剪映草稿格式解耦的中间表示 (IR)"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

MICROSECONDS_PER_SECOND = 1_000_000


def generate_id() -> str:
    """生成剪映兼容的 UUID（大写）"""
    return str(uuid.uuid4()).upper()


# ──────────────────────────────────────────────
# 枚举
# ──────────────────────────────────────────────

class TrackType(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    TEXT = "text"
    EFFECT = "effect"
    STICKER = "sticker"
    FILTER = "filter"
    TRANSITION = "transition"


class CanvasAspectRatio(str, Enum):
    RATIO_16_9 = "16:9"
    RATIO_9_16 = "9:16"
    RATIO_1_1 = "1:1"
    RATIO_4_3 = "4:3"
    RATIO_3_4 = "3:4"


# ──────────────────────────────────────────────
# 时间范围
# ──────────────────────────────────────────────

@dataclass
class TimeRange:
    """统一时间范围表示，内部存储微秒"""
    start_us: int
    duration_us: int

    @classmethod
    def from_seconds(cls, start: float, duration: float) -> TimeRange:
        return cls(
            start_us=int(start * MICROSECONDS_PER_SECOND),
            duration_us=int(duration * MICROSECONDS_PER_SECOND),
        )

    @classmethod
    def zero(cls) -> TimeRange:
        return cls(start_us=0, duration_us=0)

    @property
    def start_seconds(self) -> float:
        return self.start_us / MICROSECONDS_PER_SECOND

    @property
    def duration_seconds(self) -> float:
        return self.duration_us / MICROSECONDS_PER_SECOND

    @property
    def end_us(self) -> int:
        return self.start_us + self.duration_us

    def overlaps(self, other: TimeRange) -> bool:
        return self.start_us < other.end_us and other.start_us < self.end_us


# ──────────────────────────────────────────────
# 画布配置
# ──────────────────────────────────────────────

@dataclass
class CanvasConfig:
    width: int = 1920
    height: int = 1080
    ratio: str = "16:9"
    fps: int = 30

    @classmethod
    def horizontal(cls) -> CanvasConfig:
        return cls(width=1920, height=1080, ratio="16:9")

    @classmethod
    def vertical(cls) -> CanvasConfig:
        return cls(width=1080, height=1920, ratio="9:16")

    @classmethod
    def square(cls) -> CanvasConfig:
        return cls(width=1080, height=1080, ratio="1:1")


# ──────────────────────────────────────────────
# 素材
# ──────────────────────────────────────────────

@dataclass
class MediaInfo:
    """媒体文件探测信息"""
    path: str
    duration_us: int = 0
    width: int = 0
    height: int = 0
    fps: float = 30.0
    has_audio: bool = True
    codec: str = ""
    bitrate: int = 0


@dataclass
class VideoAsset:
    """视频/图片素材"""
    asset_id: str = field(default_factory=generate_id)
    path: str = ""
    media_type: str = "video"          # video | image
    media_info: Optional[MediaInfo] = None
    name: str = ""


@dataclass
class AudioAsset:
    """音频素材"""
    asset_id: str = field(default_factory=generate_id)
    path: str = ""
    name: str = ""
    duration_us: int = 0


@dataclass
class SubtitleBlock:
    """字幕块"""
    text: str = ""
    time_range: TimeRange = field(default_factory=TimeRange.zero)
    font_name: str = "系统默认"
    font_size: float = 8.0
    font_color: str = "#FFFFFF"
    background_color: str = ""
    alignment: str = "center"          # left | center | right
    position_y: float = 0.85           # 相对位置 0.0~1.0


@dataclass
class Effect:
    """特效"""
    effect_id: str = field(default_factory=generate_id)
    effect_type: str = ""              # filter | animation | transition
    effect_name: str = ""
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Transition:
    """转场"""
    transition_id: str = field(default_factory=generate_id)
    transition_type: str = ""
    duration_us: int = 500_000         # 默认 0.5 秒


# ──────────────────────────────────────────────
# 片段 & 轨道
# ──────────────────────────────────────────────

@dataclass
class Segment:
    """时间线上的一个片段"""
    segment_id: str = field(default_factory=generate_id)
    material_id: str = ""
    source_range: TimeRange = field(default_factory=TimeRange.zero)
    target_range: TimeRange = field(default_factory=TimeRange.zero)
    speed: float = 1.0
    volume: float = 1.0
    effects: list[Effect] = field(default_factory=list)
    transitions: list[Transition] = field(default_factory=list)
    # 变换属性
    alpha: float = 1.0
    rotation: float = 0.0
    scale_x: float = 1.0
    scale_y: float = 1.0
    position_x: float = 0.0
    position_y: float = 0.0


@dataclass
class Track:
    """轨道"""
    track_id: str = field(default_factory=generate_id)
    track_type: TrackType = TrackType.VIDEO
    segments: list[Segment] = field(default_factory=list)
    render_index: int = 0
    visible: bool = True
    muted: bool = False

    def add_segment(self, segment: Segment) -> None:
        self.segments.append(segment)

    @property
    def total_duration_us(self) -> int:
        if not self.segments:
            return 0
        return max(seg.target_range.end_us for seg in self.segments)


# ──────────────────────────────────────────────
# 时间线
# ──────────────────────────────────────────────

@dataclass
class Timeline:
    """时间线"""
    tracks: list[Track] = field(default_factory=list)
    canvas_config: CanvasConfig = field(default_factory=CanvasConfig.horizontal)

    @property
    def total_duration_us(self) -> int:
        if not self.tracks:
            return 0
        return max(track.total_duration_us for track in self.tracks)

    def get_tracks_by_type(self, track_type: TrackType) -> list[Track]:
        return [t for t in self.tracks if t.track_type == track_type]

    def add_track(self, track: Track) -> None:
        track.render_index = len(self.tracks)
        self.tracks.append(track)


# ──────────────────────────────────────────────
# 项目
# ──────────────────────────────────────────────

@dataclass
class ProjectMetadata:
    """项目元数据"""
    name: str = ""
    description: str = ""
    author: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class VideoProject:
    """视频项目 — 顶层领域对象"""
    project_id: str = field(default_factory=generate_id)
    name: str = "未命名项目"
    source_videos: list[VideoAsset] = field(default_factory=list)
    source_audios: list[AudioAsset] = field(default_factory=list)
    subtitles: list[SubtitleBlock] = field(default_factory=list)
    timeline: Timeline = field(default_factory=Timeline)
    metadata: ProjectMetadata = field(default_factory=ProjectMetadata)

    @property
    def total_duration_us(self) -> int:
        return self.timeline.total_duration_us

    @property
    def total_duration_seconds(self) -> float:
        return self.total_duration_us / MICROSECONDS_PER_SECOND


# ──────────────────────────────────────────────
# Pipeline 相关模型
# ──────────────────────────────────────────────

@dataclass
class ProjectInput:
    """Pipeline 输入"""
    video_paths: list[str] = field(default_factory=list)
    audio_paths: list[str] = field(default_factory=list)
    image_paths: list[str] = field(default_factory=list)
    canvas_config: CanvasConfig = field(default_factory=CanvasConfig.horizontal)
    pipeline_template: str = "default"
    extra_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalysisResult:
    """分析阶段产出"""
    transcript: str = ""
    subtitles: list[SubtitleBlock] = field(default_factory=list)
    scene_boundaries: list[TimeRange] = field(default_factory=list)
    highlights: list[dict[str, Any]] = field(default_factory=list)
    content_tags: list[str] = field(default_factory=list)
    sentiment_curve: list[dict[str, Any]] = field(default_factory=list)
    language: str = "zh"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class EditDecision:
    """单条编辑决策"""
    action: str = ""                   # cut | trim | split | add_text | add_bgm | add_effect
    target_track: TrackType = TrackType.VIDEO
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class EditDecisionList:
    """编辑决策列表 (EDL)"""
    decisions: list[EditDecision] = field(default_factory=list)
    source_project: Optional[VideoProject] = None


@dataclass
class ExportConfig:
    """导出配置"""
    output_path: str = ""
    format: str = "mp4"
    resolution: str = "1920x1080"
    fps: int = 30
    bitrate: str = "8000k"
    codec: str = "h264"


@dataclass
class ExportResult:
    """导出结果"""
    success: bool = False
    output_path: str = ""
    file_size_bytes: int = 0
    duration_us: int = 0
    error_message: str = ""


# ──────────────────────────────────────────────
# Pipeline 上下文
# ──────────────────────────────────────────────

@dataclass
class PipelineContext:
    """贯穿整个 Pipeline 的上下文对象"""
    project: VideoProject = field(default_factory=VideoProject)
    input: ProjectInput = field(default_factory=ProjectInput)
    analysis: Optional[AnalysisResult] = None
    edl: Optional[EditDecisionList] = None
    export_result: Optional[ExportResult] = None
    temp_dir: str = ""
    cache_dir: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
