# Architecture

## Design goals

AgentMesh is built around four separations:

1. **Ingress protocol** is not a provider implementation.
2. **Routing policy** is not network execution.
3. **Provider health** is runtime state, not configuration.
4. **Control-plane information** is isolated from model payloads.

This makes it possible to add a new coding client without rewriting providers, or add a provider without changing client-facing routes.

## Runtime flow

```text
HTTP request
  -> authentication dependency
  -> ingress parser
  -> GatewayService
  -> Router.rank()
  -> CircuitBreaker.allow()
  -> Provider.complete()/stream()
  -> metrics update
  -> protocol response renderer
```

### `agentmesh.api`
Owns public HTTP routes and authentication wiring. It should remain thin.

### `agentmesh.gateway`
Owns fallback orchestration. It never knows vendor HTTP details.

### `agentmesh.routing`
Owns ranking and circuit-breaker state. Ranking is deterministic for a given configuration and metrics snapshot.

### `agentmesh.providers`
Owns upstream network behavior. Provider adapters convert normalized requests into vendor requests and normalize vendor responses.

### `agentmesh.protocols`
Owns conversion between client wire formats and the protocol-neutral domain model.

### `agentmesh.config`
Owns environment parsing and immutable provider specifications. Provider API keys are referenced by environment variable name.

## Routing score

The balanced policy computes a normalized penalty:

```text
score = 0.45 * latency + 0.30 * cost + 0.25 * (1 - quality)
```

Unknown latency receives a neutral starting value. A provider with an open circuit is excluded before ranking.

## Failure policy

- network errors, timeouts, HTTP 408, 409, 425, 429 and 5xx are retryable across providers;
- most 4xx errors are terminal because retrying another provider could hide a malformed client request;
- repeated retryable failures open a provider circuit for a cooldown period;
- successful requests close/reset the circuit.

## Streaming

Streaming adapters expose an async iterator of normalized text chunks. The API layer emits Server-Sent Events in the client protocol. Provider failover is allowed only before the first streamed chunk is committed; a future milestone will make this boundary explicit with a commit-state object.

## Extension contract

A provider plugin implements the `Provider` protocol from `agentmesh.providers.base`. It must expose:

- `name`
- `complete(request)`
- `stream(request)`
- `list_models()`

No plugin may import FastAPI route modules.
