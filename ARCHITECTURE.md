# Architecture

## Design goals

AgentMesh is built around four separations:

1. **Ingress protocol** is not a provider implementation.
2. **Routing feasibility** is not routing optimization.
3. **Provider health** is runtime state, not configuration.
4. **Control-plane information** is isolated from model payloads.

This makes it possible to add a new coding client without rewriting providers, or add a provider without changing client-facing routes.

## Runtime flow

```text
HTTP request
  -> authentication dependency
  -> ingress parser / normalized request
  -> GatewayService
  -> Router feasibility gates
       protocol semantics
       model match
       circuit availability
       required capabilities
  -> Router policy score / ordering
  -> Provider.complete()/stream()
  -> runtime metrics update
  -> protocol response renderer
```

### `agentmesh.api`
Owns public HTTP routes and authentication wiring. It should remain thin.

### `agentmesh.gateway`
Owns fallback orchestration. It never knows vendor HTTP details.

### `agentmesh.routing`
Owns feasibility filtering, ranking, and circuit-breaker state. Ranking is deterministic for a given configuration, normalized request, and metrics snapshot.

### `agentmesh.providers`
Owns upstream network behavior. Provider adapters convert normalized requests into vendor requests and normalize vendor responses.

### `agentmesh.protocols`
Owns conversion between client wire formats and the protocol-neutral domain model.

### `agentmesh.config`
Owns environment parsing and immutable provider specifications. Provider API keys are referenced by environment-variable name. Provider capabilities are configuration constraints rather than learned runtime metrics.

## Routing feasibility

A provider reaches policy scoring only if it satisfies every hard constraint:

1. its circuit is available;
2. the requested model is `auto` or is advertised by the provider;
3. the adapter can preserve the request's protocol semantics;
4. the provider's effective capability set contains every capability required by the normalized request.

The initial capability vocabulary is `text`, `tools`, `reasoning`, and `native_responses_tools`. If a provider omits an explicit capability list, adapter-derived defaults preserve pre-v0.3 behavior. See `docs/adr/0003-capability-aware-routing.md`.

Capability feasibility is intentionally separate from optimization. A cheap provider that lacks `tools` cannot outrank a more expensive provider for a custom-function request because the cheap provider is removed before scoring.

## Routing score

For feasible providers, the balanced policy computes a normalized penalty:

```text
score = 0.45 * latency + 0.30 * cost + 0.25 * (1 - quality)
```

Unknown latency receives a neutral starting value. Provider weight is applied as a penalty multiplier. Other policies optimize latency, cost, or quality independently over the same feasible candidate set.

## Failure policy

- network errors, timeouts, HTTP 408, 409, 425, 429 and 5xx are retryable across providers;
- most 4xx errors are terminal because retrying another provider could hide a malformed client request;
- repeated retryable failures open a provider circuit for a cooldown period;
- successful requests close/reset the circuit.

## Streaming

Streaming adapters expose an async iterator of normalized chunks. The API layer emits Server-Sent Events in the client protocol. Provider eligibility is checked before streaming headers are committed. Failover is allowed only before the first client-visible text/tool/native event is committed; after commitment AgentMesh does not silently switch providers.

## Extension contract

A provider plugin implements the `Provider` protocol from `agentmesh.providers.base`. It must expose:

- `name`
- `complete(request)`
- `stream(request)`
- `list_models()`

No plugin may import FastAPI route modules.
