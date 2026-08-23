# ADR 0004: Observed-only token and cost accounting

Status: accepted

## Context

The v0.3 adaptive-router roadmap needs reproducible cost evidence. AgentMesh already has `cost_hint`, a normalized static routing heuristic, but that field is not a bill, a token price, or an observed runtime cost.

Provider APIs differ in whether and when they report token usage. Estimating missing usage from text length would mix model-specific assumptions into runtime state and would make research results difficult to reproduce or audit.

## Decision

Provider specifications may declare:

- `input_cost_per_million`: USD per one million input tokens
- `output_cost_per_million`: USD per one million output tokens

Both fields are optional and non-negative. Explicit `0.0` is distinct from an omitted price.

Runtime accounting follows an observed-only rule:

1. input/output token totals are updated only when an upstream response reports those counts through the normalized provider contract;
2. request cost is computed only when both input and output token counts are present and both prices are configured;
3. missing usage or missing prices produce no cost observation;
4. failed attempts produce no usage/cost observation;
5. streaming usage is recorded only when an adapter observes exact final usage on the wire.

The cost formula is:

```text
cost_usd = (
    input_tokens * input_cost_per_million
    + output_tokens * output_cost_per_million
) / 1_000_000
```

`cost_hint` remains unchanged and continues to drive the existing static `cost` and `balanced` routing policies. Observed cost is evidence for diagnostics, simulation, and later adaptive policies; it does not silently alter routing behavior in this work package.

## Streaming scope

Native Responses streaming can surface exact final usage from a `response.completed` response object when that usage is present. AgentMesh records it.

For streaming adapter paths where the current wire contract does not expose an exact final usage observation, AgentMesh records no token cost rather than estimating it.

## Runtime diagnostics

Provider runtime state records:

- cumulative observed input tokens
- cumulative observed output tokens
- number of token-usage observations
- cumulative observed USD cost
- number of complete cost observations
- last observed input/output token counts
- last observed complete USD cost

These fields are exposed by the authenticated `/admin/providers` endpoint together with the configured token prices.

## Consequences

- Cost evidence is auditable and does not depend on hidden token estimators.
- Local/free providers can explicitly configure zero prices and produce valid zero-cost observations when usage is reported.
- Providers with missing usage remain distinguishable from genuinely free providers.
- `cost_total_usd` is not guaranteed to cover every successful request; coverage is represented by observation counts.
- Later policy simulation must account for missing observations instead of treating them as zero.
