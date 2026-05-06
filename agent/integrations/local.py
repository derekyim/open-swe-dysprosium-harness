import logging
import os
from pathlib import Path

from deepagents.backends import LocalShellBackend

logger = logging.getLogger(__name__)

_HARNESS_ROOT = Path(__file__).resolve().parent.parent.parent


def create_local_sandbox(sandbox_id: str | None = None):
    """Create a local shell sandbox with no isolation.

    WARNING: This runs commands directly on the host machine with no sandboxing.
    Only use for local development with human-in-the-loop enabled.

    The root directory is resolved as follows:
    1. `LOCAL_SANDBOX_ROOT_DIR` env var, if set. Relative paths resolve
       against the harness repo root (so `LOCAL_SANDBOX_ROOT_DIR=sandbox`
       always means `<harness>/sandbox`, regardless of cwd).
    2. `<harness>/sandbox/` if it exists — the convention this repo
       documents in RUNBOOK.md.
    3. The current working directory (legacy fallback).

    Args:
        sandbox_id: Ignored for local sandboxes; accepted for interface compatibility.

    Returns:
        LocalShellBackend instance implementing SandboxBackendProtocol.
    """
    raw = os.environ.get("LOCAL_SANDBOX_ROOT_DIR", "").strip()
    if raw:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (_HARNESS_ROOT / candidate).resolve()
    elif (_HARNESS_ROOT / "sandbox").is_dir():
        candidate = (_HARNESS_ROOT / "sandbox").resolve()
    else:
        candidate = Path(os.getcwd()).resolve()

    candidate.mkdir(parents=True, exist_ok=True)
    logger.info("Local sandbox root: %s", candidate)

    return LocalShellBackend(
        root_dir=str(candidate),
        inherit_env=True,
    )
