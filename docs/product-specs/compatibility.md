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
- non-streaming function-call and function-result normalization across:
  - OpenAI Responses `function_call` / `function_call_output`
  - OpenAI Chat Completions `tool_calls` / `tool_call_id`
  - Anthropic Messages `tool_use` / `tool_result`
- function-tool schema conversion between flat Responses tools, Chat Completions tools,
  and Anthropic `input_schema`

## Explicitly incomplete

The following are roadmap items and must not be claimed as complete:

- streaming function-call argument delta translation across vendors
- complete OpenAI Responses compatibility for reasoning, images, audio, and built-in tools
- image/audio normalization
- prompt caching semantics
- batch APIs
- vendor-specific reasoning block preservation
- full Codex, Claude Code, Cline, and OpenCode contract suites

## Compatibility principle

When a feature cannot be translated without semantic loss, AgentMesh should expose the limitation rather than silently manufacture equivalent-looking output.
