# Durable Lessons

The harness auto-loads every `*.md` file in this directory into the
agent's system prompt as a **Durable Lessons** section. New entries
get appended here by the `record_lesson(category, title, body)` tool.

## Categories (one file each)

Pick names that group lessons usefully. Common starting points:

- `architecture-decisions.md` — schema, contract, and component-boundary
  decisions with rationale
- `known-failures.md` — past incidents, the cause, and what prevents
  recurrence
- `deploy-gotchas.md` — non-obvious things that break under real
  deployment conditions
- `testing-lessons.md` — flaky-test patterns, debugging recipes
- `prompt-lessons.md` — what the agent has learned about its own prompt /
  workflow / tooling

## Entry shape

`record_lesson` writes entries in this format:

```markdown
---

### YYYY-MM-DD — One-line title (≤ 80 chars)

One-to-three short paragraphs. Lead with the constraint or fact.
Then a brief *why*. Then "How to apply" if it's non-obvious.

_Last verified: YYYY-MM-DD_
```

## What makes a good lesson

- A constraint, gotcha, or decision-with-rationale that **future runs
  would otherwise re-learn**.
- Specific enough to be useful (cite the file/component) but not so
  task-specific that it decays in a week.
- Includes the *why* — agents and humans alike judge edge cases from
  the reasoning, not the rule.

## What doesn't belong here

- One-off task details ("fixed the bug in issue #123") — that lives
  in PR descriptions, not memory.
- Anything derivable from reading the code.
- Anything already documented in `AGENTS.md` or `default_prompt.md`.

This README is gitignored at the harness level — only files matching
`*.md` (other than this one's `README.md`) are loaded into the prompt.
