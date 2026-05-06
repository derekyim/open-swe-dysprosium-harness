# Default Prompt (harness-level fallback)

This file is a fallback only. Per-deployment / per-build-team prompt
content should live in **`$BUILD_TEAM_DIR/default_prompt.md`** — the
harness reads it from there first.

If you are seeing this content in your agent's system prompt, it means
either no build team is configured (`BUILD_TEAM_DIR` unset) or the
build team checkout has no `default_prompt.md`. Add one to your build
team repo and the harness will pick it up automatically.
