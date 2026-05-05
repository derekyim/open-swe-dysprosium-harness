# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository

This is **Dysprosium Harness Kit**, a fork of [Open SWE](https://github.com/langchain-ai/open-swe) that extends the upstream agent with Symphony-style harness patterns (SPEC-first task contracts, role-based routing, required proof artifacts, QA/release gates). See `AGENTS.md` and `docs/harness-engineering.md` for the harness conventions — they apply to work *the agent does inside its sandbox*, not to maintenance work on this codebase itself.

When changing this codebase, **preserve upstream Open SWE behavior unless a task explicitly changes it**, and keep generic harness logic separate from EvalGenie-specific logic.

## Common commands

This is a Python 3.11+ project using `uv` and a Makefile. Most workflows go through `make`:

```bash
make install           # uv pip install -e .
make dev               # langgraph dev — starts the LangGraph dev server (graph + webapp)
make run               # uvicorn agent.webapp:app --reload --port 8000 (webhooks only)
make lint              # ruff check + ruff format --diff
make format            # ruff format + ruff check --fix
make format-check      # ruff format --check (what CI runs)
make test              # pytest -vvv tests/
make test TEST_FILE=tests/test_repo_extraction.py    # single file
make integration_tests # tests/integration_tests/
```

Single-test invocation: `uv run pytest -vvv tests/test_foo.py::test_bar`.

CI (`.github/workflows/ci.yml`) runs `make lint`, `make format-check`, and `make test` against `uv sync --locked --extra dev` — match that locally before pushing.

### Running the full server locally

The agent and webhooks are served together by `langgraph dev`. Env vars **must be present in the shell that runs `langgraph dev`** — they are not auto-loaded from `.env` for the agent process. Typical pattern:

```bash
set -a; source .env; set +a
uv run langgraph dev --no-browser
```

`langgraph.json` declares the graph (`agent.server:get_agent`) and the FastAPI app (`agent.webapp:app`) — both run inside the same LangGraph server process.

## Architecture

The repo is one Python package, `agent/`, plus webhook plumbing and harness scaffolding.

### Two entry points, one process

- **`agent/server.py` → `get_agent(config)`** — async factory that returns a `create_deep_agent(...)` graph **per thread**. Each thread gets its own sandbox (cached in `SANDBOX_BACKENDS` keyed by `thread_id`); `langgraph.json` points at this for the `agent` graph.
- **`agent/webapp.py` → `app`** — FastAPI app with the webhook receivers (`/webhooks/linear`, `/webhooks/slack`, `/webhooks/github`, `/health`). Webhooks verify signatures, derive a deterministic `thread_id`, and kick off / route messages to runs on the LangGraph client. `langgraph.json` mounts this as the `http.app`.

Both are loaded by the LangGraph server, so `make dev` is enough to exercise the full webhook → agent flow.

### Sandbox lifecycle (the part with subtle ordering)

`get_agent` is called on every turn. The flow it implements is non-obvious:

1. Resolve a GitHub token (re-encrypted into `config["metadata"]["github_token_encrypted"]` so subsequent turns can reuse it).
2. Look up an in-memory `SandboxBackendProtocol` for the thread; check thread metadata for a stored `sandbox_id`. A sentinel `__creating__` indicates concurrent creation — `_wait_for_sandbox_id` polls until it resolves.
3. If the cached backend exists, refresh GitHub proxy credentials and ping it (`echo ok`); a `SandboxClientError` triggers `_recreate_sandbox`.
4. If only a stored ID exists, reconnect via the configured factory; if reconnection fails, recreate.
5. On a fresh sandbox, set git identity to `open-swe[bot]` and configure the LangSmith GitHub proxy with an installation token.

Sandbox provider selection is controlled by `SANDBOX_TYPE` (`langsmith` default; also `daytona`, `modal`, `runloop`, `local`). The factory map lives in `agent/utils/sandbox.py:SANDBOX_FACTORIES` — to add a provider you implement a `create_X_sandbox(sandbox_id=None)` factory in `agent/integrations/` and register it there. Only `langsmith` configures the GitHub proxy; other providers skip it. `validate_sandbox_startup_config()` runs in the FastAPI lifespan so misconfiguration fails at boot, not on first request.

### Tools and middleware

The agent is assembled from:

- `agent/tools/` — one file per tool. New tools go here and get added to the `tools=[...]` list in `get_agent`. The Deep Agents framework already provides `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`, `write_todos`, and `task` (subagent spawning) — don't reimplement them.
- `agent/middleware/` — deterministic hooks around the agent loop: `ToolErrorMiddleware`, `check_message_queue_before_model` (injects mid-run Linear/Slack messages), `ensure_no_empty_msg`, `open_pr_if_needed` (PR safety net). Order in the `middleware=[...]` list matters.

### System prompt construction

`agent/prompt.py:construct_system_prompt(...)` assembles a templated prompt from named sections and **injects the contents of `default_prompt.md`** (path overridable via `DEFAULT_PROMPT_PATH`) into a `### Custom Instructions` block. Curly braces in that file are escaped before `.format()`, so don't worry about literal `{}` breaking the template. `linear_project_id` and `linear_issue_number` flow through from `config["configurable"]["linear_issue"]` into the PR-title template.

### Webhook → thread routing

Each invocation source (Slack thread, Linear issue, GitHub PR/issue) maps to a deterministic `thread_id`, so follow-up messages on the same surface route to the same running agent. Slack and Linear can also send messages while the agent is mid-run — `check_message_queue_before_model` picks them up before the next model call.

`DEFAULT_REPO_OWNER`/`DEFAULT_REPO_NAME` and `SLACK_REPO_OWNER`/`SLACK_REPO_NAME` env vars set the default repo when the user didn't specify one. Slack messages support `repo:owner/name` syntax to override.

## Harness scaffolding (Dysprosium-specific)

These directories support the agent's *runtime* workflow, not this codebase's development:

- `templates/` — SPEC.md, PLAN.md, TEST_PLAN.md, QA_REPORT.md, PR_SUMMARY.md, REFLECTION.md, BEFORE.md, AFTER.md. The agent is expected to fill these in for tasks it works on.
- `roles/` — role-based playbooks (architect, backend-engineer, qa-automation-engineer, etc.).
- `gates/`, `docs/harness-engineering.md` — gate definitions and the harness-engineering overview.
- `default_prompt.md` — the custom prompt content stitched into every agent run.

When editing harness scaffolding, the change usually flows through `default_prompt.md` or the templates rather than through `agent/prompt.py` (which is upstream-shaped).

## Coding conventions

- Ruff is the only formatter/linter — line length 100, `select = [E, W, F, I, B, C4, UP]`, `E501` ignored.
- `pytest.ini_options` sets `asyncio_mode = "auto"`, so `async def test_*` works without an explicit marker.
- New tools live in `agent/tools/<tool>.py` and must be added to both `agent/tools/__init__.py` exports and the `tools=[...]` list in `agent/server.py:get_agent`.
- Sandbox integrations live in `agent/integrations/<provider>.py` and must be registered in `agent/utils/sandbox.py:SANDBOX_FACTORIES`.
