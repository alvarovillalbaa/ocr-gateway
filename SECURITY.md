# Security and operations

Report security issues privately through GitHub's private vulnerability reporting when enabled. Do not attach credentials or customer documents to public issues.

## Deployment

- The built-in HTTP service requires a bearer key on every `/v1/*` route. `/health` is public. Use TLS before exposing it remotely, and limit body size/time/concurrency at your reverse proxy as well as the gateway.
- Keys are generated locally with 256 random bits; the store keeps only hashes, provider scope, revocation and per-minute limits. The store uses exclusive file locking and atomic replacement; permissions are `0600`. Keep it on a private local filesystem. A lock left by a killed process requires operator inspection and removal after confirming no writer is live.
- File-store updates are serialized per host; in-memory rate limits are per process and reset on restart. Shared deployments need shared authentication and distributed limits. Provisioning has no unauthenticated HTTP endpoint.
- Gateway keys grant access to upstream spending. Use provider-specific spending limits. Default concurrency is 8, default body maximum 29 MB, input maximum 20 MiB decoded, overall request deadlines 100–300000 ms. Provider response limits and local parser limits also apply.
- Request BYOK is opt-in. Keys remain subject to deployment enabled-provider policy and gateway-key scope. Do not log bodies/keys or expose secrets through browser bundles. Custom adapters, local Python executables and endpoint environment variables are trusted operator code/configuration.

## Document data

Documents are sent to selected upstream providers. Consult their retention/processing terms. Parallel parsing sends the document to more than one provider. Decision routing uses only document metadata; custom trusted adapters can have their own behavior. Results retain supplied source URLs, including any presigned query string: protect them as document credentials and avoid public logging.

The gateway does not fetch document URLs. It sends HTTPS URLs to selected providers, which implement their own fetch policy. Upstream document URLs should be public or narrowly scoped presigned URLs. The gateway does not guarantee that a provider blocks private-network addresses; restrict URL ingestion in your application when needed.

Built-in local parsing only accepts text/bytes, rejects remote URLs and applies archive/resource limits. Optional third-party parsers are complex native tools: run them in a restricted container/process with OS memory/CPU/network limits for hostile uploads. Application-level bounds are not an operating-system sandbox. Keep optional tools updated.

Extracted Markdown/HTML/images are untrusted. Render text safely, sanitize HTML and protect tool loops against prompt injection. Citations record extraction location, not independent factual verification. Model descriptions can hallucinate. Keep raw responses disabled unless debugging, and apply your own document retention/access policies.

## Limits

No retries are automatically made for billable provider submissions. Async job polling is bounded by the request signal; cancellation may not cancel a job already accepted by a provider. Python async cancellation cannot terminate an already-running worker-thread transport. The gateway does not persist job IDs for resume across restarts.
