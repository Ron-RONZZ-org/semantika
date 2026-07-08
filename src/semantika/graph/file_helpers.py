"""File management helpers for node attachments.

Provides copy/move/download/detect-mime operations for file attachments
attached to knowledge graph nodes via ``:hasFilePath``, ``:hasFileMime``,
``:hasFileSize``, and ``:hasFileSource`` triples.

Ported from A-semantika's ``_file_helpers.py``.
"""

from __future__ import annotations

import ipaddress
import logging
import mimetypes
import re
import shutil
import socket
from pathlib import Path
from urllib.parse import urlparse

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


def _sanitize_filename(component: str) -> str:
    """Strip path-traversal characters from a filename component.

    Removes null bytes, path separators, and parent-directory references
    that could allow ``node_id`` values like ``../../etc/passwd`` to
    escape the managed storage directory.
    """
    # Null bytes
    safe = component.replace("\0", "")
    # Path separators
    safe = safe.replace("/", "_").replace("\\", "_")
    # Replace any ``..`` or longer dot sequences (``...``, ``....``, etc.)
    # with a single underscore.  Catches cases like ``foo../bar`` or
    # ``abc..def`` that the old word-boundary regex missed.
    safe = re.sub(r"\.\.+", "_", safe)
    # Strip leading dots/dashes that could be interpreted as hidden files
    safe = safe.lstrip(".-_")
    return safe or "unnamed"


def _files_root() -> Path:
    """Return the root directory for all attachment files."""
    root = data_dir() / "files"
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
    """Return the filename stem for *node_id*, preserving source extension.

    *node_id* is sanitised to prevent path-traversal attacks.
    """
    suffix = src.suffix.lower() if src.suffix else ""
    return f"{_sanitize_filename(node_id)}{suffix}"


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


def _resolve_and_pin(url: str) -> tuple[str, str]:
    """Resolve hostname to IP once; return (url_with_ip, original_hostname).

    Prevents DNS rebinding attacks by resolving the hostname **before**
    opening the connection and using the resolved IP as the connection
    target (with the original hostname in the ``Host`` header).

    Also validates the resolved IP is not a private/loopback/link-local
    address (SSRF prevention).

    Raises:
        ValueError: If the scheme is unsupported, resolution fails, or the
            resolved IP is a private/reserved address.
    """
    if not url.lower().startswith(("http://", "https://")):
        raise ValueError(f"Unsupported URL scheme: {url}")

    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    port = parsed.port

    try:
        addrs = socket.getaddrinfo(
            hostname,
            port or (443 if parsed.scheme == "https" else 80),
        )
    except socket.gaierror:
        raise ValueError(f"Could not resolve hostname: {hostname}")

    if not addrs:
        raise ValueError(f"Hostname resolved to no addresses: {hostname}")

    ip_str = addrs[0][4][0]

    # Validate resolved IP (SSRF prevention)
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        raise ValueError(f"Resolved address is not a valid IP: {ip_str}")

    if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
        raise ValueError(
            f"URL resolves to a private/reserved IP and is blocked: {url} "
            f"(resolved to {ip_str})"
        )

    # Reconstruct URL with pinned IP, preserving original hostname for Host header
    pinned_netloc = ip_str
    if port:
        pinned_netloc = f"{ip_str}:{port}"
    pinned_url = parsed._replace(netloc=pinned_netloc).geturl()

    return pinned_url, hostname


def _check_size_from_head(
    head_resp: httpx.Response, max_size: int, url: str
) -> None:
    """Raise ``ValueError`` if Content-Length exceeds *max_size*."""
    cl = head_resp.headers.get("content-length")
    if cl and int(cl) > max_size:
        raise ValueError(
            f"File too large: {int(cl)} bytes (max {max_size} bytes) for {url}"
        )


def _ensure_dest_dir(attachment_type: str, node_id: str) -> Path:
    """Return the destination path in the files directory.

    *node_id* is sanitised to prevent path-traversal attacks.
    """
    dest_dir = _ensure_type_dir(attachment_type)
    return dest_dir / _sanitize_filename(node_id)


def download_file(
    url: str,
    node_id: str,
    attachment_type: str = "doc",
    max_size: int = 100 * 1024 * 1024,
) -> Path:
    """Download a URL into the Semantika files directory (sync version).

    Resolves the remote hostname **once** and pins the resolved IP for
    the connection (with the original hostname in the ``Host`` header)
    to prevent DNS rebinding attacks.

    For use in non-async contexts.  Use ``async_download_file`` inside
    async FastAPI routes to avoid blocking the event loop.

    The download is streamed and the size is enforced during streaming,
    so a too-large file is rejected before it is fully buffered.
    """
    pinned_url, host_header = _resolve_and_pin(url)
    headers = {"Host": host_header}

    with httpx.Client(follow_redirects=True, timeout=30.0) as client:
        head_resp = client.head(pinned_url, headers=headers)
        _check_size_from_head(head_resp, max_size, url)

        dest = _ensure_dest_dir(attachment_type, node_id)
        with client.stream("GET", pinned_url, headers=headers) as resp:
            resp.raise_for_status()
            _check_size_from_head(resp, max_size, url)
            downloaded = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    downloaded += len(chunk)
                    if downloaded > max_size:
                        dest.unlink(missing_ok=True)
                        raise ValueError(
                            f"Download too large: exceeded {max_size} bytes "
                            f"for {url}"
                        )
                    f.write(chunk)
        return dest


async def async_download_file(
    url: str,
    node_id: str,
    attachment_type: str = "doc",
    max_size: int = 100 * 1024 * 1024,
) -> Path:
    """Download a URL into the Semantika files directory (async version).

    Resolves the remote hostname **once** and pins the resolved IP for
    the connection (with the original hostname in the ``Host`` header)
    to prevent DNS rebinding attacks.

    Uses ``httpx.AsyncClient`` so it does not block the async event loop.

    The download is streamed and the size is enforced during streaming,
    so a too-large file is rejected before it is fully buffered.
    """
    pinned_url, host_header = _resolve_and_pin(url)
    headers = {"Host": host_header}

    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        head_resp = await client.head(pinned_url, headers=headers)
        _check_size_from_head(head_resp, max_size, url)

        dest = _ensure_dest_dir(attachment_type, node_id)
        async with client.stream("GET", pinned_url, headers=headers) as resp:
            resp.raise_for_status()
            _check_size_from_head(resp, max_size, url)
            downloaded = 0
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    downloaded += len(chunk)
                    if downloaded > max_size:
                        dest.unlink(missing_ok=True)
                        raise ValueError(
                            f"Download too large: exceeded {max_size} bytes "
                            f"for {url}"
                        )
                    f.write(chunk)
        return dest


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
