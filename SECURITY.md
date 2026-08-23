# Security Policy

## Reporting

Please use a private GitHub security advisory for exploitable vulnerabilities. Do not open a public issue for leaked credentials or an unpatched vulnerability that could put users at risk.

## Secrets

AgentMesh references provider credentials through environment-variable names. Never commit real API keys, gateway tokens, or `.env` files.

## Network exposure

The default local CLI bind is loopback-only. Docker binds the service to `0.0.0.0:8787`, so publishing that port can expose the gateway beyond the local machine.

If AgentMesh is reachable by another machine, configure a strong `AGENTMESH_GATEWAY_TOKEN` and apply normal host firewall, reverse-proxy, TLS, and network-access controls appropriate to the deployment.

When a gateway token is configured, `/v1/*` and `/admin/providers` require bearer authentication. `/healthz` and `/readyz` remain unauthenticated for health probing and should not contain secrets.

## Supported release

Until 1.0, only the latest tagged minor release receives security fixes.
