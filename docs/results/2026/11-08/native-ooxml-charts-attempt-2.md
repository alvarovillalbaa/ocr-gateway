# Native chart candidate — installed checks passed; observer corrected separately

8 November 2026. [Run 42466308247](https://github.com/alvarovillalbaa/ocr-gateway/actions/runs/42466308247),
job `128686532514`, executed source
`18cb187c70a3f3e8ca4c622c8e4a5862484cb74d` under workflow
`489afc03a37f270f079d55d3fa1bb203bc2c2ce4`. Its original overall verdict is
**failed**, error `public_export_origin`. Preserve that verdict and both originals.

## Actual execution

- All **27 Python + 18 Node authored cases passed**, with exact identities and
  zero failure/error/skip/expected-failure/TODO. They used the fresh installed
  wheel/npm packages, actual Python dispatch and an authenticated loopback SDK.
- Installed CLI parsed authored DOCX, PPTX and XLSX. Source titles/order,
  lexical cache provenance, UTF-16 citation/chunk anchors and real PPTX slide
  numbers passed. DOCX/XLSX did not invent pages or geometry.
- Locked installation, strict TypeScript check/build, OpenAPI generation,
  npm packing, wheel build, archive inspection and fresh installations passed.
  The strict public-export consumer compiled successfully. Node resolved all
  five public exports successfully; the subsequent Python observer failed.

All 26 observed commands exited zero and retained 52 complete original streams.
The source vector binds 61 files / 508,375 bytes. Runtime tools were Node
22.23.4, npm 10.9.9 and Python 3.12.3. One exact setuptools 84.2.1 wheel was
hash-verified and installed in the owned build environment; the runtime
environment remained separate. No global tool or runtime dependency changed.

Independent data-only review rehashed all 56 captures (52 streams plus four
retained outputs), exact case identities and all 61 native source blobs/tree.
The CLI originals contain six chart blocks, 19 citations and five chunks;
every UTF-16 slice, supplied order/page, sparse channel and all 36 cached points
matched the authored source expectations. CLI fixture ZIP bytes were not
separately retained; their input hashes remain controller-recorded observations.

## Observer correction

The actual resolution stdout is 667 bytes, SHA-256
`68cf063d9c0f4375b9397369ca1a30c7c8755f1a0eaa16ba7b1e5ad71e336399`.
Every path points to the expected installed `dist/{index,core,local,server,react}.js`.
Python's `Path.as_uri()` spells the namespace `%40alvarovillalbaa`; Node's
`import.meta.resolve()` spells it `@alvarovillalbaa`. The original string equality
therefore rejected equivalent paths after every application check had passed.

The [separate data-only verifier](../../../../tests/scripts/verify-native-chart-export-urls.py)
checks the complete hash-bound original
stdout, exact five keys, strict file-URL syntax and exact decoded installed
paths. Its [observation receipt](native-ooxml-charts-attempt-2-url-observation.json)
is separate from the failed CI original: 4,597 bytes, SHA-256
`3431ae6a8efce63ca60abc84c19ccb300e5f1ff719c3776c1d436bc53891deba`.
Two valid URL spellings and 30 refusal cases passed as pure-data checks. It executes no
application, rebuild, install, test suite or provider call. No later source edit
is relabeled as the CI-tested source, and no single all-green CI run is claimed.

## Packages and cleanup

| Retained archive | Bytes | SHA-256 |
| --- | ---: | --- |
| `alvarovillalbaa-ocr-gateway-0.2.0.tgz` | 83,978 | `4775f9503ac09d94e9c2a39ea9381c162b7f41e527c8516e1e8d381e500890d4` |
| `ocr_gateway_client-0.2.0-py3-none-any.whl` | 26,079 | `f7b32a418cfb3b4a872b25a582fc8941dd070dfe957f2aeb36fb936a0b996ded` |

The [GitHub candidate](https://github.com/alvarovillalbaa/ocr-gateway/releases/tag/v0.2.0-native-charts.1)
uses these unchanged bytes. The 62 npm entries and 12 wheel entries were
inspected; installed payloads matched archive manifests, excluding Python's
rewritten RECORD. Independent review also validated all 12 wheel RECORD rows
and npm-pack's SHA-1/SHA-512/file table. Actual generated lock/OpenAPI bytes were adopted from this
run; only root version metadata and the optional feature/MIME descriptor changed.
Bundled status docs retain their build-time snapshot; current evidence is here.
The original v0.1.0 release stays unchanged.

Controller elapsed: 33.839 seconds. Maximum sampled owned storage: 78,464,176
bytes; aggregate RSS: 217,808,896 bytes; owned process count: four. Cleanup
verified 4,261 removed entries, absent owned root/processes and closed observed
ports 36905/42913. No owned signal was required. The workflow is disabled;
QA2 retired at `89da049ad187a537f38f0e8eff8c8318024cee79`, and the default inert
registration was removed. The first prerequisite failure remains unchanged.

| Immutable original | Bytes | SHA-256 |
| --- | ---: | --- |
| [Receipt](native-ooxml-charts-attempt-2.json) | 1,019,389 | `7fd94704dc30237d17b8492da2300e05f7b6d0cc6131b4493114fa7870aee249` |
| [Full job log](native-ooxml-charts-attempt-2.log) | 1,036,785 | `d70e0288879b6e3bac6a4aeee28e2d5cd3920112b991fba6e4db1e5326bda2cb` |

These authored cache checks do not establish visual interpretation, cache
freshness, optional PDF/image extraction, live OCR/model routing, fresh
anonymous release installation, registry publication or full-product acceptance.
No local heavy execution, new account, paid plan, database or provider call.
