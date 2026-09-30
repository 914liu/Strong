"""草稿加解密适配 — 自动处理剪映 v6.0+ 的 AES 加密草稿"""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ...core.exceptions import DraftEncryptionError

logger = logging.getLogger(__name__)


class DraftCrypto:
    """草稿加解密管理器

    剪映 v6.0+ 的 draft_content.json 使用 AES 加密。
    本模块通过调用 jy-draftc 工具（依赖 videoeditor.dll）实现加解密。
    """

    def __init__(self, jy_draftc_path: Optional[str] = None) -> None:
        self._jy_draftc = jy_draftc_path or self._find_jy_draftc()

    @staticmethod
    def _find_jy_draftc() -> str:
        """尝试在 PATH 或常见位置查找 jy-draftc"""
        # 优先从 PATH 查找
        result = shutil.which("jy-draftc")
        if result:
            return result
        # 常见安装位置
        candidates = [
            Path.home() / "tools" / "jy-draftc" / "jy-draftc.exe",
            Path("C:/tools/jy-draftc/jy-draftc.exe"),
        ]
        for c in candidates:
            if c.exists():
                return str(c)
        return ""

    @staticmethod
    def is_encrypted(draft_path: Path) -> bool:
        """检测草稿是否加密

        规则：读取首字节，如果为 '{' 则是明文 JSON，否则已加密。
        """
        if not draft_path.exists():
            return False
        try:
            first_byte = draft_path.read_bytes()[:1]
            return first_byte != b"{"
        except Exception:
            return False

    def decrypt(self, draft_path: Path, backup: bool = True) -> Path:
        """解密草稿文件

        Args:
            draft_path: 加密的 draft_content.json 路径
            backup: 是否备份原始加密文件

        Returns:
            解密后的文件路径（可能与原路径相同）
        """
        if not self.is_encrypted(draft_path):
            logger.debug(f"Draft already decrypted: {draft_path}")
            return draft_path

        if not self._jy_draftc:
            raise DraftEncryptionError(
                "Cannot decrypt draft: jy-draftc not found. "
                "Please install jy-draftc (https://github.com/wenshui330/jy-draftc) "
                "or use JianYing v5.9.x which does not encrypt drafts."
            )

        # 备份原始加密文件
        if backup:
            backup_path = draft_path.with_suffix(".json.encrypted")
            if not backup_path.exists():
                shutil.copy2(draft_path, backup_path)
                logger.debug(f"Backed up encrypted draft to {backup_path}")

        # 调用 jy-draftc 解密
        try:
            result = subprocess.run(
                [self._jy_draftc, "decrypt", str(draft_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise DraftEncryptionError(
                    f"jy-draftc decrypt failed: {result.stderr}"
                )
            logger.info(f"Decrypted draft: {draft_path}")
            return draft_path
        except subprocess.TimeoutExpired:
            raise DraftEncryptionError("jy-draftc decrypt timed out")
        except FileNotFoundError:
            raise DraftEncryptionError(
                f"jy-draftc not found at: {self._jy_draftc}"
            )

    def encrypt(self, draft_path: Path) -> Path:
        """重新加密草稿文件

        Args:
            draft_path: 明文 draft_content.json 路径

        Returns:
            加密后的文件路径
        """
        if not self._jy_draftc:
            raise DraftEncryptionError("jy-draftc not available for encryption")

        try:
            result = subprocess.run(
                [self._jy_draftc, "encrypt", str(draft_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                raise DraftEncryptionError(
                    f"jy-draftc encrypt failed: {result.stderr}"
                )
            logger.info(f"Re-encrypted draft: {draft_path}")
            return draft_path
        except subprocess.TimeoutExpired:
            raise DraftEncryptionError("jy-draftc encrypt timed out")

    def ensure_decrypted(self, draft_path: Path) -> tuple[Path, bool]:
        """确保草稿已解密，返回 (文件路径, 是否原本加密)

        用于在操作前透明处理加密草稿。操作完成后可根据 was_encrypted
        决定是否需要回加密。
        """
        was_encrypted = self.is_encrypted(draft_path)
        if was_encrypted:
            decrypted_path = self.decrypt(draft_path)
            return decrypted_path, True
        return draft_path, False

    def restore_encrypted_backup(self, draft_path: Path) -> None:
        """从备份恢复加密文件（操作失败时使用）"""
        backup_path = draft_path.with_suffix(".json.encrypted")
        if backup_path.exists():
            shutil.copy2(backup_path, draft_path)
            logger.info(f"Restored encrypted backup: {draft_path}")
