# ADR 0007: Deterministic Policy Simulation

Status: accepted

## Context

Adaptive routing cannot be evaluated responsibly by changing live selection behavior and observing uncontrolled traffic. AgentMesh needs an offline substrate where multiple policies see the same request sequence and provider outcomes.

## Decision

Provide a no-network simulator that reuses `ProviderSpec`, `Router`, and `RuntimeStateStore` semantics. A JSON provider configuration and JSONL trace describe request requirements and counterfactual provider outcomes. Every policy run starts from a fresh state and deterministic clock.

The simulator updates the same measured state concepts as runtime routing when observations are explicitly present: successful latency, exact token usage/cost, and local request-quota consumption. Missing observations remain missing.

## Why counterfactual outcomes

A policy comparison requires knowing what each candidate would have produced on the same trace. The simulator therefore accepts per-provider outcomes supplied by a synthetic generator, recorded evaluation harness, or benchmark procedure. The simulator does not manufacture unobserved outcomes itself.

## Output contract

The engine produces deterministic per-request rows and aggregate summaries. JSON is sorted and stable; CSV is available for notebooks and statistical tooling.

## Consequences

- baseline policies can be compared without API keys or network access;
- quota/capability feasibility is exercised under the same conceptual model as runtime routing;
- benchmark-derived quality and adaptive policies can be layered on top without modifying provider adapters;
- committed demonstration traces are fixtures, not empirical performance claims.
