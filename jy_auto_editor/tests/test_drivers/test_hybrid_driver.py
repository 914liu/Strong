"""HybridDriver 与 DriverInterface 单元测试"""

import asyncio
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from jy_auto_editor.core.config import DriverConfig
from jy_auto_editor.core.exceptions import DriverError
from jy_auto_editor.core.models import (
    CanvasConfig,
    ExportConfig,
    ExportResult,
    SubtitleBlock,
    TimeRange,
    TrackType,
    VideoProject,
)
from jy_auto_editor.drivers.draft_engine.schema import (
    DraftContentModel,
    DraftMetaInfoModel,
)
from jy_auto_editor.drivers.hybrid_driver import HybridDriver
from jy_auto_editor.drivers.interface import DriverInterface


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ══════════════════════════════════════════════
# DriverInterface (ABC)
# ══════════════════════════════════════════════

class TestDriverInterface:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            DriverInterface()

    def test_hybrid_driver_is_subclass(self):
        assert issubclass(HybridDriver, DriverInterface)

    def test_all_abstract_methods_implemented(self):
        """HybridDriver should implement all abstract methods"""
        driver = HybridDriver.__new__(HybridDriver)
        abstract_methods = DriverInterface.__abstractmethods__
        for method_name in abstract_methods:
            assert hasattr(HybridDriver, method_name), f"Missing implementation: {method_name}"


# ══════════════════════════════════════════════
# HybridDriver — Initialization
# ══════════════════════════════════════════════

class TestHybridDriverInit:
    def test_default_config(self):
        driver = HybridDriver()
        assert driver._config is not None
        assert driver._current_draft is None
        assert driver._current_project_dir is None
        assert driver._process is None  # GUI lazy

    def test_custom_config(self):
        config = DriverConfig(draft_root="/custom/drafts", gui_timeout=600)
        driver = HybridDriver(config)
        assert driver._config.draft_root == "/custom/drafts"
        assert driver._config.gui_timeout == 600

    def test_gui_lazy_init(self):
        driver = HybridDriver()
        assert driver._process is None
        assert driver._finder is None
        assert driver._executor is None
        assert driver._export_trigger is None


# ══════════════════════════════════════════════
# HybridDriver — No Project Open Errors
# ══════════════════════════════════════════════

class TestHybridDriverNoProject:
    def test_get_material_mgr_no_project(self):
        driver = HybridDriver()
        with pytest.raises(DriverError, match="No project open"):
            driver._get_material_mgr()

    def test_get_track_mgr_no_project(self):
        driver = HybridDriver()
        with pytest.raises(DriverError, match="No project open"):
            driver._get_track_mgr()

    def test_get_segment_op_no_project(self):
        driver = HybridDriver()
        with pytest.raises(DriverError, match="No project open"):
            driver._get_segment_op()


# ══════════════════════════════════════════════
# HybridDriver — Project Management
# ══════════════════════════════════════════════

class TestHybridDriverCreateProject:
    def test_create_project(self, tmp_path):
        config = DriverConfig(draft_root=str(tmp_path))
        driver = HybridDriver(config)

        project_id = _run(driver.create_project("Test Project"))
        assert project_id
        assert driver._current_draft is not None
        assert driver._current_draft.name == "Test Project"
        assert driver._current_project_dir is not None
        assert (driver._current_project_dir / "draft_content.json").exists()

    def test_create_project_with_canvas(self, tmp_path):
        config = DriverConfig(draft_root=str(tmp_path))
        driver = HybridDriver(config)
        canvas = CanvasConfig.vertical()

        project_id = _run(driver.create_project("Vertical", canvas))
        assert driver._current_draft.canvas_config.width == 1080
        assert driver._current_draft.canvas_config.height == 1920


class TestHybridDriverOpenProject:
    def test_open_project(self, tmp_path):
        # Create a project first
        draft_data = {
            "id": "P1",
            "name": "Existing",
            "canvas_config": {"width": 1920, "height": 1080, "ratio": "16:9"},
            "materials": {"videos": [], "audios": [], "texts": []},
            "tracks": [],
        }
        (tmp_path / "draft_content.json").write_text(
            json.dumps(draft_data), encoding="utf-8"
        )

        driver = HybridDriver()
        # Mock crypto to avoid actual encryption
        driver._crypto = MagicMock()
        driver._crypto.ensure_decrypted.return_value = (
            tmp_path / "draft_content.json", False
        )
        driver._reader = MagicMock()
        mock_draft = DraftContentModel.model_validate(draft_data)
        driver._reader.read.return_value = mock_draft
        driver._reader.to_domain_model.return_value = VideoProject(
            project_id="P1", name="Existing"
        )

        project = _run(driver.open_project(str(tmp_path)))
        assert project.project_id == "P1"
        assert driver._current_draft is not None


class TestHybridDriverSaveProject:
    def test_save_project_no_dir(self):
        driver = HybridDriver()
        with pytest.raises(DriverError, match="No project directory"):
            _run(driver.save_project(VideoProject(project_id="P1", name="Test")))

    def test_save_project(self, tmp_path):
        driver = HybridDriver()
        driver._current_project_dir = tmp_path
        driver._crypto = MagicMock()
        driver._crypto.is_encrypted.return_value = False

        project = VideoProject(project_id="P1", name="Test")
        result = _run(driver.save_project(project))
        assert result == str(tmp_path)


class TestHybridDriverListProjects:
    def test_list_projects_empty(self, tmp_path):
        config = DriverConfig(draft_root=str(tmp_path))
        driver = HybridDriver(config)
        projects = _run(driver.list_projects())
        assert projects == []

    def test_list_projects_nonexistent_root(self):
        config = DriverConfig(draft_root="/nonexistent/path")
        driver = HybridDriver(config)
        projects = _run(driver.list_projects())
        assert projects == []

    def test_list_projects_with_project(self, tmp_path):
        project_dir = tmp_path / "proj1"
        project_dir.mkdir()
        meta_data = {
            "draft_id": "D1",
            "draft_name": "My Project",
            "tm_draft_modified": 12345,
        }
        (project_dir / "draft_content.json").write_text("{}")
        (project_dir / "draft_meta_info.json").write_text(json.dumps(meta_data))

        config = DriverConfig(draft_root=str(tmp_path))
        driver = HybridDriver(config)
        driver._crypto = MagicMock()
        driver._crypto.ensure_decrypted.return_value = (
            project_dir / "draft_content.json", False
        )

        projects = _run(driver.list_projects())
        assert len(projects) == 1
        assert projects[0]["name"] == "My Project"
        assert projects[0]["id"] == "D1"


# ══════════════════════════════════════════════
# HybridDriver — Media Operations
# ══════════════════════════════════════════════

class TestHybridDriverImportMedia:
    def _setup_driver_with_project(self, tmp_path):
        driver = HybridDriver()
        driver._current_draft = DraftContentModel(id="P1", name="Test")
        driver._current_project_dir = tmp_path
        return driver

    def test_import_video(self, tmp_path):
        driver = self._setup_driver_with_project(tmp_path)
        ids = _run(driver.import_media("P1", ["/tmp/clip.mp4"]))
        assert len(ids) == 1
        # Path normalizes separators per platform
        assert "clip.mp4" in driver._current_draft.materials.videos[0].path

    def test_import_image(self, tmp_path):
        driver = self._setup_driver_with_project(tmp_path)
        ids = _run(driver.import_media("P1", ["/tmp/photo.png"]))
        assert len(ids) == 1
        # Images are stored as video materials with type "photo"
        assert driver._current_draft.materials.videos[0].type == "photo"

    def test_import_audio(self, tmp_path):
        driver = self._setup_driver_with_project(tmp_path)
        ids = _run(driver.import_media("P1", ["/tmp/bgm.mp3"]))
        assert len(ids) == 1
        assert "bgm.mp3" in driver._current_draft.materials.audios[0].path

    def test_import_unknown_ext(self, tmp_path):
        driver = self._setup_driver_with_project(tmp_path)
        ids = _run(driver.import_media("P1", ["/tmp/file.xyz"]))
        assert len(ids) == 1
        # Unknown extensions default to video
        assert "file.xyz" in driver._current_draft.materials.videos[0].path

    def test_import_multiple(self, tmp_path):
        driver = self._setup_driver_with_project(tmp_path)
        ids = _run(driver.import_media("P1", ["/tmp/a.mp4", "/tmp/b.mp3", "/tmp/c.png"]))
        assert len(ids) == 3


class TestHybridDriverAddToTimeline:
    def test_add_to_timeline(self, tmp_path):
        driver = HybridDriver()
        driver._current_draft = DraftContentModel(id="P1", name="Test")
        driver._current_project_dir = tmp_path

        # Add a material first
        mgr = driver._get_material_mgr()
        mid = mgr.add_video("/tmp/v.mp4", duration=10_000_000)

        seg_id = _run(driver.add_to_timeline("P1", mid, TrackType.VIDEO, position_us=0))
        assert seg_id
        assert len(driver._current_draft.tracks) == 1
        assert len(driver._current_draft.tracks[0].segments) == 1


# ══════════════════════════════════════════════
# HybridDriver — Edit Operations
# ══════════════════════════════════════════════

class TestHybridDriverEditOps:
    def _setup_with_segment(self, tmp_path):
        from jy_auto_editor.drivers.draft_engine.schema import (
            SegmentModel,
            TimeRangeModel,
            TrackModel,
        )
        driver = HybridDriver()
        draft = DraftContentModel(id="P1", name="Test")
        track = TrackModel(id="T1", type="video")
        seg = SegmentModel(
            id="S1",
            material_id="M1",
            source_timerange=TimeRangeModel(start=0, duration=10_000_000),
            target_timerange=TimeRangeModel(start=0, duration=10_000_000),
            speed=1.0,
            volume=1.0,
        )
        track.segments.append(seg)
        draft.tracks.append(track)
        driver._current_draft = draft
        driver._current_project_dir = tmp_path
        return driver

    def test_split_segment(self, tmp_path):
        driver = self._setup_with_segment(tmp_path)
        s1, s2 = _run(driver.split_segment("P1", "S1", 5_000_000))
        assert s1 == "S1"
        assert s2 != s1

    def test_delete_segment(self, tmp_path):
        driver = self._setup_with_segment(tmp_path)
        _run(driver.delete_segment("P1", "S1"))
        assert len(driver._current_draft.tracks[0].segments) == 0

    def test_trim_segment(self, tmp_path):
        driver = self._setup_with_segment(tmp_path)
        _run(driver.trim_segment("P1", "S1", 2_000_000, 8_000_000))
        seg = driver._current_draft.tracks[0].segments[0]
        assert seg.source_timerange.start == 2_000_000
        assert seg.source_timerange.duration == 6_000_000

    def test_set_speed(self, tmp_path):
        driver = self._setup_with_segment(tmp_path)
        _run(driver.set_speed("P1", "S1", 2.0))
        seg = driver._current_draft.tracks[0].segments[0]
        assert seg.speed == 2.0
        assert seg.target_timerange.duration == 5_000_000

    def test_set_volume(self, tmp_path):
        driver = self._setup_with_segment(tmp_path)
        _run(driver.set_volume("P1", "S1", 0.5))
        seg = driver._current_draft.tracks[0].segments[0]
        assert seg.volume == 0.5


class TestHybridDriverAddText:
    def test_add_text(self, tmp_path):
        driver = HybridDriver()
        driver._current_draft = DraftContentModel(id="P1", name="Test")
        driver._current_project_dir = tmp_path

        subtitle = SubtitleBlock(
            text="你好",
            time_range=TimeRange(start_us=0, duration_us=3_000_000),
            font_name="微软雅黑",
            font_size=12.0,
        )
        seg_id = _run(driver.add_text("P1", subtitle))
        assert seg_id
        assert len(driver._current_draft.materials.texts) == 1
        assert driver._current_draft.materials.texts[0].content == "你好"
        assert len(driver._current_draft.tracks) == 1


# ══════════════════════════════════════════════
# HybridDriver — Track Operations
# ══════════════════════════════════════════════

class TestHybridDriverTrackOps:
    def test_add_track(self, tmp_path):
        driver = HybridDriver()
        driver._current_draft = DraftContentModel(id="P1", name="Test")
        driver._current_project_dir = tmp_path

        track_id = _run(driver.add_track("P1", TrackType.VIDEO))
        assert track_id
        assert len(driver._current_draft.tracks) == 1

    def test_delete_track(self, tmp_path):
        driver = HybridDriver()
        driver._current_draft = DraftContentModel(id="P1", name="Test")
        driver._current_project_dir = tmp_path

        track_id = _run(driver.add_track("P1", TrackType.VIDEO))
        _run(driver.delete_track("P1", track_id))
        assert len(driver._current_draft.tracks) == 0


# ══════════════════════════════════════════════
# HybridDriver — Export
# ══════════════════════════════════════════════

class TestHybridDriverExport:
    def test_export_gui_disabled(self, tmp_path):
        config = DriverConfig(use_gui_export=False)
        driver = HybridDriver(config)
        driver._current_project = VideoProject(project_id="P1", name="Test")
        driver._current_project_dir = tmp_path
        driver._crypto = MagicMock()
        driver._crypto.is_encrypted.return_value = False

        export_config = ExportConfig(output_path="/tmp/out.mp4")
        result = _run(driver.export_video("P1", export_config))
        assert result.success is False
        assert "GUI export disabled" in result.error_message

    @patch.object(HybridDriver, "_ensure_gui")
    def test_export_launches_gui(self, mock_ensure_gui, tmp_path):
        config = DriverConfig(use_gui_export=True)
        driver = HybridDriver(config)
        driver._current_project = VideoProject(project_id="P1", name="Test")
        driver._current_project_dir = tmp_path
        driver._crypto = MagicMock()
        driver._crypto.is_encrypted.return_value = False

        # Mock GUI components
        mock_process = MagicMock()
        mock_process.is_running.return_value = True
        driver._process = mock_process

        mock_trigger = MagicMock()
        mock_result = ExportResult(success=True, output_path="/tmp/out.mp4")
        mock_trigger.trigger_export = AsyncMock(return_value=mock_result)
        driver._export_trigger = mock_trigger

        export_config = ExportConfig(output_path="/tmp/out.mp4")
        result = _run(driver.export_video("P1", export_config))
        assert result.success is True

    def test_get_export_status(self):
        driver = HybridDriver()
        status = _run(driver.get_export_status("task123"))
        assert status["task_id"] == "task123"
        assert status["status"] == "unknown"


# ══════════════════════════════════════════════
# HybridDriver — Effect / Transition (stubs)
# ══════════════════════════════════════════════

class TestHybridDriverStubs:
    def test_add_effect_does_not_raise(self):
        driver = HybridDriver()
        # Should just log, not raise
        _run(driver.add_effect("P1", "S1", "blur", {"intensity": 0.5}))

    def test_add_transition_does_not_raise(self):
        driver = HybridDriver()
        _run(driver.add_transition("P1", "S1", "fade", 500_000))
