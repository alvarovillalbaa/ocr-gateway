# React client replacement

29 October 2026. Started from clean personal main
`117d8694b23922061a79b987af390b8f1f36cd07`; the remote head matched.

Replacing a client during parsing aborted and fenced its old request without
clearing `loading`. The fenced `finally` could no longer restore idle state,
leaving the documented upload input disabled. Old passive cleanup could also
abort a replacement's request started earlier in a child layout effect.

Each client now gets a separate request/state lease. Snapshot identity prevents
prior data/error/busy state from appearing for its replacement. Cleanup touches
only its captured lease, and setup publishes any new-client work already
started. Generation/controller ownership changes before abort to preserve newer
requests from synchronous abort listeners. Same-client data retention and
caller-owned promises remain. Explicit callbacks retained for an old client
can still call it, but cannot publish into or cancel the current view. Public
return fields, wire/Python contracts, providers, Auth and dependencies are
unchanged.

The [machine report](react-client-ownership-checks.json) retains an exact-source
baseline reproduction: the client-swap case failed with `ERR_ASSERTION`, actual
loading `true`, expected `false`. Ten focused cases then passed against the
actual repaired TypeScript hook, with zero failures, cancellations, skips or
TODOs. They cover swap/reset, late success/failure/cancel, layout requests,
StrictMode/unmount, overlap, cancellation/retry, synchronous abort reentry and
returning to an earlier client with obsolete callbacks.

These are real ReactDOM/jsdom fixtures with controlled clients. OCR has no
installed React testing environment or corresponding dev dependencies. The
existing Search Gateway fixture was reused read-only: Node 26.8.2,
React/ReactDOM 19.3.1 and jsdom 30.1.3. Its package/lock identities are recorded.
The optional `OCR_GATEWAY_REACT_FIXTURE_ROOT` selects such a fixture project.
Only the hook's bare `react` import resolves to that peer; all other module
resolution delegates normally, and registration is removed after import using
the documented [Node module-hook API](https://nodejs.org/api/module.html#moduleregisterhooksoptions).
No hook or React behavior was mocked or substituted. Native TypeScript
loading imports actual source, not existing `dist` output.

The focused command used that explicit fixture root and a 15-second per-test bound;
individual cases also have three-second bounds:

```sh
OCR_GATEWAY_REACT_FIXTURE_ROOT="$REACT_FIXTURE_ROOT" \
  node --test --test-timeout=15000 --test-concurrency=1 --test-reporter=tap \
  tests/unit/react-ownership.test.mjs
```

A targeted no-emit TypeScript 7.0.2 check of the hook and type imports passed
with the project's explicit strict options. Its first invocation stopped with
TS5112 because a root tsconfig exists; adding `--ignoreConfig` while supplying
those options enabled the intended single-file check. No product code was
compiled by that initial invocation. Syntax and whitespace checks passed.
Forty other tracked baseline files, including backend/provider/security, wire/
Python contracts, package manifest and lock, remain byte-identical. Independent
review found no further concrete lifecycle defect.

Storage Guard returned 29.4 GiB free versus 34.0 GiB required. No install,
emitted package/app build, backend/provider suite, browser, HTTP server, model
or paid call ran. The shared-peer fixture is focused frontend evidence;
React 18, other runtimes, fresh OCR dependency installation, packaged artifacts,
real browser/device behavior and live-provider acceptance remain unverified.
Existing v0.1.0 artifacts were not rebuilt or published; README states the
source-only repair boundary. No CI, provider, Auth or production setting changed.

The report retains exact source/output hashes, every case name and normalized
TAP with the private workspace root removed. The initial extraction wrapper's
escaped-regex error produced no report and was corrected without rerunning
tests. Source publication remains separate from a new distributable release.
