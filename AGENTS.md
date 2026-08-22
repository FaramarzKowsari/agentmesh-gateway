# AGENTS.md

This file is the operating guide for Codex and other coding agents working on AgentMesh Gateway.

## Mission

Build AgentMesh as an independent universal AI coding-agent/model gateway. Do not copy source, tests, documentation, assets, naming, or internal structure from `free-claude-code` or other gateway projects. General public behavior can inspire requirements; implementations must be original.

## Sources of truth

Read these before substantial changes:

- `README.md` — product contract and setup
- `ARCHITECTURE.md` — package boundaries and runtime behavior
- `PROVENANCE.md` — independence constraints
- `ROADMAP.md` — milestone scope
- `docs/adr/` — accepted engineering decisions

## Mandatory workflow

1. Keep each task small enough for one reviewable PR.
2. Write or update tests with behavior changes.
3. Run `ruff check .` and `pytest` before finalizing.
4. Never commit API keys, tokens, cookies, OAuth artifacts, or provider credentials.
5. Do not weaken tests to make a change pass.
6. Prefer typed, protocol-neutral domain objects over vendor-shaped dictionaries outside adapters.
7. Keep FastAPI details inside `agentmesh.api` and vendor HTTP details inside `agentmesh.providers`.
8. Add an ADR when changing a package boundary, routing rule, persistence strategy, or public compatibility contract.

## Coding conventions

- Python 3.11+.
- Type annotations for public functions.
- Async for provider I/O.
- Raise `ProviderError` for normalized upstream failures.
- No broad `except Exception` unless it immediately translates/logs at a process boundary.
- Keep modules focused; avoid manager/service classes that own unrelated responsibilities.
- Tests may not require a real provider or paid API key by default.

## Pull requests

PR descriptions should contain:

- problem
- design choice
- tests run
- compatibility impact
- security/provenance note when relevant

## Next recommended tasks

Work from `ROADMAP.md` v0.2 in this order:

1. OpenAI Responses protocol domain/events.
2. Responses ingress endpoint with deterministic fixtures.
3. Tool-call normalization.
4. Codex CLI contract fixtures.
5. Capability-aware routing.
