"""Tier 2: actual local ZIP/XML parser, independently authored synthetic files.

No provider, network, renderer, formula evaluator or real user file is used.
Budget cases temporarily lower parser limits around small real ZIP/XML inputs.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = Path(os.environ.get("OCR_GATEWAY_PYTHON_PACKAGE_ROOT", str(ROOT / "python"))).resolve()
sys.path.insert(0, str(PACKAGE_ROOT))
sys.path.insert(0, str(ROOT / "tests/helpers"))

import ocr_gateway.local as local
import ocr_gateway.ooxml_charts as charts_module
from ooxml_chart_fixtures import (
    C, MIMES, archive, cache, chart, docx_entries, points,
    pptx_entries, relationships, series, xlsx_entries,
)


class NativeOOXMLChartIntegrationTier2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for module in (local, charts_module):
            actual = Path(module.__file__).resolve()
            if not actual.is_relative_to(PACKAGE_ROOT):
                raise AssertionError("Parser import did not originate in the selected package root")

    def parse(self, entries, extension="docx"):
        return local.parse_local({"name": "authored." + extension, "mimeType": MIMES[extension],
                                  "dataBase64": base64.b64encode(archive(entries)).decode("ascii")})

    def charts(self, output):
        return [block for page in output["pages"] for block in page["blocks"] if block["kind"] == "chart"]

    def one(self, xml=None):
        output = self.parse(docx_entries([chart() if xml is None else xml]))
        blocks = self.charts(output)
        self.assertEqual(len(blocks), 1)
        return output, blocks[0]

    def refused(self, entries):
        with self.assertRaises(local.LocalParseError):
            self.parse(entries)

    def test_docx_chart_is_in_body_order_with_no_invented_page_or_geometry(self):
        output, block = self.one()
        page = output["pages"][0]
        self.assertNotIn("pageNumber", page)
        self.assertEqual([item["kind"] for item in page["blocks"]], ["text", "chart", "text"])
        self.assertEqual(page["blocks"][0]["text"], "Before 🧭")
        self.assertEqual(page["blocks"][-1]["text"], "After the chart")
        self.assertFalse(block["inferred"])
        self.assertNotIn("bbox", block)
        self.assertNotIn("confidence", block)
        metadata = block["metadata"]
        self.assertEqual((metadata["source"], metadata["schemaVersion"], metadata["status"]),
                         ("ooxml-chart-cache", 1, "complete"))
        self.assertEqual((metadata["documentPart"], metadata["sourcePart"], metadata["relationshipId"]),
                         ("word/document.xml", "word/charts/chart1.xml", "chart-1"))
        self.assertEqual(metadata["title"], "Revenue 🚀")
        self.assertFalse(metadata["visualInterpretation"])
        self.assertFalse(metadata["workbookResolved"])
        self.assertEqual(metadata["cacheFreshness"], "unverified")

    def test_sparse_categories_and_numeric_lexemes_preserve_indices_without_padding(self):
        _, block = self.one()
        row = block["metadata"]["series"][0]
        self.assertEqual((row["index"], row["order"], row["chartType"], row["groupIndex"]), (0, 0, "barChart", 0))
        self.assertEqual(row["name"]["literal"], "North 🧭")
        self.assertEqual({point["index"]: point["value"] for point in row["categories"]["points"]},
                         {2: "三", 0: "Alpha 🚀", 1: ""})
        self.assertEqual({point["index"]: point["value"] for point in row["values"]["points"]},
                         {2: "-2.50E+1", 0: "1.25", 1: "0"})
        self.assertEqual(row["values"]["formatCode"], "0.00")
        self.assertEqual(row["values"]["formula"], "Sheet1!$A$1:$A$3")
        self.assertEqual(len(row["values"]["points"]), 3)

    def test_bar_line_pie_groups_retain_their_supplied_series_and_group_order(self):
        xml = chart(groups=[("barChart", [series(index="7", order="2", name="Bars")]),
                            ("lineChart", [series(index="9", order="0", name="Lines")]),
                            ("pieChart", [series(index="4", order="1", name="Pie")])])
        _, block = self.one(xml)
        metadata = block["metadata"]
        self.assertEqual(metadata["chartTypes"], ["barChart", "lineChart", "pieChart"])
        self.assertEqual([(row["chartType"], row["groupIndex"], row["index"], row["order"])
                          for row in metadata["series"]], [("barChart", 0, 7, 2), ("lineChart", 1, 9, 0), ("pieChart", 2, 4, 1)])

    def test_supported_group_families_preserve_authored_cache_without_rendering(self):
        families = ("areaChart", "area3DChart", "barChart", "bar3DChart", "bubbleChart", "doughnutChart",
                    "lineChart", "line3DChart", "ofPieChart", "pieChart", "pie3DChart", "radarChart",
                    "scatterChart", "stockChart", "surfaceChart", "surface3DChart")
        for family in families:
            with self.subTest(family=family):
                if family in ("scatterChart", "bubbleChart"):
                    source = series(x_values=cache("numLit", [(0, "1")], count=1),
                                    y_values=cache("numLit", [(0, "2")], count=1),
                                    bubble_sizes=cache("numLit", [(0, "3")], count=1) if family == "bubbleChart" else None)
                else:
                    source = series()
                _, block = self.one(chart(kind=family, series_xml=source))
                self.assertEqual(block["metadata"]["chartTypes"], [family])
                self.assertEqual(block["metadata"]["series"][0]["chartType"], family)
                self.assertEqual(block["metadata"]["status"], "complete")
                self.assertFalse(block["metadata"]["visualInterpretation"])

    def test_xy_and_bubble_channels_are_separate_and_not_paired_by_array_position(self):
        xy = series(x_values=cache("numLit", [(0, "1E-3"), (2, "-2")], count=3),
                    y_values=cache("numRef", [(1, "3"), (2, "4.5")], count=3))
        bubble = series(x_values=cache("numLit", [(0, "1")], count=1),
                        y_values=cache("numLit", [(0, "2")], count=1),
                        bubble_sizes=cache("numLit", [(0, "0.25")], count=1))
        _, block = self.one(chart(groups=[("scatterChart", [xy]), ("bubbleChart", [bubble])]))
        first, second = block["metadata"]["series"]
        self.assertEqual(first["xValues"]["points"], [{"index": 0, "value": "1E-3"}, {"index": 2, "value": "-2"}])
        self.assertEqual(first["yValues"]["points"], [{"index": 1, "value": "3"}, {"index": 2, "value": "4.5"}])
        self.assertIsNone(first["values"])
        self.assertIsNone(first["categories"])
        self.assertEqual(second["bubbleSizes"]["points"], [{"index": 0, "value": "0.25"}])

    def test_multilevel_category_cache_retains_each_sparse_level(self):
        categories = ('<c:multiLvlStrRef><c:f>Sheet1!$A$1:$B$3</c:f><c:multiLvlStrCache><c:ptCount val="3"/>'
                      '<c:lvl>' + points([(0, "Q1"), (2, "Q3")]) + '</c:lvl><c:lvl>'
                      + points([(0, "2025"), (1, "2026")]) + '</c:lvl></c:multiLvlStrCache></c:multiLvlStrRef>')
        _, block = self.one(chart(series_xml=series(categories=categories)))
        channel = block["metadata"]["series"][0]["categories"]
        self.assertEqual(channel["kind"], "multiLvlStrRef")
        self.assertEqual(channel["pointCount"], 3)
        self.assertEqual(channel["levels"], [[{"index": 0, "value": "Q1"}, {"index": 2, "value": "Q3"}],
                                             [{"index": 0, "value": "2025"}, {"index": 1, "value": "2026"}]])

    def test_blank_and_missing_values_remain_distinct_without_invented_zeros(self):
        _, block = self.one(chart(series_xml=series(values=cache("numLit", [(0, ""), (1, None), (3, "-0")], count=4))))
        channel = block["metadata"]["series"][0]["values"]
        self.assertEqual(channel["points"], [{"index": 0, "value": ""}, {"index": 1, "value": None}, {"index": 3, "value": "-0"}])
        self.assertEqual(block["metadata"]["status"], "partial")

    def test_formula_only_cache_is_partial_and_never_reads_a_workbook(self):
        uncached = '<c:numRef><c:f>DO_NOT_RESOLVE!$A$1</c:f></c:numRef>'
        entries = docx_entries([chart(series_xml=series(values=uncached), external=True)])
        entries["word/charts/_rels/chart1.xml.rels"] = relationships([("workbook", "package", "https://fixture.invalid/private.xlsx", True)])
        entries["word/embeddings/ignored.xlsx"] = b"must not be opened as a workbook"
        output = self.parse(entries)
        metadata = self.charts(output)[0]["metadata"]
        self.assertEqual(metadata["status"], "partial")
        self.assertEqual(metadata["series"][0]["values"]["formula"], "DO_NOT_RESOLVE!$A$1")
        self.assertEqual(metadata["series"][0]["values"]["points"], [])
        self.assertFalse(metadata["series"][0]["values"]["cachePresent"])
        self.assertTrue(metadata["externalData"])
        self.assertFalse(metadata["workbookResolved"])
        self.assertIn("workbook_not_resolved", metadata["warnings"])
        self.assertNotIn("must not be opened", output["pages"][0]["text"])

    def test_unknown_groups_and_cache_markup_remain_explicitly_partial(self):
        _, block = self.one(chart(kind="futureChart"))
        self.assertEqual(block["metadata"]["status"], "partial")
        self.assertTrue(block["metadata"]["warnings"])
        self.assertFalse(block["metadata"]["visualInterpretation"])
        known_point = '<c:pt idx="0"><c:v>1</c:v></c:pt>'
        variants = [
            ('<c:numRef><c:f>A1</c:f><c:numCache><c:foo/></c:numCache></c:numRef>', []),
            ('<c:numRef><c:f>A1</c:f><c:numCache>' + known_point + '</c:numCache><c:foo/></c:numRef>', [{"index": 0, "value": "1"}]),
            ('<c:numRef><c:f>A1</c:f><c:numCache>' + known_point + '<c:foo/></c:numCache></c:numRef>', [{"index": 0, "value": "1"}]),
            ('<c:numLit><c:pt idx="0"><c:v>1</c:v><c:foo/></c:pt></c:numLit>', [{"index": 0, "value": "1"}]),
        ]
        for value, expected_points in variants:
            with self.subTest(source=value):
                try:
                    _, block = self.one(chart(series_xml=series(values=value)))
                except local.LocalParseError:
                    continue
                self.assertEqual(block["metadata"]["status"], "partial")
                self.assertIn("unsupported_cache_structure", block["metadata"]["warnings"])
                self.assertEqual(block["metadata"]["series"][0]["values"]["points"], expected_points)
        categories = ('<c:multiLvlStrRef><c:f>A1</c:f><c:multiLvlStrCache><c:lvl>'
                      '<c:pt idx="0"><c:v>A</c:v></c:pt><c:foo/></c:lvl></c:multiLvlStrCache></c:multiLvlStrRef>')
        try:
            _, block = self.one(chart(series_xml=series(categories=categories)))
        except local.LocalParseError:
            pass
        else:
            self.assertEqual(block["metadata"]["status"], "partial")
            self.assertIn("unsupported_cache_structure", block["metadata"]["warnings"])
            self.assertEqual(block["metadata"]["series"][0]["categories"]["levels"], [[{"index": 0, "value": "A"}]])
        extended = '<c:numLit>' + known_point + '<c:extLst/></c:numLit>'
        _, block = self.one(chart(series_xml=series(values=extended)))
        self.assertEqual(block["metadata"]["status"], "partial")
        self.assertIn("unsupported_chart_extension", block["metadata"]["warnings"])
        self.assertEqual(block["metadata"]["series"][0]["values"]["points"], [{"index": 0, "value": "1"}])

    def test_unsupported_chart_namespace_is_unavailable_instead_of_visual_inference(self):
        unsupported = '<cx:chartSpace xmlns:cx="http://schemas.microsoft.com/office/drawing/2014/chartex"><cx:chart/></cx:chartSpace>'
        _, block = self.one(unsupported)
        self.assertEqual(block["metadata"]["status"], "unavailable")
        self.assertEqual(block["metadata"]["series"], [])
        self.assertIn("unsupported_chart_part", block["metadata"]["warnings"])
        self.assertFalse(block["inferred"])

    def test_external_and_dangling_chart_references_produce_unavailable_blocks(self):
        for target, external in (("https://fixture.invalid/chart.xml", True), ("charts/missing.xml", False)):
            with self.subTest(target=target):
                output = self.parse(docx_entries([], chart_links=[("unavailable", "chart", target, external)]))
                block = self.charts(output)[0]
                self.assertEqual(block["metadata"]["status"], "unavailable")
                self.assertIsNone(block["metadata"]["sourcePart"])
                self.assertEqual(block["metadata"]["series"], [])
                self.assertTrue(block["metadata"]["warnings"])
                self.assertFalse(block["inferred"])

    def test_wrong_type_encoded_and_uri_chart_targets_are_not_opened(self):
        for kind, target, expected_warning in (("image", "charts/chart1.xml", "invalid_chart_relationship_type"),
                                               ("chart", "charts/%63hart1.xml", "encoded_chart_target_unsupported"),
                                               ("chart", "https://fixture.invalid/chart.xml", "non_package_chart_target")):
            entries = docx_entries([chart()], chart_links=[("chart-1", kind, target, False)])
            with self.subTest(kind=kind, target=target):
                metadata = self.charts(self.parse(entries))[0]["metadata"]
                self.assertEqual(metadata["status"], "unavailable")
                self.assertIn(expected_warning, metadata["warnings"])
                self.assertIsNone(metadata["sourcePart"])

    def test_pptx_uses_presentation_manifest_order_not_filename_or_relationship_order(self):
        output = self.parse(pptx_entries(), "pptx")
        self.assertEqual([page["pageNumber"] for page in output["pages"]], [1, 2])
        self.assertEqual([block["metadata"]["title"] for block in self.charts(output)], ["First slide 🚀", "Second slide"])
        self.assertEqual([block["metadata"]["documentPart"] for block in self.charts(output)],
                         ["ppt/slides/slide9.xml", "ppt/slides/slide2.xml"])

    def test_xlsx_follows_sheet_drawing_and_chart_relationships_without_pages(self):
        output = self.parse(xlsx_entries(), "xlsx")
        self.assertTrue(all("pageNumber" not in page for page in output["pages"]))
        self.assertEqual([block["metadata"]["title"] for block in self.charts(output)], ["Drawing 9", "Drawing 3", "Drawing 2"])
        self.assertEqual([block["metadata"]["sourcePart"] for block in self.charts(output)],
                         ["xl/charts/chart9.xml", "xl/charts/chart3.xml", "xl/charts/chart2.xml"])
        self.assertEqual(output["pages"][0]["blocks"][0]["metadata"]["sheetName"], "First 🧭")

    def test_unreferenced_chart_parts_are_not_discovered_by_zip_scanning(self):
        entries = docx_entries([])
        entries["word/charts/chart999.xml"] = chart(title="Unreferenced secret")
        output = self.parse(entries)
        self.assertEqual(self.charts(output), [])
        self.assertNotIn("Unreferenced secret", output["pages"][0]["text"])

    def test_chart_text_is_exact_compact_source_data_and_not_visual_inference(self):
        _, block = self.one()
        heading, raw = block["text"].split("\n", 1)
        self.assertEqual(heading, "Native OOXML chart cache (not rendered; freshness unverified)")
        expected = {key: block["metadata"][key] for key in ("title", "titleData", "chartTypes", "series", "status", "warnings")}
        self.assertEqual(raw, json.dumps(expected, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        self.assertIn("🚀", raw)
        source = chart()
        start, end = source.index("<c:title>"), source.index("</c:title>") + len("</c:title>")
        title = '<c:title><c:tx>' + cache("strRef", [(0, "Cached title 🚀")], count=1, formula="Sheet1!$D$1") + '</c:tx></c:title>'
        _, block = self.one(source[:start] + title + source[end:])
        self.assertEqual(block["metadata"]["title"], "Cached title 🚀")
        self.assertEqual(block["metadata"]["titleData"]["formula"], "Sheet1!$D$1")
        self.assertEqual(block["metadata"]["titleData"]["points"], [{"index": 0, "value": "Cached title 🚀"}])

    def test_duplicate_package_entries_and_ambiguous_relationship_ids_are_refused(self):
        entries = docx_entries()
        self.refused([*entries.items(), ("word/document.xml", entries["word/document.xml"])])
        entries["word/_rels/document.xml.rels"] = relationships([
            ("chart-1", "chart", "charts/chart1.xml", False), ("chart-1", "chart", "charts/chart2.xml", False)])
        entries["word/charts/chart2.xml"] = chart()
        self.refused(entries)

    def test_package_and_relationship_traversal_are_refused(self):
        entries = docx_entries()
        entries["../escape.xml"] = "<escaped/>"
        self.refused(entries)
        entries = docx_entries([], chart_links=[("escape", "chart", "../../../escape.xml", False)])
        self.refused(entries)

    def test_chart_dtd_entities_malformed_xml_and_nested_scalars_are_refused(self):
        nested_value = '<c:numLit><c:pt idx="0"><c:v>1<c:foo>2</c:foo></c:v></c:pt></c:numLit>'
        nested_formula = '<c:numRef><c:f>A<c:foo>B</c:foo></c:f><c:numCache/></c:numRef>'
        sources = ('<!DOCTYPE chart [<!ENTITY injected "no">]>' + chart(),
                   '<?xml version="1.0"?><!ENTITY injected "no">' + chart(),
                   '<c:chartSpace xmlns:c="' + C + '"><c:chart>',
                   chart().replace('<a:t>Revenue 🚀</a:t>', '<a:t>Outer<a:t>Hidden</a:t>Tail</a:t>'),
                   chart(series_xml=series(values=nested_value)),
                   chart(series_xml=series(values=nested_formula)),
                   chart().replace('<c:formatCode>0.00</c:formatCode>', '<c:formatCode>0<c:foo/>Tail</c:formatCode>'),
                   chart().replace('<c:v>North 🧭</c:v>', '<c:v>Outer<c:foo/>Tail</c:v>'))
        for source in sources:
            with self.subTest(source=source[:50]):
                self.refused(docx_entries([source]))

    def test_duplicate_negative_out_of_count_and_excessive_point_indices_are_refused(self):
        for rows, count in (([(0, "1"), (0, "2")], 2), ([(-1, "1")], 1), ([(2, "1")], 2), ([(2**32, "1")], 2**32 + 1)):
            with self.subTest(rows=rows):
                self.refused(docx_entries([chart(series_xml=series(values=cache("numLit", rows, count=count)))]))

    def test_numeric_cache_preserves_error_and_nonfinite_lexemes_as_source_claims(self):
        for value in ("NaN", "Infinity", "-Infinity", "#DIV/0!", "not-a-number"):
            with self.subTest(value=value):
                _, block = self.one(chart(series_xml=series(values=cache("numLit", [(0, value)], count=1))))
                channel = block["metadata"]["series"][0]["values"]
                self.assertEqual(channel["points"], [{"index": 0, "value": value}])
                self.assertTrue(channel["cachePresent"])
                self.assertFalse(block["metadata"]["visualInterpretation"])

    def test_optional_point_count_and_empty_cache_do_not_invent_observations(self):
        values = '<c:numLit>' + points([(2**32 - 1, "1E3")]) + '</c:numLit>'
        _, block = self.one(chart(series_xml=series(values=values)))
        channel = block["metadata"]["series"][0]["values"]
        self.assertIsNone(channel["pointCount"])
        self.assertEqual(channel["points"], [{"index": 2**32 - 1, "value": "1E3"}])
        self.assertTrue(channel["cachePresent"])
        self.assertEqual(block["metadata"]["status"], "complete")
        _, block = self.one(chart(series_xml=series(values='<c:numRef><c:f>A1</c:f><c:numCache><c:ptCount val="0"/></c:numCache></c:numRef>')))
        channel = block["metadata"]["series"][0]["values"]
        self.assertEqual(channel["points"], [])
        self.assertEqual(channel["pointCount"], 0)
        self.assertTrue(channel["cachePresent"])
        self.assertEqual(block["metadata"]["status"], "complete")

    def test_zip_entry_count_expanded_total_and_xml_byte_budgets_are_enforced(self):
        for field, bound in (("MAX_ZIP_ENTRIES", 2), ("MAX_ZIP_TOTAL", 256), ("MAX_ZIP_ENTRY", 256)):
            with self.subTest(field=field), patch.object(local, field, bound):
                self.refused(docx_entries())

    def test_point_budget_accepts_boundary_and_refuses_one_more_cached_point(self):
        for count in (4, 5):
            values = cache("numLit", [(index, str(index)) for index in range(count)], count=count)
            entries = docx_entries([chart(series_xml=series(categories="", values=values))])
            with self.subTest(count=count), patch.object(charts_module, "MAX_CHART_POINTS", 4):
                if count == 4:
                    self.assertEqual(len(self.charts(self.parse(entries))[0]["metadata"]["series"][0]["values"]["points"]), 4)
                else:
                    self.refused(entries)

    def test_reference_series_and_chart_text_budgets_fail_closed(self):
        variants = (("MAX_CHART_REFERENCES", 1, docx_entries([chart(), chart()])),
                    ("MAX_CHART_SERIES", 1, docx_entries([chart(groups=[("lineChart", [series(), series(index="1")])])])),
                    ("MAX_CHART_TEXT", 32, docx_entries([chart(title="x" * 100)])))
        for field, bound, entries in variants:
            with self.subTest(field=field), patch.object(charts_module, field, bound):
                self.refused(entries)

    def test_chart_xml_and_drawing_budgets_are_shared_across_one_document(self):
        for field, bound in (("MAX_CHART_XML_BYTES", 256), ("MAX_CHART_XML_ELEMENTS", 8), ("MAX_CHART_PARTS", 1)):
            with self.subTest(field=field), patch.object(charts_module, field, bound):
                self.refused(docx_entries())
        with patch.object(charts_module, "MAX_DRAWING_REFERENCES", 1), self.assertRaises(local.LocalParseError):
            self.parse(xlsx_entries(), "xlsx")
        with patch.object(charts_module, "MAX_CHART_POINTS", 8):
            self.refused(docx_entries([chart(), chart()]))

    def test_chart_string_byte_limit_refuses_oversized_unicode_title(self):
        self.refused(docx_entries([chart(title="é" * 8193)]))
