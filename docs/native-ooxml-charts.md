# Native Office chart caches

The 0.2.0 source adds standard-library extraction of referenced native chart
caches in DOCX, PPTX and XLSX, addressing the [owning brief](https://app.notion.com/p/3fda1ee8bd06802ebaa0dac708eddb90)'s
local parsing, charts, citations and chunks. The returned brief was read in full;
its unverified connector snapshot is 19 October 2026, 16:57:46 UTC, last edit
16:57:00 UTC. Whole-project and provider-accuracy acceptance remain separate.

## Inputs and source data

Follow only referenced chart parts: DOCX main-body content including nested
and table nodes; PPTX slides in presentation manifest order; XLSX workbook-order
sheets through their drawing relationships. Ignore unreferenced chart parts.
Headers/footers, slide notes/masters, rendering, SmartArt/diagrams and raster
chart interpretation remain outside these host readers.

Read DrawingML titles, series and cached category/value/XY/bubble channels
across supported 2D/3D area, bar, line, pie, of-pie, doughnut, scatter, bubble,
radar, stock and surface groups and combinations. Preserve supplied series
indices/order, sparse point indices, multilevel categories, format codes,
source formulas and lexical values. Do not fill holes, invent labels, evaluate
formulas, resolve workbooks or infer trends. Cached error/non-numeric strings
remain source strings. Cache freshness is unverified.

Each chart is a `kind: chart`, `inferred: false` block with source-backed text
and version-one metadata. No confidence, geometry or DOCX/XLSX page is invented.
PPTX citations retain the actual slide number. The normalizer supplies
document-global UTF-16 block/citation offsets and embedding-ready chunks.
Quotes anchor extracted cache text; they do not certify freshness or rendering.

## Metadata

`source` is `ooxml-chart-cache`; `schemaVersion` is 1. `status` is `complete`,
`partial` or `unavailable`, describing supported cache extraction. Fields include
`documentPart`, `relationshipSourcePart`, `sourcePart`, `relationshipId`,
`title`, `titleData`, `chartTypes`, `series`, `externalData`,
`workbookResolved: false`, `cacheFreshness: unverified`,
`visualInterpretation: false` and finite warning codes.

Series retain group/type, supplied index/order and name/category/value/x/y/
bubble channels. Channels retain reference/literal kind, `cachePresent`, source
formula/format code/count, literal text, sparse points and category levels.
Points retain supplied `index`, lexical `value` and optional point format code.
Missing counts remain null; empty caches/values, absent caches and sparse
omissions stay distinct. Block text labels a canonical JSON representation of
the source data.

Missing/unsupported/external targets, absent caches/values and unknown
structures carry explicit status/warnings. Encoded relationship targets are
not guessed or decoded. Ambiguous duplicate relationships/point indices,
unsafe paths, malformed XML, nested scalar markup, DTD/entities and exceeded
budgets fail finitely. No relationship fetches a URL. See the
[primary sources](references/native-ooxml-chart-sources.md).

## Eligibility and limits

`createLocalProvider()` advertises `charts` only for the three OOXML MIME types.
Optional `ProviderAdapter.featureMimeTypes` restricts a declared feature to
MIME patterns; it cannot add undeclared features. Missing entries inherit
`mimeTypes`; empty entries permit no formats. Provider/key/URL/exclusion policy
still applies before routing. Local PDF/image/ODT/text chart requests fail
before Python dispatch. Discovery exposes the optional map through the shared
OpenAPI/TypeScript descriptor.

Existing input, ZIP/XML, text and output budgets remain. Additional per-document
limits: 256 chart references, 1,024 series, 50,000 actual cache point records,
4 MiB cumulative strings, 16 KiB per string, declared counts at most 50,000,
unsigned-32-bit sparse indices, 512 unique referenced XML parts, 32 MiB aggregate
chart/reference XML and 200,000 aggregate XML nodes. No allocation scales with
a sparse index. The [check contract](proposals/native-ooxml-chart-checks.md)
owns actual runtime/distribution evidence. Native cache extraction remains
separate from visual understanding and optional PDF/image dependencies.

The existing `license = "MIT"` package metadata uses an SPDX expression.
[Setuptools documents support from version 77](https://setuptools.pypa.io/en/stable/userguide/license_migration.html),
so 0.2.0 corrects its build minimum from 68 to 77. Python runtime requirements
and optional extraction dependencies are unchanged. CI requires a compatible
preinstalled toolchain and records it rather than installing build tooling.
