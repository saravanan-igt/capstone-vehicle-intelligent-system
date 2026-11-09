# ADR-001: Modular monolith with a deterministic lending engine

**Status:** Accepted, 2026-11-07

## Context

Lending decisions must be reproducible, auditable and cited at clause level. One team owns the whole system. A decision, its snapshot and its audit event must be written in one transaction.

## Decision

- Build a single FastAPI deployable with hexagonal boundaries. The `domain/` package imports no FastAPI, ORM, Redis or Gemini code.
- Eligibility and loan amounts come only from `domain/eligibility.py`, which evaluates typed rules from a versioned, published policy. Calculations use `Decimal` and policy-defined rounding.
- The LLM explains recorded results only. Its output is validated against the decision (outcome, citations and numbers), with a template as the fallback.

## Alternatives

- **Microservices per module:** rejected for now. They add distributed transactions and operational cost without a scaling or ownership driver.
- **LLM-decided eligibility:** rejected. It is non-reproducible, can invent thresholds and cannot be audited.
- **Rules as free-form expressions or code from documents:** rejected. That would allow code injection through uploaded policies.

## Limitations

- New rule types need code changes, plus tests and an engine version bump.

## Revisit when

- A module needs independent scaling or release cadence. Ingestion workers are the first candidate (Phase 4).
- Separate teams take ownership of separate modules.
