# Working in OCR Gateway

Read README.md and docs/architecture.md before changing behavior. The TypeScript contract in src/types.ts owns the wire shape; keep the Python TypedDicts and OpenAPI aligned.

- Keep provider keys in trusted processes. Browser imports use the HTTP client and optional React hook only.
- Follow the official sources in PROVIDERS.md. Do not invent page numbers, bounding boxes, confidence, or verified citations.
- Enabled providers and gateway-key scopes constrain every routing path, including custom and model decisions.
- Use apply_patch for manual edits. Preserve unrelated work. Never commit keys, document uploads, or local stores.
- Respect the user's verification limits: do not run backend test suites without an explicit request. Compile/package checks and documented example execution are available; test fixtures use synthetic data only.
- No live paid-provider calls, hosted provisioning, or registry publication without authorization. GitHub publication is requested.
- Run git diff --check before publication. Verify distributable npm and Python package contents.
