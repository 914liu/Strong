"""统一异常体系"""


class JYAutoEditorError(Exception):
    """所有异常的基类"""
    pass


class ConfigError(JYAutoEditorError):
    """配置相关错误"""
    pass


class DriverError(JYAutoEditorError):
    """驱动层错误"""
    pass


class DraftError(DriverError):
    """草稿操作错误"""
    pass


class DraftEncryptionError(DraftError):
    """草稿加解密错误"""
    pass


class DraftVersionError(DraftError):
    """草稿版本不兼容"""
    pass


class GUIControllerError(DriverError):
    """GUI 自动化错误"""
    pass


class ElementNotFoundError(GUIControllerError):
    """UI 元素未找到"""
    pass


class ExportError(DriverError):
    """导出失败"""
    pass


class AIPluginError(JYAutoEditorError):
    """AI 插件错误"""
    pass


class ProviderUnavailableError(AIPluginError):
    """AI Provider 不可用"""
    pass


class ProviderRateLimitError(AIPluginError):
    """AI Provider 限流"""
    pass


class PipelineError(JYAutoEditorError):
    """Pipeline 执行错误"""
    pass


class StageFailedError(PipelineError):
    """某个 Stage 执行失败"""

    def __init__(self, stage_name: str, original_error: Exception):
        self.stage_name = stage_name
        self.original_error = original_error
        super().__init__(f"Stage '{stage_name}' failed: {original_error}")


class StageTimeoutError(PipelineError):
    """Stage 执行超时"""

    def __init__(self, stage_name: str, timeout: int):
        self.stage_name = stage_name
        self.timeout = timeout
        super().__init__(f"Stage '{stage_name}' timed out after {timeout}s")


class ValidationError(JYAutoEditorError):
    """数据校验错误"""
    pass


class FFmpegError(JYAutoEditorError):
    """FFmpeg 操作错误"""
    pass
