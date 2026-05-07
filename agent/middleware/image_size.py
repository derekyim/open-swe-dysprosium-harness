"""Downscale oversized base64 image blocks before they hit the model.

Anthropic's "many-image" rule rejects any single image > 2000 px on either
side when a request contains multiple images. New screenshots already get
downscaled at capture time, but historical images persisted in a thread's
state from before that fix — and any image fetched in a previous turn —
will still be oversized. This middleware catches them in flight, decoding
each base64 image block on every model call and resizing if needed.

The middleware is a no-op for images already <= 2000 px (Pillow's
`Image.open` is lazy and only reads enough bytes to determine size, so
the per-message overhead is small even for many small images).
"""

from __future__ import annotations

import base64
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, AgentState

from ..utils.image import downscale_image_bytes

logger = logging.getLogger(__name__)


def _sanitize_image_block(block: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Return (block, changed). Handles both langchain-native and Anthropic-native shapes.

    Langchain-native: `{"type": "image", "base64": "...", "mime_type": "..."}`
    Anthropic-native: `{"type": "image", "source": {"type": "base64", "media_type": "...", "data": "..."}}`
    """
    # Langchain-native shape (used by `create_image_block`).
    b64 = block.get("base64")
    mime = block.get("mime_type")
    if isinstance(b64, str) and isinstance(mime, str):
        try:
            decoded = base64.b64decode(b64)
        except Exception:  # noqa: BLE001
            return block, False
        new_bytes, new_mime, _orig, new_dims = downscale_image_bytes(decoded, mime)
        if new_dims is None:
            return block, False
        new_block = dict(block)
        new_block["base64"] = base64.b64encode(new_bytes).decode("ascii")
        new_block["mime_type"] = new_mime
        return new_block, True

    # Anthropic-native shape (post-serialization or supplied directly).
    source = block.get("source")
    if isinstance(source, dict) and source.get("type") == "base64":
        data = source.get("data")
        media_type = source.get("media_type")
        if isinstance(data, str) and isinstance(media_type, str):
            try:
                decoded = base64.b64decode(data)
            except Exception:  # noqa: BLE001
                return block, False
            new_bytes, new_mime, _orig, new_dims = downscale_image_bytes(decoded, media_type)
            if new_dims is None:
                return block, False
            new_block = dict(block)
            new_source = dict(source)
            new_source["data"] = base64.b64encode(new_bytes).decode("ascii")
            new_source["media_type"] = new_mime
            new_block["source"] = new_source
            return new_block, True

    return block, False


def _sanitize_blocks(blocks: list[Any]) -> tuple[list[Any], bool]:
    new_blocks: list[Any] = []
    changed = False
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "image":
            new_block, block_changed = _sanitize_image_block(block)
            new_blocks.append(new_block)
            changed = changed or block_changed
        else:
            new_blocks.append(block)
    return new_blocks, changed


def _sanitize_message(msg: Any) -> tuple[Any, bool]:
    content = getattr(msg, "content", None)
    if not isinstance(content, list):
        return msg, False
    new_content, changed = _sanitize_blocks(content)
    if not changed:
        return msg, False
    try:
        new_msg = msg.model_copy(update={"content": new_content})
    except AttributeError:
        # Fall back to in-place mutation if it isn't a pydantic model
        # (older langchain message shapes). Still functionally correct.
        msg.content = new_content
        return msg, True
    return new_msg, True


def _sanitize_messages(messages: list[Any]) -> tuple[list[Any], int]:
    """Return (messages, downscaled_count). Returns same list if nothing changed."""
    out: list[Any] = []
    n_changed = 0
    for msg in messages:
        new_msg, changed = _sanitize_message(msg)
        out.append(new_msg)
        if changed:
            n_changed += 1
    if n_changed == 0:
        return messages, 0
    return out, n_changed


class ImageSizeMiddleware(AgentMiddleware):
    """Walk outgoing messages and downscale any base64 image > 2000 px.

    Runs on every model call so it catches:
      - tool results (e.g. `screenshot`) — already downscaled at source,
        no-ops here.
      - multimodal-fetched images embedded into prompts.
      - images persisted in a thread's state from earlier runs (before
        capture-time downscaling shipped).
      - any future image source the harness adds.
    """

    state_schema = AgentState

    def wrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Any],
    ) -> Any:
        new_messages, n = _sanitize_messages(request.messages)
        if n > 0:
            logger.info("Downscaled %d oversized image-bearing message(s) before model call", n)
            return handler(request.override(messages=new_messages))
        return handler(request)

    async def awrap_model_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        new_messages, n = _sanitize_messages(request.messages)
        if n > 0:
            logger.info("Downscaled %d oversized image-bearing message(s) before model call", n)
            return await handler(request.override(messages=new_messages))
        return await handler(request)
