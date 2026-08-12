# ADR-0001: Monorepo first

[中文](0001-monorepo-first_CN.md)

- Status: Accepted
- Date: 2026-08-12

## Context

One owner currently designs, develops, tests and operates the product. Desktop, gateway and engine contracts will evolve together during discovery. Premature repository separation would add release coordination without proven independent consumers.

## Decision

Keep all three modules in one repository with explicit dependency direction and contract tests. Split only when independent release cadence, access control or external engine consumers justify the cost.

## Consequences

Cross-module changes are atomic and CI is centralized. Maintainers must actively prevent direct database coupling and accidental imports across boundaries.
