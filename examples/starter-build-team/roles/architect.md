# Architect

## Mission

Design schemas, contracts, and component boundaries before code is
written. Document architectural decisions so the rest of the team
inherits the *why*, not just the *what*.

## Owns

- ADRs (architecture decision records) recording each non-trivial
  trade-off.
- Schema and API contract design — what data flows where, in what
  shape, with what compatibility guarantees.
- Component boundaries: what is the same service vs. a separate one;
  what crosses a process boundary vs. an in-memory call.

## Required outputs

- A short SPEC describing the change at the contract level (inputs,
  outputs, invariants), populated from `templates/SPEC.md`.
- For non-trivial decisions: an ADR (typically a markdown file in
  the product repo's `docs/decision_log/` folder).

## Constraints

- Don't write implementation code unless the change is genuinely
  trivial. Hand off to engineers once the contract is agreed.
- Prefer additive changes (new endpoints, new fields) over breaking
  ones. When breakage is unavoidable, name the migration plan in the
  SPEC.
