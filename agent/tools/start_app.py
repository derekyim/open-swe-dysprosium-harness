"""Start an app dev server in the background and wait for it to be ready.

The harness is generic — what to start (`yarn dev`, `pnpm dev`, `make dev`,
`uvicorn ...`, etc.), which port to poll, and the readiness path are
specified by the caller. The per-app recipe lives in each app's playbook
or `AGENTS.md`.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

LOG_DIR = Path("/tmp/dysprosium_app_logs")
_TAIL_BYTES = 4000


def _tail(path: Path, max_bytes: int = _TAIL_BYTES) -> str:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return ""
    return text[-max_bytes:]


def _pid_path(port: int) -> Path:
    return LOG_DIR / f"port_{port}.pid"


def _log_path(port: int) -> Path:
    return LOG_DIR / f"port_{port}.log"


def start_app(
    working_dir: str,
    command: str,
    port: int,
    ready_path: str = "/",
    timeout_seconds: int = 60,
    scheme: str = "http",
    verify_tls: bool = True,
) -> dict[str, Any]:
    """Spawn a dev server in the background and poll for HTTP(S) readiness.

    The process runs detached (its own session/process group) so it
    survives this tool call. Output is redirected to a log file. The
    function polls `<scheme>://localhost:<port><ready_path>` once a
    second until it returns any non-5xx response, or the timeout
    expires.

    Args:
        working_dir: Repo root or package directory in which to run
            `command`. Same shape as you'd `cd` into.
        command: Shell command (passed to bash, not exec'd directly).
            Examples: `"yarn dev"`, `"pnpm --filter web dev"`,
            `"uvicorn app:app --port 8000"`. Use `"bash -lc '...'"`
            to get a login shell that sources `~/.nvm/nvm.sh` so
            `nvm use 20 && npm start` works.
        port: TCP port the app will bind. Used to construct the
            readiness URL and to dedupe state files (one app per port).
        ready_path: Path component for the readiness probe. Defaults to
            `"/"`. Use `"/health"` or `"/api/health"` if the root path
            is slow or auth-gated.
        timeout_seconds: Max seconds to wait for readiness. Default 60.
            Bump to 180+ for first-time Vite/webpack cold compiles.
        scheme: `"http"` (default) or `"https"`. Use `"https"` for dev
            servers that bind TLS only (mkcert / office-addin-dev-certs).
        verify_tls: Whether to verify TLS certs on the readiness probe.
            Default `True`. Set `False` for self-signed local certs.

    Returns:
        Dict with `success` (bool). On success: `url`, `pid`,
        `status_code`, `log_path`, `elapsed_seconds`. On failure:
        `error`, plus `log_tail`, `log_path`, `pid`, `last_error` for
        debugging. Use `stop_app(port)` to shut it down.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _log_path(port)
    pid_path = _pid_path(port)

    log_file = log_path.open("wb")
    try:
        proc = subprocess.Popen(  # noqa: S602 — shell=True is intentional
            command,
            cwd=working_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            shell=True,
        )
    except OSError as exc:
        log_file.close()
        return {"success": False, "error": f"failed to spawn: {exc}", "log_path": str(log_path)}

    pid_path.write_text(str(proc.pid))
    pid = proc.pid
    url = f"{scheme}://localhost:{port}{ready_path}"

    start = time.time()
    deadline = start + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            return {
                "success": False,
                "error": f"process exited prematurely with code {proc.returncode}",
                "url": url,
                "pid": pid,
                "log_path": str(log_path),
                "log_tail": _tail(log_path),
            }
        try:
            response = httpx.get(url, timeout=2, follow_redirects=False, verify=verify_tls)
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
        else:
            if response.status_code < 500:
                return {
                    "success": True,
                    "url": url,
                    "pid": pid,
                    "status_code": response.status_code,
                    "log_path": str(log_path),
                    "elapsed_seconds": round(time.time() - start, 1),
                }
        time.sleep(1)

    return {
        "success": False,
        "url": url,
        "pid": pid,
        "log_path": str(log_path),
        "log_tail": _tail(log_path),
        "last_error": last_error,
        "error": f"app did not become ready at {url} within {timeout_seconds}s",
    }


def stop_app(port: int) -> dict[str, Any]:
    """Stop a previously-started app dev server on the given port.

    Sends SIGTERM to the whole process group, waits 2s, then SIGKILL
    anything still alive. Cleans up the PID file. Idempotent — safe to
    call when nothing is running.

    Args:
        port: The same port that was passed to `start_app`.

    Returns:
        Dict with `success` (bool) and either `pid` (when stopped) or
        `error` (when no PID file or process not found).
    """
    pid_path = _pid_path(port)
    if not pid_path.exists():
        return {"success": False, "error": f"no PID file for port {port}"}
    try:
        pid = int(pid_path.read_text().strip())
    except (OSError, ValueError) as exc:
        return {"success": False, "error": f"could not read PID: {exc}"}

    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        pid_path.unlink(missing_ok=True)
        return {"success": True, "pid": pid, "note": "process already gone"}

    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    time.sleep(2)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    pid_path.unlink(missing_ok=True)
    return {"success": True, "pid": pid, "pgid": pgid}
