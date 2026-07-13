"""E2E browser tests — wrap Playwright .mjs scripts.

Run with::

    pytest --e2e tests/test_e2e.py

Each test runs an .mjs script as a subprocess, passing the server URL
and Chromium path via environment variables.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

# ── Script registry ─────────────────────────────────────────────────────────

SCRIPTS: list[tuple[str, str, int]] = [
    (
        "semantika_full_e2e.mjs",
        "126 tests: all commands + flags/options, GUI (tabs, forms, autocomplete, keyboard shortcuts), CLI→GUI routing, empty states, LLM endpoints, SPARQL editor, canonical/default IRI display + click navigation",
        660,
    ),
]

# ── Tests ───────────────────────────────────────────────────────────────────


@pytest.mark.e2e
@pytest.mark.parametrize(
    "script,description,timeout",
    SCRIPTS,
    ids=[s[0].replace(".mjs", "") for s in SCRIPTS],
)
def test_playwright_script(
    e2e_server: dict,
    script: str,
    description: str,
    timeout: int,
) -> None:
    """Run a Playwright E2E script as a subprocess and verify exit code."""
    scripts_dir = Path(__file__).parent
    script_path = scripts_dir / script
    web_root = scripts_dir.parent / "web"

    assert script_path.is_file(), f"Script not found: {script_path}"
    playwright_installed = (
        (web_root / "node_modules" / "playwright").is_dir()
        or Path(e2e_server.get("chrome_path", "")).exists()
    )
    assert playwright_installed, (
        "Playwright not found. Run: cd web && npx playwright install chromium"
    )

    # ── Build environment ────────────────────────────────────────────────
    env = os.environ.copy()
    env["FRONTEND_URL"] = e2e_server["url"]
    env["CHROME_PATH"] = e2e_server["chrome_path"]

    # ── Run script ───────────────────────────────────────────────────────
    result = subprocess.run(
        ["node", str(script_path)],
        cwd=web_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    # ── Print full output for debugging ──────────────────────────────────
    cap = result.stdout
    if result.stderr:
        cap += "\n--- STDERR ---\n" + result.stderr[-1000:]
    print(cap[:3000])

    # ── Parse results line for structured reporting ──────────────────────
    passed = failed = 0
    for line in result.stdout.splitlines():
        m = re.search(r"(\d+) passed.*?(\d+) failed", line)
        if m:
            passed, failed = int(m.group(1)), int(m.group(2))

    # ── Assert ───────────────────────────────────────────────────────────
    msg_parts = [f"E2E '{script}' exited with code {result.returncode}"]
    if passed or failed:
        msg_parts.append(f"({passed} passed, {failed} failed)")
    if result.stderr:
        last_lines = "\n".join(result.stderr.splitlines()[-15:])
        msg_parts.append(f"\nLast stderr:\n{last_lines}")
    if result.stdout and failed > 0:
        fail_lines = [
            l for l in result.stdout.splitlines() if "✗" in l or "FAIL" in l
        ]
        if fail_lines:
            msg_parts.append("\nFailures:\n" + "\n".join(fail_lines[:10]))

    assert result.returncode == 0, "\n".join(msg_parts)
