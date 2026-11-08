# Native OOXML chart extraction: primary sources and boundaries

Read on 8 November 2026. This is a source contract and research record, not a
runtime result. The selected slice reads chart XML already inside DOCX, PPTX and
XLSX packages. It extracts stored chart facts; it does not render charts, inspect
chart images, recalculate a workbook, call a model or fetch a linked resource.

## Standard and schema sources

[ECMA-376](https://dev.ecma-international.org/publications-and-standards/standards/ecma-376/)
separates the markup reference in Part 1 from Open Packaging Conventions in
Part 2. Microsoft Learn's Open XML SDK pages reproduce relevant ISO/IEC 29500
element descriptions. They are used below alongside Microsoft's actual schema
declarations, rather than treating a third-party example as a format contract.

The inspected Microsoft
[Open-XML-SDK v3.0.1 chart schema](https://github.com/dotnet/Open-XML-SDK/blob/v3.0.1/data/schemas/schemas_openxmlformats_org_drawingml_2006_chart.json)
has Git blob `00a3213b8cc8dea689880db910be0dc45c75ea02`. It was read as text
only. No SDK or schema dependency is installed or included in the parser.
This versioned schema resolves child choices and optionality where the prose
remarks and generated API property lists differ.

## Find the chart through its host relationship

[ChartReference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.chartreference?view=openxml-3.0.1)
defines `c:chart` and its relationship-namespace `r:id`. That value identifies a
relationship local to the hosting part. Microsoft’s
[OPC parts overview](https://learn.microsoft.com/en-us/previous-versions/windows/desktop/opc/parts-overview)
explains why part names cannot be predicted and why a consumer first identifies
the relationship and resolves its target. `TargetMode` defaults to Internal;
relationship Type and target content type carry format meaning.

Consequences for this parser:

- DOCX: visit chart references in the main document's supported content and
  resolve each against that host part's relationships.
- PPTX: resolve references in each actual slide part, using that slide's own
  relationships. Do not use the presentation relationships for slide charts.
- XLSX: resolve the sheet's drawing relationship, then each chart reference
  against the drawing part's relationships. A chart's reference is not a direct
  relationship from the worksheet unless the source explicitly defines it so.
- Do not enumerate `chart1.xml`, `chart2.xml`, or every ZIP member under a
  `charts/` directory and treat those names as visible document order. Orphan
  parts must not become extracted chart occurrences.
- Distinguish an external target, a missing relationship, a dangling target,
  a wrong relationship Type and an ambiguous duplicate relationship ID. A
  successful parse of another part does not establish that the chart was read.

These are relationship-based extraction rules. They are not permission to fetch
an external target or embedded workbook.

## URI targets and the deliberately bounded path profile

Microsoft’s
[ResolvePartUri documentation](https://learn.microsoft.com/en-us/dotnet/api/system.io.packaging.packurihelper.resolveparturi?view=windowsdesktop-9.0)
resolves a target relative to its **source part URI**, with `/` representing
the package root. The `.rels` filename is not the target's base URI.

The official implementation also matters when deciding what *not* to infer:
[PackUriHelper](https://source.dot.net/System.IO.Packaging/System/IO/Packaging/PackUriHelper.cs.html)
produces a canonical escaped part-name string; its validation distinguishes a
part URI from an arbitrary URI. Microsoft’s
[ZipPackage implementation](https://source.dot.net/System.IO.Packaging/System/IO/Packaging/ZipPackage.cs.html)
uses that part string without its leading slash when creating a ZIP item.
Blindly decoding a target and trying both decoded/escaped names is therefore
not a justified general OPC resolution rule.

This release chooses a narrower explicit profile: chart/drawing targets with
percent escapes are unavailable with `encoded_chart_target_unsupported`.
There is no unquote or alternate-name fallback. Reject schemes, authorities,
query strings, fragments, backslashes, control characters and traversal outside
the package. Resolve supported plain internal targets within the existing
bounded ZIP member map. These are local admission choices, not a claim that
all percent-encoded OOXML part names are invalid under the standard.

## Preserve host order and distinguish pages from containers

Microsoft’s
[move-slide example](https://learn.microsoft.com/en-us/office/open-xml/presentation/how-to-move-a-slide-to-a-new-position-in-a-presentation)
moves a slide by changing its position in `SlideIdList`. Its child order and
resolved `r:id` values establish presentation order; numeric slide filenames
do not. The existing parser already follows this list and must retain that
behavior. A slide ordinal is a source location, not an inferred printed page.

[Sheets](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.sheets?view=openxml-2.20.0)
contains the workbook's sheet collection, names and relationship references;
sheets can have different kinds. Preserve that collection's order when adding
chart extraction, including sheets with no chart. Retain the actual sheet name
and source part. Do not turn a worksheet into a fabricated rendered page number.
Microsoft’s [sheet overview](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-sheets)
also distinguishes worksheet data from its optional supporting structures.

Within supported source parts, retain chart occurrence and drawing order.
This does not claim geometric reading order, Office rendering, layout reflow,
header/footer expansion or slide-master/notes inheritance.

## Cached data, literal data and formulas

[NumberingCache](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.numberingcache?view=openxml-3.0.1)
defines `c:numCache` as previously displayed series data. It contains an optional
format code, point count and indexed numeric points.
[StringReference](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.stringreference?view=openxml-3.0.1)
uses `c:f` plus an optional `c:strCache` for stored reference values.
The [numeric literal type](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.numberliteral?view=openxml-3.0.1)
stores literal numeric chart data rather than a reference requiring calculation.

Keep reference formulas as source strings. Stored caches can be stale or absent
even in valid OOXML. Do not claim cached numbers are current spreadsheet values,
evaluate formulas, follow external workbooks, infer dates/currencies from format
codes, or replace errors and missing values with zero. Preserve lexical values,
including trailing zeros, exponent spelling and stored error/non-numeric text;
their presence does not establish a finite measured quantity.

The schema's channel choices are:

| Channel | Supported stored-data alternatives |
| --- | --- |
| Category `c:cat` and X `c:xVal` | `multiLvlStrRef`, `numRef`, `numLit`, `strRef`, `strLit` |
| Value `c:val`, Y `c:yVal`, size `c:bubbleSize` | `numRef`, `numLit` |

The official
[CategoryAxisData class](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.categoryaxisdata?view=openxml-3.0.1)
and versioned schema identify these alternatives. Reference branches carry
their formula/cache provenance; literal branches remain distinguishable.

## Point indices, counts and multilevel labels

[NumericPoint](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.numericpoint?view=openxml-3.0.1)
defines `c:pt/@idx`, optional point-specific formatting and a value child.
The versioned schema requires `idx` on numeric and string points, and their
value child; it makes `ptCount` optional in numeric/string cache/literal data
and multilevel caches. Preserve an absent count as absent. A smaller number of
stored points than a declared count does not by itself establish corruption.

Use explicit point indices as identity. Sparse or out-of-order point storage
must not shift categories onto different values. Do not allocate a dense array
from a potentially huge `idx`/`ptCount`, interpolate gaps, deduplicate unequal
points silently, or claim a missing index is a measured zero. Missing required
identity/value data must remain visibly incomplete rather than acquire invented
indices or values.

[MultiLevelStringCache](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.multilevelstringcache?view=openxml-2.20.0)
contains `lvl` collections and a point count. Preserve level order and each
level's indexed points independently. Do not silently fill sparse parent labels
or collapse levels into an invented single flat category.

## Titles, series identity and chart groups

[ChartText](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.charttext?view=openxml-3.0.1)
describes chart/title text with a rich-text or string-reference choice. The
inspected v3.0.1 schema additionally admits `strLit` in that choice. Read rich
DrawingML text within the title's own scope, respecting paragraphs, rather than
joining every text node in the whole chart as its title.
[SeriesText](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.seriestext?view=openxml-3.0.1)
is a different `c:tx`: its alternatives are a string reference or a direct
`c:v` text value, without rich formatting. A missing title/name stays missing;
an invented “Series 1” must not become an extracted fact.

[Order](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.order?view=openxml-3.0.1)
is zero-based series order in a collection. Preserve it separately from series
identity `c:idx`. The inspected bar/line/pie series schema requires both;
missing source values cannot be replaced by array positions and claimed native.

[PlotArea](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.drawing.charts.plotarea?view=openxml-3.0.1)
and the versioned schema allow repeated chart-group choices, enabling combined
charts. Preserve groups, their chart-type element names and all supported
series. A first-group/first-series extraction loses native data. Keep group
document position, declared series order and source index as separate provenance;
do not reinterpret these as a new chart layout or derived trend.

## OCR Gateway capability and proof boundary

The trusted adapter's `features` remains the upper bound. Optional
`featureMimeTypes` narrows individual features with the same MIME pattern
semantics as `mimeTypes`: exact, `type/*`, or `*/*`. An absent entry inherits
the ordinary format list; an empty list denies that feature for every format.
An entry cannot add a globally undeclared feature. Legacy custom providers
without the map retain their existing eligibility behavior.

Local charts are declared only for the DOCX, PPTX and XLSX MIME types. Central
eligibility applies before every execution/routing path and before Python
startup. Direct local-adapter chart calls also refuse other MIME types before
spawn. Provider discovery exposes the optional map so a client need not infer
that local PDF/image extraction understands charts. No existing hosted provider
endpoint, credential or capability declaration is broadened by this map.

Native chart blocks cite stored extracted text and source-part provenance.
No bounding box, confidence, physical DOCX/XLSX page, external workbook value,
visual interpretation, semantic verification or model-generated description is
invented. Unsupported chart schemas, unavailable references and incomplete
caches need explicit bounded warnings. Synthetic DOCX/PPTX/XLSX acceptance,
real Node-to-Python dispatch and serialized citation checks require their own
recorded remote execution; this reference establishes none of those outcomes.
