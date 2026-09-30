"""
CLI 主入口 - 基于 Typer 的命令行界面

提供 jy-edit 命令入口及各子命令。
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

import typer

from jy_auto_editor.infra.logging import setup_logging

# 创建主应用
app = typer.Typer(
    name="jy-edit",
    help="剪映 AI 自动剪辑工具",
    add_completion=False,
)


def run_async(coro):
    """运行异步协程"""
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        typer.echo("\n操作已取消")
        sys.exit(1)


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="安静模式"),
    log_file: Optional[Path] = typer.Option(None, "--log-file", help="日志文件路径"),
):
    """全局选项"""
    level = "DEBUG" if verbose else ("WARNING" if quiet else "INFO")
    setup_logging(level=level, log_file=log_file)


# ── 子命令 ─────────────────────────────────────────────────────────

@app.command()
def subtitle(
    video_path: Path = typer.Argument(..., help="视频/音频文件路径"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出路径"),
    provider: str = typer.Option("openai", help="ASR 提供商"),
    language: str = typer.Option("zh", help="语言代码"),
):
    """自动添加字幕"""
    from jy_auto_editor.ui.cli.commands import cmd_subtitle
    run_async(cmd_subtitle(video_path, output, provider, language))


@app.command()
def smart_cut(
    video_path: Path = typer.Argument(..., help="视频文件路径"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出路径"),
    style: str = typer.Option("highlight", help="剪辑风格: highlight/narrative/commercial"),
    duration: Optional[int] = typer.Option(None, help="目标时长(秒)"),
):
    """智能剪辑 - 自动提取精彩片段"""
    from jy_auto_editor.ui.cli.commands import cmd_smart_cut
    run_async(cmd_smart_cut(video_path, output, style, duration))


@app.command()
def long_to_short(
    video_path: Path = typer.Argument(..., help="长视频文件路径"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出路径"),
    target_duration: int = typer.Option(60, help="目标时长(秒)"),
    platform: str = typer.Option("douyin", help="目标平台: douyin/kuaishou/xiaohongshu"),
):
    """长视频转短视频"""
    from jy_auto_editor.ui.cli.commands import cmd_long_to_short
    run_async(cmd_long_to_short(video_path, output, target_duration, platform))


@app.command()
def bgm(
    video_path: Path = typer.Argument(..., help="视频文件路径"),
    mood: str = typer.Option("auto", help="音乐情绪: auto/happy/sad/energetic/calm"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出路径"),
):
    """智能 BGM 推荐"""
    from jy_auto_editor.ui.cli.commands import cmd_bgm
    run_async(cmd_bgm(video_path, mood, output))


@app.command(name="run")
def full_pipeline(
    video_paths: list[Path] = typer.Argument(..., help="视频文件路径（支持多个）"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出路径"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    export: bool = typer.Option(False, help="是否导出视频"),
    resume: bool = typer.Option(False, help="从上次中断处恢复"),
):
    """完整流水线 - 一键全自动处理"""
    from jy_auto_editor.ui.cli.commands import cmd_full_pipeline
    run_async(cmd_full_pipeline(video_paths, output, config, export, resume))


@app.command()
def info(
    draft_path: Path = typer.Argument(..., help="剪映草稿路径"),
):
    """查看草稿信息"""
    from jy_auto_editor.ui.cli.commands import cmd_info
    run_async(cmd_info(draft_path))


@app.command()
def check():
    """检查环境依赖"""
    from jy_auto_editor.ui.cli.commands import cmd_check
    run_async(cmd_check())


# ── 入口 ───────────────────────────────────────────────────────────

def main():
    """CLI 入口点"""
    app()


if __name__ == "__main__":
    main()
