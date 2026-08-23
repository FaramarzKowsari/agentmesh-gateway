# ADR 0005: Bounded latency distributions alongside EWMA

Status: accepted

## Context

AgentMesh currently tracks one latency EWMA per provider and uses that value in the existing `latency` and `balanced` routing policies. EWMA is cheap and responsive, but it does not describe tail latency or the spread of recent observations. The v0.3 simulation/research plan needs reproducible p50/p95 evidence without adding an external metrics backend or unbounded memory growth.

Changing the live routing signal at the same time as adding measurement would confound behavior changes with instrumentation changes.

## Decision

Each provider runtime state retains a bounded deque of successful request latencies.

- default window: 128 successful observations
- oldest successful observation is evicted when the window is full
- failed attempts do not enter the window
- tests/simulations may instantiate `RuntimeStateStore` with a smaller explicit window
- current `latency_ewma_ms` update and routing score remain unchanged

p50 and p95 use the deterministic nearest-rank definition:

```text
ordered = sort(recent_success_latencies)
rank = max(1, ceil(percentile * N))
value = ordered[rank - 1]
```

For an empty window, the percentile is undefined (`None`). For a one-sample window, p50 and p95 are both that sample.

## Diagnostics

The authenticated `/admin/providers` endpoint exposes:

- `latency_ewma_ms`
- `latency_p50_ms`
- `latency_p95_ms`
- `latency_sample_count`
- `latency_window_size`

The raw sample deque remains an internal runtime implementation detail.

## Consequences

- Runtime memory is bounded by provider count × window size.
- p50/p95 are exactly reproducible from a known retained sample window and percentile definition.
- Tail-latency evidence becomes available for policy simulation and benchmark reports.
- The live router does not change behavior in this work package; any later use of p95 in routing must be a separate policy decision with its own tests/ADR.
- Percentiles describe only the retained recent-success window, not the lifetime distribution and not failed request duration.
