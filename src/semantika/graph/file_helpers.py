"""File management helpers for node attachments.

Provides copy/move/download/detect-mime operations for file attachments
attached to knowledge graph nodes via ``:hasFilePath``, ``:hasFileMime``,
``:hasFileSize``, and ``:hasFileSource`` triples.

Ported from A-semantika's ``_file_helpers.py``.
"""

from __future__ import annotations

import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Literal

import httpx

from semantika.core.paths import data_dir

logger = logging.getLogger(__name__)

_MIME_EXTENSIONS: dict[str, set[str]] = {
    "img": {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".bmp"},
    "vid": {".mp4", ".webm", ".avi", ".mov", ".mkv"},
    "doc": {".pdf", ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
            ".doc", ".docx", ".xls", ".xlsx", ".zip", ".tar", ".gz"},
}

# Subdirectory names for each attachment type
_ATTACHMENT_SUBDIRS: dict[str, str] = {
    "img": "img",
    "vid": "vid",
    "doc": "doc",
}


def _files_root() -> Path:
    """Return the root directory for all attachment files."""
    root = data_dir() / "semantika" / "files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ensure_type_dir(attachment_type: str) -> Path:
    """Return (creating if needed) the subdirectory for *attachment_type*.

    Args:
        attachment_type: One of ``"img"``, ``"vid"``, ``"doc"``.

    Returns:
        Path to the subdirectory (e.g. ``.../files/img/``).
    """
    sub = _ATTACHMENT_SUBDIRS.get(attachment_type, "doc")
    d = _files_root() / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def _resolve_stem(node_id: str, src: Path) -> str:
    """Return the filename stem for *node_id*, preserving source extension."""
    suffix = src.suffix.lower() if src.suffix else ""
    return f"{node_id}{suffix}"


def detect_mime(path: Path) -> str:
    """Detect MIME type from file extension.

    Args:
        path: Path to the file.

    Returns:
        MIME type string (e.g. ``"image/jpeg"``), or
        ``"application/octet-stream"`` if unknown.
    """
    mime_type, _ = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"


def get_file_size(path: Path) -> int:
    """Return file size in bytes.

    Args:
        path: Path to the file.

    Returns:
        File size in bytes, or 0 if the path does not exist.
    """
    try:
        return path.stat().st_size
    except OSError:
        return 0


def classify_attachment(path: Path) -> str:
    """Classify a file path into an attachment type by extension.

    Args:
        path: Path to the file.

    Returns:
        ``"img"``, ``"vid"``, or ``"doc"`` (fallback).
    """
    ext = path.suffix.lower()
    for atype, exts in _MIME_EXTENSIONS.items():
        if ext in exts:
            return atype
    return "doc"


def copy_file(src: Path, node_id: str, attachment_type: str | None = None) -> Path:
    """Copy *src* into the Semantika files directory.

    The destination filename is ``{node_id}{ext}``.

    Args:
        src: Source file path.
        node_id: Node ID (destination filename stem).
        attachment_type: One of ``"img"``, ``"vid"``, ``"doc"``.
            If None, auto-detected from extension.

    Returns:
        Destination path.

    Raises:
        FileNotFoundError: If *src* does not exist.
        OSError: If the copy fails.
    """
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    if attachment_type is None:
        attachment_type = classify_attachment(src)
    dest_dir = _ensure_type_dir(attachment_type)
    stem = _resolve_stem(node_id, src)
    dest = dest_dir / stem
    shutil.copy2(str(src), str(dest))
    return dest


def move_file(src: Path, node_id: str, attachment_type: str | None = None) -> Path:
    """Move *src* into the Semantika files directory.

    Same naming convention as :func:`copy_file`.

    Args:
        src: Source file path.
        node_id: Node ID (destination filename stem).
        attachment_type: One of ``"img"``, ``"vid"``, ``"doc"``.

    Returns:
        Destination path.

    Raises:
        FileNotFoundError: If *src* does not exist.
        OSError: If the move fails.
    """
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(f"File not found: {src}")
    if attachment_type is None:
        attachment_type = classify_attachment(src)
    dest_dir = _ensure_type_dir(attachment_type)
    stem = _resolve_stem(node_id, src)
    dest = dest_dir / stem
    shutil.move(str(src), str(dest))
    return dest


def download_file(
    url: str,
    node_id: str,
    attachment_type: str = "doc",
    max_size: int = 100 * 1024 * 1024,
) -> Path:
    """Download a URL into the Semantika files directory (sync version).

    For use in non-async contexts.  Use ``async_download_file`` inside
    async FastAPI routes to avoid blocking the event loop.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"Unsupported URL scheme: {url}")

    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        head_resp = client.head(url)
        _check_size_from_head(head_resp, max_size, url)
        resp = client.get(url)
        resp.raise_for_status()
        _check_size_from_content(resp.content, max_size, url)
        dest_dir = _ensure_type_dir(attachment_type)
        dest = dest_dir / node_id
        dest.write_bytes(resp.content)
        return dest


async def async_download_file(
    url: str,
    node_id: str,
    attachment_type: str = "doc",
    max_size: int = 100 * 1024 * 1024,
) -> Path:
    """Download a URL into the Semantika files directory (async version).

    Uses ``httpx.AsyncClient`` so it does not block the async event loop.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"Unsupported URL scheme: {url}")

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        head_resp = await client.head(url)
        _check_size_from_head(head_resp, max_size, url)
        resp = await client.get(url)
        resp.raise_for_status()
        _check_size_from_content(resp.content, max_size, url)
        dest_dir = _ensure_type_dir(attachment_type)
        dest = dest_dir / node_id
        dest.write_bytes(resp.content)
        return dest


def _check_size_from_head(
    head_resp: httpx.Response, max_size: int, url: str
) -> None:
    """Raise ``ValueError`` if Content-Length exceeds *max_size*."""
    cl = head_resp.headers.get("content-length")
    if cl and int(cl) > max_size:
        raise ValueError(
            f"File too large: {int(cl)} bytes (max {max_size} bytes) for {url}"
        )


def _check_size_from_content(
    content: bytes, max_size: int, url: str
) -> None:
    """Raise ``ValueError`` if actual content exceeds *max_size*."""
    if len(content) > max_size:
        raise ValueError(
            f"Download too large: {len(content)} bytes (max {max_size} bytes) for {url}"
        )


def delete_file(stored_path: Path) -> None:
    """Delete a previously stored attachment file.

    Silently succeeds if the file does not exist (idempotent).
    """
    try:
        stored_path.unlink(missing_ok=True)
    except OSError as exc:
        logger.debug("Could not delete file %s: %s", stored_path, exc)


def is_managed_file(path: Path) -> bool:
    """Check whether *path* lives under the Semantika files directory."""
    try:
        root = _files_root().resolve()
        return root in path.resolve().parents
    except OSError:
        return False
