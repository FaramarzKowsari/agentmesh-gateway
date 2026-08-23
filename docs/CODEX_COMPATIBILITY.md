# Codex compatibility contract

AgentMesh includes deterministic contract harnesses for the public custom-provider boundary used by OpenAI Codex. The harnesses do not download Codex, do not contact OpenAI, and do not require a live provider API key.

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

## Translation contracts

`tests/test_codex_contract.py` sends a translatable Responses text request into the real AgentMesh ASGI application. `tests/test_codex_tool_contract.py` extends the same public boundary through a complete custom-function turn. These tests route through AgentMesh's real provider selection and Chat Completions adapter backed by `httpx.MockTransport`.

They verify that:

- instructions become a system message for a Chat Completions-style upstream;
- user input survives normalization;
- a Responses function tool becomes the nested Chat Completions function schema;
- text Chat Completions SSE is reconstructed as an ordered Responses SSE lifecycle;
- streamed Chat Completions `tool_calls` become Responses function-call argument events;
- the completed function call preserves its call ID, function name, and exact JSON arguments;
- a following Responses `function_call_output` becomes the matching assistant tool call plus tool-result message for the upstream;
- the continuation can stream a final assistant text response through `/v1/responses`;
- a streamed tool call commits the response, preventing silent failover after the client has observed tool state.

## Native Responses reasoning contract

`tests/test_native_responses.py` covers request semantics that must not be downgraded to Chat Completions or Anthropic Messages. The test configures an ordinary Chat Completions provider before a native `responses` provider and proves that a reasoning-bearing Codex-style request skips the ordinary provider.

The native contract preserves on the upstream wire:

- `reasoning.effort`, `reasoning.summary`, and `reasoning.context`;
- `include`, including `reasoning.encrypted_content`;
- prior reasoning input items and encrypted content;
- `prompt_cache_key` and `service_tier`;
- Responses `text` and `stream_options` controls;
- `client_metadata`;
- `tool_choice`, `parallel_tool_calls`, and `store`.

Native Responses SSE events are proxied as Responses events instead of being reconstructed from a reduced text-only representation. The contract therefore verifies that reasoning output items and encrypted reasoning content remain present in the client-facing stream. The native adapter also normalizes assistant text and custom function-call deltas internally so the provider boundary remains observable and testable.

## Native Responses tool contract

`tests/test_native_responses_tools.py` covers recognized Responses-native tools that cannot be represented losslessly as ordinary Chat Completions or Anthropic custom functions. The test deliberately places a translated provider before a native `responses` provider and verifies that a native-tool request skips the translated provider.

The contract verifies that:

- recognized non-`function` Responses tools force native-only routing;
- native tool JSON definitions are forwarded without schema rewriting;
- coding-oriented tool literals such as `local_shell`, `shell`, and `apply_patch` are recognized by the current explicit whitelist;
- web-search lifecycle SSE events pass through `/v1/responses` unchanged;
- an unknown tool type is rejected as a client error before provider execution;
- a native-only tool request returns a clean no-eligible-provider error before stream headers start when no native Responses provider is configured;
- ordinary custom `function` tools remain eligible for cross-protocol translation.

This is protocol preservation, not local tool execution. AgentMesh does not claim to execute provider-native web search, shell, patch, computer-use, MCP, code-interpreter, or other native tools itself.

No external network call is made by these contract tests.

## Provenance of the contract

The Codex custom-provider boundary was checked against the upstream `openai/codex` repository at commit `343074d4207d572809bd8cea15f4be1d09d98e0b`:

- `sdk/typescript/tests/testCodex.ts` configures a mock provider with `base_url`, `wire_api = "responses"`, and `supports_websockets = false`.
- `codex-rs/core/tests/suite/cli_stream.rs` configures a custom Responses provider at `<server>/v1` and verifies that Codex posts to `/v1/responses`.
- `codex-rs/codex-api/src/common.rs` defines the Responses request surface used by the compatibility harness.

The native Responses tool whitelist is maintained against the public Responses tool types rather than inferred from private provider behavior. AgentMesh intentionally tests public wire contracts instead of copying Codex implementation code or test fixtures.

## What this does not prove

This contract must not be described as complete Codex compatibility. It does not prove cross-vendor reasoning translation, cross-vendor translation or local execution of provider-native built-in tools, websocket sampling, all authentication modes, images/audio, multi-agent behavior, compaction/memory endpoints, or every Codex CLI/SDK feature. Those require separate explicit gates.
