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
- The harness's `screenshot()` tool launches its own headless
  Chromium — it does **not** share cookies with whatever your product's
  Playwright spec used. For authenticated pages, run the spec via
  `npx playwright test ...` (which uses the `storageState` recipe
  below) and call `view_image()` on the resulting screenshots, OR
  navigate the harness's Chromium through the login form yourself
  before screenshotting.

## Auth: the `storageState` recipe

Test credentials live in the harness's `.env`:

```bash
# .env (gitignored)
TEST_USER_EMAIL="qa+yourproduct@example.com"
TEST_USER_PASSWORD="..."
```

Add a `globalSetup` to your product's Playwright config that logs in
once per test run and saves the auth state to disk. Subsequent specs
reuse it without ever touching the password.

### `playwright/global-setup.ts`

```typescript
import { chromium, FullConfig } from '@playwright/test';

const AUTH_FILE = 'playwright/.auth/user.json';

export default async function globalSetup(_config: FullConfig) {
  const email = process.env.TEST_USER_EMAIL;
  const password = process.env.TEST_USER_PASSWORD;
  if (!email || !password) {
    throw new Error(
      'TEST_USER_EMAIL / TEST_USER_PASSWORD must be set in the harness .env',
    );
  }

  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  await page.goto(process.env.BASE_URL ?? 'http://localhost:3000');
  await page.getByRole('button', { name: /sign in/i }).click();
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole('button', { name: /^sign in$/i }).click();
  // Wait for an authenticated-only element so we know login finished
  await page.waitForSelector('[data-testid="user-menu"]', { timeout: 10_000 });

  await context.storageState({ path: AUTH_FILE });
  await browser.close();
}
```

### `playwright.config.ts`

```typescript
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  globalSetup: require.resolve('./playwright/global-setup'),
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',
    storageState: 'playwright/.auth/user.json',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
```

### `.gitignore` in the product repo

```
playwright/.auth/
playwright-report/
test-results/
```

### What the agent should do

1. Confirm `TEST_USER_EMAIL` / `TEST_USER_PASSWORD` are set:
   `execute(command="test -n \"$TEST_USER_EMAIL\" && echo ok || echo MISSING")`.
2. `start_app(...)` to bring the dev server up.
3. `execute("npx playwright test e2e/your-spec.spec.ts")` — the
   `globalSetup` runs once, all subsequent specs are pre-authenticated.
4. Use `view_image(path)` on the spec's saved screenshots, or
   `upload_image(path, label="...")` to put them on the GitHub thread.

### Multi-role variant

If you need both an admin and a regular user (e.g. testing permission
boundaries), use `TEST_USERS_JSON` and a `globalSetup` that writes one
storageState file per role:

```bash
# .env
TEST_USERS_JSON='{"admin":{"email":"...","password":"..."},"viewer":{"email":"...","password":"..."}}'
```

```typescript
// global-setup.ts
const users = JSON.parse(process.env.TEST_USERS_JSON ?? '{}');
for (const [role, creds] of Object.entries(users)) {
  // ... log in, save to playwright/.auth/<role>.json
}
```

Then in specs: `test.use({ storageState: 'playwright/.auth/admin.json' })`.
