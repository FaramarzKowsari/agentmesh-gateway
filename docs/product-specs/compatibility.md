# Compatibility Product Spec

## Goal

A coding client should target one AgentMesh endpoint and continue to work when the selected upstream changes without silently losing protocol semantics.

## Verified support

- OpenAI Chat Completions-shaped ingress for text conversations
- OpenAI Responses-shaped ingress for text, custom functions, and native Responses controls
- Anthropic Messages-shaped ingress for text conversations
- generic OpenAI-compatible Chat Completions upstreams
- native OpenAI Responses-compatible upstreams
- Anthropic Messages upstreams
- non-streaming completion
- text streaming with failover only before the first committed chunk
- request ID propagation and provider circuit recovery
- function-call and function-result normalization across:
  - OpenAI Responses `function_call` / `function_call_output`
  - OpenAI Chat Completions `tool_calls` / `tool_call_id`
  - Anthropic Messages `tool_use` / `tool_result`
- function-tool schema conversion between flat Responses tools, Chat Completions tools,
  and Anthropic `input_schema`
- streamed custom function-call argument translation from OpenAI-compatible and Anthropic
  upstreams into the Responses function-call event lifecycle
- failover protection after either text or function-call output has been committed
- a deterministic Codex custom-provider wire-contract harness covering:
  - Responses text streaming
  - a streamed function call
  - `function_call_output` continuation back into the selected upstream
- native Responses preservation for Responses-only request semantics including:
  - `reasoning` controls
  - `include`
  - reasoning input items
  - `prompt_cache_key`
  - `service_tier`
  - Responses `text` controls
  - `stream_options`
  - `client_metadata`
  - `tool_choice`, `parallel_tool_calls`, and `store`
- native Responses SSE passthrough so reasoning items and encrypted reasoning content are not
  flattened into text or discarded
- native Responses tool-definition preservation for the current public SDK tool-type union,
  including web/file search, computer use, MCP, code interpreter, local/sandbox shell,
  apply-patch, tool-search, namespace/custom tools, and related native types
- native built-in-tool SSE passthrough: tool lifecycle events are preserved at `/v1/responses`
  rather than translated into invented custom-function events

## Explicitly incomplete

The following are roadmap items and must not be claimed as complete:

- cross-vendor reasoning translation between Responses, Chat Completions, and Anthropic thinking
- cross-vendor translation of native Responses built-in tools into other provider tool systems
- local execution of provider-native built-in tools by AgentMesh itself
- image/audio input normalization across protocols
- websocket sampling
- cross-vendor prompt caching semantics
- batch APIs
- translation of vendor-specific reasoning blocks into a shared reasoning representation
- complete authentication-mode coverage for coding clients
- full Codex, Claude Code, Cline, and OpenCode contract suites

## Routing rule

If a Responses request contains semantics that AgentMesh cannot translate losslessly, only a native
`responses` provider is eligible. The gateway must return that no eligible provider is available
rather than silently sending a downgraded request to another adapter.

Recognized native Responses tools follow the same rule: `function` remains cross-protocol
translatable, while other recognized Responses tool types require a native Responses provider.
Unknown tool types are rejected as client errors before provider execution.

## Compatibility principle

When a feature cannot be translated without semantic loss, AgentMesh should expose the limitation
or preserve the native protocol boundary rather than manufacture equivalent-looking output.
