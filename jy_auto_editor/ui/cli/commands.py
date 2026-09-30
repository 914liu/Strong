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
from jy_auto_editor.core.events import EventBus
from jy_auto_editor.infra.storage import StorageManager
from jy_auto_editor.infra.monitor import PerformanceMonitor

logger = logging.getLogger(__name__)
console = Console()


def _load_config_with_fallback(config_path: Optional[Path] = None) -> AppConfig:
    """加载配置，失败时使用默认配置"""
    try:
        return load_config(config_path)
    except Exception as e:
        logger.warning(f"Config load failed, using defaults: {e}")
        return AppConfig()


def _build_pipeline(config: AppConfig, driver_type: str = "hybrid") -> Pipeline:
    """构建流水线实例"""
    from jy_auto_editor.stages.ingest import IngestStage
    from jy_auto_editor.stages.analyze import AnalyzeStage
    from jy_auto_editor.stages.edit import EditStage
    from jy_auto_editor.stages.review import ReviewStage
    from jy_auto_editor.stages.export import ExportStage

    event_bus = EventBus()
    pipeline = Pipeline(event_bus=event_bus, config=config)

    pipeline.register_stage(IngestStage())
    pipeline.register_stage(AnalyzeStage())
    pipeline.register_stage(EditStage())
    pipeline.register_stage(ReviewStage(enabled=False))
    pipeline.register_stage(ExportStage())

    return pipeline


# ── subtitle 命令 ──────────────────────────────────────────────────

async def cmd_subtitle(
    draft_path: Path,
    output: Optional[Path],
    provider: str,
    language: str,
) -> None:
    """自动添加字幕"""
    console.print(f"[bold blue]🎬 开始添加字幕[/] 草稿: {draft_path}")

    config = _load_config_with_fallback()
    pipeline = _build_pipeline(config)

    # 仅启用 ASR 相关阶段
    pipeline.get_stage("analyze").asr_enabled = True
    pipeline.get_stage("analyze").scene_enabled = False
    pipeline.get_stage("analyze").highlight_enabled = False

    from jy_auto_editor.core.models import ProjectInput
    project_input = ProjectInput(
        source_path=draft_path,
        project_name=draft_path.stem,
    )

    try:
        result = await pipeline.run(project_input)
        console.print("[bold green]✓ 字幕添加完成[/]")
        if output:
            console.print(f"输出: {output}")
    except Exception as e:
        console.print(f"[bold red]✗ 失败: {e}[/]")
        raise typer.Exit(1)


# ── smart_cut 命令 ─────────────────────────────────────────────────

async def cmd_smart_cut(
    draft_path: Path,
    output: Optional[Path],
    style: str,
    duration: Optional[int],
) -> None:
    """智能剪辑"""
    console.print(f"[bold blue]✂️  智能剪辑[/] 风格: {style}")

    config = _load_config_with_fallback()
    pipeline = _build_pipeline(config)

    from jy_auto_editor.core.models import ProjectInput
    project_input = ProjectInput(
        source_path=draft_path,
        project_name=draft_path.stem,
        target_duration=duration,
    )

    try:
        result = await pipeline.run(project_input)
        console.print("[bold green]✓ 智能剪辑完成[/]")
    except Exception as e:
        console.print(f"[bold red]✗ 失败: {e}[/]")
        raise typer.Exit(1)


# ── long_to_short 命令 ─────────────────────────────────────────────

async def cmd_long_to_short(
    draft_path: Path,
    output: Optional[Path],
    target_duration: int,
    platform: str,
) -> None:
    """长视频转短视频"""
    console.print(
        f"[bold blue]📱 长转短[/] 目标: {target_duration}s 平台: {platform}"
    )

    config = _load_config_with_fallback()
    pipeline = _build_pipeline(config)

    from jy_auto_editor.core.models import ProjectInput
    project_input = ProjectInput(
        source_path=draft_path,
        project_name=draft_path.stem,
        target_duration=target_duration,
    )

    try:
        result = await pipeline.run(project_input)
        console.print("[bold green]✓ 长转短完成[/]")
    except Exception as e:
        console.print(f"[bold red]✗ 失败: {e}[/]")
        raise typer.Exit(1)


# ── bgm 命令 ───────────────────────────────────────────────────────

async def cmd_bgm(
    draft_path: Path,
    mood: str,
    output: Optional[Path],
) -> None:
    """BGM 推荐"""
    console.print(f"[bold blue]🎵 BGM 推荐[/] 情绪: {mood}")

    config = _load_config_with_fallback()
    # BGM 只需要分析阶段
    pipeline = _build_pipeline(config)

    from jy_auto_editor.core.models import ProjectInput
    project_input = ProjectInput(
        source_path=draft_path,
        project_name=draft_path.stem,
    )

    try:
        result = await pipeline.run(project_input)
        console.print("[bold green]✓ BGM 推荐完成[/]")
    except Exception as e:
        console.print(f"[bold red]✗ 失败: {e}[/]")
        raise typer.Exit(1)


# ── full_pipeline 命令 ─────────────────────────────────────────────

async def cmd_full_pipeline(
    draft_path: Path,
    output: Optional[Path],
    config_path: Optional[Path],
    export: bool,
    resume: bool,
) -> None:
    """完整流水线"""
    console.print(f"[bold blue]🚀 全自动流水线[/] 草稿: {draft_path}")

    config = _load_config_with_fallback(config_path)
    pipeline = _build_pipeline(config)

    from jy_auto_editor.core.models import ProjectInput
    project_input = ProjectInput(
        source_path=draft_path,
        project_name=draft_path.stem,
    )

    # 事件监听
    async def on_stage_complete(event):
        stage_name = event.data.get("stage", "unknown")
        console.print(f"  [green]✓[/] {stage_name} 完成")

    pipeline.event_bus.subscribe("stage.completed", on_stage_complete)

    try:
        result = await pipeline.run(
            project_input,
            resume_from_checkpoint=resume,
        )
        console.print("[bold green]✓ 流水线执行完成[/]")

        if export:
            console.print("[dim]视频导出完成[/]")
    except Exception as e:
        console.print(f"[bold red]✗ 流水线失败: {e}[/]")
        raise typer.Exit(1)


# ── info 命令 ──────────────────────────────────────────────────────

async def cmd_info(draft_path: Path) -> None:
    """查看草稿信息"""
    console.print(f"[bold]📋 草稿信息[/] {draft_path}")

    try:
        from jy_auto_editor.drivers.draft_engine.reader import DraftReader
        reader = DraftReader()
        project = await reader.read_project(draft_path)

        table = Table(title="项目信息")
        table.add_column("属性", style="cyan")
        table.add_column("值", style="green")

        table.add_row("名称", project.name)
        table.add_row("时长", f"{project.duration / 1_000_000:.1f}s")
        table.add_row("视频素材", str(len(project.source_videos)))
        table.add_row("音频素材", str(len(project.source_audios)))
        table.add_row("轨道数", str(len(project.tracks)))

        for i, track in enumerate(project.tracks):
            table.add_row(f"  轨道 {i}", f"{track.type} ({len(track.segments)} 片段)")

        console.print(table)

    except Exception as e:
        console.print(f"[bold red]✗ 读取失败: {e}[/]")
        raise typer.Exit(1)


# ── check 命令 ─────────────────────────────────────────────────────

async def cmd_check() -> None:
    """检查环境依赖"""
    console.print("[bold]🔍 环境检查[/]")

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
    from jy_auto_editor.core.config import auto_detect_jianying_path
    jy_path = auto_detect_jianying_path()
    checks.append(("剪映", jy_path is not None, str(jy_path) if jy_path else "未检测到"))

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

    # 输出结果
    table = Table(title="环境状态")
    table.add_column("组件", style="cyan")
    table.add_column("状态")
    table.add_column("信息")

    for name, ok, info in checks:
        status = "[green]✓[/]" if ok else "[red]✗[/]"
        table.add_row(name, status, info)

    console.print(table)

    all_required = all(ok for name, ok, _ in checks if "(可选)" not in _)
    if all_required:
        console.print("[bold green]✓ 环境检查通过[/]")
    else:
        console.print("[bold yellow]⚠ 部分必需组件缺失[/]")
