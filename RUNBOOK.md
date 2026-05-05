# Runbook

Operational reference for the Dysprosium harness running locally via `langgraph dev`. Use this when a Linear/GitHub/Slack mention seems stuck or silent.

## TL;DR — is anything wrong?

```bash
# Server alive? (default port 2024; override with LANGGRAPH_PORT in .env or shell)
curl -s http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}/health

# Recent threads with status (idle / busy / error / interrupted)
curl -s http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}/threads/search \
  -X POST -H 'Content-Type: application/json' -d '{"limit":5}' \
  | python -m json.tool | grep -E '"thread_id"|"status"|"updated_at"'
```

`status: error` means the run already terminated — the agent will never post back to GitHub/Linear/Slack on its own from that point. Look up the trace (below) to see what blew up, then re-trigger.

## Where logs and state live

| Source | What's there | When to use |
|---|---|---|
| **Terminal running `langgraph dev`** | Every log line, warning, and traceback | First place to look — errors are loud |
| **Local API** `http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}` | Run/thread state, message history, queued runs | When you need structured data, not text |
| **LangGraph Studio UI** `https://smith.langchain.com/studio/?baseUrl=http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}` | GUI over the local API | Click through threads + runs visually |
| **LangSmith traces** `https://smith.langchain.com` → project `dysprosium-open-swe` | Per-run model calls, tool calls, latency, errors | See *why* a run stalled or which tool failed. Requires `LANGCHAIN_TRACING_V2=true` (already set in `.env`) |
| **`.langgraph_api/*.pckl`** | Checkpoint store (pickled) | Don't read directly — use the API above |

## Useful local API calls

The dev server is plain HTTP, so `curl` is enough. Replace `<thread_id>` and `<run_id>` from the output of the search above.

```bash
# Most recent runs across all threads
curl -s http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}/threads/search \
  -X POST -H 'Content-Type: application/json' \
  -d '{"limit":10,"sort_by":"updated_at","sort_order":"desc"}' | python -m json.tool

# Runs on one thread (each agent invocation is a run)
curl -s http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}/threads/<thread_id>/runs | python -m json.tool

# Current state of a thread (messages, tool calls so far)
curl -s http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}/threads/<thread_id>/state | python -m json.tool

# Cancel a stuck run
curl -s -X POST http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}/threads/<thread_id>/runs/<run_id>/cancel

# Decode the base64 error blob the API returns on failed threads
echo '<base64-error-string>' | base64 -d | python -m json.tool
```

## Common symptoms

**Linear/GitHub/Slack mention got "👀" but nothing happened after.**
The webhook fired and a thread was created, but the agent run errored. Run the TL;DR check — if the latest thread is `status: error`, look at the LangSmith trace for that thread's run. Re-trigger the mention after fixing.

**Mention returned no reaction at all.**
Webhook didn't reach the harness. Check:
- ngrok tunnel is up and pointing at `localhost:2024` — see `setup.md` for the configured tunnel URL
- The webhook signing secret in the GitHub/Linear/Slack app config matches `.env` (`GITHUB_WEBHOOK_SECRET`, `LINEAR_WEBHOOK_SECRET`, `SLACK_SIGNING_SECRET`)
- Terminal log shows the webhook arriving — if not, it's an ingress/auth problem, not an agent problem

**Run is `status: busy` for a long time.**
Could be legitimate (model is thinking, sandbox is running a long command) or stuck. LangSmith trace will show the last tool call. If it's `execute` with no return after several minutes, the sandbox command is the bottleneck — the harness sets a 5-minute timeout per `execute` call by default.

**Long agent run got cancelled mid-call with `CancelledError: Shutting down background workers`.**
The dev server has file-watch auto-reload on (default). Any edit to a watched file (`.env`, `agent/**`, `*.md`, etc.) triggers a restart that kills the running worker. LangGraph's `RETRYING` logic usually catches this and resumes the run on the new process — check `curl /threads/<id>/runs` to confirm the run's `status` went back to `running` rather than `error`. To avoid the disruption entirely on a long task, restart with `make dev-stable` (which adds `--no-reload`); you'll need to manually restart when you want to pick up code changes.

**`BlockingError` on first request after a code change.**
Something in the request path is doing sync filesystem/network I/O. Either move it to module import time (preferred for static lookups like role files) or wrap it in `await asyncio.to_thread(...)`. Restart `langgraph dev` after the fix.

**Cannot clone repo / GitHub permission errors.**
The `.env` vars `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, and `GITHUB_APP_PRIVATE_KEY` must be present in the shell that runs `langgraph dev` — sourcing them after starting the server has no effect. Restart with `set -a; source .env; set +a; uv run langgraph dev --no-browser`.

## Restarting cleanly

```bash
# Kill any running dev server first (Ctrl-C in its terminal)
set -a; source .env; set +a
make dev               # auto-reloads on file changes
# OR
make dev-stable        # disables auto-reload — use when you have a long task in flight
```

Watch the startup log for `validate_sandbox_startup_config` errors — they fail fast on missing env vars rather than dying on the first request.

## When state gets weird

The local checkpoint store at `.langgraph_api/` persists across restarts. To wipe it (loses all thread history; safe in dev):

```bash
rm -rf .langgraph_api/
```

Don't do this in production — you'll lose every thread's message queue and follow-up routing.

## Configuration knobs

All values below default to current behavior — uncomment in `.env` to override. The "Tuning" block at the bottom of `.env` lists them all.

| Env var | Default | What it does |
|---|---|---|
| `LANGGRAPH_HOST` | `localhost` | Bind host for `langgraph dev` (set to `0.0.0.0` to expose to LAN / tunnel) |
| `LANGGRAPH_PORT` | `2024` | Port for `langgraph dev`. Also feeds `LANGGRAPH_URL` when that's not set explicitly |
| `LANGGRAPH_URL` | `http://$HOST:$PORT` | Fully qualified URL the webapp uses to call its own runs API. Override only when behind a tunnel/proxy |
| `RUN_PORT` | `8000` | Port for `make run` (webhook-only mode, no graph) |
| `AGENT_RECURSION_LIMIT` | `1000` | Max graph steps per run before LangGraph aborts |
| `LLM_MAX_TOKENS` | `20000` | Per-step model output token limit |
| `LLM_MODEL_ID` | `anthropic:claude-opus-4-6` | Model used by the agent loop |
| `SANDBOX_TYPE` | `langsmith` | Sandbox provider: `langsmith` / `daytona` / `modal` / `runloop` / `local` |
| `SANDBOX_CREATION_TIMEOUT_SECONDS` | `180` | How long to wait for a sandbox to come up |
| `SANDBOX_POLL_INTERVAL_SECONDS` | `1.0` | Poll cadence while waiting for sandbox |
| `OPEN_SWE_BOT_NAME` | `open-swe[bot]` | Git author name for sandbox commits + PR trailers |
| `OPEN_SWE_BOT_EMAIL` | `open-swe@users.noreply.github.com` | Git author email |
| `ROLES_DIR` | `evalgenie-build-team/roles` | Where `role_status` reads role definitions from |
| `GITHUB_USER_EMAIL_MAP_JSON` | `{}` | JSON object mapping GitHub usernames → emails for collaborator attribution |

### Changing the port

Edit `.env`:

```bash
LANGGRAPH_PORT=3030
LANGGRAPH_HOST=0.0.0.0
```

Then:

```bash
set -a; source .env; set +a
make dev
# → langgraph dev --host 0.0.0.0 --port 3030
```

The webapp's `LANGGRAPH_URL` (used by the harness to call its own runs API) automatically rebuilds to `http://0.0.0.0:3030`. You only need to set `LANGGRAPH_URL` explicitly if you're behind an ngrok tunnel or proxy.

One-shot override without editing `.env`:

```bash
make dev LANGGRAPH_PORT=3030 LANGGRAPH_HOST=0.0.0.0
```

After changing the port, update the curl commands in the TL;DR check above:

```bash
curl -s http://localhost:3030/health
curl -s http://localhost:3030/threads/search -X POST \
  -H 'Content-Type: application/json' -d '{"limit":5}'
```

(Or just rely on the `${LANGGRAPH_PORT:-2024}` fallback in this runbook's snippets — they already adapt if the env var is sourced.)

### Bot identity for commits

If you fork the GitHub App, change the bot identity so commits are attributed correctly. Both `OPEN_SWE_BOT_NAME` and `OPEN_SWE_BOT_EMAIL` flow through to the in-sandbox `git config --global` and to the `Co-authored-by:` trailer in PRs.

```bash
OPEN_SWE_BOT_NAME=my-bot[bot]
OPEN_SWE_BOT_EMAIL=my-bot@users.noreply.github.com
```

Restart `langgraph dev` after changing — the git config is applied when the sandbox is first created for a thread.

### Tuning agent reach

Two knobs matter for long, complex tasks:

- `AGENT_RECURSION_LIMIT` — bump if a multi-role task hits "Recursion limit reached" before finishing. Default 1000 is generous; raise to 1500–2000 only if you see real graph-step exhaustion (not infinite loops).
- `LLM_MAX_TOKENS` — bump for tasks that produce long files (architecture docs, large refactors). Costs more per step; default 20k is fine for most code edits.

Both take effect on the next `langgraph dev` restart.
