# Dysprosium Harness Kit Agent Instructions

This repository extends Open SWE with Symphony-style harness engineering patterns.

## Prime Directive

Do not jump directly to code. For every meaningful task:

1. Understand the task.
2. Produce or update a SPEC.
3. Produce a PLAN.
4. Define acceptance criteria.
5. Implement changes.
6. Run relevant checks.
7. Produce QA evidence.
8. Summarize the PR honestly.

## Required Artifacts

For normal feature work:

- SPEC.md
- PLAN.md
- TEST_PLAN.md
- QA_REPORT.md
- PR_SUMMARY.md
- REFLECTION.md

For bug fixes:

- BEFORE.md
- AFTER.md

For UI work:

- screenshots or Playwright trace evidence where practical

## Rules

- Never claim tests passed unless they were actually run.
- Record commands attempted and their results.
- Prefer small, reviewable PRs.
- Preserve upstream Open SWE behavior unless a task explicitly changes it.
- Keep generic harness logic separate from per-project / per-build-team logic. Project-specific content (product names, role definitions, playbooks, default prompts) lives in `$BUILD_TEAM_DIR`, never in the harness repo.
