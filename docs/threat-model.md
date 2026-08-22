# Threat model

## Assets and trust boundaries

Assets are upstream credentials, gateway bearer tokens, prompts, responses, and availability. Untrusted clients cross the HTTP ingress boundary; upstream services cross an outbound boundary; configuration and operators are trusted. Provider output remains untrusted data.

## Principal threats and controls

- Unauthorized use: optional constant-value bearer comparison and recommended network isolation/TLS.
- Credential disclosure: secret types, ignored environment files, sanitized errors, and no request logging.
- Upstream abuse or outage: explicit timeouts, bounded retries, fallback, and circuit breaking.
- Resource exhaustion: request validation and bounded attempts; deployment-level body/concurrency limits remain necessary.
- Malicious model content: output is returned as data; consumers must escape it for their context.
- Admin disclosure: admin endpoints expose metadata, never credentials; operators should additionally restrict them by network policy.

## Non-goals in v0.1

The gateway does not provide tenant isolation, quotas, content moderation, a secrets manager, TLS termination, or distributed circuit state.
