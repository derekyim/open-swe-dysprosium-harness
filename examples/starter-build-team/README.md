# Starter Build Team

A minimal scaffold for setting up a build team that the
`open-swe-dysprosium-harness` agent can operate inside.

## What's in here

| Path | Purpose |
|---|---|
| `roles/` | One markdown file per role. The H1 (`# Role Name`) becomes the role's display name in role-status announcements; the filename stem (`engineering-manager.md`) is the slug the agent uses. |
| `templates/` | Artifact templates the agent fills in per task — SPEC, PLAN, PR_SUMMARY, etc. |
| `playbooks/` | Repeatable workflows by task type (`add-backend-endpoint.md`, `fix-bug.md`, `frontend-visual-verification.md`, …). Optional but encouraged once you spot patterns. |
| `default_prompt.md` | Per-deployment prompt fragment that the harness injects into the agent's system prompt. Document product context, conventions, and non-negotiables here. |
| `AGENTS.md` | Read by the agent after cloning the *product* repo (a different file lives there) — but having one here is useful as the build team's own contract. |

## How to use this scaffold

1. Copy this directory into a new repo:
   ```bash
   cp -r examples/starter-build-team ~/code/my-product-build-team
   cd ~/code/my-product-build-team
   git init && git add . && git commit -m "initial scaffold"
   gh repo create my-product-build-team --private --source=. --push
   ```
2. Rename / edit each role file to match your team. Keep the filename slugs
   short and stable — they appear in every role-status announcement.
3. Replace the placeholder text in `default_prompt.md` with your product
   context (what the product is, where the PRD lives, conventions).
4. In your harness `.env`, point at this checkout:
   ```
   BUILD_TEAM_DIR="my-product-build-team"
   BUILD_TEAM_NAME="My Product Build Team"
   BUILD_TEAM_REPO_URL="https://github.com/<you>/my-product-build-team"
   PRODUCT_NAME="My Product"
   PRODUCT_REPO="<you>/my-product"
   ```
5. Restart the harness (`make dev`). The agent will load the new roles and
   read your `default_prompt.md` on the next run.

## What lives here vs. in the harness

- **Here (build-team-side):** roles, playbooks, artifact templates,
  product context, team-member context, anything project-specific.
- **In the harness (`open-swe-dysprosium-harness`):** the agent loop,
  tools (screenshot/start_app/upload_image/role_status/etc.),
  middleware, sandbox plumbing.

If you find yourself wanting to edit harness code to mention your
product, that's a sign the content actually belongs here instead.
