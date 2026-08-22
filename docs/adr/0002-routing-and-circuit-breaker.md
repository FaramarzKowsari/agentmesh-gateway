# ADR 0002: Policy routing with per-provider circuit breakers

- Status: Accepted
- Date: 2026-08-22

## Context

A gateway must keep working when a provider is slow, rate-limited, or unavailable.

## Decision

Rank eligible providers using a selectable policy. Track runtime success/failure/latency separately from immutable provider configuration. Open a provider circuit after a configurable number of retryable failures and exclude it until cooldown expires.

## Consequences

Fallback becomes deterministic and testable. Later versions can persist metrics without changing the provider interface.
