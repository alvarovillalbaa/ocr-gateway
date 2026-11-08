"""Tiny independently authored OOXML ZIP/XML inputs, never product encoders.

All content is synthetic. Fixtures contain no macros, images, real workbooks,
network fetches or document uploads. Limits also cover deliberately bad inputs.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import warnings
from xml.sax.saxutils import escape, quoteattr
import zipfile


MAX_FIXTURE_ENTRIES = 64
MAX_FIXTURE_EXPANDED_BYTES = 512 * 1024
MAX_FIXTURE_ZIP_BYTES = 128 * 1024
C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XDR = "http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing"
MIMES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def archive(entries):
    rows = list(entries.items()) if isinstance(entries, dict) else list(entries)
    rows = [(name, value.encode("utf-8") if isinstance(value, str) else value) for name, value in rows]
    assert len(rows) <= MAX_FIXTURE_ENTRIES
    assert sum(len(value) for _, value in rows) <= MAX_FIXTURE_EXPANDED_BYTES
    target = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as package:
            for name, value in rows:
                info = zipfile.ZipInfo(name, (2026, 11, 8, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                package.writestr(info, value)
    result = target.getvalue()
    assert len(result) <= MAX_FIXTURE_ZIP_BYTES
    return result


def relationships(rows):
    return '<Relationships xmlns="' + REL + '">' + "".join(
        '<Relationship Id=' + quoteattr(identity) + ' Type=' + quoteattr(R + "/" + kind)
        + ' Target=' + quoteattr(target) + (' TargetMode="External"' if external else '') + '/>'
        for identity, kind, target, external in rows) + '</Relationships>'


def points(rows):
    return "".join('<c:pt idx=' + quoteattr(str(index)) + '>'
                   + ('<c:v>' + escape(value) + '</c:v>' if value is not None else '') + '</c:pt>'
                   for index, value in rows)


def cache(kind, rows, *, count=None, formula="Sheet1!$A$1:$A$3", format_code=None):
    rows = list(rows)
    count = max((index for index, _ in rows), default=-1) + 1 if count is None else count
    numeric = kind.startswith("num")
    content = ('<c:formatCode>' + escape(format_code) + '</c:formatCode>' if format_code is not None else '')
    content += '<c:ptCount val=' + quoteattr(str(count)) + '/>' + points(rows)
    if kind.endswith("Ref"):
        child = "numCache" if numeric else "strCache"
        return '<c:' + kind + '><c:f>' + escape(formula) + '</c:f><c:' + child + '>' + content + '</c:' + child + '></c:' + kind + '>'
    return '<c:' + kind + '>' + content + '</c:' + kind + '>'


def series(*, index="0", order="0", name="North 🧭", categories=None, values=None,
           x_values=None, y_values=None, bubble_sizes=None):
    if values is None and x_values is None:
        values = cache("numRef", [(2, "-2.50E+1"), (0, "1.25"), (1, "0")], count=3, format_code="0.00")
    if categories is None and x_values is None:
        categories = cache("strRef", [(2, "三"), (0, "Alpha 🚀"), (1, "")], count=3)
    result = '<c:ser><c:idx val=' + quoteattr(index) + '/><c:order val=' + quoteattr(order) + '/>'
    result += '<c:tx><c:v>' + escape(name) + '</c:v></c:tx>'
    for tag, content in (("cat", categories), ("val", values), ("xVal", x_values), ("yVal", y_values), ("bubbleSize", bubble_sizes)):
        if content is not None:
            result += '<c:' + tag + '>' + content + '</c:' + tag + '>'
    return result + '</c:ser>'


def chart(*, kind="barChart", title="Revenue 🚀", series_xml=None, groups=None, external=False):
    groups = [(kind, [series() if series_xml is None else series_xml])] if groups is None else groups
    plot = ''.join('<c:' + family + '>' + ''.join(rows) + '</c:' + family + '>' for family, rows in groups)
    return ('<c:chartSpace xmlns:c="' + C + '" xmlns:a="' + A + '" xmlns:r="' + R + '">'
            '<c:chart><c:title><c:tx><c:rich><a:p><a:r><a:t>' + escape(title)
            + '</a:t></a:r></a:p></c:rich></c:tx></c:title><c:plotArea>' + plot
            + '</c:plotArea></c:chart>' + ('<c:externalData r:id="workbook"/>' if external else '') + '</c:chartSpace>')


def docx_entries(charts=None, *, chart_links=None, trailing="After the chart"):
    charts = [chart()] if charts is None else list(charts)
    links = [(f"chart-{i}", "chart", f"charts/chart{i}.xml", False) for i in range(1, len(charts) + 1)] if chart_links is None else chart_links
    references = ''.join('<w:p><w:r><w:drawing><a:graphic><a:graphicData uri="' + C + '"><c:chart r:id='
                         + quoteattr(row[0]) + '/></a:graphicData></a:graphic></w:drawing></w:r></w:p>' for row in links)
    entries = {
        "word/document.xml": '<w:document xmlns:w="' + W + '" xmlns:a="' + A + '" xmlns:c="' + C + '" xmlns:r="' + R
        + '"><w:body><w:p><w:r><w:t>Before 🧭</w:t></w:r></w:p>' + references
        + '<w:p><w:r><w:t>' + escape(trailing) + '</w:t></w:r></w:p></w:body></w:document>',
        "word/_rels/document.xml.rels": relationships(links),
    }
    entries.update({f"word/charts/chart{i}.xml": value for i, value in enumerate(charts, 1)})
    return entries


def pptx_entries():
    entries = {
        "ppt/presentation.xml": '<p:presentation xmlns:p="' + P + '" xmlns:r="' + R
        + '"><p:sldIdLst><p:sldId id="900" r:id="first"/><p:sldId id="200" r:id="second"/></p:sldIdLst></p:presentation>',
        "ppt/_rels/presentation.xml.rels": relationships([
            ("second", "slide", "slides/slide2.xml", False), ("first", "slide", "slides/slide9.xml", False)]),
    }
    for number, title, kind in ((2, "Second slide", "pieChart"), (9, "First slide 🚀", "lineChart")):
        entries[f"ppt/slides/slide{number}.xml"] = ('<p:sld xmlns:p="' + P + '" xmlns:a="' + A + '" xmlns:c="' + C
            + '" xmlns:r="' + R + '"><p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>' + title
            + '</a:t></a:r></a:p></p:txBody></p:sp><p:graphicFrame><a:graphic><a:graphicData uri="' + C
            + '"><c:chart r:id="the-chart"/></a:graphicData></a:graphic></p:graphicFrame></p:spTree></p:cSld></p:sld>')
        entries[f"ppt/slides/_rels/slide{number}.xml.rels"] = relationships([("the-chart", "chart", f"../charts/chart{number}.xml", False)])
        entries[f"ppt/charts/chart{number}.xml"] = chart(kind=kind, title=title)
    return entries


def xlsx_entries():
    entries = {
        "xl/workbook.xml": '<workbook xmlns="' + S + '" xmlns:r="' + R + '"><sheets><sheet name="First 🧭" sheetId="9" r:id="first"/>'
        '<sheet name="Second" sheetId="2" r:id="second"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": relationships([
            ("second", "worksheet", "worksheets/sheet2.xml", False), ("first", "worksheet", "worksheets/sheet9.xml", False)]),
    }
    for sheet, drawings in ((2, [2]), (9, [9, 3])):
        entries[f"xl/worksheets/sheet{sheet}.xml"] = '<worksheet xmlns="' + S + '" xmlns:r="' + R + '"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Sheet '
        entries[f"xl/worksheets/sheet{sheet}.xml"] += str(sheet) + '</t></is></c></row></sheetData>' + ''.join('<drawing r:id="draw-' + str(drawing) + '"/>' for drawing in drawings) + '</worksheet>'
        entries[f"xl/worksheets/_rels/sheet{sheet}.xml.rels"] = relationships([
            (f"draw-{drawing}", "drawing", f"../drawings/drawing{drawing}.xml", False) for drawing in reversed(drawings)])
        for drawing in drawings:
            entries[f"xl/drawings/drawing{drawing}.xml"] = '<xdr:wsDr xmlns:xdr="' + XDR + '" xmlns:a="' + A + '" xmlns:c="' + C + '" xmlns:r="' + R
            entries[f"xl/drawings/drawing{drawing}.xml"] += '"><xdr:twoCellAnchor><xdr:graphicFrame><a:graphic><a:graphicData uri="' + C + '"><c:chart r:id="chart"/>'
            entries[f"xl/drawings/drawing{drawing}.xml"] += '</a:graphicData></a:graphic></xdr:graphicFrame></xdr:twoCellAnchor></xdr:wsDr>'
            entries[f"xl/drawings/_rels/drawing{drawing}.xml.rels"] = relationships([("chart", "chart", f"../charts/chart{drawing}.xml", False)])
            entries[f"xl/charts/chart{drawing}.xml"] = chart(title=f"Drawing {drawing}")
    return entries


def named_fixture(name):
    if name == "docx":
        return "docx", archive(docx_entries())
    if name == "pptx":
        return "pptx", archive(pptx_entries())
    if name == "xlsx":
        return "xlsx", archive(xlsx_entries())
    if name == "missing-cache":
        uncached = '<c:numRef><c:f>DO_NOT_RESOLVE!$A$1</c:f></c:numRef>'
        return "docx", archive(docx_entries([chart(series_xml=series(values=uncached))]))
    if name == "dtd":
        return "docx", archive(docx_entries(['<!DOCTYPE chart [<!ENTITY leak "blocked">]>' + chart()]))
    raise ValueError("Unknown authored fixture")


def document(name):
    extension, data = named_fixture(name)
    return {"name": "authored-native-chart." + extension, "mimeType": MIMES[extension],
            "dataBase64": base64.b64encode(data).decode("ascii")}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Supply one authored fixture name")
    print(json.dumps(document(sys.argv[1]), ensure_ascii=False, allow_nan=False))
