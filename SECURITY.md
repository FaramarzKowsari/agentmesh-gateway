# Security

Report vulnerabilities privately through GitHub security advisories rather than public issues. Do not include live credentials in reports.

Bind to loopback by default. Enable bearer authentication before sharing access, use TLS at a trusted reverse proxy, restrict admin endpoints at the network layer, rotate upstream credentials, and avoid committing `.env`. Gateway authentication is optional for local development and is not a substitute for network isolation. Upstream response bodies and credentials are excluded from normalized client errors.
