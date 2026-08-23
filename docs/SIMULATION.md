# Deterministic Policy Simulation

AgentMesh can replay routing policies without contacting any provider:

```bash
agentmesh simulate \
  --providers examples/simulation/providers.json \
  --trace examples/simulation/trace.jsonl \
  --policies ordered,latency,cost,quality,balanced
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

Missing usage remains missing. Cost is calculated only when both exact token counts and both explicit provider prices exist. Missing quality remains missing.

## Fair policy comparison

Each policy is replayed from a fresh runtime state and an independent deterministic clock. This prevents a prior policy run from consuming another policy's quota or seeding its latency state.

The baseline policies are `ordered`, `latency`, `cost`, `quality`, and `balanced`.

## Output

JSON output contains a per-policy summary plus per-request rows. CSV output contains the row-level fields:

- policy
- request ID / simulation time
- selected provider
- status
- latency
- observed cost
- supplied quality
- local quota pressure after the attempt

## Research caution

The committed files in `examples/simulation/` are tiny deterministic fixtures for demonstrating mechanics. They are **not benchmark evidence** and must not be cited as measured model/provider performance. Research claims require a documented trace source or a committed benchmark-generation procedure.
