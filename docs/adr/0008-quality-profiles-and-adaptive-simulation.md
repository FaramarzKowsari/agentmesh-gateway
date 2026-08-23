# ADR 0008: Provenance Quality Profiles and Adaptive Simulation

Status: accepted

## Context

Static quality hints are useful configuration priors but are not benchmark evidence. Adaptive routing research also needs a controlled way to use contextual quality evidence and evolving runtime observations without silently changing production selection behavior.

## Decision

AgentMesh introduces:

1. deterministic semantic task classes (`text`, `tool`, `reasoning`, `native_tool`);
2. versioned benchmark quality profiles with mandatory provenance and sample counts;
3. two offline-only adaptive simulation policies:
   - `adaptive_balanced`, a deterministic multi-objective penalty using evolving latency/cost state, contextual quality prior, and quota pressure;
   - `constrained_ucb`, an experimental contextual UCB baseline using chosen-only feedback.

Both adaptive policies first obtain the feasible provider set through the ordinary router in ordered mode. Model, protocol, capability, circuit, and quota-exhaustion constraints therefore dominate every adaptive score.

## Adaptive balanced objective

The simulation-only penalty is:

```text
0.40 * latency_norm
+ 0.25 * cost_norm
+ 0.25 * (1 - quality_prior)
+ 0.10 * quota_pressure
```

Latency and cost components evolve from selected outcomes when observed. Missing cost uses the provider's static `cost_hint`; contextual quality uses a matching benchmark profile when available and otherwise `quality_hint`.

## Constrained UCB baseline

For each `(task_class, provider)` the simulator keeps selected-feedback count and mean reward. UCB combines the observed mean reward (or the same contextual prior before observation) with a deterministic exploration bonus. Provider configuration order breaks exact ties.

The UCB implementation is an experimental baseline for reproducible comparison, not a claim of optimality or a theorem about regret under arbitrary traces.

## Production boundary

Neither adaptive policy is enabled in the live gateway in v0.3. Existing production policies retain their previous behavior. Moving an adaptive policy into production would require a separate ADR, operational safeguards, and benchmark evidence.

## Consequences

- contextual quality evidence has explicit provenance;
- simulation can compare static and adaptive constrained policies on identical traces;
- hard validity constraints remain outside the optimization objective;
- no performance claim follows merely from implementing the policies.
