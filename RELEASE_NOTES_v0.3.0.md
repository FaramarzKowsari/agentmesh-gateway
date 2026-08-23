# AgentMesh Gateway v0.3.0

AgentMesh Gateway v0.3.0 adds a reproducible constrained-routing and offline adaptive-policy research layer on top of the v0.2 protocol gateway.

## Highlights

### Feasibility before optimization

Provider selection now has explicit hard gates for:

- configured model support;
- provider circuit availability;
- protocol-lossless translation requirements;
- declared provider capabilities;
- deterministic local request-quota exhaustion.

Only the remaining feasible provider set is passed to a ranking policy.

### Explicit capabilities

Providers can declare `text`, `tools`, `reasoning`, and `native_responses_tools` capabilities. Existing configurations that omit capabilities retain adapter-derived defaults for backward compatibility.

### Observed usage and cost evidence

v0.3 records exact input/output token counts when providers report them. Optional input/output USD-per-million prices allow observed request cost to be calculated only when both exact counts and both prices exist. Missing evidence remains missing.

The existing `cost_hint` remains a separate production-routing heuristic.

### Latency distributions

Successful provider attempts populate a bounded recent-latency window with deterministic p50/p95 diagnostics while preserving the existing EWMA live routing signal.

### Local request-quota windows

Providers can define a deterministic fixed local request-attempt window. Every outbound provider attempt consumes one unit, including failed attempts. Exhaustion removes the provider from the feasible set until the local window resets.

This is a local AgentMesh control model and is not presented as a mirror of vendor-side billing or rate-limit counters.

### No-network policy simulator

`agentmesh simulate` replays provider configurations and JSONL counterfactual outcome traces without contacting any provider. Static policy runs start from independent deterministic state and can be exported as JSON or CSV.

### Quality profiles and semantic task classes

A versioned quality-profile schema requires benchmark ID, benchmark version, source, metric, score, and sample count. Context is determined from normalized request semantics using `text`, `tool`, `reasoning`, and `native_tool` task classes.

The schema validates evidence structure but does not certify the scientific quality of an external benchmark.

### Offline adaptive research baselines

Two adaptive policies are available only in simulation:

- `adaptive_balanced` — a deterministic constrained multi-objective baseline using evolving latency/cost state, contextual quality prior, and quota pressure;
- `constrained_ucb` — a contextual UCB-style experimental baseline using selected-provider feedback and deterministic tie-breaking.

Both can choose only from the hard-feasible provider set.

## Production behavior

The live gateway still exposes the production policies:

- `ordered`
- `latency`
- `cost`
- `quality`
- `balanced`

v0.3.0 does not enable adaptive/UCB routing in production.

## Reproducibility

The default test and simulation paths require no paid provider API key. CI validates the project on Python 3.11, 3.12, and 3.13 with Ruff and pytest.

The files under `examples/simulation/` are synthetic mechanics fixtures. They are not empirical provider/model benchmark results.

## Explicit non-claims

v0.3.0 does not claim:

- empirical superiority of adaptive policies;
- equivalence between AgentMesh local quota windows and vendor quotas;
- complete billing accounting when providers do not expose exact usage;
- live production adaptive routing;
- vision/audio/context-aware capability routing;
- full OpenAI Responses compatibility;
- full Codex, Claude Code, Cline, or OpenCode compatibility;
- cross-vendor translation of native reasoning or built-in tools.

## Upgrade notes

Existing provider configurations remain valid. All new capability, token-price, and local quota fields are optional.

The package/runtime version is `0.3.0` and Python 3.11+ remains required.
