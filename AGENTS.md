# Working in OCR Gateway

Read README.md and docs/architecture.md before changing behavior. The TypeScript contract in src/types.ts owns the wire shape; keep the Python TypedDicts and OpenAPI aligned.

- Keep provider keys in trusted processes. Browser imports use the HTTP client and optional React hook only.
- Follow the official sources in PROVIDERS.md. Do not invent page numbers, bounding boxes, confidence, or verified citations.
- Enabled providers and gateway-key scopes constrain every routing path, including custom and model decisions.
- Use apply_patch for manual edits. Preserve unrelated work. Never commit keys, document uploads, or local stores.
- Respect the user's verification limits: do not run backend test suites without an explicit request. Compile/package checks and documented example execution are available; test fixtures use synthetic data only.
- No live paid-provider calls, hosted provisioning, or registry publication without authorization. GitHub publication is requested.
- Run git diff --check before publication. Verify distributable npm and Python package contents.

## Approved native chart candidate — 8 November 2026

Standing owner approval covers the [native contract](docs/native-ooxml-charts.md)
and [focused scope](docs/proposals/native-ooxml-chart-checks.md): three OOXML
hosts, format-specific chart eligibility/discovery, 45 authored Python/Node
cases against fresh installed artifacts, three installed file CLI checks,
a strict public-export consumer, build/package generation and one temporary
free public Ubuntu job capped at 20 minutes per changed candidate. Release
reviewed 0.2.0 archives as a GitHub candidate; registries/live providers remain
separate. No runtime dependency upgrades or Auth changes. The build minimum
is corrected to setuptools 77 for the existing SPDX license string, following
its official packaging contract. Generated lock/OpenAPI changes
come from the owned CI export.

Keep native cached data distinct from visual understanding. Preserve lexical/
sparse values, explicit status, unverified freshness, manifest order and real
UTF-16 anchors. No workbook fetch/formula evaluation, invented page/geometry/
confidence or unreferenced chart scraping. Existing package/XML/output fences
remain; chart budgets apply per document.

Storage Guard failed at 2.2 GiB free/34.0 GiB required. No local app/test/parser,
install/build/environment or browser exception. Source static checks and bounded
evidence handling only. Own/verify runner exports/dependencies/venvs, fixtures,
keys, servers/processes and teardown. Preserve failures and retire temporary CI.
Do not repeat the closed ten-case React packet.

The [first invocation](docs/results/2026/11-08/native-ooxml-charts-attempt-1.md)
refused actual setuptools 68.1.2 before build/tests; owned cleanup passed.
Standing approval covers a changed second control with one exact PyPI
setuptools 84.2.1 wheel, hash-verified and installed only in an owned isolated
CI build environment. Do not install wheel/packaging extras, alter global
tooling or add runtime dependencies. Runtime consumer environment stays
separate. Preserve first originals and run all 45 cases/build/consumers afresh.
