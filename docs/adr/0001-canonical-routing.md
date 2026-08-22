# ADR 0001: Canonical routing boundary

**Status:** Accepted

Public protocol payloads are converted to canonical request and response models before routing. Provider adapters translate only at the upstream boundary. This adds deliberate translation code but prevents routing and resilience policy from depending on any vendor wire format.
