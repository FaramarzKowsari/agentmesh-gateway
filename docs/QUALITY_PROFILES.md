# Benchmark Quality Profiles

AgentMesh keeps benchmark quality evidence separate from live provider runtime state and from the static `quality_hint` configuration.

A quality-profile document has schema version 1 and requires explicit provenance:

```json
{
  "schema_version": 1,
  "benchmark_id": "my-coding-benchmark",
  "benchmark_version": "2026-08",
  "source": "Reproducible procedure or dataset reference",
  "metric": "pass_rate",
  "profiles": [
    {
      "provider": "provider-a",
      "model": "model-a",
      "task_class": "tool",
      "score": 0.81,
      "sample_count": 120
    }
  ]
}
```

The loader rejects missing provenance, scores outside `[0, 1]`, non-positive sample counts, unknown task classes, and duplicate provider/model/task-class entries.

## Deterministic task classes

v0.3 classifies requests from normalized protocol semantics only:

- `text` — ordinary text request;
- `tool` — custom function/tool use;
- `reasoning` — request carries Responses reasoning semantics;
- `native_tool` — request carries a recognized non-function native Responses tool.

The classifier does not inspect prompt wording to guess difficulty or subject. Vision, audio, and context-window classes remain deferred until the normalized request model represents those dimensions explicitly.

## Use in v0.3

Quality profiles are optional inputs to the offline simulator. `adaptive_balanced` and `constrained_ucb` use a matching profile score as contextual quality prior when available, otherwise falling back to the provider's configured `quality_hint`.

Profiles do **not** silently replace live production routing. The ordinary gateway `quality` and `balanced` policies retain their existing semantics in v0.3.

## Evidence discipline

A score is evidence only to the extent that the declared benchmark and source support it. AgentMesh validates structure and provenance presence; it cannot validate the scientific quality of an external benchmark merely by loading JSON.

The committed `examples/simulation/quality-profiles.json` file is a synthetic mechanics-only fixture. Its numbers are not measurements of real models or providers and must not be reported as benchmark results.
