# Native chart packet 1 — build prerequisite refused

8 November 2026. [Run 42464680803](https://github.com/alvarovillalbaa/ocr-gateway/actions/runs/42464680803),
job `128681334027`, failed at checked source
`8d85a93bd93387774a1f9654caac873b33b458a7`, workflow
`efc9517b4ac1bf6600b04fea73aa0c8c8bfb2941`. Controller elapsed: 3.54 seconds.

The finite error is **`preinstalled_setuptools_77_required`**. Actual tool
originals report Node 22.23.4, npm 10.9.9, Python 3.12.3, setuptools 68.1.2,
wheel 0.42.0 and pip 24.0. The first control deliberately required compatible
preinstalled tooling. Version 68.1.2 cannot satisfy the package's corrected
setuptools 77 minimum for its existing SPDX license expression.

All three version-observation commands exited zero with complete original
streams. No npm install, lock/schema generation, TypeScript compile, wheel
build/install, application import, parser execution, test, CLI parse or package
consumer ran. All **45 cases and runtime acceptance remain unrun**. This is
a runner prerequisite failure, with no observed parser or fixture defect.

The full source guard binds 58 files and 435,440 bytes. The owned source export
was prepared; maximum sampled scratch was 583,495 bytes and RSS 58,953,728 bytes.
Cleanup verified removal of 141 entries, no remaining owned process, absent
root and no listening ports. No local environment or upstream provider was used.

The workflow was disabled and QA1 retired at
`712d2c319c7c69f4fc5917524b3d848cda6f0cdc`. The changed second control may
install one exact hash-pinned compatible setuptools wheel inside an owned CI
build environment. It must rerun all actual build/package/45-case/CLI/consumer
work afresh. It changes no application/parser/test behavior or runtime
dependencies. Preserve this failure and the scoped cleanup result unchanged.

| Immutable original | Bytes | SHA-256 |
| --- | ---: | --- |
| [Receipt](native-ooxml-charts-attempt-1.json) | 21,309 | `c1ba8a8fc0a0e4ba94729cc4df905b44f1591127bd0ff6bfbd46c69f7375c8d4` |
| [Full job log](native-ooxml-charts-attempt-1.log) | 38,713 | `dfd21a63a70a2edc2e5f3ef0e335c494b8b588ac8af4804417f73203ba3c906b` |

The receipt is the exact result-line JSON plus newline. The
[approved contract](../../../proposals/native-ooxml-chart-checks.md) separates
prerequisites, source, runtime, package and distribution evidence.
