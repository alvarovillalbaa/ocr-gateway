# Fresh public OCR Gateway consumers

All eight delivery identities passed together against the unchanged public
`v0.2.0-native-charts.1` archives. [Run 43328902287](https://github.com/alvarovillalbaa/ocr-gateway/actions/runs/43328902287),
job `131568307896`, executed source
`1e2dcea5069dabd974d798b6f82806e7ba87a32c` on Ubuntu 24.04, Node 24.21.0,
npm 11.19.0 and Python 3.12.3. The controller took 7.856 seconds after checkout/
toolchain setup. This is public artifact consumption, not another package build
or repetition of the 45 producer cases, three OOXML CLI cases or ten React cases.

| Identity | Actual result |
| --- | --- |
| F01 | Three credential-free HTTPS GETs returned 200; 83,978-byte npm archive, 26,079-byte wheel and 212-byte checksum manifest matched their published SHA-256 values. |
| F02 | Actual public-URL npm installation into a fresh consumer; all 62 installed package files matched the independently downloaded tarball. Four non-React entries imported; all five public export paths resolved within that installation. The real executable bin link was verified. |
| F03 | Actual public-URL wheel installation into a fresh venv, without index/dependencies/extras/bytecode. Eleven archive payload files, version/import origin and installer direct-URL SHA-256 matched. Installer-generated RECORD was excluded from archive-byte comparison. |
| F04 | Installed CLI created/listed a disposable local-scoped key in a 0600 hashed store and served on owned loopback. Installed Node SDK discovered the configured local provider, parsed authored Unicode HTML into five citations/one chunk, rejected unauthenticated discovery and refused local URL parsing. |
| F05 | Installed sync and async Python SDKs uploaded the authored file to the real CLI gateway/Python parser. Text and Unicode anchors matched; URL-only local parsing was refused. |
| F06 | Installed CLI uploaded the HTML file through its actual HTTP client and received matching normalized citations/chunks. This was not a repeated direct OOXML parse. |
| F07 | Installed stdio MCP initialized, listed the real URL-only tool schema and returned the expected error through its HTTP client for a local URL parse. No synthetic URL-capable provider or positive hosted URL claim. |
| F08 | Installed CLI revoked the key; a fresh installed SDK request returned 401. Installed Node/Python package namespaces and metadata stayed byte-stable after execution. All owned groups, descendants, port and scratch closed. |

The [structured receipt](fresh-public-consumers.json) retains 15 commands,
32 complete capture representations (including two server streams), three source
guards of 75 files, installed payload inventories, actual result observations,
16 allowed runtime-network events and teardown. Independent readback verified
every retained capture's byte count/digest. One key-create stdout is explicitly
redacted; its original byte count/hash is recorded, and the bearer/store is not
retained. No full bearer pattern appeared in decoded retained streams.

Raw receipt: 41,922 bytes, SHA-256
`a3c60d872a8bebf9a776d5d01d31236ff90e79762ca99f7caeff166bde302c8b`.
The repository JSON rendering has SHA-256
`ef715cf59f0170c5dabd97c57d7850bcd2db8a40c3076a63e2af01c05225f555`.

The downloaded npm SHA-256 is
`4775f9503ac09d94e9c2a39ea9381c162b7f41e527c8516e1e8d381e500890d4`;
wheel SHA-256 is
`f7b32a418cfb3b4a872b25a582fc8941dd070dfe957f2aeb36fb936a0b996ded`.
GitHub release `438146413`, its three asset IDs/digests and tag target
`f0ef2b530083e383a895fb787991ea3c8b4323f7` were read back unchanged. The
archives retain their original build-time documentation snapshot; current
qualification belongs to this receipt, separately from
[the original producer result](../11-08/native-ooxml-charts-attempt-2.md).

The [first new invocation](fresh-public-consumers-attempt-1.md) remains failed.
Its SDK exception and buffered receipt are unobserved, and original cleanup is
unverified. The second control uses discovery's actual contract and excludes
pre-existing PID/start identities from task inspection, without changing any
permissions. No pass is carried from the failed first profile. The current run
reaped all 16 direct groups, observed no owned descendants, closed port 38473,
rechecked root identity/nonce and removed only its own scratch.

Workflow `416686067` is disabled and both exact task QA refs are absent. No
workflow was added to main. Local Storage Guard refused 3.7/38 GiB; only local
source/static checks and bounded evidence handling ran. No archive rebuild,
version/dependency/OpenAPI/Auth-policy change, registry upload, provider/model
call, real document, paid service, new account or hosting provisioning occurred.

This one profile does not establish optional PDF/image OCR, other fresh Node/
Python/platform profiles, React/browser behavior, live provider or model quality,
positive URL-provider execution, managed hosting, distributed limits or npm/PyPI
availability. Local parsing deliberately accepts bytes/text and never fetches
URLs. The self-hosted SDK/server needs no new Vercel or Supabase service.
