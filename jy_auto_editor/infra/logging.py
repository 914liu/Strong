"""
日志配置 - 统一日志管理

支持控制台彩色输出、文件轮转、结构化日志。
"""

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    json_format: bool = False,
    color: bool = True,
) -> None:
    """
    配置日志系统

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 日志文件路径
        json_format: 是否使用 JSON 格式
        color: 是否启用控制台颜色
    """
    root_logger = logging.getLogger("jy_auto_editor")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除已有处理器
    root_logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if json_format:
        console_fmt = JsonFormatter()
        console_handler.setFormatter(console_fmt)
    elif color and sys.stdout.isatty():
        console_fmt = ColorFormatter(
            "%(asctime)s | %(level_color)s%(levelname)-8s%(reset)s | %(name)s | %(message)s"
        )
        console_handler.setFormatter(console_fmt)
    else:
        console_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )
        console_handler.setFormatter(console_fmt)

    root_logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
        )
        file_handler.setFormatter(file_fmt)
        root_logger.addHandler(file_handler)

    # 降低第三方库日志级别
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


class ColorFormatter(logging.Formatter):
    """彩色日志格式化器"""

    COLORS = {
        "DEBUG": "\033[36m",     # 青色
        "INFO": "\033[32m",      # 绿色
        "WARNING": "\033[33m",   # 黄色
        "ERROR": "\033[31m",     # 红色
        "CRITICAL": "\033[35m",  # 紫色
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        record.level_color = self.COLORS.get(record.levelname, "")
        record.reset = self.RESET
        return super().format(record)


class JsonFormatter(logging.Formatter):
    """JSON 格式日志"""

    def format(self, record: logging.LogRecord) -> str:
        import json
        data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """获取模块日志器"""
    return logging.getLogger(f"jy_auto_editor.{name}")
