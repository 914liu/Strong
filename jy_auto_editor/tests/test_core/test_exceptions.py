"""core/exceptions 单元测试"""

import pytest
from jy_auto_editor.core.exceptions import (
    JYAutoEditorError,
    ConfigError,
    DriverError,
    DraftError,
    DraftEncryptionError,
    DraftVersionError,
    GUIControllerError,
    ElementNotFoundError,
    ExportError,
    AIPluginError,
    ProviderUnavailableError,
    ProviderRateLimitError,
    PipelineError,
    StageFailedError,
    StageTimeoutError,
    ValidationError,
    FFmpegError,
)


class TestExceptionHierarchy:
    def test_config_error_is_base(self):
        with pytest.raises(JYAutoEditorError):
            raise ConfigError("bad config")

    def test_driver_error_is_base(self):
        with pytest.raises(JYAutoEditorError):
            raise DriverError("driver fail")

    def test_draft_error_is_driver_error(self):
        with pytest.raises(DriverError):
            raise DraftError("draft fail")

    def test_draft_encryption_is_draft_error(self):
        with pytest.raises(DraftError):
            raise DraftEncryptionError("encrypted")

    def test_draft_version_is_draft_error(self):
        with pytest.raises(DraftError):
            raise DraftVersionError("version mismatch")

    def test_gui_error_is_driver_error(self):
        with pytest.raises(DriverError):
            raise GUIControllerError("gui fail")

    def test_element_not_found_is_gui_error(self):
        with pytest.raises(GUIControllerError):
            raise ElementNotFoundError("not found")

    def test_export_error_is_driver_error(self):
        with pytest.raises(DriverError):
            raise ExportError("export fail")

    def test_ai_plugin_error_is_base(self):
        with pytest.raises(JYAutoEditorError):
            raise AIPluginError("ai fail")

    def test_provider_unavailable_is_ai_error(self):
        with pytest.raises(AIPluginError):
            raise ProviderUnavailableError("no provider")

    def test_provider_rate_limit_is_ai_error(self):
        with pytest.raises(AIPluginError):
            raise ProviderRateLimitError("rate limited")

    def test_pipeline_error_is_base(self):
        with pytest.raises(JYAutoEditorError):
            raise PipelineError("pipeline fail")

    def test_stage_failed_is_pipeline_error(self):
        with pytest.raises(PipelineError):
            raise StageFailedError("my_stage", ValueError("inner"))

    def test_stage_timeout_is_pipeline_error(self):
        with pytest.raises(PipelineError):
            raise StageTimeoutError("my_stage", 300)

    def test_validation_error_is_base(self):
        with pytest.raises(JYAutoEditorError):
            raise ValidationError("invalid")

    def test_ffmpeg_error_is_base(self):
        with pytest.raises(JYAutoEditorError):
            raise FFmpegError("ffmpeg fail")


class TestStageFailedError:
    def test_attributes(self):
        original = ValueError("inner error")
        err = StageFailedError("analyze", original)
        assert err.stage_name == "analyze"
        assert err.original_error is original
        assert "analyze" in str(err)

    def test_message(self):
        err = StageFailedError("export", RuntimeError("disk full"))
        assert "export" in str(err)
        assert "disk full" in str(err)


class TestStageTimeoutError:
    def test_attributes(self):
        err = StageTimeoutError("ingest", 120)
        assert err.stage_name == "ingest"
        assert err.timeout == 120
        assert "ingest" in str(err)
        assert "120" in str(err)
