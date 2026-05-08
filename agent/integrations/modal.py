import logging
import os

import modal
from langchain_modal import ModalSandbox

logger = logging.getLogger(__name__)

MODAL_APP_NAME = os.getenv("MODAL_APP_NAME", "open-swe")


def create_modal_sandbox(sandbox_id: str | None = None):
    """Create or reconnect to a Modal sandbox.

    Args:
        sandbox_id: Optional existing sandbox ID to reconnect to.
            If None, creates a new sandbox.

    Returns:
        ModalSandbox instance implementing SandboxBackendProtocol.
    """
    # `create_if_missing=True` lazily creates the Modal app on first run, so
    # operators don't need a separate `modal deploy` step before the harness
    # can spawn sandboxes. The app is just a logical namespace; sandboxes
    # are spun up per-run regardless.
    app = modal.App.lookup(MODAL_APP_NAME, create_if_missing=True)

    if sandbox_id:
        logger.info("Reconnecting to Modal sandbox %s in app %s", sandbox_id, MODAL_APP_NAME)
        sandbox = modal.Sandbox.from_id(sandbox_id, app=app)
    else:
        logger.info("Creating new Modal sandbox in app %s", MODAL_APP_NAME)
        sandbox = modal.Sandbox.create(app=app)

    return ModalSandbox(sandbox=sandbox)
