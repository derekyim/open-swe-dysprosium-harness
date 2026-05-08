import logging
import os

import modal
from langchain_modal import ModalSandbox

logger = logging.getLogger(__name__)

MODAL_APP_NAME = os.getenv("MODAL_APP_NAME", "open-swe")


async def create_modal_sandbox(sandbox_id: str | None = None):
    """Create or reconnect to a Modal sandbox (async).

    Modal's sync `Sandbox.create()` internally drives its own asyncio loop
    that calls `tempfile.TemporaryFile()` → `os.getcwd()`, which langgraph
    dev's blockbuster instrumentation refuses on any event loop. Using the
    `.aio` async API skips the sync→async bridge entirely so blockbuster
    never sees a blocking call.

    `create_if_missing=True` lazily creates the Modal app on first run, so
    operators don't need a separate `modal deploy` step before the harness
    can spawn sandboxes. The app is just a logical namespace; sandboxes
    are spun up per-run regardless.

    Args:
        sandbox_id: Optional existing sandbox ID to reconnect to.
            If None, creates a new sandbox.

    Returns:
        ModalSandbox instance implementing SandboxBackendProtocol.
    """
    app = await modal.App.lookup.aio(MODAL_APP_NAME, create_if_missing=True)

    if sandbox_id:
        logger.info("Reconnecting to Modal sandbox %s in app %s", sandbox_id, MODAL_APP_NAME)
        sandbox = await modal.Sandbox.from_id.aio(sandbox_id, app=app)
    else:
        logger.info("Creating new Modal sandbox in app %s", MODAL_APP_NAME)
        sandbox = await modal.Sandbox.create.aio(app=app)

    return ModalSandbox(sandbox=sandbox)
