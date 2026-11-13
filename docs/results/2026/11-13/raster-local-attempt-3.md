# Raster OCR attempt 3: fixture writer refused

The [actual job](https://github.com/alvarovillalbaa/ocr-gateway/actions/runs/43410273690/job/131834642691)
failed before recognition. R01–R04 are **UNRUN**; no OCR quality or case pass is
carried. Source `3eaf9945c474aff9b76ad65a16da26c57d597394`, tree
`67c3f00e5ed3e3b1c3a51225af791f8edfb6a00e`, 105 files /4,883,378 bytes.
Activation `24e97691869119d28f246d1f66e612d38ad90c2e`, tree
`532e8ccad8f0a290350400cb90af066a28fffd44`; only the temporary workflow was added.

The explicit private libgif supplement resolved the loader failure. Actual
ldd retained 57 resolved-library identities and private Tesseract/Leptonica/GIF
bindings; Tesseract reported5.3.4 and Leptonica1.82.0. Signed libgif7
5.2.2-1ubuntu1.2 archive:35,608 bytes, SHA-256
`8137945ac9167f26d0264f403ffb48a45974f096e8acab5479e33fdba6c28a36`.
This SHA was observed from authenticated indexes, not predeclared in runtime-v2.

All21 commands have actual exits and42 complete original streams independently
decoded and size/hash checked. The first20 exited0. The fixture writer exited1
with `io.UnsupportedOperation: read`: Pillow's multi-frame TIFF appender read
the exclusive write-only handle. The PNG had already been written:13,842 bytes,
SHA-256 `132e6f7eaf68486dc82df512cadf7fb94247a99121531562dae391b0c368653e`.
The TIFF remained zero bytes. No fixture admission, recognition freeze, parser
call or model recognition occurred. All observer errors are null.

Three complete105-file source guards matched. All21 direct leaders were reaped
and their groups absent; attributed descendants were empty. The owned root was
removed/read back absent after a2,066-leaf vector (365,317,589 regular-file bytes;
six additional symlink entries), SHA-256
`1b39a84a6f9f4f4e4a54c4e704c46ed28149ee2cc34de5f389040b685be7864c`.
This is scoped process/cleanup evidence, not a trace of every transient child.

The unchanged [original JSON](raster-local-attempt-3.json) is445,325 bytes,
SHA-256 `2fc8f90b47f407dab9b95360b7cbde58037d7fca2655577fb6da2c9ec1abce72`.
The [original ZIP](raster-local-attempt-3.zip), artifact14028619497, is144,474 bytes,
SHA-256 `89bfb28852a59f7a2b4b1face698aaa9f82564a87e5e238769fb366a4d8fe73b`.
Its single member is exactly that JSON. The native engine's recognition diagnostics
are not retained by the product; no recognition occurred in this invocation.

Workflow417152311 was disabled/read back `disabled_manually`. The exact
QA3 ref was verified at activation24e97691, deleted and read back empty. The
connected fetch tool does not support workflow-registration reads; the existing
GitHub CLI supplied that retirement readback. Both earlier failures remain intact.

The concrete next repair changes only the TIFF handle from `xb` to `x+b`.
Rendering, corpus, protocol, font, models, package versions and consumer assertions
stay unchanged; require the already rendered PNG's exact hash and all six observed
native package identities. No outcome or model pass is carried.
