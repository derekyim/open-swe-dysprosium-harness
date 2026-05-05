# Runbook

Operational reference for the Dysprosium harness running locally via `langgraph dev`. Use this when a Linear/GitHub/Slack mention seems stuck or silent.

## TL;DR — is anything wrong?

```bash
# Server alive?
curl -s http://localhost:2024/health

# Recent threads with status (idle / busy / error / interrupted)
curl -s http://localhost:2024/threads/search \
  -X POST -H 'Content-Type: application/json' -d '{"limit":5}' \
  | python -m json.tool | grep -E '"thread_id"|"status"|"updated_at"'
```

`status: error` means the run already terminated — the agent will never post back to GitHub/Linear/Slack on its own from that point. Look up the trace (below) to see what blew up, then re-trigger.

## Where logs and state live

| Source | What's there | When to use |
|---|---|---|
| **Terminal running `langgraph dev`** | Every log line, warning, and traceback | First place to look — errors are loud |
| **Local API** `http://localhost:2024` | Run/thread state, message history, queued runs | When you need structured data, not text |
| **LangGraph Studio UI** `https://smith.langchain.com/studio/?baseUrl=http://localhost:2024` | GUI over the local API | Click through threads + runs visually |
| **LangSmith traces** `https://smith.langchain.com` → project `dysprosium-open-swe` | Per-run model calls, tool calls, latency, errors | See *why* a run stalled or which tool failed. Requires `LANGCHAIN_TRACING_V2=true` (already set in `.env`) |
| **`.langgraph_api/*.pckl`** | Checkpoint store (pickled) | Don't read directly — use the API above |

## Useful local API calls

The dev server is plain HTTP, so `curl` is enough. Replace `<thread_id>` and `<run_id>` from the output of the search above.

```bash
# Most recent runs across all threads
curl -s http://localhost:2024/threads/search \
  -X POST -H 'Content-Type: application/json' \
  -d '{"limit":10,"sort_by":"updated_at","sort_order":"desc"}' | python -m json.tool

# Runs on one thread (each agent invocation is a run)
curl -s http://localhost:2024/threads/<thread_id>/runs | python -m json.tool

# Current state of a thread (messages, tool calls so far)
curl -s http://localhost:2024/threads/<thread_id>/state | python -m json.tool

# Cancel a stuck run
curl -s -X POST http://localhost:2024/threads/<thread_id>/runs/<run_id>/cancel

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

**`BlockingError` on first request after a code change.**
Something in the request path is doing sync filesystem/network I/O. Either move it to module import time (preferred for static lookups like role files) or wrap it in `await asyncio.to_thread(...)`. Restart `langgraph dev` after the fix.

**Cannot clone repo / GitHub permission errors.**
The `.env` vars `GITHUB_APP_ID`, `GITHUB_APP_INSTALLATION_ID`, and `GITHUB_APP_PRIVATE_KEY` must be present in the shell that runs `langgraph dev` — sourcing them after starting the server has no effect. Restart with `set -a; source .env; set +a; uv run langgraph dev --no-browser`.

## Restarting cleanly

```bash
# Kill any running dev server first (Ctrl-C in its terminal)
set -a; source .env; set +a
uv run langgraph dev --no-browser
```

Watch the startup log for `validate_sandbox_startup_config` errors — they fail fast on missing env vars rather than dying on the first request.

## When state gets weird

The local checkpoint store at `.langgraph_api/` persists across restarts. To wipe it (loses all thread history; safe in dev):

```bash
rm -rf .langgraph_api/
```

Don't do this in production — you'll lose every thread's message queue and follow-up routing.
