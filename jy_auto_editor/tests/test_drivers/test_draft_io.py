"""Draft I/O 单元测试 — DraftCrypto / DraftReader / DraftWriter"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jy_auto_editor.core.exceptions import DraftEncryptionError, DraftError
from jy_auto_editor.core.models import (
    AudioAsset,
    CanvasConfig,
    Segment,
    SubtitleBlock,
    TimeRange,
    Track,
    TrackType,
    VideoAsset,
    VideoProject,
)
from jy_auto_editor.drivers.draft_engine.crypto import DraftCrypto
from jy_auto_editor.drivers.draft_engine.reader import DraftReader
from jy_auto_editor.drivers.draft_engine.schema import (
    AudioMaterialModel,
    CanvasConfigModel,
    ClipTransformModel,
    DraftContentModel,
    DraftMetaInfoModel,
    MaterialsModel,
    PositionModel,
    SegmentModel,
    SizeModel,
    TextMaterialModel,
    TimeRangeModel,
    TrackModel,
    VideoMaterialModel,
)
from jy_auto_editor.drivers.draft_engine.writer import DraftWriter


# ══════════════════════════════════════════════
# DraftCrypto
# ══════════════════════════════════════════════

class TestDraftCryptoIsEncrypted:
    def test_plain_json(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_text('{"id": "test"}', encoding="utf-8")
        assert DraftCrypto.is_encrypted(draft) is False

    def test_encrypted_binary(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_bytes(b"\x00\x01\x02encrypted_data")
        assert DraftCrypto.is_encrypted(draft) is True

    def test_nonexistent_file(self, tmp_path):
        draft = tmp_path / "nonexistent.json"
        assert DraftCrypto.is_encrypted(draft) is False

    def test_empty_file(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_bytes(b"")
        # empty file → first_byte is b"" which != b"{"
        assert DraftCrypto.is_encrypted(draft) is True


class TestDraftCryptoDecrypt:
    def test_already_decrypted(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_text('{"id": "test"}')
        crypto = DraftCrypto(jy_draftc_path="/fake/jy-draftc")
        result = crypto.decrypt(draft)
        assert result == draft

    def test_decrypt_no_tool(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_bytes(b"\x00encrypted")
        crypto = DraftCrypto(jy_draftc_path="")
        with pytest.raises(DraftEncryptionError, match="jy-draftc not found"):
            crypto.decrypt(draft)

    @patch("subprocess.run")
    def test_decrypt_success(self, mock_run, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_bytes(b"\x00encrypted")
        mock_run.return_value = MagicMock(returncode=0)

        crypto = DraftCrypto(jy_draftc_path="/usr/bin/jy-draftc")
        result = crypto.decrypt(draft, backup=True)
        assert result == draft
        mock_run.assert_called_once()
        # backup should be created
        backup = tmp_path / "draft_content.json.encrypted"
        assert backup.exists()

    @patch("subprocess.run")
    def test_decrypt_failure(self, mock_run, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_bytes(b"\x00encrypted")
        mock_run.return_value = MagicMock(returncode=1, stderr="decrypt error")

        crypto = DraftCrypto(jy_draftc_path="/usr/bin/jy-draftc")
        with pytest.raises(DraftEncryptionError, match="decrypt failed"):
            crypto.decrypt(draft)

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_decrypt_tool_not_found(self, mock_run, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_bytes(b"\x00encrypted")

        crypto = DraftCrypto(jy_draftc_path="/bad/path")
        with pytest.raises(DraftEncryptionError, match="not found"):
            crypto.decrypt(draft)

    @patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="x", timeout=30))
    def test_decrypt_timeout(self, mock_run, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_bytes(b"\x00encrypted")

        crypto = DraftCrypto(jy_draftc_path="/usr/bin/jy-draftc")
        with pytest.raises(DraftEncryptionError, match="timed out"):
            crypto.decrypt(draft)


class TestDraftCryptoEncrypt:
    def test_encrypt_no_tool(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_text('{"id": "test"}')
        crypto = DraftCrypto(jy_draftc_path="")
        with pytest.raises(DraftEncryptionError, match="jy-draftc not available"):
            crypto.encrypt(draft)

    @patch("subprocess.run")
    def test_encrypt_success(self, mock_run, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_text('{"id": "test"}')
        mock_run.return_value = MagicMock(returncode=0)

        crypto = DraftCrypto(jy_draftc_path="/usr/bin/jy-draftc")
        result = crypto.encrypt(draft)
        assert result == draft

    @patch("subprocess.run")
    def test_encrypt_failure(self, mock_run, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_text('{"id": "test"}')
        mock_run.return_value = MagicMock(returncode=1, stderr="encrypt error")

        crypto = DraftCrypto(jy_draftc_path="/usr/bin/jy-draftc")
        with pytest.raises(DraftEncryptionError, match="encrypt failed"):
            crypto.encrypt(draft)


class TestDraftCryptoEnsureDecrypted:
    def test_already_plain(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_text('{"id": "test"}')
        crypto = DraftCrypto(jy_draftc_path="")
        path, was_enc = crypto.ensure_decrypted(draft)
        assert path == draft
        assert was_enc is False

    @patch("subprocess.run")
    def test_decrypts_encrypted(self, mock_run, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_bytes(b"\x00encrypted")
        mock_run.return_value = MagicMock(returncode=0)

        crypto = DraftCrypto(jy_draftc_path="/usr/bin/jy-draftc")
        path, was_enc = crypto.ensure_decrypted(draft)
        assert was_enc is True


class TestDraftCryptoRestore:
    def test_restore_backup(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        backup = tmp_path / "draft_content.json.encrypted"
        backup.write_bytes(b"\x00original_encrypted")
        draft.write_text('{"corrupted": true}')

        crypto = DraftCrypto()
        crypto.restore_encrypted_backup(draft)
        assert draft.read_bytes() == b"\x00original_encrypted"

    def test_restore_no_backup(self, tmp_path):
        draft = tmp_path / "draft_content.json"
        draft.write_text('{"id": "test"}')
        crypto = DraftCrypto()
        # Should not raise
        crypto.restore_encrypted_backup(draft)


# ══════════════════════════════════════════════
# DraftReader
# ══════════════════════════════════════════════

class TestDraftReaderRead:
    def test_read_success(self, tmp_path):
        draft_data = {
            "id": "PROJECT1",
            "name": "Test Project",
            "type": "draft",
            "canvas_config": {"width": 1920, "height": 1080, "ratio": "16:9"},
            "materials": {"videos": [], "audios": [], "texts": []},
            "tracks": [],
        }
        (tmp_path / "draft_content.json").write_text(
            json.dumps(draft_data), encoding="utf-8"
        )

        mock_crypto = MagicMock()
        mock_crypto.ensure_decrypted.return_value = (
            tmp_path / "draft_content.json", False
        )
        reader = DraftReader(crypto=mock_crypto)
        draft = reader.read(tmp_path)

        assert draft.id == "PROJECT1"
        assert draft.name == "Test Project"
        assert draft.canvas_config.width == 1920

    def test_read_not_found(self, tmp_path):
        mock_crypto = MagicMock()
        reader = DraftReader(crypto=mock_crypto)
        with pytest.raises(DraftError, match="not found"):
            reader.read(tmp_path)

    def test_read_invalid_json(self, tmp_path):
        (tmp_path / "draft_content.json").write_text("not json{{{", encoding="utf-8")
        mock_crypto = MagicMock()
        mock_crypto.ensure_decrypted.return_value = (
            tmp_path / "draft_content.json", False
        )
        reader = DraftReader(crypto=mock_crypto)
        with pytest.raises(DraftError, match="Invalid JSON"):
            reader.read(tmp_path)


class TestDraftReaderReadMeta:
    def test_read_meta_success(self, tmp_path):
        meta_data = {
            "draft_id": "D1",
            "draft_name": "My Draft",
            "tm_draft_create": 1000,
            "tm_draft_modified": 2000,
        }
        (tmp_path / "draft_meta_info.json").write_text(
            json.dumps(meta_data), encoding="utf-8"
        )
        reader = DraftReader()
        meta = reader.read_meta(tmp_path)
        assert meta.draft_id == "D1"
        assert meta.draft_name == "My Draft"
        assert meta.tm_draft_modified == 2000

    def test_read_meta_not_found(self, tmp_path):
        reader = DraftReader()
        with pytest.raises(DraftError, match="not found"):
            reader.read_meta(tmp_path)


class TestDraftReaderToDomainModel:
    def test_basic_conversion(self):
        draft = DraftContentModel(
            id="P1",
            name="Test",
            canvas_config=CanvasConfigModel(width=1920, height=1080, ratio="16:9"),
            materials=MaterialsModel(
                videos=[
                    VideoMaterialModel(id="V1", path="/tmp/v.mp4", type="video", name="clip1"),
                ],
                audios=[
                    AudioMaterialModel(id="A1", path="/tmp/a.mp3", name="bgm", duration=30_000_000),
                ],
                texts=[
                    TextMaterialModel(id="T1", content="你好", base_content="你好", font_name="微软雅黑"),
                ],
            ),
            tracks=[
                TrackModel(
                    id="TR1",
                    type="video",
                    render_index=0,
                    segments=[
                        SegmentModel(
                            id="S1",
                            material_id="V1",
                            source_timerange=TimeRangeModel(start=0, duration=5_000_000),
                            target_timerange=TimeRangeModel(start=0, duration=5_000_000),
                            speed=1.0,
                            volume=1.0,
                        ),
                    ],
                ),
            ],
        )

        reader = DraftReader()
        project = reader.to_domain_model(draft)

        assert project.project_id == "P1"
        assert project.name == "Test"
        assert project.timeline.canvas_config.width == 1920
        assert len(project.source_videos) == 1
        assert project.source_videos[0].asset_id == "V1"
        assert project.source_videos[0].path == "/tmp/v.mp4"
        assert len(project.source_audios) == 1
        assert project.source_audios[0].duration_us == 30_000_000
        assert len(project.timeline.tracks) == 1
        assert project.timeline.tracks[0].track_type == TrackType.VIDEO
        assert len(project.timeline.tracks[0].segments) == 1
        seg = project.timeline.tracks[0].segments[0]
        assert seg.segment_id == "S1"
        assert seg.material_id == "V1"
        assert seg.speed == 1.0
        assert len(project.subtitles) == 1
        assert project.subtitles[0].text == "你好"

    def test_empty_draft_conversion(self):
        draft = DraftContentModel(id="P2", name="Empty")
        reader = DraftReader()
        project = reader.to_domain_model(draft)
        assert project.project_id == "P2"
        assert len(project.source_videos) == 0
        assert len(project.timeline.tracks) == 0

    def test_parse_track_type(self):
        assert DraftReader._parse_track_type("video") == TrackType.VIDEO
        assert DraftReader._parse_track_type("audio") == TrackType.AUDIO
        assert DraftReader._parse_track_type("text") == TrackType.TEXT
        assert DraftReader._parse_track_type("effect") == TrackType.EFFECT
        assert DraftReader._parse_track_type("sticker") == TrackType.STICKER
        # Unknown defaults to VIDEO
        assert DraftReader._parse_track_type("unknown") == TrackType.VIDEO

    def test_segment_transform_conversion(self):
        draft = DraftContentModel(
            id="P3",
            name="Transform Test",
            tracks=[
                TrackModel(
                    id="TR1",
                    type="video",
                    segments=[
                        SegmentModel(
                            id="S1",
                            material_id="M1",
                            source_timerange=TimeRangeModel(start=100, duration=200),
                            target_timerange=TimeRangeModel(start=0, duration=200),
                            speed=1.0,
                            volume=0.8,
                            clip=ClipTransformModel(
                                alpha=0.9,
                                rotation=45.0,
                                scale=SizeModel(width=2.0, height=2.0),
                                transform=PositionModel(x=10.0, y=20.0),
                            ),
                        ),
                    ],
                ),
            ],
        )
        reader = DraftReader()
        project = reader.to_domain_model(draft)
        seg = project.timeline.tracks[0].segments[0]
        assert seg.alpha == 0.9
        assert seg.rotation == 45.0
        assert seg.scale_x == 2.0
        assert seg.scale_y == 2.0
        assert seg.position_x == 10.0
        assert seg.position_y == 20.0


class TestDraftReaderReadProject:
    def test_read_project(self, tmp_path):
        draft_data = {
            "id": "P1",
            "name": "Full Test",
            "canvas_config": {"width": 1280, "height": 720, "ratio": "16:9"},
            "materials": {"videos": [], "audios": [], "texts": []},
            "tracks": [],
        }
        (tmp_path / "draft_content.json").write_text(
            json.dumps(draft_data), encoding="utf-8"
        )
        mock_crypto = MagicMock()
        mock_crypto.ensure_decrypted.return_value = (
            tmp_path / "draft_content.json", False
        )
        reader = DraftReader(crypto=mock_crypto)
        project = reader.read_project(tmp_path)
        assert isinstance(project, VideoProject)
        assert project.project_id == "P1"
        assert project.name == "Full Test"


# ══════════════════════════════════════════════
# DraftWriter
# ══════════════════════════════════════════════

class TestDraftWriterSave:
    def test_save_creates_file(self, tmp_path):
        draft = DraftContentModel(id="P1", name="Test")
        mock_crypto = MagicMock()
        mock_crypto.is_encrypted.return_value = False

        writer = DraftWriter(crypto=mock_crypto)
        result = writer.save(draft, tmp_path)
        assert result == tmp_path / "draft_content.json"
        assert (tmp_path / "draft_content.json").exists()

        data = json.loads((tmp_path / "draft_content.json").read_text(encoding="utf-8"))
        assert data["id"] == "P1"
        assert data["name"] == "Test"

    def test_save_re_encrypts_if_was_encrypted(self, tmp_path):
        # File must exist first so is_encrypted() is actually called
        (tmp_path / "draft_content.json").write_bytes(b"\x00encrypted")
        draft = DraftContentModel(id="P1", name="Test")
        mock_crypto = MagicMock()
        mock_crypto.is_encrypted.return_value = True

        writer = DraftWriter(crypto=mock_crypto)
        writer.save(draft, tmp_path, re_encrypt=True)
        mock_crypto.encrypt.assert_called_once()

    def test_save_no_re_encrypt(self, tmp_path):
        (tmp_path / "draft_content.json").write_bytes(b"\x00encrypted")
        draft = DraftContentModel(id="P1", name="Test")
        mock_crypto = MagicMock()
        mock_crypto.is_encrypted.return_value = True

        writer = DraftWriter(crypto=mock_crypto)
        writer.save(draft, tmp_path, re_encrypt=False)
        mock_crypto.encrypt.assert_not_called()


class TestDraftWriterSaveMeta:
    def test_save_meta(self, tmp_path):
        meta = DraftMetaInfoModel(
            draft_id="D1",
            draft_name="My Draft",
            tm_draft_create=1000,
            tm_draft_modified=2000,
        )
        writer = DraftWriter()
        result = writer.save_meta(meta, tmp_path)
        assert result == tmp_path / "draft_meta_info.json"

        data = json.loads((tmp_path / "draft_meta_info.json").read_text(encoding="utf-8"))
        assert data["draft_id"] == "D1"
        assert data["draft_name"] == "My Draft"


class TestDraftWriterCreateNewProject:
    def test_create_new_project(self, tmp_path):
        project_dir = tmp_path / "new_project"
        writer = DraftWriter(crypto=MagicMock())
        draft, meta = writer.create_new_project(project_dir, name="Test Project")

        assert draft.name == "Test Project"
        assert draft.id
        assert draft.canvas_config.width == 1920
        assert draft.canvas_config.height == 1080
        assert meta.draft_name == "Test Project"
        assert meta.draft_id == draft.id
        assert (project_dir / "draft_content.json").exists()
        assert (project_dir / "draft_meta_info.json").exists()

    def test_create_new_project_custom_size(self, tmp_path):
        project_dir = tmp_path / "vertical"
        writer = DraftWriter(crypto=MagicMock())
        draft, _ = writer.create_new_project(project_dir, width=1080, height=1920)
        assert draft.canvas_config.width == 1080
        assert draft.canvas_config.height == 1920

    def test_create_new_project_square_ratio(self, tmp_path):
        project_dir = tmp_path / "square"
        writer = DraftWriter(crypto=MagicMock())
        draft, _ = writer.create_new_project(project_dir, width=1080, height=1080)
        assert draft.canvas_config.ratio == "1:1"


class TestDraftWriterFromDomainModel:
    def test_roundtrip(self, tmp_path):
        """VideoProject → DraftContentModel → save → read back"""
        project = VideoProject(project_id="P1", name="Round Trip")
        project.timeline.canvas_config = CanvasConfig(width=1920, height=1080, ratio="16:9")
        project.source_videos.append(VideoAsset(
            asset_id="V1", path="/tmp/v.mp4", media_type="video", name="clip"
        ))
        track = Track(track_id="T1", track_type=TrackType.VIDEO, render_index=0)
        track.segments.append(Segment(
            segment_id="S1",
            material_id="V1",
            source_range=TimeRange(start_us=0, duration_us=5_000_000),
            target_range=TimeRange(start_us=0, duration_us=5_000_000),
            speed=1.0,
            volume=1.0,
        ))
        project.timeline.add_track(track)
        project.subtitles.append(SubtitleBlock(text="你好", font_name="微软雅黑", font_size=12.0))

        mock_crypto = MagicMock()
        mock_crypto.is_encrypted.return_value = False
        writer = DraftWriter(crypto=mock_crypto)
        writer.from_domain_model(project, tmp_path)

        # Read back
        data = json.loads((tmp_path / "draft_content.json").read_text(encoding="utf-8"))
        assert data["id"] == "P1"
        assert data["name"] == "Round Trip"
        assert len(data["materials"]["videos"]) == 1
        assert data["materials"]["videos"][0]["id"] == "V1"
        assert len(data["tracks"]) == 1
        assert len(data["tracks"][0]["segments"]) == 1
        assert data["tracks"][0]["segments"][0]["id"] == "S1"
        assert len(data["materials"]["texts"]) == 1
        assert data["materials"]["texts"][0]["content"] == "你好"
