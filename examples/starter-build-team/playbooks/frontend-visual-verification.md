# Playbook: Frontend Visual Verification

When a task changes a UI surface, follow this recipe to produce
visible evidence the GitHub / Linear comment will surface.

## Setup (per product — fill in once)

| Field | Value |
|---|---|
| Dev command | `&lt;e.g. pnpm dev / yarn dev:demo / make dev&gt;` |
| Working directory | `&lt;path inside the product repo&gt;` |
| Default port | `&lt;e.g. 3000&gt;` |
| Ready path | `&lt;e.g. / or /api/health&gt;` |
| Auth fixture | `&lt;test creds env vars or "n/a"&gt;` |
| Key URLs to verify | `&lt;e.g. /, /pricing, /admin/users&gt;` |

## Steps

1. **Engineering Manager — starting**
   `role_status(role="engineering-manager", phase="starting", summary="visual change to <surface>")`.

2. **Frontend Engineer — starting**
   `role_status(role="frontend-engineer", phase="starting", summary="<one sentence>")`.

3. **Capture baseline (before changes):**
   - `start_app(working_dir, command, port, ready_path)` — confirm `success: true`
   - `screenshot(url, ...)` for each key URL
   - `upload_image(path, label="before: <url>")` — keep the markdown
     output for the PR comment

4. **Implement the change.** Edit code. Run lint/typecheck/format.

5. **Capture after-state:**
   - If the dev server is hot-reload-aware, just re-`screenshot()`.
   - Otherwise `stop_app(port)` then `start_app(...)` again.
   - `upload_image(path, label="after: <url>")`

6. **Review the screenshots yourself** before declaring done. Code
   that compiles is not the same as a UI that works.

7. **PR + completion:**
   - `commit_and_open_pr(...)` — the harness auto-posts the PR-opened
     announcement.
   - `github_comment` (or `linear_comment`) with the visual evidence:
     ```
     **Visual evidence**

     Before: &lt;upload_image markdown&gt;
     After: &lt;upload_image markdown&gt;

     &lt;1–2 sentences of narration&gt;
     ```
   - `role_status(role="frontend-engineer", phase="done", ...)` then
     `role_status(role="engineering-manager", phase="done", ...)`.

## Common gotchas

- `wait_for` selector is essential for SPAs whose root path renders
  before data loads. Use `wait_for="[data-testid='page-ready']"`
  or similar.
- For pages behind auth, set the test creds in `.env` and have the
  fixture log in via the Playwright `storageState` mechanism in your
  product's `e2e/` config — the harness's screenshot tool inherits
  the same browser session via `start_app`'s dev server, but only if
  the product itself reads the test session from a known location.
