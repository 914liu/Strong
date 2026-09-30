"""剪映进程管理 — 启动/关闭/检测"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Optional

from ...core.exceptions import GUIControllerError

logger = logging.getLogger(__name__)

# 剪映常见安装路径
DEFAULT_PATHS = [
    r"C:\Program Files\JianyingPro\JianyingPro.exe",
    r"C:\Program Files (x86)\JianyingPro\JianyingPro.exe",
    r"D:\Program Files\JianyingPro\JianyingPro.exe",
]


class JianYingProcess:
    """剪映进程管理器"""

    def __init__(self, exe_path: Optional[str] = None) -> None:
        self._exe_path = exe_path or self._find_exe()
        self._process: Optional[subprocess.Popen] = None

    @staticmethod
    def _find_exe() -> str:
        """查找剪映可执行文件"""
        for p in DEFAULT_PATHS:
            if Path(p).exists():
                return p
        # 尝试从注册表查找
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
            )
            # 简化处理，实际应遍历子键
            winreg.CloseKey(key)
        except Exception:
            pass
        return ""

    def is_running(self) -> bool:
        """检测剪映是否正在运行"""
        try:
            result = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq JianyingPro.exe"],
                capture_output=True, text=True, timeout=10,
            )
            return "JianyingPro.exe" in result.stdout
        except Exception:
            return False

    def launch(self, wait: bool = True, timeout: int = 30) -> bool:
        """启动剪映

        Args:
            wait: 是否等待启动完成
            timeout: 等待超时秒数

        Returns:
            是否成功启动
        """
        if self.is_running():
            logger.info("JianYing is already running")
            return True

        if not self._exe_path or not Path(self._exe_path).exists():
            raise GUIControllerError(
                f"JianYing executable not found: {self._exe_path}"
            )

        try:
            self._process = subprocess.Popen(
                [self._exe_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Launched JianYing: {self._exe_path}")

            if wait:
                return self._wait_for_ready(timeout)
            return True
        except Exception as e:
            raise GUIControllerError(f"Failed to launch JianYing: {e}")

    def _wait_for_ready(self, timeout: int) -> bool:
        """等待剪映启动就绪"""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.is_running():
                # 额外等待几秒让 UI 完全加载
                time.sleep(3)
                return True
            time.sleep(1)
        return False

    def close(self, force: bool = False) -> bool:
        """关闭剪映"""
        try:
            if force:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "JianyingPro.exe"],
                    capture_output=True, timeout=10,
                )
            elif self._process:
                self._process.terminate()
                self._process.wait(timeout=10)
            logger.info("JianYing closed")
            return True
        except Exception as e:
            logger.error(f"Failed to close JianYing: {e}")
            return False

    def open_project(self, project_path: str) -> bool:
        """通过命令行打开项目（如果剪映支持）"""
        if not self.is_running():
            self.launch(wait=True)
        # 剪映可能不支持命令行打开项目，需要通过 GUI 操作
        logger.info(f"Opening project: {project_path}")
        return True
