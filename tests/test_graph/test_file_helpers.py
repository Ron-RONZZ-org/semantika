"""Tests for file_helpers.py — file copy/move/download/detect/delete."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from semantika.graph.file_helpers import (
    classify_attachment,
    copy_file,
    move_file,
    delete_file,
    detect_mime,
    get_file_size,
    is_managed_file,
    _files_root,
    _ensure_type_dir,
    _resolve_and_pin,
    _resolve_stem,
    _sanitize_filename,
)


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Redirect SEMANTIKA_DATA_DIR to an isolated temp path."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("SEMANTIKA_DATA_DIR", str(data_dir))

    # Also set XDG_* for lightercore's data_dir()
    monkeypatch.setenv("XDG_DATA_HOME", str(data_dir))
    return data_dir


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    """Create a sample text file for testing."""
    src = tmp_path / "test.txt"
    src.write_text("hello world")
    return src


@pytest.fixture
def sample_image(tmp_path: Path) -> Path:
    """Create a sample image file for testing."""
    src = tmp_path / "photo.jpg"
    src.write_text("fake jpeg data")
    return src


class TestClassifyAttachment:
    def test_jpg_is_img(self):
        assert classify_attachment(Path("photo.jpg")) == "img"

    def test_png_is_img(self):
        assert classify_attachment(Path("image.png")) == "img"

    def test_svg_is_img(self):
        assert classify_attachment(Path("vector.svg")) == "img"

    def test_mp4_is_vid(self):
        assert classify_attachment(Path("video.mp4")) == "vid"

    def test_pdf_is_doc(self):
        assert classify_attachment(Path("doc.pdf")) == "doc"

    def test_txt_is_doc(self):
        assert classify_attachment(Path("notes.txt")) == "doc"

    def test_unknown_extension_defaults_to_doc(self):
        assert classify_attachment(Path("data.bin")) == "doc"

    def test_no_extension_defaults_to_doc(self):
        assert classify_attachment(Path("README")) == "doc"

    def test_case_insensitive(self):
        assert classify_attachment(Path("Photo.JPG")) == "img"
        assert classify_attachment(Path("Video.MP4")) == "vid"


class TestDetectMime:
    def test_txt(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert detect_mime(f) == "text/plain"

    def test_jpg(self, tmp_path: Path):
        f = tmp_path / "photo.jpg"
        f.write_text("data")
        assert detect_mime(f) == "image/jpeg"

    def test_png(self, tmp_path: Path):
        f = tmp_path / "img.png"
        f.write_text("data")
        assert detect_mime(f) == "image/png"

    def test_pdf(self, tmp_path: Path):
        f = tmp_path / "doc.pdf"
        f.write_text("data")
        assert detect_mime(f) == "application/pdf"

    def test_unknown(self, tmp_path: Path):
        f = tmp_path / "data.foobarxyz"
        f.write_text("data")
        mime = detect_mime(f)
        assert mime == "application/octet-stream", f"Got {mime}"


class TestGetFileSize:
    def test_existing_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        assert get_file_size(f) == 5

    def test_nonexistent_file_returns_zero(self, tmp_path: Path):
        assert get_file_size(tmp_path / "nonexistent.txt") == 0


class TestResolveStem:
    def test_preserves_extension(self, tmp_path: Path):
        src = tmp_path / "test.txt"
        result = _resolve_stem("NODE1", src)
        assert result == "NODE1.txt"

    def test_no_extension(self, tmp_path: Path):
        src = tmp_path / "README"
        result = _resolve_stem("NODE1", src)
        assert result == "NODE1"


class TestEnsureTypeDir:
    def test_creates_subdirectory(self):
        d = _ensure_type_dir("img")
        assert d.exists()
        assert d.name == "img"

    def test_returns_path_under_files_root(self):
        d = _ensure_type_dir("doc")
        root = _files_root()
        assert str(d).startswith(str(root))

    def test_unknown_type_falls_back_to_doc(self):
        d = _ensure_type_dir("unknown")
        assert d.name == "doc"


class TestCopyFile:
    def test_copies_file(self, sample_file: Path):
        dest = copy_file(sample_file, "NODE1")
        assert dest.exists()
        assert dest.read_text() == "hello world"
        # Original still exists
        assert sample_file.exists()

    def test_auto_detect_type(self, sample_image: Path):
        dest = copy_file(sample_image, "PHOTO1")
        assert dest.exists()
        # Should be under img/ subdirectory
        assert "img" in str(dest.parent)

    def test_specified_type(self, sample_file: Path):
        dest = copy_file(sample_file, "NODE1", attachment_type="doc")
        assert dest.exists()
        assert "doc" in str(dest.parent)

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            copy_file(tmp_path / "nonexistent.txt", "NODE1")


class TestMoveFile:
    def test_moves_file(self, sample_file: Path):
        dest = move_file(sample_file, "NODE1")
        assert dest.exists()
        assert dest.read_text() == "hello world"
        # Original no longer exists
        assert not sample_file.exists()

    def test_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            move_file(tmp_path / "nonexistent.txt", "NODE1")


class TestDeleteFile:
    def test_deletes_existing_file(self, tmp_path: Path):
        f = tmp_path / "to-delete.txt"
        f.write_text("data")
        delete_file(f)
        assert not f.exists()

    def test_missing_file_succeeds_silently(self, tmp_path: Path):
        delete_file(tmp_path / "nonexistent.txt")  # Should not raise


class TestIsManagedFile:
    def test_file_under_root_is_managed(self, sample_file: Path):
        copy_file(sample_file, "MANAGED")
        dest = _files_root() / "doc" / "MANAGED.txt"
        assert is_managed_file(dest)

    def test_file_outside_root_is_not_managed(self, tmp_path: Path):
        assert not is_managed_file(tmp_path / "outside.txt")

    def test_nonexistent_file_not_managed(self, tmp_path: Path):
        assert not is_managed_file(tmp_path / "nonexistent.txt")


class TestSanitizeFilename:
    """_sanitize_filename strips path-traversal sequences."""

    def test_null_bytes_removed(self):
        assert _sanitize_filename("foo\x00bar") == "foobar"

    def test_path_separators_replaced(self):
        assert "/" not in _sanitize_filename("a/b/c")
        assert "\\" not in _sanitize_filename("a\\b\\c")

    def test_dot_dot_sequences_replaced(self):
        """Any ``..`` (or longer) sequence is replaced."""
        assert ".." not in _sanitize_filename("foo../bar")
        assert ".." not in _sanitize_filename("abc..def")

    def test_leading_dots_stripped(self):
        assert not _sanitize_filename("...hidden").startswith(".")

    def test_leading_dashes_stripped(self):
        assert not _sanitize_filename("-hidden").startswith("-")

    def test_empty_returns_unnamed(self):
        assert _sanitize_filename("") == "unnamed"

    def test_safe_passthrough(self):
        assert _sanitize_filename("hello") == "hello"


class TestResolveAndPin:
    """_resolve_and_pin validates URL scheme and resolves hostname.

    DNS resolution is tested via monkeypatching to avoid network dependencies.
    """

    def test_rejects_unsupported_scheme(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            _resolve_and_pin("ftp://example.com/file")

    def test_rejects_non_url(self):
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            _resolve_and_pin("not-a-url")

    def test_resolves_and_pins(self, monkeypatch: pytest.MonkeyPatch):
        """Hostname is resolved to IP and pinned."""
        import socket as _socket

        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, "", ("93.184.216.34", port))]  # example.com IP

        monkeypatch.setattr(_socket, "getaddrinfo", fake_getaddrinfo)
        pinned_url, host_header = _resolve_and_pin("http://example.com/file.txt")
        assert "93.184.216.34" in pinned_url
        assert host_header == "example.com"

    def test_rejects_private_ip(self, monkeypatch: pytest.MonkeyPatch):
        """Private/reserved IPs are blocked."""
        import socket as _socket

        def fake_getaddrinfo(host, port, *args, **kwargs):
            return [(2, 1, 6, "", ("127.0.0.1", port))]

        monkeypatch.setattr(_socket, "getaddrinfo", fake_getaddrinfo)
        with pytest.raises(ValueError, match="private/reserved IP"):
            _resolve_and_pin("http://internal.local/secret")


class TestFilesRoot:
    def test_returns_path(self):
        root = _files_root()
        assert isinstance(root, Path)
        assert root.exists()
        assert root.name == "files"
