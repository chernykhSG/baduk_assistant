# Backend Sidecar Skeleton + Engine Manager Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Python backend as a standalone, testable sidecar service: a FastAPI health-check endpoint with token auth, and an `EngineManager` that launches the KataGo Analysis Engine, sends a position, and parses winrate/ownership/PV out of its JSON response — the exact smoke-test criterion for Phase 1 in `docs/ARCHITECTURE.md`.

**Architecture:** `EngineManager` wraps a long-lived KataGo subprocess (JSON over stdin/stdout, one line per request/response), read via a background thread into a queue so requests can time out without blocking. A `KataGoProfile` dataclass + template function render the engine's static `.cfg` file; per-request fields (rules/komi/board size) are sent in the JSON query, not baked into the config. FastAPI exposes `/health` behind a token generated at process start and printed to stdout as JSON, so Electron (in a later plan) can read `{port, token}` from the sidecar's stdout.

**Tech Stack:** Python ≥3.11, managed by `uv` (no pip/poetry). FastAPI + uvicorn. pytest for tests, `httpx`-backed `TestClient`.

## Global Constraints

- This plan is **backend-only**. No Electron/frontend code — that's a separate later plan (per `docs/superpowers/specs/2026-08-03-phase-1-viewer-katago-design.md`, step 4 of the vertical slice).
- Python tooling is `uv` exclusively: `uv init`, `uv add`, `uv run`. Do not hand-write `pyproject.toml` dependency sections — use `uv add`.
- `rules`, `komi`, `boardXSize`, `boardYSize` are per-request JSON fields in KataGo's Analysis Engine protocol, not `.cfg` file settings — do not add them to `render_analysis_config`.
- Integration tests that need a real KataGo binary/model are marked `@pytest.mark.integration`, excluded by default (`addopts = -m "not integration"`), and additionally self-skip via `backend/tests/conftest.py`'s `local_katago_config` fixture, which reads the `BADUK_KATAGO_BINARY` and `BADUK_KATAGO_MODEL` environment variables and calls `pytest.skip(...)` naming both variables if either is unset — never required for the default `uv run pytest` to pass.
- No machine-specific config file is committed or created: paths come from the `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` environment variables; `local_config.json.example` documents these two variables (it is not a JSON template to be copied).
- All file paths below are relative to the repo root `c:\GithubProject\baduk_assistant`. Run all `uv`/`pytest` commands from inside `backend/` once it exists.

---

### Task 1: Backend project scaffold + sidecar health-check endpoint

**Files:**
- Create: `backend/pyproject.toml` (via `uv init`, then `uv add`)
- Create: `backend/src/baduk_backend/main.py`
- Create: `backend/tests/test_main.py`
- Create: `backend/.gitignore`

**Interfaces:**
- Produces: `app` (FastAPI instance), `AUTH_TOKEN: str`, `build_startup_message(port: int, token: str) -> str`, `_find_free_port() -> int`, `run() -> None` — all in `baduk_backend.main`, used by later tasks/plans as the sidecar entrypoint.

- [ ] **Step 1: Scaffold the uv project**

```bash
cd c:/GithubProject/baduk_assistant
uv init --package --name baduk-backend backend
cd backend
uv add fastapi "uvicorn[standard]"
uv add --dev pytest httpx
```

- [ ] **Step 2: Configure pytest markers**

Add to `backend/pyproject.toml` (append this section):

```toml
[tool.pytest.ini_options]
markers = [
    "integration: requires a real KataGo binary/model (see tests/local_config.json.example)",
]
addopts = "-m \"not integration\""
testpaths = ["tests"]
```

- [ ] **Step 3: Write `.gitignore`**

Create `backend/.gitignore`:

```
.venv/
__pycache__/
*.pyc
```

- [ ] **Step 4: Write the failing test**

Create `backend/tests/test_main.py`:

```python
import json
import socket

from fastapi.testclient import TestClient

from baduk_backend.main import AUTH_TOKEN, _find_free_port, app, build_startup_message


def test_health_with_valid_token_returns_ok():
    client = TestClient(app)
    response = client.get("/health", headers={"X-Auth-Token": AUTH_TOKEN})
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_with_invalid_token_returns_401():
    client = TestClient(app)
    response = client.get("/health", headers={"X-Auth-Token": "wrong-token"})
    assert response.status_code == 401


def test_health_without_token_returns_422():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 422


def test_build_startup_message_contains_port_and_token():
    message = build_startup_message(port=12345, token="abc123")
    assert json.loads(message) == {"port": 12345, "token": "abc123"}


def test_find_free_port_returns_bindable_port():
    port = _find_free_port()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
```

- [ ] **Step 5: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'baduk_backend.main'` (or similar import error) — `main.py` doesn't exist yet.

- [ ] **Step 6: Write minimal implementation**

Create `backend/src/baduk_backend/main.py`:

```python
import json
import secrets
import socket

from fastapi import FastAPI, Header, HTTPException

app = FastAPI()

AUTH_TOKEN = secrets.token_urlsafe(32)


@app.get("/health")
def health(x_auth_token: str = Header(...)) -> dict:
    if x_auth_token != AUTH_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")
    return {"status": "ok"}


def build_startup_message(port: int, token: str) -> str:
    return json.dumps({"port": port, "token": token})


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run() -> None:
    import uvicorn

    port = _find_free_port()
    print(build_startup_message(port, AUTH_TOKEN), flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    run()
```

- [ ] **Step 7: Run test to verify it passes**

Run: `uv run pytest tests/test_main.py -v`
Expected: 5 passed

- [ ] **Step 7b: Fix the auto-generated console-script entry point**

`uv init --package` auto-generates a `[project.scripts]` entry in `backend/pyproject.toml` shaped like `baduk-backend = "baduk_backend:main"`. That target doesn't exist — this task's entrypoint function is `run()`, not `main()` — so the packaged script crashes with `TypeError: 'module' object is not callable` if invoked. Edit that line in `backend/pyproject.toml` to:

```toml
[project.scripts]
baduk-backend = "baduk_backend:run"
```

Verify: `uv run baduk-backend` should print the `{"port": ..., "token": ...}` startup line and then block running the server (Ctrl+C to stop it) — it must NOT raise `TypeError: 'module' object is not callable`.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/src backend/tests backend/.gitignore backend/README.md backend/.python-version
git commit -m "$(cat <<'EOF'
Add backend project scaffold with sidecar health-check endpoint

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

`backend/README.md` and `backend/.python-version` are also generated by `uv init --package` and must be committed — `pyproject.toml`'s `readme = "README.md"` key otherwise points at a file absent from the repo, breaking `uv sync`/`uv build` on a fresh clone.

---

### Task 2: KataGo profile model + analysis config templating

**Files:**
- Create: `backend/src/baduk_backend/config/__init__.py` (empty)
- Create: `backend/src/baduk_backend/config/profile.py`
- Create: `backend/tests/test_profile.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `KataGoProfile` (dataclass: `model_id: str, display_name: str, rules: str, board_size: int, komi: float, max_visits: int, num_analysis_threads: int = 1`), `render_analysis_config(profile: KataGoProfile) -> str` — used by Task 5's integration test and by the later API plan.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_profile.py`:

```python
from baduk_backend.config.profile import KataGoProfile, render_analysis_config


def test_render_analysis_config_includes_thread_and_visit_settings():
    profile = KataGoProfile(
        model_id="kata1-b28c512nbt",
        display_name="Default profile",
        rules="chinese",
        board_size=19,
        komi=7.5,
        max_visits=50,
        num_analysis_threads=2,
    )
    config_text = render_analysis_config(profile)
    assert "numAnalysisThreads = 2" in config_text
    assert "numSearchThreads = 2" in config_text
    assert "maxVisits = 50" in config_text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.config'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/src/baduk_backend/config/__init__.py` (empty file).

Create `backend/src/baduk_backend/config/profile.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class KataGoProfile:
    model_id: str
    display_name: str
    rules: str
    board_size: int
    komi: float
    max_visits: int
    num_analysis_threads: int = 1


ANALYSIS_CONFIG_TEMPLATE = """\
logDir =
logAllRequests = false
logAllResponses = false
logSearchInfo = false
logToStderr = true

numAnalysisThreads = {num_analysis_threads}
numSearchThreads = {num_analysis_threads}

nnMaxBatchSize = 8
nnCacheSizePowerOfTwo = 20
nnMutexPoolSizePowerOfTwo = 16
nnRandomize = true

maxVisits = {max_visits}
"""


def render_analysis_config(profile: KataGoProfile, home_data_dir_override: str | None = None) -> str:
    config_text = ANALYSIS_CONFIG_TEMPLATE.format(
        num_analysis_threads=profile.num_analysis_threads,
        max_visits=profile.max_visits,
    )
    if home_data_dir_override is not None:
        config_text += f"\nhomeDataDirOverride = {home_data_dir_override}\n"
    return config_text
```

**Retroactive addition (discovered during Task 5, applied here for a single source of truth):** without `homeDataDirOverride`, KataGo's OpenCL backend defaults its tuning-cache location to `<directory containing the katago binary>/KataGoData/opencltuning/` — a fresh, empty directory distinct from wherever an existing KataGo install (e.g. KaTrain) already keeps its tuned cache, forcing a full from-scratch OpenCL auto-tune (can take a very long time) instead of reusing it. Passing `home_data_dir_override` (the directory that already contains a populated `opencltuning/` for the target GPU — typically the katago binary's own directory, since GUI installers colocate the two) lets KataGo reuse the existing tuned cache immediately. Defaulting the parameter to `None` (which omits the line entirely) keeps this backward compatible with Task 2's original test, which calls `render_analysis_config(profile)` with no second argument.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_profile.py -v`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add backend/src/baduk_backend/config backend/tests/test_profile.py
git commit -m "$(cat <<'EOF'
Add KataGoProfile and analysis config templating

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Engine Manager core (start/stop/analyze) against a fake KataGo process

**Files:**
- Create: `backend/src/baduk_backend/engine_manager.py`
- Create: `backend/tests/fixtures/__init__.py` (empty)
- Create: `backend/tests/fixtures/fake_katago.py`
- Create: `backend/tests/test_engine_manager.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–2 directly (fully independent module).
- Produces: `EngineManager(command: list[str])` with `.start() -> None`, `.stop() -> None`, `.is_running() -> bool`, `.analyze(request: dict, timeout: float = 30.0) -> dict`, `.command: list[str]` (mutable attribute); `KataGoCrashError(RuntimeError)`; `build_katago_command(katago_binary: str, config_path: str, model_path: str) -> list[str]` — used by Task 4 (crash tests) and Task 5 (integration test).

- [ ] **Step 1: Write the fake KataGo fixture**

Create `backend/tests/fixtures/__init__.py` (empty file).

Create `backend/tests/fixtures/fake_katago.py`:

```python
import json
import sys


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        response = {
            "id": request["id"],
            "turnNumber": 0,
            "moveInfos": [
                {
                    "move": "Q4",
                    "winrate": 0.55,
                    "scoreLead": 1.2,
                    "visits": 50,
                    "prior": 0.3,
                    "pv": ["Q4", "D4"],
                }
            ],
            "rootInfo": {"winrate": 0.55, "scoreLead": 1.2, "visits": 50},
            "ownership": [0.1] * 361,
        }
        print(json.dumps(response), flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_engine_manager.py`:

```python
import sys
from pathlib import Path

from baduk_backend.engine_manager import EngineManager

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def fake_katago_command() -> list[str]:
    return [sys.executable, str(FIXTURES_DIR / "fake_katago.py")]


def test_analyze_sends_request_and_parses_response():
    manager = EngineManager(fake_katago_command())
    try:
        response = manager.analyze({"id": "test-1", "moves": []})
        assert response["id"] == "test-1"
        assert "moveInfos" in response
        assert "rootInfo" in response
        assert "ownership" in response
    finally:
        manager.stop()


def test_analyze_auto_starts_process_if_not_running():
    manager = EngineManager(fake_katago_command())
    assert not manager.is_running()
    try:
        response = manager.analyze({"id": "test-2", "moves": []})
        assert response["id"] == "test-2"
        assert manager.is_running()
    finally:
        manager.stop()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_engine_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'baduk_backend.engine_manager'`

- [ ] **Step 4: Write minimal implementation**

Create `backend/src/baduk_backend/engine_manager.py`:

```python
import json
import queue
import subprocess
import threading


class KataGoCrashError(RuntimeError):
    """Raised when the KataGo process is not running or exits unexpectedly."""


def build_katago_command(katago_binary: str, config_path: str, model_path: str) -> list[str]:
    return [katago_binary, "analysis", "-config", config_path, "-model", model_path]


class EngineManager:
    def __init__(self, command: list[str]):
        self.command = command
        self._process: subprocess.Popen | None = None
        self._stdout_queue: queue.Queue = queue.Queue()
        self._reader_thread: threading.Thread | None = None
        self._stderr_lines: list[str] = []
        self._stderr_thread: threading.Thread | None = None

    def start(self) -> None:
        self._process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._stderr_lines = []
        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self._process is not None
        assert self._process.stdout is not None
        for line in self._process.stdout:
            line = line.strip()
            if line:
                self._stdout_queue.put(line)

    def _read_stderr(self) -> None:
        # Must be drained continuously, not just on demand: an unread stderr
        # pipe fills its OS buffer once the child logs enough (KataGo logs
        # heavily at startup), which blocks the child's own stderr write and
        # wedges analyze() for the full timeout instead of failing fast.
        assert self._process is not None
        assert self._process.stderr is not None
        for line in self._process.stderr:
            line = line.strip()
            if line:
                self._stderr_lines.append(line)

    def stderr_output(self) -> str:
        return "\n".join(self._stderr_lines)

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def stop(self) -> None:
        if self._process is not None:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None

    def analyze(self, request: dict, timeout: float = 30.0) -> dict:
        if not self.is_running():
            self.start()
        assert self._process is not None
        assert self._process.stdin is not None
        request_id = request["id"]
        try:
            self._process.stdin.write(json.dumps(request) + "\n")
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise KataGoCrashError("KataGo process pipe closed unexpectedly") from exc
        try:
            line = self._stdout_queue.get(timeout=timeout)
        except queue.Empty:
            if not self.is_running():
                raise KataGoCrashError("KataGo process exited while waiting for response")
            raise TimeoutError(f"No response from KataGo within {timeout}s")
        response = json.loads(line)
        # A single request can in principle receive multiple lines (one per
        # analyzeTurns entry); Phase 1 only sends single-turn requests, so the
        # first matching-id line is assumed to be the whole answer.
        if response.get("id") != request_id:
            raise ValueError(f"Unexpected response id {response.get('id')!r}, expected {request_id!r}")
        return response
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_engine_manager.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add backend/src/baduk_backend/engine_manager.py backend/tests/fixtures backend/tests/test_engine_manager.py
git commit -m "$(cat <<'EOF'
Add EngineManager core against a fake KataGo process

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Engine Manager crash detection and auto-restart

**Files:**
- Create: `backend/tests/fixtures/fake_katago_crash.py`
- Modify: `backend/tests/test_engine_manager.py`

**Interfaces:**
- Consumes: `EngineManager`, `KataGoCrashError` from Task 3 (no signature changes).
- Produces: nothing new — this task validates the crash-handling branches already written in Task 3's `analyze()`.

- [ ] **Step 1: Write the crash fixture**

Create `backend/tests/fixtures/fake_katago_crash.py`:

```python
import sys

sys.exit(1)
```

- [ ] **Step 2: Write the failing tests**

Add these two imports to the **top** of `backend/tests/test_engine_manager.py`, alongside the existing `import sys` / `from pathlib import Path` / `from baduk_backend.engine_manager import EngineManager` (do not duplicate those):

```python
import pytest

from baduk_backend.engine_manager import KataGoCrashError
```

Then **append** to the bottom of the same file:

```python
def fake_katago_crash_command() -> list[str]:
    return [sys.executable, str(FIXTURES_DIR / "fake_katago_crash.py")]


def test_analyze_raises_crash_error_when_process_exits_immediately():
    manager = EngineManager(fake_katago_crash_command())
    with pytest.raises(KataGoCrashError):
        manager.analyze({"id": "test-3", "moves": []}, timeout=2.0)
    assert not manager.is_running()


def test_manager_recovers_after_crash_with_working_command():
    manager = EngineManager(fake_katago_crash_command())
    with pytest.raises(KataGoCrashError):
        manager.analyze({"id": "test-4", "moves": []}, timeout=2.0)

    manager.command = fake_katago_command()
    try:
        response = manager.analyze({"id": "test-5", "moves": []})
        assert response["id"] == "test-5"
    finally:
        manager.stop()
```

- [ ] **Step 3: Run tests to verify the new ones fail or pass unexpectedly**

Run: `uv run pytest tests/test_engine_manager.py -v`
Expected: The two new tests should already PASS, since Task 3's `analyze()` implementation already handles this — this step is a verification that the crash-handling code written earlier is actually correct, not a driver for new code. If either fails, fix `analyze()` in `backend/src/baduk_backend/engine_manager.py` before proceeding.

- [ ] **Step 4: Run full test file to confirm no regressions**

Run: `uv run pytest tests/test_engine_manager.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/tests/fixtures/fake_katago_crash.py backend/tests/test_engine_manager.py
git commit -m "$(cat <<'EOF'
Add crash-detection and auto-restart tests for EngineManager

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Engine Manager integration test against real local KataGo

**Files:**
- Create: `backend/tests/local_config.json.example`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_engine_manager_integration.py`
- Modify: `backend/.gitignore`

**Interfaces:**
- Consumes: `EngineManager`, `build_katago_command` from Task 3; `KataGoProfile`, `render_analysis_config` from Task 2.
- Produces: `local_katago_config` pytest fixture (from `conftest.py`), reusable by future integration tests in later plans.

- [ ] **Step 1: Add the git-ignored safety-net entry and the example doc**

Append to `backend/.gitignore` (defense-in-depth only — the shipped design never creates this file, but a future developer might for local convenience):

```
tests/local_config.json
```

Create `backend/tests/local_config.json.example` — not a JSON template to copy, but a comment-only doc explaining that the real integration test config comes from two environment variables, `BADUK_KATAGO_BINARY` (absolute path to the katago executable) and `BADUK_KATAGO_MODEL` (absolute path to the `.bin.gz` neural net model), with example `PowerShell` invocations (`$env:BADUK_KATAGO_BINARY = "C:/path/to/katago.exe"`, etc.) and a note that these paths are machine-local and never committed.

- [ ] **Step 2: Write the conftest fixture**

Create `backend/tests/conftest.py`:

```python
import os

import pytest


@pytest.fixture
def local_katago_config():
    katago_binary = os.environ.get("BADUK_KATAGO_BINARY")
    katago_model = os.environ.get("BADUK_KATAGO_MODEL")
    if not katago_binary or not katago_model:
        pytest.skip(
            "BADUK_KATAGO_BINARY and BADUK_KATAGO_MODEL env vars not set; "
            "see tests/local_config.json.example"
        )
    return {"katago_binary": katago_binary, "katago_model": katago_model}
```

- [ ] **Step 3: Write the integration test**

Create `backend/tests/test_engine_manager_integration.py`:

```python
import pytest

from baduk_backend.config.profile import KataGoProfile, render_analysis_config
from baduk_backend.engine_manager import EngineManager, build_katago_command

pytestmark = pytest.mark.integration


def test_real_katago_returns_winrate_ownership_and_pv(local_katago_config, tmp_path):
    profile = KataGoProfile(
        model_id="dev-local",
        display_name="Dev local profile",
        rules="chinese",
        board_size=19,
        komi=7.5,
        max_visits=50,
        num_analysis_threads=2,
    )
    katago_binary_dir = str(Path(local_katago_config["katago_binary"]).parent)
    config_path = tmp_path / "analysis_config.cfg"
    config_path.write_text(render_analysis_config(profile, home_data_dir_override=katago_binary_dir))

    command = build_katago_command(
        katago_binary=local_katago_config["katago_binary"],
        config_path=str(config_path),
        model_path=local_katago_config["katago_model"],
    )
    manager = EngineManager(command)
    try:
        response = manager.analyze(
            {
                "id": "smoke-test-1",
                "moves": [],
                "rules": profile.rules,
                "komi": profile.komi,
                "boardXSize": profile.board_size,
                "boardYSize": profile.board_size,
                "analyzeTurns": [0],
                "maxVisits": profile.max_visits,
                "includeOwnership": True,
            },
            timeout=60.0,
        )
    finally:
        manager.stop()

    assert response["id"] == "smoke-test-1"
    assert len(response["moveInfos"]) > 0
    first_move = response["moveInfos"][0]
    assert "winrate" in first_move
    assert "pv" in first_move
    assert "ownership" in response
    assert len(response["ownership"]) == profile.board_size * profile.board_size
```

- [ ] **Step 4: Run the integration test explicitly**

With `BADUK_KATAGO_BINARY` and `BADUK_KATAGO_MODEL` set in your shell to your local katago executable and model paths, run: `uv run pytest tests/test_engine_manager_integration.py -v -m integration`
Expected: 1 passed.

If it instead raises `KataGoCrashError`: the process died on startup, almost always because `analysis_config.cfg` is missing a key your installed KataGo version requires. Print `manager.stderr_output()` (captured continuously by the background stderr-reader thread added in Task 3) to see KataGo's own error message directly — no need to re-run manually in a separate terminal unless that's more convenient. Adjust `ANALYSIS_CONFIG_TEMPLATE` in `backend/src/baduk_backend/config/profile.py` (Task 2) to match, and re-run this test — do not change `EngineManager` itself for this.

- [ ] **Step 5: Confirm the integration test is skipped by default**

Run: `uv run pytest -v`
Expected: All Task 1–4 tests run and pass; `test_real_katago_returns_winrate_ownership_and_pv` does not appear in the run (excluded by the default `-m "not integration"`).

- [ ] **Step 6: Commit**

```bash
git add backend/.gitignore backend/tests/local_config.json.example backend/tests/conftest.py backend/tests/test_engine_manager_integration.py
git commit -m "$(cat <<'EOF'
Add real KataGo integration test for EngineManager

Verifies the Phase 1 smoke-test criterion from docs/ARCHITECTURE.md:
Engine Manager launches the real Analysis Engine, sends a test
position, and parses winrate/ownership/PV from the response.
BADUK_KATAGO_BINARY and BADUK_KATAGO_MODEL env vars hold this
machine's KataGo binary/model paths; only local_config.json.example,
which documents these two variables, is committed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Definition of Done

- `uv run pytest -v` (from `backend/`) passes with 0 failures, running Tasks 1–4's tests (11 tests) and skipping the Task 5 integration test only if `BADUK_KATAGO_BINARY`/`BADUK_KATAGO_MODEL` are unset.
- `uv run pytest -v -m integration` (from `backend/`) passes, proving the real local KataGo binary/model produce a parseable `winrate`/`ownership`/`pv` response — this is the exact Phase 1 backend smoke-test criterion in `docs/ARCHITECTURE.md` § «Проверка → Фаза 1».
- No frontend/Electron code exists yet — that starts in the next plan in the sequence (per the design spec's vertical-slice ordering).
