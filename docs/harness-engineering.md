# Dysprosium Harness Engineering

Dysprosium Harness Kit extends Open SWE with a stricter engineering harness inspired by Symphony-style autonomous software engineering.

## Base System

Open SWE provides the core async coding-agent workflow:

- task intake
- planning
- implementation
- review
- sandboxed execution
- PR creation

## Dysprosium Additions

This fork adds:

- SPEC-first task contracts
- role-based work routing
- required proof artifacts
- QA and release gates
- memory and reflection artifacts
- EvalGenie-compatible observability hooks, planned for later phases

## Target Workflow

Issue or task file
→ Product/engineering planning
→ SPEC
→ PLAN
→ implementation
→ tests and verification
→ QA report
→ PR summary
→ human review
→ merge readiness

## Initial Principle

The first phase should not alter Open SWE behavior. It should add structure, documentation, templates, and conventions.
