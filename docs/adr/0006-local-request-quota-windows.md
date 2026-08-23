# ADR 0006: Local Request-Quota Windows

Status: accepted

## Context

Adaptive routing needs a reproducible way to represent provider exhaustion and quota pressure. Provider-side billing and rate-limit counters are vendor-specific, may be unavailable, and cannot be inferred reliably from successful responses alone.

## Decision

AgentMesh supports an optional local fixed request-attempt window per provider through:

- `request_quota_limit`
- `request_quota_window_seconds`

The two fields must be configured together. A window begins on the first outbound attempt. Every outbound attempt consumes one unit, including attempts that later fail. Once `used >= limit`, the provider is removed from the feasible set before policy scoring. At or after the fixed-window duration, local usage resets deterministically.

The runtime exposes used, remaining, pressure, exhaustion state, and reset interval. Pressure is diagnostic evidence in this work package; it is not silently injected into the existing balanced/latency/cost/quality scores.

## Why outbound attempts

A provider boundary has been exercised once AgentMesh issues the request. Counting only successful requests would systematically understate pressure during provider instability and would make retry-heavy traces incomparable.

## Limitations

This is a local control model, not a claim about vendor billing, RPM/TPM state, or private server counters. It does not parse provider rate-limit headers and it does not assert that its reset boundary matches an upstream service.

## Consequences

- quota exhaustion becomes a hard feasibility constraint;
- simulations can reproduce exhaustion without live APIs;
- failed attempts correctly consume local request budget;
- later research policies may use pressure as a soft signal only through an explicit policy change and benchmarked comparison.
