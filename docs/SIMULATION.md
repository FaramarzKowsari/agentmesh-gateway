# Deterministic Policy Simulation

AgentMesh can replay routing policies without contacting any provider:

```bash
agentmesh simulate \
  --providers examples/simulation/providers.json \
  --trace examples/simulation/trace.jsonl \
  --policies ordered,latency,cost,quality,balanced
```

Adaptive research policies can be included with an optional provenance-checked quality profile:

```bash
agentmesh simulate \
  --providers examples/simulation/providers.json \
  --trace examples/simulation/trace.jsonl \
  --quality-profiles examples/simulation/quality-profiles.json \
  --policies balanced,adaptive_balanced,constrained_ucb
```

Use `--format csv` for row-oriented output or `--output PATH` to write a file.

## Provider file

The provider file is a JSON list accepted by `ProviderSpec.from_dict`. Simulation therefore uses the same model lists, capability gates, cost hints, explicit token prices, and local request-quota configuration as the runtime gateway.

No `base_url` is contacted during simulation.

## Trace format

Each non-comment JSONL line is one request:

```json
{
  "id": "request-1",
  "at_seconds": 0,
  "model": "m",
  "requirements": ["text", "tools"],
  "outcomes": {
    "provider-a": {
      "success": true,
      "latency_ms": 125,
      "input_tokens": 100,
      "output_tokens": 40,
      "quality": 0.82
    }
  }
}
```

Supported request requirements are currently `text`, `tools`, `reasoning`, and `native_responses_tools`. They map to the same feasibility concepts used by the runtime router. Unsupported modalities are not invented by the simulator.

For each selected provider, the trace may report:

- `success`: boolean, default `true`;
- `latency_ms`: required for a successful selected outcome;
- `input_tokens` / `output_tokens`: optional exact non-negative counts;
- `quality`: optional observed score in `[0, 1]` supplied by the trace producer.

Missing usage remains missing. Cost is calculated only when both exact token counts and both explicit provider prices exist. Missing outcome quality remains missing in reported measurements.

## Fair policy comparison

Each policy is replayed from a fresh runtime state and an independent deterministic clock. This prevents a prior policy run from consuming another policy's quota, seeding its latency state, or training its bandit state.

Static policies are `ordered`, `latency`, `cost`, `quality`, and `balanced`.

Two simulation-only adaptive policies are available:

- `adaptive_balanced` — a deterministic multi-objective score whose latency and cost terms evolve from selected observations and whose contextual quality prior comes from a matching benchmark quality profile when available;
- `constrained_ucb` — an experimental contextual UCB baseline with selected-only feedback and deterministic tie-breaking.

Both receive their candidate set from the normal feasibility logic. Model, protocol, capability, circuit, and quota-exhaustion constraints cannot be overridden by adaptive scoring.

See [QUALITY_PROFILES.md](QUALITY_PROFILES.md) for the quality evidence contract and ADR 0008 for the adaptive research boundary.

## Output

JSON output contains a per-policy summary plus per-request rows. CSV output contains:

- policy
- request ID / simulation time
- semantic task class
- selected provider and status
- latency and observed cost
- supplied outcome quality
- matching profile quality, when available
- policy selection value for adaptive policies
- local quota pressure after the attempt

`constrained_ucb` JSON output also includes final per-task/provider feedback counts and mean rewards.

## Research caution

The committed files in `examples/simulation/` are tiny deterministic fixtures for demonstrating mechanics. They are **not benchmark evidence** and must not be cited as measured model/provider performance. The quality-profile example explicitly identifies itself as synthetic. Research claims require a documented trace source or a committed benchmark-generation procedure.
