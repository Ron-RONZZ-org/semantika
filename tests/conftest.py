"""Pytest fixtures for Semantika — DB isolation, seeded test data, E2E server."""

from __future__ import annotations

import glob
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest


def _detect_chromium_path() -> str | None:
    """Find the Playwright Chromium binary.

    Checks Playwright's cache dirs first, then system paths.
    Returns ``None`` if not found.
    """
    home = str(Path.home())
    candidates: list[str] = []
    # Playwright-managed Chromium (most common)
    for pattern in [
        home + "/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        home + "/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        home + "/.cache/ms-playwright/chromium-*/chrome-linux64/chrome",
    ]:
        candidates.extend(glob.glob(pattern))
    # System installations
    candidates += [
        shutil.which("chromium") or "",
        shutil.which("chromium-browser") or "",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


@pytest.fixture(scope="session")
def e2e_server(request: pytest.FixtureRequest) -> Iterator[dict[str, Any]]:
    """Start a seeded Semantika server on a dynamic port.

    Yields a dict with:
        url: str — base URL (e.g., ``http://127.0.0.1:34567``)
        port: int
        tmp_dir: Path — temp data directory
        chrome_path: str or None — detected Chromium path

    Teardown: terminates the uvicorn process and removes temp dir.
    """
    # ── 1. Find free port ────────────────────────────────────────────────
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    # ── 2. Create isolated data directory ────────────────────────────────
    tmp_dir = Path(tempfile.mkdtemp(prefix="semantika-e2e-"))

    # ── 3. Set up environment ────────────────────────────────────────────
    env = os.environ.copy()
    env["SEMANTIKA_DATA_DIR"] = str(tmp_dir)
    env["SEMANTIKA_CONFIG_DIR"] = str(tmp_dir)
    env["SEMANTIKA_CACHE_DIR"] = str(tmp_dir)
    env["SEMANTIKA_STATE_DIR"] = str(tmp_dir)
    # Ensure lightercore is importable (add its src to PYTHONPATH)
    lightercore_src = str(Path(__file__).resolve().parent.parent.parent / "lightercore" / "src")
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{lightercore_src}:{existing}" if existing else lightercore_src

    # ── 4. Start uvicorn subprocess ──────────────────────────────────────
    # Use the venv python (sys.executable may be outside venv for `uv run`)
    venv_python = Path(sys.prefix) / "bin" / "python"
    python_bin = str(venv_python) if venv_python.is_file() else sys.executable
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        [
            python_bin,
            "-m",
            "uvicorn",
            "semantika.server.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    # ── 5. Health check (up to 15s) ──────────────────────────────────────
    health_url = f"{url}/api/v1/command/tree"
    deadline = time.monotonic() + 15
    last_err = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[e2e] Server ready at {url}")
                    break
        except (urllib.error.URLError, OSError) as e:
            last_err = str(e)
        time.sleep(0.5)
    else:
        out = proc.communicate(timeout=5)[1]
        proc.kill()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        pytest.fail(
            f"Server failed to start on port {port}\n"
            f"Last error: {last_err}\n"
            f"Server stderr:\n{out.decode(errors='replace')}"
        )

    # ── 6. Detect browser path ───────────────────────────────────────────
    chrome_path = _detect_chromium_path()
    if not chrome_path:
        proc.terminate()
        shutil.rmtree(tmp_dir, ignore_errors=True)
        pytest.fail(
            "No Chromium browser found for Playwright. "
            "Run: cd web && npx playwright install chromium"
        )

    yield {
        "url": url,
        "port": port,
        "tmp_dir": tmp_dir,
        "chrome_path": chrome_path,
    }

    # ── 7. Teardown ──────────────────────────────────────────────────────
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    keep = request.config.getoption("--keep-e2e-data", default=False)
    if not keep:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="Run E2E browser tests",
    )
    parser.addoption(
        "--keep-e2e-data",
        action="store_true",
        default=False,
        help="Keep E2E temp data for debugging",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "e2e: E2E browser tests (skipped by default)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not config.getoption("--e2e"):
        skip_e2e = pytest.mark.skip(reason="Use --e2e to run E2E tests")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip_e2e)
