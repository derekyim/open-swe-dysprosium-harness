# Build Team Agent Instructions

This is the build team's contract. The harness injects a different
`AGENTS.md` (the one inside the *product* repo) into the agent's
prompt — but if you also keep one here, the team can refer to it for
cross-cutting conventions that apply to every product.

## Prime Directive

For every meaningful task:

1. Understand the task end-to-end before changing code.
2. Pick the role(s) that apply (see `roles/`).
3. Produce the artifacts named in `templates/`.
4. Run the relevant checks; record what was attempted and what failed.
5. Open a small reviewable PR.
6. Honestly summarize what was done — never claim a check passed if
   it was skipped.

## Non-negotiables

- Never claim tests passed unless they were actually run.
- Prefer small, reviewable PRs over broad rewrites.
- Don't introduce secrets, credentials, or large generated files.
- When a reasonable assumption can unblock the task, document the
  assumption and proceed rather than blocking on clarification.
