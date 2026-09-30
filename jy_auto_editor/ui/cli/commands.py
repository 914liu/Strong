"""
CLI 命令实现 - 各子命令的具体逻辑

每个命令函数负责：
1. 解析参数、加载配置
2. 组装 Pipeline
3. 执行并输出结果
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from jy_auto_editor.core.config import load_config, AppConfig
from jy_auto_editor.core.pipeline import Pipeline
from jy_auto_editor.core.events import EventBus, EventType, Event
from jy_auto_editor.core.models import ProjectInput, CanvasConfig
from jy_auto_editor.infra.storage import StorageManager
from jy_auto_editor.infra.monitor import PerformanceMonitor

logger = logging.getLogger(__name__)
console = Console()


def _load_config_with_fallback(config_path: Optional[Path] = None) -> AppConfig:
    """加载配置，失败时使用默认配置"""
    try:
        return load_config(str(config_path) if config_path else None)
    except Exception as e:
        logger.warning(f"Config load failed, using defaults: {e}")
        return AppConfig()


def _build_pipeline(config: AppConfig, driver_type: str = "hybrid") -> Pipeline:
    """构建流水线实例（通过 bootstrap 自动装配所有组件）"""
    from jy_auto_editor.core.bootstrap import bootstrap

    app_ctx = bootstrap(config=config)
    return app_ctx.pipeline


def _make_project_input(
    video_paths: Optional[list[str]] = None,
    audio_paths: Optional[list[str]] = None,
    image_paths: Optional[list[str]] = None,
    canvas_config: Optional[CanvasConfig] = None,
    **extra_params,
) -> ProjectInput:
    """构造 ProjectInput 的便捷工厂"""
    return ProjectInput(
        video_paths=video_paths or [],
        audio_paths=audio_paths or [],
        image_paths=image_paths or [],
        canvas_config=canvas_config or CanvasConfig.horizontal(),
        extra_params=extra_params,
    )


# ── subtitle 命令 ──────────────────────────────────────────────────

async def cmd_subtitle(
    video_path: Path,
    output: Optional[Path],
    provider: str,
    language: str,
) -> None:
    """自动添加字幕"""
    console.print(f"[bold blue]开始添加字幕[/] 视频: {video_path}")

    config = _load_config_with_fallback()
    pipeline = _build_pipeline(config)

    # 仅启用 ASR，关闭场景检测和高光
    analyze_stage = pipeline.get_stage("analyze")
    analyze_stage.asr_enabled = True
    analyze_stage.scene_enabled = False
    analyze_stage.highlight_enabled = False

    project_input = _make_project_input(
        video_paths=[str(video_path)],
        language=language,
    )

    try:
        result = await pipeline.run(project_input)
        console.print("[bold green]字幕添加完成[/]")

        # 输出字幕信息
        if result.analysis:
            console.print(f"  转录文本: {len(result.analysis.transcript)} 字")
            console.print(f"  字幕条数: {len(result.analysis.subtitles)}")

        if output:
            console.print(f"  输出: {output}")
    except Exception as e:
        console.print(f"[bold red]失败: {e}[/]")
        raise typer.Exit(1)


# ── smart_cut 命令 ─────────────────────────────────────────────────

async def cmd_smart_cut(
    video_path: Path,
    output: Optional[Path],
    style: str,
    duration: Optional[int],
) -> None:
    """智能剪辑"""
    console.print(f"[bold blue]智能剪辑[/] 风格: {style}")

    config = _load_config_with_fallback()
    pipeline = _build_pipeline(config)

    extra = {"style": style}
    if duration:
        extra["target_duration"] = duration

    project_input = _make_project_input(
        video_paths=[str(video_path)],
        **extra,
    )

    try:
        result = await pipeline.run(project_input)
        console.print("[bold green]智能剪辑完成[/]")

        if result.export_result:
            console.print(f"  输出: {result.export_result.output_path}")
    except Exception as e:
        console.print(f"[bold red]失败: {e}[/]")
        raise typer.Exit(1)


# ── long_to_short 命令 ─────────────────────────────────────────────

async def cmd_long_to_short(
    video_path: Path,
    output: Optional[Path],
    target_duration: int,
    platform: str,
) -> None:
    """长视频转短视频"""
    console.print(
        f"[bold blue]长转短[/] 目标: {target_duration}s 平台: {platform}"
    )

    config = _load_config_with_fallback()
    pipeline = _build_pipeline(config)

    project_input = _make_project_input(
        video_paths=[str(video_path)],
        target_duration=target_duration,
        platform=platform,
        max_clips=5,
    )

    try:
        result = await pipeline.run(project_input)
        console.print("[bold green]长转短完成[/]")

        if result.analysis and result.analysis.highlights:
            console.print(f"  提取了 {len(result.analysis.highlights)} 个高光片段")
    except Exception as e:
        console.print(f"[bold red]失败: {e}[/]")
        raise typer.Exit(1)


# ── bgm 命令 ───────────────────────────────────────────────────────

async def cmd_bgm(
    video_path: Path,
    mood: str,
    output: Optional[Path],
) -> None:
    """BGM 推荐"""
    console.print(f"[bold blue]BGM 推荐[/] 情绪: {mood}")

    config = _load_config_with_fallback()
    pipeline = _build_pipeline(config)

    project_input = _make_project_input(
        video_paths=[str(video_path)],
        bgm_mood=mood,
    )

    try:
        result = await pipeline.run(project_input)
        console.print("[bold green]BGM 推荐完成[/]")
    except Exception as e:
        console.print(f"[bold red]失败: {e}[/]")
        raise typer.Exit(1)


# ── full_pipeline 命令 ─────────────────────────────────────────────

async def cmd_full_pipeline(
    video_paths: list[Path],
    output: Optional[Path],
    config_path: Optional[Path],
    export: bool,
    resume: bool,
) -> None:
    """完整流水线"""
    paths_str = [str(p) for p in video_paths]
    console.print(f"[bold blue]全自动流水线[/] 文件: {len(video_paths)} 个")

    config = _load_config_with_fallback(config_path)
    pipeline = _build_pipeline(config)

    # 事件监听
    def on_stage_complete(event: Event):
        stage_name = event.data.get("stage", "unknown")
        duration = event.data.get("duration", 0)
        console.print(f"  [green]✓[/] {stage_name} 完成 ({duration:.1f}s)")

    def on_stage_failed(event: Event):
        stage_name = event.data.get("stage", "unknown")
        error = event.data.get("error", "")
        console.print(f"  [red]✗[/] {stage_name} 失败: {error}")

    pipeline.event_bus.on_async(EventType.STAGE_COMPLETED, on_stage_complete)
    pipeline.event_bus.on_async(EventType.STAGE_FAILED, on_stage_failed)

    project_input = _make_project_input(video_paths=paths_str)

    try:
        result = await pipeline.run(
            project_input,
            resume_from_checkpoint=resume,
        )
        console.print("[bold green]流水线执行完成[/]")

        if result.export_result:
            if result.export_result.success:
                console.print(f"  输出: {result.export_result.output_path}")
            else:
                console.print(f"  [red]导出失败: {result.export_result.error_message}[/]")

    except Exception as e:
        console.print(f"[bold red]流水线失败: {e}[/]")
        raise typer.Exit(1)


# ── info 命令 ──────────────────────────────────────────────────────

async def cmd_info(draft_path: Path) -> None:
    """查看草稿信息"""
    console.print(f"[bold]草稿信息[/] {draft_path}")

    try:
        from jy_auto_editor.drivers.draft_engine.reader import DraftReader
        reader = DraftReader()
        project = await reader.read_project(draft_path)

        table = Table(title="项目信息")
        table.add_column("属性", style="cyan")
        table.add_column("值", style="green")

        table.add_row("名称", project.name)
        table.add_row("时长", f"{project.total_duration_seconds:.1f}s")
        table.add_row("视频素材", str(len(project.source_videos)))
        table.add_row("音频素材", str(len(project.source_audios)))
        table.add_row("轨道数", str(len(project.timeline.tracks)))

        for i, track in enumerate(project.timeline.tracks):
            table.add_row(
                f"  轨道 {i}",
                f"{track.track_type.value} ({len(track.segments)} 片段)",
            )

        console.print(table)

    except Exception as e:
        console.print(f"[bold red]读取失败: {e}[/]")
        raise typer.Exit(1)


# ── check 命令 ─────────────────────────────────────────────────────

async def cmd_check() -> None:
    """检查环境依赖"""
    console.print("[bold]环境检查[/]")

    checks = []

    # Python 版本
    py_version = sys.version_info
    checks.append(("Python >= 3.11", py_version >= (3, 11), f"{py_version.major}.{py_version.minor}"))

    # FFmpeg
    from jy_auto_editor.infra.ffmpeg import FFmpegWrapper
    ffmpeg = FFmpegWrapper()
    ffmpeg_ok = await ffmpeg.check_available()
    checks.append(("FFmpeg", ffmpeg_ok, "可用" if ffmpeg_ok else "未安装"))

    # 剪映路径
    from jy_auto_editor.core.config import _detect_jianying_paths
    jy_path, draft_root = _detect_jianying_paths()
    checks.append(("剪映", bool(jy_path), jy_path if jy_path else "未检测到"))

    # 可选依赖
    optional_deps = [
        ("scenedetect", "PySceneDetect"),
        ("faster_whisper", "faster-whisper"),
        ("openai", "openai"),
        ("dashscope", "dashscope (通义千问)"),
        ("psutil", "psutil (性能监控)"),
    ]

    for module, name in optional_deps:
        try:
            __import__(module)
            checks.append((name, True, "已安装"))
        except ImportError:
            checks.append((name, False, "未安装(可选)"))

    # API Key 检查
    config = _load_config_with_fallback()
    for name, llm_cfg in config.providers.llm_providers.items():
        if name == "ollama":
            checks.append((f"LLM:{name}", True, "无需密钥"))
        elif llm_cfg.api_key:
            checks.append((f"LLM:{name} 密钥", True, "已配置"))
        else:
            checks.append((f"LLM:{name} 密钥", False, "未配置"))

    for name, asr_cfg in config.providers.asr_providers.items():
        key = getattr(asr_cfg, "extra", {}).get("api_key", "")
        if not key and "openai" in config.providers.llm_providers:
            key = config.providers.llm_providers["openai"].api_key
        if key:
            checks.append((f"ASR:{name}", True, "已配置"))
        else:
            checks.append((f"ASR:{name}", False, "未配置"))

    # 输出结果
    table = Table(title="环境状态")
    table.add_column("组件", style="cyan")
    table.add_column("状态")
    table.add_column("信息")

    for name, ok, info in checks:
        status = "[green]✓[/]" if ok else "[red]✗[/]"
        table.add_row(name, status, info)

    console.print(table)

    all_required = all(
        ok for name, ok, info in checks
        if "(可选)" not in info
    )
    if all_required:
        console.print("[bold green]环境检查通过[/]")
    else:
        console.print("[bold yellow]部分必需组件缺失[/]")
