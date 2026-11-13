# Installed raster OCR qualification

**R01–R04 passed together** at source
`291edf87fdf847603dd02c5c9b3bef71e798e2fc` in the
[actual public runner job](https://github.com/alvarovillalbaa/ocr-gateway/actions/runs/43411077345/job/131837354089).
This closes the fixed English image/scanned-PDF integration packet. It does
not establish general OCR accuracy, arbitrary-file security or full-product acceptance.

| Case | Actual retained observation |
| --- | --- |
| R01 | Installed Python0.2.0 parsed both TIFF frames through real Tesseract, preserving exact words, order,1200×400 dimensions and page1/2; no invented boxes/confidence |
| R02 | Installed Node0.2.0 SDK parsed the PNG through the local Python engine; exact words, no invented page number, byte-exact original image, two UTF16 block citations and valid chunks |
| R03 | Installed Node file CLI parsed the image-only PDF through raster OCR; exact words, page1,600×200 point dimensions, `tesseract-page-raster` provenance, embedded image and valid citations/chunks |
| R04 | Installed Python CLI actually exited1 for invalid PNG; empty stdout, generic LOCAL_PARSE_ERROR, no authored private marker echo |

The text was exactly `RIVER CARGO\nACCOUNT SEVEN`; TIFF frame2 was
`COPPER WAREHOUSE\nACCOUNT NINE`. Only whitespace-split words were compared.
No corpus/font/model/threshold tuning followed recognition output. The core
[protocol](../../../studies/raster-local-v1.json) SHAec97ea93 and explicit
[runtime supplement](../../../studies/raster-runtime-v2.json) SHAd128d3ee stay
byte-exact. Actual Pillow13.0.0 Aileron Regular48 font bytes SHA
`69853909b940023570964e29cffe30da95aea8de3627736b5cd15ab30143169f` were
recorded before recognition. Full authored PNG/TIFF/PDF/invalid-file originals
are compressed losslessly in the receipt. Actual PDF admission observed no
native text, no fonts and one image. The previously rendered PNG remains byte-exact.

The unchanged public Node/Python0.2.0 release archives were anonymously fetched,
hash checked, installed privately and compared with their archive members on
the runner. Runtime: Node24.21.0/Python3.12.3 x86_64, PyMuPDF1.26.6, Pillow13.0.0,
Tesseract5.3.4/Leptonica1.82.0 and English traineddata4.1.0. Six fixed Ubuntu
archives came from authenticated private APT indexes, with exact prior observed
hashes. No sudo, global package mutation or maintainer script ran. Native
libraries/model, installed payloads and inputs were frozen before first OCR
and matched the final cleanup vector. Native recognition is real model execution;
no hosted provider/model API or paid call was involved.

The [original JSON](raster-local-attempt-4.json) is834,693 bytes, SHA-256
`2bec62a5bd95d1565848c6eb925b1a96e7d7f677fac1bcf851aed114510c4f14`.
The [original ZIP](raster-local-attempt-4.zip), artifact14029218228, is319,006 bytes,
SHA-256 `16cfcb68e76c4b62f6bc473baaff3c786a3c0011b82cde24d8553ff20488b70c`;
its only member equals that JSON. All26 actual command outcomes and52 original
streams are retained, including expected R04 exit1. Five complete108-file source
guards passed. All26 direct leaders were reaped/their groups absent; attributed
descendants were empty. Owned2,079 leaves/368,365,333 regular-file bytes were
removed/read back absent; final vector SHA
`ea36e221c5d04ca2033dff38bf5668c47daf3472720a9baea38888f36718ae9b`.

The [data-only verifier](verify-raster-receipts.py) and its
[audit output](raster-local-audit.json) verify all four original ZIP/raw packets,
their complete Git vectors,154 retained streams/14 source guards, actual case
outputs, exact UTF16 anchors, full authored fixtures, frozen payloads and cleanup
vectors. It does not reexecute any parser, fixture or model. It preserves the
[first observer failure](raster-local-attempt-1.md),
[second missing decoder](raster-local-attempt-2.md) and
[third TIFF handle failure](raster-local-attempt-3.md). No earlier case passed;
all four identities ran fresh in the fourth invocation. First command14's actual
exit/streams remain unknown rather than inferred from empty cleanup files.

All four temporary workflows are disabled and exact SHA-verified QA branches
deleted/read back empty; [retirement receipt](raster-local-retirement.json).
Fourth activation3a01c926 adds only its workflow to prepared source291edf87;
the application source was checked out at291edf87. The controller is archived
for provenance, not reusable against arbitrary current main. No closed PDF,
chart, public-consumer or React case was replayed. Product/version/lock/OpenAPI/
release/tag/archive bytes remain unchanged; only verification sources/docs changed.

The product suppresses native Tesseract recognition stdout/stderr and trims
output-file edges. Originals here mean supervisor streams and returned application
OCR text, not a complete native-engine transcript. Node/Python network tripwires
observed no event; this does not independently confine native networking. Scoped
process snapshots do not attest every transient child or whole-host disposal.
No local heavy execution, browser, account, API key, database, hosted service or
registry publication occurred. Live-provider, broad OCR/platform quality and
full-product acceptance remain open.
