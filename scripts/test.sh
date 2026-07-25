#!/usr/bin/env bash
# semantika test runner — delegates to shared smart-test.sh.
#
# Usage:  ./scripts/test.sh [pytest-args...]

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND_PATTERNS="web/*"
BACKEND_PATTERNS="src/*.py tests/*.py pyproject.toml"
META_PATTERNS="scripts/*.sh AGENTS.md AGENTS-*.md"
source /home/rongzhou/kodo/basculer/opencode-config/scripts/smart-test.sh
