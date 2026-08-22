# Compatibility Product Spec

## Goal

A coding client should target one AgentMesh endpoint and continue to work when the selected upstream changes.

## Verified support

- OpenAI Chat Completions-shaped ingress for text conversations
- OpenAI Responses-shaped text ingress and ordered text streaming lifecycle
- Anthropic Messages-shaped ingress for text conversations
- generic OpenAI-compatible upstreams
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

## Explicitly incomplete

The following are roadmap items and must not be claimed as complete:

- OpenAI Responses reasoning-item preservation or translation
- built-in OpenAI tool semantics such as web search, file search, computer use, or code interpreter
- image/audio normalization
- websocket sampling
- prompt caching semantics
- batch APIs
- vendor-specific reasoning block preservation
- complete authentication-mode coverage for coding clients
- full Codex, Claude Code, Cline, and OpenCode contract suites

## Compatibility principle

When a feature cannot be translated without semantic loss, AgentMesh should expose the limitation rather than silently manufacture equivalent-looking output.
