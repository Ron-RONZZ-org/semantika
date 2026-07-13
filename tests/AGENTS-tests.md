# AGENTS-tests.md — Testing Module Agent Instructions

## Summary

Testing infrastructure, dev server lifecycle, user-simulation testing, and data isolation for Semantika.

This file is the canonical home for **execution procedures** — how to start servers, run tests, and clean up. For **what to test** and testing strategy, see the root `AGENTS.md`.

## Test Commands

| Operation | Command |
|-----------|---------|
| Run all tests | `uv run pytest tests/` |
| Run single test file | `uv run pytest tests/test_graph/test_nodes.py -v` |

## E2E Test Automation

Playwright E2E tests are integrated into pytest:

| Command | Behavior |
|---------|----------|
| `uv run pytest tests/` | Unit tests only (E2E skipped) |
| `uv run pytest --e2e tests/test_e2e.py` | E2E tests only (auto-starts seeded server) |
| `uv run pytest --e2e --keep-e2e-data` | E2E + preserve temp data for debugging |

The ``e2e_server`` fixture in ``tests/conftest.py`` handles the full lifecycle:
1. Finds a free TCP port (no conflicts)
2. Creates a temp data directory with isolated ``SEMANTIKA_*`` env vars
3. Starts uvicorn as a subprocess
4. Health-checks up to 15s
5. Yields URL + config to the test
6. Terminates server + removes temp dir on teardown

Existing ``.mjs`` scripts (``tests/semantika_full_e2e.mjs``) are wrapped by ``tests/test_e2e.py`` via ``subprocess.run()``.

### One-time Chromium setup

```bash
cd web && npx playwright install chromium
```

## Dev Server for Manual Testing

When running user-simulation tests against the backend, **always use a dynamically-allocated free port**. Never kill a process on the default port (6015) — it may belong to the user's manual dev instance.

### Lifecycle (start → test → cleanup)

```bash
# 1. Find a free TCP port (never kill a foreign process on the default port)
PORT=$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); print(s.getsockname()[1]); s.close()")

# 2. Start isolated seeded server — detach via setsid so it survives bash timeout
setsid uv run semantika-dev --seed --port $PORT > /tmp/semantika-dev.log 2>&1 &
echo $! > /tmp/semantika-dev.pid

# Or start with persistent data (survives restarts)
setsid uv run semantika-dev --data-dir ~/semantika-dev-data --seed --port $PORT > /tmp/semantika-dev.log 2>&1 &
echo $! > /tmp/semantika-dev.pid

# 3. Wait for server to accept connections (up to 30s)
for i in $(seq 1 30); do
  curl -sf -o /dev/null http://127.0.0.1:$PORT/ && break
  sleep 1
done

# 4. Run tests or queries against http://127.0.0.1:$PORT
```

Always use `http://127.0.0.1:<port>` (IPv4) when connecting to a local dev server.

### Restart after frontend rebuild

If you rebuild ``web/dist/`` (e.g. ``npm run build``), the Python dev server caches old SPA files. Restart:

```bash
kill $(cat /tmp/semantika-dev.pid)
# Repeat steps 2-4 from the lifecycle above
```

### Cleanup

```bash
kill $(cat /tmp/semantika-dev.pid) 2>/dev/null
rm -f /tmp/semantika-dev.pid /tmp/semantika-dev.log
```

## Data Isolation

- **Unit tests**: the ``e2e_server`` fixture in ``tests/conftest.py`` sets ``SEMANTIKA_DATA_DIR`` / ``SEMANTIKA_CONFIG_DIR`` / ``SEMANTIKA_CACHE_DIR`` / ``SEMANTIKA_STATE_DIR`` to an isolated temp directory. No test reaches the real data directory.
- **Manual testing**: ``semantika-dev --seed`` uses a temp directory (cleaned on exit). Use ``--data-dir`` for persistent data.
- **Testing with production data**: clone the data directory first:
  ```bash
  cp -r ~/.local/share/semantika/ ~/tmp/semantika-backup/
  uv run semantika-dev --data-dir ~/tmp/semantika-backup --port $PORT
  # ... test ...
  rm -rf ~/tmp/semantika-backup/
  ```

## User-Simulation Testing

As the final verification step before declaring work done, run through the app as a user would.

### Reporting format

| what exact I have done | what results I expect to get | what results I got | what are my conclusions |
|------------------------|------------------------------|--------------------|-------------------------|

### What to test manually

- Type ``!command`` sequences end-to-end: incomplete → form opens → fill fields → submit → result tab appears
- Navigate list tabs: select items, batch delete, search, sort, keyboard shortcuts
- Form validation: submit empty, invalid data, verify error messages render
- Test the same scenarios via the API (curl / Python requests)
