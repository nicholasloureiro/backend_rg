# 1. Record architecture decisions

Date: 2026-04-19

## Status

Accepted

## Context

We need to record the architectural decisions made on this project.

## Decision

We will use Architecture Decision Records (ADRs), as [described by Michael Nygard](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions).

Each ADR:
- Lives in `docs/adr/` as a numbered markdown file (e.g. `0001-title.md`).
- Has sections: **Status**, **Context**, **Decision**, **Consequences**.
- Is immutable once accepted. Superseded decisions are replaced with a new ADR that references the old one.

## Consequences

- Every significant architectural choice has a written rationale.
- New contributors can read ADRs to understand why the system is shaped the way it is.
- Revisiting a decision means writing a new ADR, not editing an existing one.
