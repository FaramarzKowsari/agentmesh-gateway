# ADR 0001: Independent gateway architecture

- Status: Accepted
- Date: 2026-08-22

## Context

The project needs a universal coding-agent/model gateway while maintaining a clear, reviewable implementation history independent from existing gateway repositories.

## Decision

Use a protocol-neutral domain model between ingress parsers and provider adapters. Keep routing, provider health, HTTP API, and vendor networking in separate modules. Record architectural changes as ADRs.

## Consequences

This introduces conversion code at boundaries, but prevents vendor wire formats from becoming the internal architecture and makes independent evolution easier to demonstrate.
