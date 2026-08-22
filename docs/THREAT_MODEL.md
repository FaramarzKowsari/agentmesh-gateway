# Threat Model

## Protected assets

- provider API keys and OAuth tokens
- gateway bearer token
- user prompts, source code, tool arguments, and model output
- provider routing and usage metadata

## Trust boundaries

1. client -> AgentMesh ingress
2. AgentMesh -> upstream provider
3. local configuration -> runtime process
4. future dashboard/control plane -> gateway runtime

## Primary threats

### Secret leakage
Provider credentials must be read from environment variables and must never appear in model responses or structured error bodies.

### Untrusted upstream errors
Provider response bodies can contain user-controlled or vendor-controlled text. The gateway currently returns normalized status messages instead of arbitrary upstream bodies.

### Unauthorized gateway use
Deployments exposed beyond localhost should set `AGENTMESH_GATEWAY_TOKEN` and terminate TLS at a trusted reverse proxy until native TLS is introduced.

### SSRF through provider configuration
Provider base URLs are administrator configuration, not per-request input. Future remote control-plane APIs must validate and authorize provider URL changes.

### Cost amplification
Fallback can consume quota from multiple providers. `max_attempts` caps a single request's upstream attempts. Future versions should add per-request budget limits.

### Supply-chain risk
CI uses pinned major GitHub Action versions and Dependabot. A future release milestone requires SBOM generation and signed provenance attestations.
