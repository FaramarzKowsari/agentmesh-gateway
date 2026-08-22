# Codex compatibility contract

AgentMesh includes a deterministic contract harness for the public custom-provider boundary used by OpenAI Codex. The harness does not download Codex, does not contact OpenAI, and does not require a provider API key.

## Contract boundary

The fixture follows the current upstream Codex test configuration:

```toml
model = "m"
model_provider = "agentmesh"

[model_providers.agentmesh]
name = "AgentMesh Gateway"
base_url = "http://127.0.0.1:8787/v1"
wire_api = "responses"
supports_websockets = false
```

With that shape, the client-facing sampling endpoint is:

```text
POST /v1/responses
```

The fixture is stored at `tests/fixtures/codex/config.toml`.

## What the harness proves

`tests/test_codex_contract.py` sends a Codex-shaped text request into the real AgentMesh ASGI application. `tests/test_codex_tool_contract.py` extends the same public boundary through a complete custom-function turn. Both tests route through AgentMesh's real provider selection and OpenAI-compatible adapter backed by `httpx.MockTransport`.

The contract suite verifies that:

- instructions become a system message for a Chat Completions-style upstream;
- user input survives normalization;
- a Responses function tool becomes the nested Chat Completions function schema;
- text Chat Completions SSE is reconstructed as an ordered Responses SSE lifecycle;
- streamed Chat Completions `tool_calls` become Responses function-call argument events;
- the completed function call preserves its call ID, function name, and exact JSON arguments;
- a following Responses `function_call_output` becomes the matching assistant tool call plus tool-result message for the upstream;
- the continuation can stream a final assistant text response through `/v1/responses`;
- a streamed tool call commits the response, preventing silent failover after the client has observed tool state.

No external network call is made by the contract tests.

## Provenance of the contract

The boundary was checked against the upstream `openai/codex` repository at commit `343074d4207d572809bd8cea15f4be1d09d98e0b`:

- `sdk/typescript/tests/testCodex.ts` configures a mock provider with `base_url`, `wire_api = "responses"`, and `supports_websockets = false`.
- `codex-rs/core/tests/suite/cli_stream.rs` configures a custom Responses provider at `<server>/v1` and verifies that Codex posts to `/v1/responses`.

AgentMesh intentionally tests the public wire boundary rather than copying Codex implementation code or test fixtures.

## What this does not prove

This contract must not be described as complete Codex compatibility. It does not yet prove reasoning-item preservation, built-in OpenAI tool semantics, websocket sampling, all authentication modes, images/audio, multi-agent behavior, or every Codex CLI/SDK feature. Those require separate explicit gates.
