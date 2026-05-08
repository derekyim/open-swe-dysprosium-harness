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


| Source                                                                                                                            | What's there                                     | When to use                                                                                                |
| --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| **Terminal running `langgraph dev`**                                                                                              | Every log line, warning, and traceback           | First place to look — errors are loud                                                                      |
| **Local API** `http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}`                                                       | Run/thread state, message history, queued runs   | When you need structured data, not text                                                                    |
| **LangGraph Studio UI** `https://smith.langchain.com/studio/?baseUrl=http://${LANGGRAPH_HOST:-localhost}:${LANGGRAPH_PORT:-2024}` | GUI over the local API                           | Click through threads + runs visually                                                                      |
| **LangSmith traces** `https://smith.langchain.com` → project `dysprosium-open-swe`                                                | Per-run model calls, tool calls, latency, errors | See *why* a run stalled or which tool failed. Requires `LANGCHAIN_TRACING_V2=true` (already set in `.env`) |
| `**.langgraph_api/*.pckl`**                                                                                                       | Checkpoint store (pickled)                       | Don't read directly — use the API above                                                                    |


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
The dev server has file-watch auto-reload on (default). Any edit to a watched file (`.env`, `agent/`**, `*.md`, etc.) triggers a restart that kills the running worker. LangGraph's `RETRYING` logic usually catches this and resumes the run on the new process — check `curl /threads/<id>/runs` to confirm the run's `status` went back to `running` rather than `error`. To avoid the disruption entirely on a long task, restart with `make dev-stable` (which adds `--no-reload`); you'll need to manually restart when you want to pick up code changes.

`**BlockingError` on first request after a code change.**
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


| Env var                            | Default                                 | What it does                                                                                                                            |
| ---------------------------------- | --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `LANGGRAPH_HOST`                   | `localhost`                             | Bind host for `langgraph dev` (set to `0.0.0.0` to expose to LAN / tunnel)                                                              |
| `LANGGRAPH_PORT`                   | `2024`                                  | Port for `langgraph dev`. Also feeds `LANGGRAPH_URL` when that's not set explicitly                                                     |
| `LANGGRAPH_URL`                    | `http://$HOST:$PORT`                    | Fully qualified URL the webapp uses to call its own runs API. Override only when behind a tunnel/proxy                                  |
| `RUN_PORT`                         | `8000`                                  | Port for `make run` (webhook-only mode, no graph)                                                                                       |
| `AGENT_RECURSION_LIMIT`            | `1000`                                  | Max graph steps per run before LangGraph aborts                                                                                         |
| `LLM_MAX_TOKENS`                   | `20000`                                 | Per-step model output token limit                                                                                                       |
| `LLM_MODEL_ID`                     | `anthropic:claude-opus-4-6`             | Model used by the agent loop                                                                                                            |
| `SANDBOX_TYPE`                     | `langsmith`                             | Sandbox provider: `langsmith` / `daytona` / `modal` / `runloop` / `local`                                                               |
| `LOCAL_SANDBOX_ROOT_DIR`           | `sandbox` (when `SANDBOX_TYPE=local`)   | Working dir for the local sandbox. Relative paths resolve against the harness root. The agent's clones land here.                       |
| `SANDBOX_CREATION_TIMEOUT_SECONDS` | `180`                                   | How long to wait for a sandbox to come up                                                                                               |
| `SANDBOX_POLL_INTERVAL_SECONDS`    | `1.0`                                   | Poll cadence while waiting for sandbox                                                                                                  |
| `RUN_ERROR_NOTIFY_ENABLED`         | `true`                                  | When an agent run errors before it can post for itself, a background watcher posts a short "run failed" comment to the source channel. Set `false` to disable. |
| `RUN_ERROR_POLL_INTERVAL_SECONDS`  | `10`                                    | How often the run-error watcher polls for new failures. Min 2.                                                                          |
| `OPEN_SWE_BOT_NAME`                | `open-swe[bot]`                         | Git author name for sandbox commits + PR trailers                                                                                       |
| `OPEN_SWE_BOT_EMAIL`               | `open-swe@users.noreply.github.com`     | Git author email                                                                                                                        |
| `BUILD_TEAM_DIR`                   | `build-team` (relative to harness root) | Path to your build-team checkout — provides `roles/`, `templates/`, `playbooks/`, `default_prompt.md`, `repos.json`                     |
| `BUILD_TEAM_NAME`                  | `Build Team`                            | Display name surfaced in the agent's role-announcement prompt                                                                           |
| `BUILD_TEAM_REPO_URL`              | *(unset)*                               | Optional GitHub URL of the build team repo, for prompt context                                                                          |
| `PRODUCT_NAME`                     | *(unset)*                               | Display name of the product the build team ships, for prompt context                                                                    |
| `PRODUCT_REPO`                     | *(unset)*                               | `owner/name` of the primary product repo                                                                                                |
| `PROJECT_REPOS_JSON`               | *(unset)*                               | Optional override for the build team's `repos.json`. Same JSON shape — useful for ad-hoc additions without committing to the build team |
| `FRONT_END_REPO_NAME_FOR_VISUAL_TESTING` | *(unset)*                         | Slug from `repos.json` naming the repo whose dev server is the UI for visual testing. Annotated in the agent's prompt as the unambiguous `screenshot()` / Playwright target. |
| `FRONT_END_MAIN_PAGE_URL`          | *(unset)*                               | Full URL (scheme + port + path) the agent should open as its default visual-testing baseline (e.g. `https://localhost:3000/admin/users`). Surfaced verbatim in the prompt's Visual Verification section. |
| `TEAM_MEMBERS_JSON`                | `{}`                                    | Optional JSON mapping GitHub login → "Name + role"                                                                                      |
| `ROLES_DIR`                        | `$BUILD_TEAM_DIR/roles`                 | Where `role_status` reads role definitions from. Override only if your roles live outside the build team root                           |
| `GITHUB_USER_EMAIL_MAP_JSON`       | `{}`                                    | JSON object mapping GitHub usernames → emails for collaborator attribution                                                              |
| `OPEN_SWE_MENTION_TAGS`            | `@openswe,@open-swe,@openswe-dev`       | Comma-separated `@`-mentions that trigger the agent on a GitHub issue/PR                                                                |


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

For a clean run where you don't risk the agent stopping due to code changes
set -a && source .env && set +a && make dev-stable

Modal
if using modal sandboxes with multiple projects 
 /Users/<username>/.modal.toml
just make sure only one profile is active and the rest have
 active = false

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

## Using your new dev team

The harness is generic — every project-specific concept (the team's identity, the role personas, artifact templates, playbooks, the product's prompt, and which repos compose the product) lives in a separate **build team** repo. To plug in a new team you create a build-team checkout, point the harness at it via `.env`, and restart.

This section is the end-to-end recipe.

### What's in a build team

A build team is a git repo (or any directory) with this shape:

```
your-build-team/
├── roles/                      # one .md per role; H1 = display name, filename stem = slug
│   ├── engineering-manager.md
│   ├── architect.md
│   ├── frontend-engineer.md
│   ├── backend-engineer.md
│   └── qa-manager.md
├── templates/                  # artifact templates the agent fills in per task
│   ├── SPEC.md
│   ├── PR_SUMMARY.md
│   └── QA_REPORT.md
├── playbooks/                  # repeatable workflows by task type (optional)
│   └── frontend-visual-verification.md
├── memory/                     # durable lessons (auto-loaded into the prompt)
│   ├── architecture-decisions.md
│   ├── known-failures.md
│   └── deploy-gotchas.md
├── default_prompt.md           # injected into the agent's system prompt every run
├── repos.json                  # the product repos this team operates on
└── AGENTS.md                   # optional: cross-cutting team conventions
```

Nothing here is harness-side. You can add files (e.g. `memory/`, `quality-gates/`) for your team's own use — the harness only reads the four marked files plus any extra prompt content from `default_prompt.md`.

### Step-by-step: plug in a new team

**1. Scaffold from the starter.** The harness ships a working example at `examples/starter-build-team/`:

```bash
cp -r examples/starter-build-team ~/code/my-build-team
cd ~/code/my-build-team
git init && git add . && git commit -m "initial scaffold"
gh repo create my-build-team --private --source=. --push
```

**2. Customize the roles.** Edit each file in `roles/` to match your team. The H1 (`# QA Manager`) becomes the role's display name in announcements; the filename slug (`qa-manager.md`) is what the agent passes to `role_status`. Add or delete role files freely — the harness loads whatever's there.

**3. Fill in `default_prompt.md`.** Replace the `<placeholders>` with your product's name, repo paths, PRD location, conventions, and any non-negotiables. This content is injected into the agent's system prompt on every run as a "Custom Instructions" block.

**4. (Optional) Add a `memory/` directory.** Create `<your-build-team>/memory/` with one `.md` file per category of durable lessons (e.g. `architecture-decisions.md`, `known-failures.md`). The harness auto-loads everything in there into the agent's prompt as a "Durable Lessons" section, and the `record_lesson` tool appends new entries the agent learns. Skip this until you have lessons worth recording — leaving the dir empty is fine.

**5. Define `repos.json`.** This is how the agent knows which repos compose your product:

```json
[
  {
    "slug": "frontend",
    "repo": "your-org/your-frontend",
    "local_checkout": "sandbox/your-frontend",
    "purpose": "Next.js companion app + sidecar UI"
  },
  {
    "slug": "api",
    "repo": "your-org/your-api",
    "local_checkout": "sandbox/your-api",
    "purpose": "FastAPI services + worker pipelines"
  },
  {
    "slug": "infra",
    "repo": "your-org/your-infra",
    "purpose": "Terraform + GitHub Actions for deploys"
  }
]
```

- `slug` is the short tag the agent uses (`role_status(... summary="starting on frontend ...")`)
- `repo` is `owner/name` — used to build clone URLs and API calls
- `local_checkout` is optional — a path to an already-cloned copy. **Convention: put it under `sandbox/<repo-name>`** so it lives in the harness's gitignored working area (see "The `sandbox/` directory" below). When set and you're running `SANDBOX_TYPE=local`, the agent uses the existing checkout instead of re-cloning. Ignored for remote sandboxes.
- `purpose` is one sentence telling the agent what the repo is for. The agent uses these descriptions to decide which repo a task belongs to.

#### The `sandbox/` directory

When `SANDBOX_TYPE=local`, the agent's working directory is `<harness>/sandbox/`. Everything inside `sandbox/` is gitignored (except its own README), so cloned product repos don't leak into the harness's diff. To pre-clone something so the agent skips the clone step:

```bash
cd <harness>/sandbox
git clone git@github.com:your-org/your-frontend.git
```

Then set `local_checkout: "sandbox/your-frontend"` in the build team's `repos.json`. The agent will see the existing checkout and operate on it directly. If `local_checkout` points to a path that doesn't exist, the agent falls back to a fresh clone.

The agent reads this list automatically and exposes it via the `list_project_repos()` tool for cross-repo workflows.

**6. Configure the harness's `.env`.**

Required:

```bash
BUILD_TEAM_DIR="path/to/my-build-team"      # absolute or relative to harness root
BUILD_TEAM_NAME="My Build Team"             # display name in role announcements
PRODUCT_NAME="My Product"                   # for prompt context
PRODUCT_REPO="your-org/your-frontend"       # primary product repo (used as fallback default)
DEFAULT_REPO_OWNER="your-org"               # webhook routing fallback
DEFAULT_REPO_NAME="your-frontend"           # webhook routing fallback
OPEN_SWE_MENTION_TAGS="@yourbot,@your-other-tag"   # what triggers the agent on GitHub
FRONT_END_REPO_NAME_FOR_VISUAL_TESTING="frontend"  # slug from repos.json — UI target for screenshots/Playwright
FRONT_END_MAIN_PAGE_URL="https://localhost:3000/"  # default URL for screenshots — full scheme + port + path
```

Optional:

```bash
BUILD_TEAM_REPO_URL="https://github.com/you/my-build-team"
TEAM_MEMBERS_JSON='{"alice":"Alice — engineering manager"}'
PROJECT_REPOS_JSON='[ ... ]'                # only for ad-hoc override of repos.json
```

If a value contains spaces, **quote it** — `BUILD_TEAM_NAME=My Build Team` will fail (`source .env` reads `Build` as a command). Use `BUILD_TEAM_NAME="My Build Team"`.

**7. Verify it loads.** Before mentioning the agent on a real ticket:

```bash
set -a; source .env; set +a
uv run python -c "
from agent.utils.build_team import get_build_team_dir, get_build_team_name
from agent.utils.roles import load_roles
from agent.utils.project_repos import load_project_repos
print('Team:', get_build_team_name(), '@', get_build_team_dir())
print('Roles:', list(load_roles()))
print('Repos:', [r['slug'] for r in load_project_repos()])
"
```

You should see your team name, all your role slugs, and all your repo slugs.

**8. Restart and trigger a real run.**

```bash
make dev-stable    # or `make dev` if you'll edit code while it runs
```

…then mention one of your `OPEN_SWE_MENTION_TAGS` on a GitHub issue. Watch the issue thread for:

- `**<Your Team Name>** opens with a routing announcement` (engineering-manager `starting`)
- `Role transitions` between specialists
- `**Engineering Manager** — PR opened: <url>` when `commit_and_open_pr` succeeds
- A final completion comment

If any of these are missing, check the LangGraph dev server's terminal log — the agent's tool calls are visible there, and any `role_status` / `upload_image` failures print the reason.

### Running multiple projects

For a second product, clone the harness into a separate directory and give each its own `.env`:

```
~/code/
├── open-swe-dysprosium-harness-evalgenie/      # harness clone 1
│   └── .env  (BUILD_TEAM_DIR=../evalgenie-build-team, LANGGRAPH_PORT=2024, ...)
├── open-swe-dysprosium-harness-project2/       # harness clone 2
│   └── .env  (BUILD_TEAM_DIR=../project2-build-team, LANGGRAPH_PORT=2025, ...)
├── evalgenie-build-team/
├── project2-build-team/
├── agent-quality-helper/
└── project2-product/
```

The two harness instances run on different ports, see different webhooks (each project's GitHub App points at its own ngrok tunnel → its own port), and operate on different products. Pull harness updates with `git pull` in each — both pick up new tools and prompt changes the same way.

### Test credentials for Playwright

When the agent uses `screenshot()` or runs the product's Playwright specs against an authenticated surface, it needs login credentials. The right home for them is the harness's **`.env`** — it's already gitignored, already sourced into the shell that runs `langgraph dev`, and `LocalShellBackend(inherit_env=True)` propagates env vars into every process the agent spawns (including `npx playwright test`).

```bash
# .env
TEST_USER_EMAIL="qa+yourproduct@example.com"
TEST_USER_PASSWORD="..."

# Multi-role variant:
TEST_USERS_JSON='{"admin":{"email":"...","password":"..."},"viewer":{"email":"...","password":"..."}}'
```

**Where to NOT put them:**

- The build team repo — committed, shared with anyone with read access; it's for *configuration*, not secrets.
- The product repo — same risk if `.env` ever gets tracked accidentally.

#### The `storageState` pattern

Once a test run uses the password to log in, save the resulting cookies/localStorage to a file so subsequent specs start authenticated. Playwright's built-in mechanism is `storageState`:

1. A `globalSetup` script runs once at the top of the test session. It opens a browser, fills in the login form using `process.env.TEST_USER_EMAIL` / `..._PASSWORD`, navigates to the post-login page, and calls `page.context().storageState({ path: 'playwright/.auth/user.json' })`.
2. Every subsequent spec uses `test.use({ storageState: 'playwright/.auth/user.json' })` (or sets it project-wide in `playwright.config.ts`). The browser starts already logged in.
3. `playwright/.auth/` is gitignored.

This means the password lives only in your shell and one short-lived browser session per test run. The agent passes it through; it never lands in test code, fixtures, or screenshots.

The skeleton lives in `examples/starter-build-team/playbooks/frontend-visual-verification.md` — copy it into your product's Playwright config and adjust selectors.

### Things that aren't config

If you find yourself wanting one of these, the answer is "put it in your build team," not "add a harness env var":

- Product-specific PRDs, design docs, or memory notes → build team `memory/` or product repo `docs/`
- Dev commands (`yarn dev`, `pnpm test`, etc.) → build team playbooks; the agent reads them when needed
- Task templates beyond SPEC/PLAN/QA_REPORT → build team `templates/`
- Quality gates / definition-of-done → build team `quality-gates/`
- Per-repo lint commands → product repo `AGENTS.md` (which the agent reads after cloning)

Everything in `.env` should be either a credential, an integration setting, or one of the small set of identifiers the harness needs to find your build team. Anything richer belongs in the build team repo where the team can review changes.