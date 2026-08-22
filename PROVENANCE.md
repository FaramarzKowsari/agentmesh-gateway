# Provenance and Independence Statement

AgentMesh Gateway is an original implementation created for the general problem of connecting AI coding clients to multiple model providers through a stable local or hosted gateway.

## Independence rules

The project follows these rules:

1. Do not copy source code, tests, documentation prose, assets, UI layouts, internal identifiers, or file organization from `free-claude-code` or another gateway implementation.
2. Publicly observable product capabilities may be used as requirements, but implementation choices must be independently designed and documented here.
3. Third-party libraries are used only under their own licenses and are declared in `pyproject.toml` or future package manifests.
4. Every substantial architectural change should receive an ADR in `docs/adr/`.
5. Git history should preserve incremental development rather than importing a rewritten snapshot from another project.
6. Contributors must not submit code copied from incompatible or unattributed sources.

## Initial design basis

The initial feature requirements are generic gateway requirements: protocol ingress, provider abstraction, failover, health tracking, policy routing, authentication, observability, local-model support, and agent integration. The package structure, data model, routing algorithm, configuration model, API composition, tests, documentation, and naming in this repository were designed specifically for AgentMesh.

This file is a technical provenance record, not a legal opinion.
