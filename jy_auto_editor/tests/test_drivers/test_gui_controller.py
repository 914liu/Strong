"""GUI Controller 单元测试 — Process / Finder / Actions / Export / Verifier"""

import asyncio
import pytest
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch, AsyncMock

from jy_auto_editor.core.exceptions import ElementNotFoundError, GUIControllerError
from jy_auto_editor.core.models import ExportConfig, ExportResult
from jy_auto_editor.drivers.gui_controller.actions import ActionExecutor
from jy_auto_editor.drivers.gui_controller.export import ExportTrigger
from jy_auto_editor.drivers.gui_controller.finder import UIElementFinder
from jy_auto_editor.drivers.gui_controller.process import JianYingProcess
from jy_auto_editor.drivers.gui_controller.verifier import OperationVerifier


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ══════════════════════════════════════════════
# JianYingProcess
# ══════════════════════════════════════════════

class TestJianYingProcessInit:
    def test_custom_exe_path(self):
        proc = JianYingProcess(exe_path="C:/custom/JianyingPro.exe")
        assert proc._exe_path == "C:/custom/JianyingPro.exe"

    @patch("jy_auto_editor.drivers.gui_controller.process.Path.exists", return_value=False)
    def test_auto_detect_not_found(self, mock_exists):
        proc = JianYingProcess()
        # If no default path exists and no registry, exe_path may be empty
        # Just verify it doesn't crash
        assert isinstance(proc._exe_path, str)


class TestJianYingProcessIsRunning:
    @patch("subprocess.run")
    def test_is_running_true(self, mock_run):
        mock_run.return_value = MagicMock(stdout="JianyingPro.exe  1234  Console  1  100,000 K")
        proc = JianYingProcess(exe_path="C:/fake.exe")
        assert proc.is_running() is True

    @patch("subprocess.run")
    def test_is_running_false(self, mock_run):
        mock_run.return_value = MagicMock(stdout="INFO: No tasks are running.")
        proc = JianYingProcess(exe_path="C:/fake.exe")
        assert proc.is_running() is False

    @patch("subprocess.run", side_effect=Exception("tasklist failed"))
    def test_is_running_error(self, mock_run):
        proc = JianYingProcess(exe_path="C:/fake.exe")
        assert proc.is_running() is False


class TestJianYingProcessLaunch:
    @patch("subprocess.run")
    def test_launch_already_running(self, mock_run):
        mock_run.return_value = MagicMock(stdout="JianyingPro.exe running")
        proc = JianYingProcess(exe_path="C:/fake.exe")
        assert proc.launch() is True

    @patch("subprocess.Popen")
    @patch("subprocess.run")
    def test_launch_exe_not_found(self, mock_run, mock_popen):
        mock_run.return_value = MagicMock(stdout="No tasks running")
        proc = JianYingProcess(exe_path="/nonexistent/path.exe")
        with pytest.raises(GUIControllerError, match="not found"):
            proc.launch()

    @patch("jy_auto_editor.drivers.gui_controller.process.Path.exists", return_value=True)
    @patch("subprocess.run")
    def test_launch_success_no_wait(self, mock_run, mock_exists):
        # First call: is_running → not running
        mock_run.return_value = MagicMock(stdout="No tasks running")
        mock_popen = MagicMock()
        with patch("subprocess.Popen", return_value=mock_popen):
            proc = JianYingProcess(exe_path="C:/JianyingPro.exe")
            result = proc.launch(wait=False)
            assert result is True


class TestJianYingProcessClose:
    def test_close_with_process(self):
        proc = JianYingProcess(exe_path="C:/fake.exe")
        mock_popen = MagicMock()
        proc._process = mock_popen
        assert proc.close(force=False) is True
        mock_popen.terminate.assert_called_once()

    @patch("subprocess.run")
    def test_close_force(self, mock_run):
        mock_run.return_value = MagicMock()
        proc = JianYingProcess(exe_path="C:/fake.exe")
        assert proc.close(force=True) is True

    def test_close_no_process(self):
        proc = JianYingProcess(exe_path="C:/fake.exe")
        # No _process set, not force → no action but still returns True
        assert proc.close(force=False) is True


class TestJianYingProcessOpenProject:
    @patch("subprocess.run")
    def test_open_project(self, mock_run):
        mock_run.return_value = MagicMock(stdout="JianyingPro.exe running")
        proc = JianYingProcess(exe_path="C:/fake.exe")
        result = proc.open_project("/path/to/project")
        assert result is True


# ══════════════════════════════════════════════
# UIElementFinder
# ══════════════════════════════════════════════

class TestUIElementFinderInit:
    @patch("jy_auto_editor.drivers.gui_controller.finder.UIElementFinder._init_uiautomation")
    def test_init_without_uiautomation(self, mock_init):
        finder = UIElementFinder()
        finder._uia = None
        with pytest.raises(ElementNotFoundError, match="uiautomation not available"):
            finder.find_window()


class TestUIElementFinderFindWindow:
    def test_find_window_success(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        mock_uia = MagicMock()
        mock_window = MagicMock()
        mock_window.Exists.return_value = True
        mock_uia.WindowControl.return_value = mock_window
        finder._uia = mock_uia

        result = finder.find_window("剪映", timeout=1.0)
        assert result == mock_window

    def test_find_window_timeout(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        mock_uia = MagicMock()
        mock_window = MagicMock()
        mock_window.Exists.return_value = False
        mock_uia.WindowControl.return_value = mock_window
        finder._uia = mock_uia

        with pytest.raises(ElementNotFoundError, match="not found"):
            finder.find_window("剪映", timeout=0.1)

    def test_find_window_no_uia(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        finder._uia = None
        with pytest.raises(ElementNotFoundError, match="not available"):
            finder.find_window()


class TestUIElementFinderFindElement:
    def test_find_element_by_name(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        mock_uia = MagicMock()
        finder._uia = mock_uia

        mock_parent = MagicMock()
        mock_element = MagicMock()
        mock_element.Exists.return_value = True
        mock_parent.ElementControl.return_value = mock_element

        result = finder.find_element(mock_parent, name="导出", timeout=1.0)
        assert result == mock_element

    def test_find_element_not_found(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        mock_uia = MagicMock()
        finder._uia = mock_uia

        mock_parent = MagicMock()
        mock_element = MagicMock()
        mock_element.Exists.return_value = False
        mock_parent.ElementControl.return_value = mock_element

        with pytest.raises(ElementNotFoundError):
            finder.find_element(mock_parent, name="Missing", timeout=0.1)

    def test_find_element_no_uia(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        finder._uia = None
        with pytest.raises(ElementNotFoundError, match="not available"):
            finder.find_element(MagicMock(), name="test")


class TestUIElementFinderHelpers:
    def test_find_button_no_uia(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        finder._uia = None
        with pytest.raises(ElementNotFoundError):
            finder.find_button(MagicMock(), name="OK")

    def test_find_edit_no_uia(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        finder._uia = None
        with pytest.raises(ElementNotFoundError):
            finder.find_edit(MagicMock(), name="Input")

    def test_wait_for_element_delegates(self):
        finder = UIElementFinder.__new__(UIElementFinder)
        mock_uia = MagicMock()
        finder._uia = mock_uia

        mock_parent = MagicMock()
        mock_element = MagicMock()
        mock_element.Exists.return_value = True
        mock_parent.ElementControl.return_value = mock_element

        result = finder.wait_for_element(mock_parent, name="test", timeout=1.0)
        assert result == mock_element


# ══════════════════════════════════════════════
# ActionExecutor
# ══════════════════════════════════════════════

class TestActionExecutorClick:
    def test_click_success(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        _run(executor.click(mock_element, retries=1))
        mock_element.Click.assert_called_once()

    def test_click_retry_then_success(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        # Fail first, succeed second
        mock_element.Click.side_effect = [Exception("fail"), None]
        _run(executor.click(mock_element, retries=2))
        assert mock_element.Click.call_count == 2

    def test_click_all_retries_fail(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        mock_element.Click.side_effect = Exception("always fails")
        with pytest.raises(GUIControllerError, match="Click failed"):
            _run(executor.click(mock_element, retries=2))


class TestActionExecutorDoubleClick:
    def test_double_click(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        _run(executor.double_click(mock_element))
        mock_element.DoubleClick.assert_called_once()


class TestActionExecutorRightClick:
    def test_right_click(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        _run(executor.right_click(mock_element))
        mock_element.RightClick.assert_called_once()


class TestActionExecutorInputText:
    def test_input_text_with_clear(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        _run(executor.input_text(mock_element, "hello", clear_first=True))
        mock_element.SelectAll.assert_called_once()
        mock_element.SendKeys.assert_called_once_with("hello")

    def test_input_text_without_clear(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        _run(executor.input_text(mock_element, "hello", clear_first=False))
        mock_element.SelectAll.assert_not_called()
        mock_element.SendKeys.assert_called_once_with("hello")


class TestActionExecutorDrag:
    def test_drag(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        _run(executor.drag(mock_element, 100, 200))
        mock_element.Drag.assert_called_once_with(100, 200)


class TestActionExecutorSetValue:
    def test_set_value(self):
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        mock_element = MagicMock()
        mock_pattern = MagicMock()
        mock_element.GetValuePattern.return_value = mock_pattern
        _run(executor.set_value(mock_element, "new_value"))
        mock_pattern.SetValue.assert_called_once_with("new_value")


class TestActionExecutorPressKey:
    def test_press_key_import_error(self):
        """When uiautomation is not importable"""
        mock_finder = MagicMock()
        executor = ActionExecutor(mock_finder)
        # The press_key method does a local import of uiautomation
        with patch.dict("sys.modules", {"uiautomation": None}):
            with pytest.raises((GUIControllerError, ImportError, TypeError)):
                _run(executor.press_key("Ctrl+S"))


# ══════════════════════════════════════════════
# ExportTrigger
# ══════════════════════════════════════════════

class TestExportTrigger:
    def test_trigger_export_success(self, tmp_path):
        output_file = tmp_path / "output.mp4"
        output_file.write_bytes(b"\x00" * 1000)

        mock_finder = MagicMock()
        mock_executor = MagicMock()
        mock_window = MagicMock()
        mock_finder.find_window.return_value = mock_window
        mock_finder.find_element.return_value = MagicMock()
        mock_finder.find_button.return_value = MagicMock()

        # Mock press_key and click as async no-ops
        async def noop(*args, **kwargs):
            pass
        mock_executor.press_key = noop
        mock_executor.click = noop

        trigger = ExportTrigger(mock_finder, mock_executor)
        result = _run(trigger.trigger_export(str(output_file), timeout=1))

        assert isinstance(result, ExportResult)
        assert result.success is True
        assert result.output_path == str(output_file)

    def test_trigger_export_timeout(self, tmp_path):
        output_file = tmp_path / "output.mp4"
        # File does not exist → will timeout

        mock_finder = MagicMock()
        mock_executor = MagicMock()
        mock_finder.find_window.return_value = MagicMock()
        mock_finder.find_element.return_value = MagicMock()
        mock_finder.find_button.return_value = MagicMock()

        async def noop(*args, **kwargs):
            pass
        mock_executor.press_key = noop
        mock_executor.click = noop

        trigger = ExportTrigger(mock_finder, mock_executor)
        result = _run(trigger.trigger_export(str(output_file), timeout=1))
        assert result.success is False

    def test_trigger_export_exception(self):
        mock_finder = MagicMock()
        mock_finder.find_window.side_effect = Exception("window not found")
        mock_executor = MagicMock()

        trigger = ExportTrigger(mock_finder, mock_executor)
        result = _run(trigger.trigger_export("/tmp/out.mp4", timeout=1))
        assert result.success is False
        assert "window not found" in result.error_message


class TestExportTriggerWaitForExport:
    def test_wait_file_appears(self, tmp_path):
        output = tmp_path / "out.mp4"
        output.write_bytes(b"\x00" * 100)

        trigger = ExportTrigger(MagicMock(), MagicMock())
        result = _run(trigger._wait_for_export(output, timeout=5))
        assert result is True

    def test_wait_timeout(self, tmp_path):
        output = tmp_path / "nonexistent.mp4"
        trigger = ExportTrigger(MagicMock(), MagicMock())
        result = _run(trigger._wait_for_export(output, timeout=1))
        assert result is False


# ══════════════════════════════════════════════
# OperationVerifier
# ══════════════════════════════════════════════

class TestOperationVerifier:
    def test_verify_element_exists_true(self):
        verifier = OperationVerifier()
        mock_element = MagicMock()
        mock_element.Exists.return_value = True
        assert verifier.verify_element_exists(mock_element) is True

    def test_verify_element_exists_false(self):
        verifier = OperationVerifier()
        mock_element = MagicMock()
        mock_element.Exists.return_value = False
        assert verifier.verify_element_exists(mock_element) is False

    def test_verify_element_exists_exception(self):
        verifier = OperationVerifier()
        mock_element = MagicMock()
        mock_element.Exists.side_effect = Exception("UI error")
        assert verifier.verify_element_exists(mock_element) is False

    def test_verify_text_content_match(self):
        verifier = OperationVerifier()
        mock_element = MagicMock()
        mock_element.Name = "导出视频"
        assert verifier.verify_text_content(mock_element, "导出") is True

    def test_verify_text_content_no_match(self):
        verifier = OperationVerifier()
        mock_element = MagicMock()
        mock_element.Name = "导入"
        assert verifier.verify_text_content(mock_element, "导出") is False

    def test_verify_text_content_exception(self):
        verifier = OperationVerifier()
        mock_element = MagicMock(spec=[])  # No attributes
        assert verifier.verify_text_content(mock_element, "test") is False

    def test_verify_export_dialog(self):
        verifier = OperationVerifier()
        mock_parent = MagicMock()
        mock_dialog = MagicMock()
        mock_dialog.Exists.return_value = True
        mock_parent.ElementControl.return_value = mock_dialog
        assert verifier.verify_export_dialog(mock_parent) is True

    def test_verify_export_dialog_not_found(self):
        verifier = OperationVerifier()
        mock_parent = MagicMock()
        mock_parent.ElementControl.side_effect = Exception("not found")
        assert verifier.verify_export_dialog(mock_parent) is False

    def test_take_screenshot_no_uia(self):
        verifier = OperationVerifier()
        with patch.dict("sys.modules", {"uiautomation": None}):
            result = verifier.take_screenshot("/tmp/shot.png")
            assert result is None
