"""
存储管理 - 临时文件与缓存管理

管理处理过程中的临时文件、缓存和输出目录。
"""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StorageManager:
    """存储管理器 - 管理临时文件和输出目录"""

    def __init__(self, base_dir: Optional[Path] = None):
        """
        Args:
            base_dir: 基础目录，默认为系统临时目录
        """
        self.base_dir = base_dir or Path(tempfile.gettempdir()) / "jy_auto_editor"
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.temp_dir = self.base_dir / "temp"
        self.cache_dir = self.base_dir / "cache"
        self.output_dir = self.base_dir / "output"
        self.logs_dir = self.base_dir / "logs"

        for d in [self.temp_dir, self.cache_dir, self.output_dir, self.logs_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def create_session_dir(self, session_id: str) -> Path:
        """
        为一次处理会话创建独立目录

        Args:
            session_id: 会话ID

        Returns:
            会话目录路径
        """
        session_dir = self.temp_dir / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def get_output_path(self, filename: str, sub_dir: Optional[str] = None) -> Path:
        """
        获取输出文件路径

        Args:
            filename: 文件名
            sub_dir: 可选子目录

        Returns:
            完整输出路径
        """
        target_dir = self.output_dir / sub_dir if sub_dir else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / filename

    def get_cache_path(self, key: str) -> Path:
        """
        获取缓存文件路径(基于key的哈希)

        Args:
            key: 缓存键

        Returns:
            缓存文件路径
        """
        import hashlib
        h = hashlib.md5(key.encode()).hexdigest()[:12]
        return self.cache_dir / f"{h}"

    def cleanup_session(self, session_id: str) -> None:
        """清理会话临时文件"""
        session_dir = self.temp_dir / session_id
        if session_dir.exists():
            shutil.rmtree(session_dir)
            logger.info(f"Cleaned session: {session_id}")

    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """
        清理过期的会话目录

        Args:
            max_age_hours: 最大保留时间(小时)

        Returns:
            清理的目录数量
        """
        import time
        now = time.time()
        max_age_seconds = max_age_hours * 3600
        cleaned = 0

        for session_dir in self.temp_dir.iterdir():
            if session_dir.is_dir():
                age = now - session_dir.stat().st_mtime
                if age > max_age_seconds:
                    shutil.rmtree(session_dir)
                    cleaned += 1

        if cleaned:
            logger.info(f"Cleaned {cleaned} expired sessions")
        return cleaned

    def get_disk_usage(self) -> dict:
        """获取各目录磁盘使用情况"""
        def dir_size(path: Path) -> int:
            total = 0
            for f in path.rglob("*"):
                if f.is_file():
                    total += f.stat().st_size
            return total

        return {
            "temp": dir_size(self.temp_dir),
            "cache": dir_size(self.cache_dir),
            "output": dir_size(self.output_dir),
            "total": dir_size(self.base_dir),
        }
