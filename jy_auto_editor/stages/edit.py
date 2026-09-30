"""Edit Stage — 编辑执行阶段

职责：
1. 根据分析结果 (AnalysisResult) 生成编辑决策列表 (EDL)
2. 将 EDL 应用到项目时间线，构建完整的 Track / Segment 结构
3. 支持的编辑操作：
   - cut       → 智能切片（基于高光 / 场景边界裁剪视频）
   - add_text  → 字幕轨生成
   - add_bgm   → 背景音乐轨
   - add_effect → 特效 / 转场
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.events import Event, EventType, get_event_bus
from ..core.models import (
    AudioAsset,
    EditDecision,
    EditDecisionList,
    Effect,
    PipelineContext,
    Segment,
    SubtitleBlock,
    TimeRange,
    Track,
    TrackType,
    Transition,
    VideoAsset,
    generate_id,
)
from ..core.pipeline import Stage

logger = logging.getLogger(__name__)


class EditStage(Stage):
    """编辑执行阶段

    根据分析结果和编辑策略，生成 EDL 并构建完整的时间线。
    """

    name = "edit"
    dependencies = ["analyze"]
    can_skip = False
    timeout = 300

    async def validate(self, context: PipelineContext) -> bool:
        return context.analysis is not None

    async def execute(self, context: PipelineContext) -> dict[str, Any]:
        analysis = context.analysis
        if analysis is None:
            return {"status": "skipped", "reason": "no analysis"}

        event_bus = get_event_bus()
        edl = EditDecisionList(source_project=context.project)

        # ── Step 1: 生成编辑决策 ─────────────────────
        self._build_video_decisions(context, edl)
        self._build_subtitle_decisions(context, edl)
        self._build_bgm_decisions(context, edl)
        self._build_effect_decisions(context, edl)

        logger.info(f"EDL generated: {len(edl.decisions)} decisions")

        await event_bus.emit_async(Event(
            type=EventType.STAGE_PROGRESS,
            data={"stage": self.name, "progress": 0.3, "phase": "edl_built"},
            source=self.name,
        ))

        # ── Step 2: 应用 EDL 到时间线 ────────────────
        applied = 0
        failed = 0
        for decision in edl.decisions:
            try:
                self._apply_decision(context, decision)
                applied += 1
            except Exception as e:
                logger.error(f"Failed to apply decision '{decision.action}': {e}")
                failed += 1

        await event_bus.emit_async(Event(
            type=EventType.STAGE_PROGRESS,
            data={"stage": self.name, "progress": 0.9, "phase": "edl_applied"},
            source=self.name,
        ))

        context.edl = edl

        # ── Step 3: 计算时间线总时长 ─────────────────
        total_duration = context.project.timeline.total_duration_us
        logger.info(
            f"EditStage complete: {applied}/{len(edl.decisions)} decisions applied, "
            f"timeline duration={total_duration / 1e6:.1f}s"
        )

        return {
            "total_decisions": len(edl.decisions),
            "applied": applied,
            "failed": failed,
            "timeline_duration_us": total_duration,
            "track_count": len(context.project.timeline.tracks),
        }

    # ══════════════════════════════════════════════════
    # EDL 决策生成
    # ══════════════════════════════════════════════════

    def _build_video_decisions(self, context: PipelineContext, edl: EditDecisionList) -> None:
        """根据分析结果生成视频切片决策

        策略优先级：
        1. 有高光片段 → 按高光裁剪
        2. 有场景边界 + target_duration → 智能裁剪到目标时长
        3. 都没有 → 使用完整视频
        """
        analysis = context.analysis
        assert analysis is not None

        target_duration_s = context.input.extra_params.get("target_duration")
        target_duration_us = int(target_duration_s * 1_000_000) if target_duration_s else None
        platform = context.input.extra_params.get("platform", "")

        if analysis.highlights:
            # ── 高光模式：每个高光片段作为一个 cut 决策 ──
            for h in analysis.highlights:
                start_s = h.get("start_second", 0)
                end_s = h.get("end_second", 0)
                if end_s <= start_s:
                    continue
                edl.decisions.append(EditDecision(
                    action="cut",
                    target_track=TrackType.VIDEO,
                    params={
                        "source_start_us": int(start_s * 1_000_000),
                        "source_end_us": int(end_s * 1_000_000),
                        "title": h.get("title", ""),
                        "score": h.get("score", 0),
                    },
                ))
            logger.info(f"Built {len(analysis.highlights)} highlight-based cut decisions")

        elif target_duration_us and analysis.scene_boundaries:
            # ── 智能裁剪模式：选择场景组合接近目标时长 ──
            segments = self._select_scenes_for_duration(
                analysis.scene_boundaries,
                target_duration_us,
            )
            for seg_range in segments:
                edl.decisions.append(EditDecision(
                    action="cut",
                    target_track=TrackType.VIDEO,
                    params={
                        "source_start_us": seg_range.start_us,
                        "source_end_us": seg_range.end_us,
                    },
                ))
            logger.info(f"Built {len(segments)} smart-cut decisions for target {target_duration_s}s")

        else:
            # ── 完整模式：使用整个视频 ──────────────
            if context.project.source_videos:
                video = context.project.source_videos[0]
                duration_us = 0
                if video.media_info:
                    duration_us = video.media_info.duration_us
                if duration_us > 0:
                    edl.decisions.append(EditDecision(
                        action="cut",
                        target_track=TrackType.VIDEO,
                        params={
                            "source_start_us": 0,
                            "source_end_us": duration_us,
                        },
                    ))

    def _build_subtitle_decisions(self, context: PipelineContext, edl: EditDecisionList) -> None:
        """根据 ASR 字幕生成 add_text 决策"""
        analysis = context.analysis
        assert analysis is not None

        for sub in analysis.subtitles:
            if isinstance(sub, SubtitleBlock):
                text = sub.text
                start_us = sub.time_range.start_us
                duration_us = sub.time_range.duration_us
            elif isinstance(sub, dict):
                text = sub.get("text", "")
                start_us = sub.get("start_us", 0)
                end_us = sub.get("end_us", 0)
                duration_us = end_us - start_us
            else:
                continue

            if not text.strip():
                continue

            edl.decisions.append(EditDecision(
                action="add_text",
                target_track=TrackType.TEXT,
                params={
                    "text": text,
                    "start_us": start_us,
                    "duration_us": duration_us,
                    "font_name": context.input.extra_params.get("font_name", "系统默认"),
                    "font_size": context.input.extra_params.get("font_size", 8.0),
                    "font_color": context.input.extra_params.get("font_color", "#FFFFFF"),
                    "position_y": context.input.extra_params.get("subtitle_position_y", 0.85),
                },
            ))

    def _build_bgm_decisions(self, context: PipelineContext, edl: EditDecisionList) -> None:
        """如果有 BGM 素材，生成 add_bgm 决策"""
        bgm_path = context.input.extra_params.get("bgm_path")
        if bgm_path:
            edl.decisions.append(EditDecision(
                action="add_bgm",
                target_track=TrackType.AUDIO,
                params={
                    "bgm_path": bgm_path,
                    "volume": context.input.extra_params.get("bgm_volume", 0.3),
                    "fade_in": context.input.extra_params.get("bgm_fade_in", 1.0),
                    "fade_out": context.input.extra_params.get("bgm_fade_out", 2.0),
                },
            ))
        elif context.project.source_audios:
            # 使用输入提供的音频素材作为 BGM
            for audio in context.project.source_audios:
                edl.decisions.append(EditDecision(
                    action="add_bgm",
                    target_track=TrackType.AUDIO,
                    params={
                        "bgm_path": audio.path,
                        "volume": 0.5,
                        "fade_in": 1.0,
                        "fade_out": 2.0,
                    },
                ))

    def _build_effect_decisions(self, context: PipelineContext, edl: EditDecisionList) -> None:
        """根据场景边界生成转场效果决策"""
        analysis = context.analysis
        assert analysis is not None

        # 如果启用了转场效果，在视频片段之间添加转场
        enable_transitions = context.input.extra_params.get("enable_transitions", False)
        if enable_transitions and len(edl.decisions) > 1:
            video_decisions = [
                d for d in edl.decisions
                if d.action == "cut" and d.target_track == TrackType.VIDEO
            ]
            # 在相邻视频片段之间添加转场
            for i in range(len(video_decisions) - 1):
                edl.decisions.append(EditDecision(
                    action="add_effect",
                    target_track=TrackType.VIDEO,
                    params={
                        "effect_type": "transition",
                        "transition_type": context.input.extra_params.get("transition_type", "dissolve"),
                        "duration_us": context.input.extra_params.get("transition_duration_us", 500_000),
                        "after_segment_index": i,
                    },
                ))

    # ══════════════════════════════════════════════════
    # EDL 应用（写入时间线）
    # ══════════════════════════════════════════════════

    def _apply_decision(self, context: PipelineContext, decision: EditDecision) -> None:
        """将单条编辑决策应用到项目时间线"""
        handler = {
            "cut": self._apply_cut,
            "add_text": self._apply_add_text,
            "add_bgm": self._apply_add_bgm,
            "add_effect": self._apply_add_effect,
        }.get(decision.action)

        if handler is None:
            logger.warning(f"Unknown action: {decision.action}")
            return

        handler(context, decision)

    def _apply_cut(self, context: PipelineContext, decision: EditDecision) -> None:
        """应用视频切片 → 创建视频轨 + 片段"""
        source_start = decision.params.get("source_start_us", 0)
        source_end = decision.params.get("source_end_us", 0)
        duration_us = source_end - source_start

        if duration_us <= 0:
            return

        # 获取或创建视频轨
        video_tracks = context.project.timeline.get_tracks_by_type(TrackType.VIDEO)
        if not video_tracks:
            track = Track(track_type=TrackType.VIDEO)
            context.project.timeline.add_track(track)
            video_tracks = [track]

        video_track = video_tracks[0]

        # 计算目标位置（紧接上一个片段之后）
        target_start = video_track.total_duration_us

        # 关联到源视频素材
        material_id = ""
        if context.project.source_videos:
            material_id = context.project.source_videos[0].asset_id

        segment = Segment(
            segment_id=generate_id(),
            material_id=material_id,
            source_range=TimeRange(start_us=source_start, duration_us=duration_us),
            target_range=TimeRange(start_us=target_start, duration_us=duration_us),
            speed=1.0,
            volume=1.0,
        )
        video_track.add_segment(segment)

        logger.debug(
            f"Applied cut: source [{source_start / 1e6:.1f}s - {source_end / 1e6:.1f}s] "
            f"-> target [{target_start / 1e6:.1f}s - {(target_start + duration_us) / 1e6:.1f}s]"
        )

    def _apply_add_text(self, context: PipelineContext, decision: EditDecision) -> None:
        """应用字幕 → 创建文本轨 + 字幕块"""
        text = decision.params.get("text", "")
        start_us = decision.params.get("start_us", 0)
        duration_us = decision.params.get("duration_us", 0)

        if not text or duration_us <= 0:
            return

        # 创建字幕块
        subtitle = SubtitleBlock(
            text=text,
            time_range=TimeRange(start_us=start_us, duration_us=duration_us),
            font_name=decision.params.get("font_name", "系统默认"),
            font_size=decision.params.get("font_size", 8.0),
            font_color=decision.params.get("font_color", "#FFFFFF"),
            position_y=decision.params.get("position_y", 0.85),
            alignment="center",
        )
        context.project.subtitles.append(subtitle)

        # 获取或创建文本轨
        text_tracks = context.project.timeline.get_tracks_by_type(TrackType.TEXT)
        if not text_tracks:
            track = Track(track_type=TrackType.TEXT)
            context.project.timeline.add_track(track)
            text_tracks = [track]

        # 添加文本轨片段
        seg = Segment(
            segment_id=generate_id(),
            material_id="",
            source_range=TimeRange.zero(),
            target_range=TimeRange(start_us=start_us, duration_us=duration_us),
        )
        text_tracks[0].add_segment(seg)

    def _apply_add_bgm(self, context: PipelineContext, decision: EditDecision) -> None:
        """应用背景音乐 → 创建音频轨"""
        bgm_path = decision.params.get("bgm_path", "")
        volume = decision.params.get("volume", 0.5)

        if not bgm_path:
            return

        # 计算 BGM 的目标时长（跟随视频轨总时长）
        video_tracks = context.project.timeline.get_tracks_by_type(TrackType.VIDEO)
        target_duration = video_tracks[0].total_duration_us if video_tracks else 0

        if target_duration <= 0:
            return

        # 获取或创建音频轨
        audio_tracks = context.project.timeline.get_tracks_by_type(TrackType.AUDIO)
        if not audio_tracks:
            track = Track(track_type=TrackType.AUDIO)
            context.project.timeline.add_track(track)
            audio_tracks = [track]

        audio_track = audio_tracks[0]

        # 查找对应的音频素材
        material_id = ""
        for audio_asset in context.project.source_audios:
            if audio_asset.path == bgm_path:
                material_id = audio_asset.asset_id
                break

        # 创建 BGM 片段
        segment = Segment(
            segment_id=generate_id(),
            material_id=material_id,
            source_range=TimeRange(start_us=0, duration_us=target_duration),
            target_range=TimeRange(start_us=0, duration_us=target_duration),
            volume=volume,
        )
        audio_track.add_segment(segment)

        logger.debug(f"Applied BGM: {bgm_path} volume={volume}")

    def _apply_add_effect(self, context: PipelineContext, decision: EditDecision) -> None:
        """应用特效 / 转场"""
        effect_type = decision.params.get("effect_type", "")

        if effect_type == "transition":
            transition_type = decision.params.get("transition_type", "dissolve")
            transition_duration = decision.params.get("duration_us", 500_000)

            # 找到对应的视频片段并添加转场
            video_tracks = context.project.timeline.get_tracks_by_type(TrackType.VIDEO)
            if video_tracks and video_tracks[0].segments:
                last_segment = video_tracks[0].segments[-1]
                transition = Transition(
                    transition_type=transition_type,
                    duration_us=transition_duration,
                )
                last_segment.transitions.append(transition)
                logger.debug(f"Applied transition: {transition_type} ({transition_duration / 1e6:.1f}s)")

        elif effect_type == "filter":
            filter_name = decision.params.get("filter_name", "")
            if filter_name:
                # 查找目标片段
                video_tracks = context.project.timeline.get_tracks_by_type(TrackType.VIDEO)
                if video_tracks and video_tracks[0].segments:
                    target_seg = video_tracks[0].segments[-1]
                    effect = Effect(
                        effect_type="filter",
                        effect_name=filter_name,
                        params=decision.params.get("filter_params", {}),
                    )
                    target_seg.effects.append(effect)

    # ══════════════════════════════════════════════════
    # 辅助算法
    # ══════════════════════════════════════════════════

    def _select_scenes_for_duration(
        self,
        scenes: list[TimeRange],
        target_duration_us: int,
    ) -> list[TimeRange]:
        """从场景列表中选择总时长最接近 target 的组合

        使用贪心策略：按场景得分（时长利用率）排序，
        依次选取直到达到目标时长的 90%~110%。
        """
        if not scenes:
            return []

        target = target_duration_us
        selected: list[TimeRange] = []
        total = 0

        # 按场景时长降序排列（优先选长场景，减少碎片化）
        sorted_scenes = sorted(scenes, key=lambda s: s.duration_us, reverse=True)

        for scene in sorted_scenes:
            if total + scene.duration_us <= target * 1.1:
                selected.append(scene)
                total += scene.duration_us
                if total >= target * 0.9:
                    break

        # 按时间顺序排序
        selected.sort(key=lambda s: s.start_us)
        return selected

    async def rollback(self, context: PipelineContext) -> None:
        """回滚：清空时间线和 EDL"""
        context.edl = None
        context.project.timeline.tracks.clear()
        context.project.subtitles.clear()
        logger.info("EditStage rolled back: cleared timeline and EDL")
