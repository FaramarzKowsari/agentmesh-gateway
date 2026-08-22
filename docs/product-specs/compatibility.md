# Compatibility Product Spec

## Goal

A coding client should target one AgentMesh endpoint and continue to work when the selected upstream changes.

## Supported in v0.1

- OpenAI Chat Completions-shaped ingress for text conversations
- Anthropic Messages-shaped ingress for text conversations
- generic OpenAI-compatible upstreams
- Anthropic Messages upstreams
- non-streaming completion
- text streaming
- optional tool payload pass-through where the selected upstream uses the same tool schema

## Explicitly incomplete

The following are roadmap items and must not be claimed as complete:

- OpenAI Responses API lifecycle compatibility
- cross-vendor tool-call translation
- image/audio normalization
- prompt caching semantics
- batch APIs
- vendor-specific reasoning block preservation
- full Codex, Claude Code, Cline, and OpenCode contract suites

## Compatibility principle

When a feature cannot be translated without semantic loss, AgentMesh should expose the limitation rather than silently manufacture equivalent-looking output.
