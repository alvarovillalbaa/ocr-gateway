"""Bounded extraction of referenced OOXML chart caches, without rendering."""

from __future__ import annotations

import json
from pathlib import PurePosixPath
import re
from typing import Any, Callable
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET


MAX_CHART_REFERENCES = 256
MAX_CHART_SERIES = 1024
MAX_CHART_POINTS = 50_000
MAX_CHART_TEXT = 4 * 1024 * 1024
MAX_CHART_STRING = 16_384
MAX_CHART_XML_BYTES = 32 * 1024 * 1024
MAX_CHART_XML_ELEMENTS = 200_000
MAX_CHART_PARTS = 512
MAX_DRAWING_REFERENCES = 1024

_C_URI = "http://schemas.openxmlformats.org/drawingml/2006/chart"
_C = "{" + _C_URI + "}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_R_URI = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_PACKAGE = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_GROUPS = frozenset({
    "areaChart", "area3DChart", "barChart", "bar3DChart", "bubbleChart", "doughnutChart",
    "lineChart", "line3DChart", "ofPieChart", "pieChart", "pie3DChart", "radarChart",
    "scatterChart", "stockChart", "surfaceChart", "surface3DChart",
})
_CHOICES = frozenset({"strRef", "strLit", "numRef", "numLit", "multiLvlStrRef"})
_CHANNELS = {"name": "tx", "categories": "cat", "values": "val", "xValues": "xVal",
             "yValues": "yVal", "bubbleSizes": "bubbleSize"}
_HEADING = "Native OOXML chart cache (not rendered; freshness unverified)\n"


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


class ChartExtractor:
    """Share source, point and text budgets across all host parts of one file."""

    def __init__(self, package: Any, block: Callable[..., dict], relationships: Callable[..., dict],
                 error: type[ValueError], warnings: list[str]):
        self.package = package
        self.block = block
        self.relationships = relationships
        self.error = error
        self.warnings = warnings
        self.references = self.series = self.points = self.text_bytes = self.xml_bytes = self.xml_elements = 0
        self.drawing_references = 0
        self.xml: dict[str, ET.Element] = {}
        self.records: dict[str, dict[str, tuple[str, str, str]]] = {}
        self.targets: dict[str, dict[str, str]] = {}

    def _fail(self, message: str) -> None:
        raise self.error(message)

    def _text(self, value: str | None) -> str | None:
        if value is not None:
            size = len(value.encode("utf-8"))
            self.text_bytes += size
            if size > MAX_CHART_STRING or self.text_bytes > MAX_CHART_TEXT:
                self._fail("OOXML chart text exceeds local limit")
        return value

    def _integer(self, value: str | None, maximum: int = 2**32 - 1) -> int:
        if value is None or not re.fullmatch(r"[0-9]{1,10}", value) or int(value) > maximum:
            self._fail("Invalid or excessive OOXML chart index/count")
        return int(value)

    def _one(self, parent: ET.Element, name: str) -> ET.Element | None:
        matches = parent.findall(_C + name)
        if len(matches) > 1:
            self._fail("Ambiguous OOXML chart structure")
        return matches[0] if matches else None

    def _scalar(self, node: ET.Element) -> str:
        if len(node):
            self._fail("Unsupported markup in OOXML chart scalar data")
        return self._text(node.text or "")

    def _children(self, parent: ET.Element, allowed: set[str], problems: list[str]) -> None:
        if any(child.tag not in {_C + name for name in allowed} for child in parent):
            problems.append("unsupported_cache_structure")

    def _load(self, part: str) -> ET.Element:
        if part not in self.xml:
            self.xml_bytes += self.package.archive.getinfo(part).file_size
            if len(self.xml) >= MAX_CHART_PARTS or self.xml_bytes > MAX_CHART_XML_BYTES:
                self._fail("OOXML chart source parts exceed local limit")
            root = self.package.xml(part)
            self.xml_elements += sum(1 for _ in root.iter())
            if self.xml_elements > MAX_CHART_XML_ELEMENTS:
                self._fail("OOXML chart XML elements exceed local limit")
            self.xml[part] = root
        return self.xml[part]

    def _relations(self, owner: str) -> dict[str, tuple[str, str, str]]:
        if owner not in self.records:
            path = PurePosixPath(owner)
            rel_part = str(path.parent / "_rels" / (path.name + ".rels"))
            rows = {}
            if rel_part in self.package.names:
                root = self._load(rel_part)
                if root.tag != _PACKAGE + "Relationships":
                    self._fail("Invalid OOXML chart relationship part")
                for item in root:
                    if item.tag != _PACKAGE + "Relationship":
                        self._fail("Invalid OOXML chart relationship record")
                    identity = item.get("Id", "")
                    if not identity or len(identity.encode("utf-8")) > MAX_CHART_STRING or identity in rows:
                        self._fail("Ambiguous or invalid OOXML chart relationship identifier")
                    rows[identity] = (item.get("Target", ""), item.get("TargetMode", "Internal"), item.get("Type", ""))
            self.records[owner] = rows
        return self.records[owner]

    def validate_host_relationships(self, owner: str) -> None:
        # Parent host IDs choose the slide/sheet before its chart references are
        # visited. Reject ambiguity there instead of accepting a last-wins map.
        self._relations(owner)

    def _target(self, owner: str, identity: str | None, kind: str, problems: list[str]) -> str | None:
        if not identity:
            problems.append("missing_" + kind + "_relationship_id")
            return None
        record = self._relations(owner).get(identity)
        if record is None:
            problems.append("missing_" + kind + "_relationship")
            return None
        target, mode, relation_type = record
        if mode == "External":
            problems.append("external_" + kind + "_relationship")
            return None
        if mode != "Internal":
            self._fail("Invalid OOXML chart relationship target mode")
        if relation_type != _R_URI + kind:
            problems.append("invalid_" + kind + "_relationship_type")
            return None
        if "\\" in target or any(ord(char) < 32 or ord(char) == 127 for char in target):
            self._fail("Unsafe OOXML chart relationship target")
        try:
            uri = urlsplit(target)
        except ValueError:
            self._fail("Invalid OOXML chart relationship target")
        if uri.scheme or uri.netloc or uri.query or uri.fragment:
            problems.append("non_package_" + kind + "_target")
            return None
        if "%" in target:
            problems.append("encoded_" + kind + "_target_unsupported")
            return None
        if not target:
            problems.append("missing_" + kind + "_part")
            return None
        if owner not in self.targets:
            path = PurePosixPath(owner)
            self.targets[owner] = self.relationships(self.package, str(path.parent), str(path.parent / "_rels" / (path.name + ".rels")))
        result = self.targets[owner].get(identity)
        if result is None:
            problems.append("missing_" + kind + "_part")
        return result

    def _publish(self, problems: list[str]) -> None:
        for problem in dict.fromkeys(problems):
            warning = "Native OOXML chart extraction: " + problem
            if warning not in self.warnings:
                self.warnings.append(warning)

    def _point_list(self, parent: ET.Element, count: int | None, problems: list[str]) -> list[dict]:
        result = []
        seen = set()
        for point in parent.findall(_C + "pt"):
            self.points += 1
            if self.points > MAX_CHART_POINTS:
                self._fail("OOXML chart cache points exceed local limit")
            index = self._integer(point.get("idx"))
            if index in seen or (count is not None and index >= count):
                self._fail("Duplicate or out-of-range OOXML chart point index")
            seen.add(index)
            self._children(point, {"v", "extLst"}, problems)
            value = self._one(point, "v")
            if value is None:
                problems.append("missing_cache_value")
            # Cache values, including Excel error strings, are source lexemes.
            # They are not parsed, rounded or asserted to be finite numbers.
            row = {"index": index, "value": self._scalar(value) if value is not None else None}
            if "formatCode" in point.attrib:
                row["formatCode"] = self._text(point.get("formatCode"))
            result.append(row)
        return result

    def _data(self, parent: ET.Element | None, problems: list[str], *, literal: bool = False,
              allowed: frozenset[str] = _CHOICES) -> dict | None:
        if parent is None:
            return None
        choices = [child for child in parent if child.tag in {_C + name for name in allowed}
                   or (literal and child.tag == _C + "v")]
        if len(choices) > 1:
            self._fail("Ambiguous OOXML chart data source")
        if not choices or any(child.tag not in {_C + name for name in allowed}
                              and not (literal and child.tag == _C + "v") for child in parent):
            problems.append("unsupported_cache_structure")
        if not choices:
            return None
        source = choices[0]
        kind = _name(source.tag)
        result = {"kind": "literal" if kind == "v" else kind, "formula": None, "formatCode": None,
                  "pointCount": None, "literal": None, "points": [], "levels": [], "cachePresent": None}
        if kind == "v":
            result["literal"] = self._scalar(source)
            return result
        if kind.endswith("Ref"):
            formula = self._one(source, "f")
            result["formula"] = self._scalar(formula) if formula is not None else None
            if formula is None:
                problems.append("missing_reference_formula")
            elif not result["formula"].strip():
                problems.append("empty_reference_formula")
            cache_name = {"strRef": "strCache", "numRef": "numCache", "multiLvlStrRef": "multiLvlStrCache"}[kind]
            self._children(source, {"f", cache_name, "extLst"}, problems)
            cache = self._one(source, cache_name)
        else:
            cache = source
        result["cachePresent"] = cache is not None
        if cache is None:
            problems.append("missing_cache")
            return result
        children = {"ptCount", "extLst", "lvl" if kind == "multiLvlStrRef" else "pt"}
        if kind in ("numRef", "numLit"):
            children.add("formatCode")
        self._children(cache, children, problems)
        point_count = self._one(cache, "ptCount")
        if point_count is not None:
            self._children(point_count, set(), problems)
            result["pointCount"] = self._integer(point_count.get("val"), MAX_CHART_POINTS)
        format_code = self._one(cache, "formatCode")
        if format_code is not None:
            result["formatCode"] = self._scalar(format_code)
        if kind == "multiLvlStrRef":
            for level in cache.findall(_C + "lvl"):
                self._children(level, {"pt", "extLst"}, problems)
                result["levels"].append(self._point_list(level, result["pointCount"], problems))
        else:
            result["points"] = self._point_list(cache, result["pointCount"], problems)
        return result

    def _title(self, chart: ET.Element, problems: list[str]) -> tuple[str | None, dict | None]:
        title = self._one(chart, "title")
        if title is None:
            return None, None
        tx = self._one(title, "tx")
        if tx is None:
            problems.append("missing_chart_title_cache")
            return None, None
        rich = self._one(tx, "rich")
        if rich is not None:
            if any(child.tag in {_C + name for name in _CHOICES} for child in tx):
                self._fail("Ambiguous OOXML chart title source")
            paragraphs = []
            for paragraph in rich.findall(_A + "p"):
                pieces = []
                for node in paragraph.iter():
                    if node.tag == _A + "t":
                        pieces.append(self._scalar(node))
                    elif node.tag == _A + "br":
                        pieces.append("\n")
                    elif node.tag == _A + "tab":
                        pieces.append("\t")
                paragraphs.append("".join(pieces))
            return self._text("\n".join(paragraphs)), None
        data = self._data(tx, problems, allowed=frozenset({"strRef", "strLit"}))
        if data is not None and len(data["points"]) == 1 and data["points"][0]["index"] == 0:
            return data["points"][0]["value"], data
        problems.append("missing_chart_title_cache")
        return None, data

    def _chart(self, root: ET.Element, metadata: dict, problems: list[str]) -> None:
        if root.tag != _C + "chartSpace":
            problems.append("unsupported_chart_part")
            return
        chart = self._one(root, "chart")
        if chart is None:
            problems.append("missing_chart")
            return
        metadata["title"], metadata["titleData"] = self._title(chart, problems)
        metadata["externalData"] = self._one(root, "externalData") is not None
        if metadata["externalData"]:
            problems.append("workbook_not_resolved")
        if any(node.tag == _C + "extLst" or (node.tag.startswith("{") and not node.tag.startswith((_C, _A))) for node in root.iter()):
            problems.append("unsupported_chart_extension")
        plot = self._one(chart, "plotArea")
        if plot is None:
            problems.append("missing_plot_area")
            return
        groups = [child for child in plot if child.tag.startswith(_C) and _name(child.tag).endswith("Chart")]
        if not groups:
            problems.append("missing_chart_groups")
        for group_index, group in enumerate(groups):
            name = _name(group.tag)
            metadata["chartTypes"].append(name)
            if name not in _GROUPS:
                problems.append("unsupported_chart_group")
                continue
            series = group.findall(_C + "ser")
            if not series:
                problems.append("missing_series")
            for source in series:
                self.series += 1
                if self.series > MAX_CHART_SERIES:
                    self._fail("OOXML chart series exceed local limit")
                index, order = self._one(source, "idx"), self._one(source, "order")
                if index is None:
                    problems.append("missing_series_index")
                if order is None:
                    problems.append("missing_series_order")
                row = {"chartType": name, "groupIndex": group_index,
                       "index": self._integer(index.get("val")) if index is not None else None,
                       "order": self._integer(order.get("val")) if order is not None else None}
                for channel, tag in _CHANNELS.items():
                    choices = frozenset({"strRef"}) if channel == "name" else (
                        _CHOICES if channel in ("categories", "xValues") else frozenset({"numRef", "numLit"}))
                    row[channel] = self._data(self._one(source, tag), problems, literal=channel == "name", allowed=choices)
                required = ("xValues", "yValues", "bubbleSizes") if name == "bubbleChart" else (
                    ("xValues", "yValues") if name == "scatterChart" else ("values",))
                if any(row[channel] is None for channel in required):
                    problems.append("missing_required_data")
                metadata["series"].append(row)
        metadata["status"] = "partial" if any(problem != "workbook_not_resolved" for problem in problems) else "complete"

    def from_host(self, root: ET.Element, owner: str, *, document_part: str | None = None,
                  sheet_name: str | None = None) -> list[dict]:
        blocks = []
        for reference in root.iter():
            namespace = reference.tag.partition("}")[0].lstrip("{")
            if _name(reference.tag) != "chart" or "chart" not in namespace.lower():
                continue
            self.references += 1
            if self.references > MAX_CHART_REFERENCES:
                self._fail("OOXML chart references exceed local limit")
            problems = []
            identity = self._text(reference.get(_R + "id"))
            metadata = {"source": "ooxml-chart-cache", "schemaVersion": 1, "status": "unavailable",
                        "documentPart": self._text(document_part or owner), "sourcePart": None,
                        "relationshipSourcePart": self._text(owner), "relationshipId": identity,
                        "title": None, "titleData": None, "chartTypes": [], "series": [], "externalData": False,
                        "workbookResolved": False, "cacheFreshness": "unverified", "visualInterpretation": False, "warnings": []}
            if sheet_name is not None:
                metadata["sheetName"] = self._text(sheet_name)
            target = self._target(owner, identity, "chart", problems)
            metadata["sourcePart"] = self._text(target)
            if reference.tag != _C + "chart":
                problems.append("unsupported_chart_namespace")
            elif target is not None:
                self._chart(self._load(target), metadata, problems)
            metadata["warnings"] = list(dict.fromkeys(problems))
            text = {key: metadata[key] for key in ("title", "titleData", "chartTypes", "series", "status", "warnings")}
            blocks.append(self.block("chart", _HEADING + json.dumps(text, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
                                     inferred=False, metadata=metadata))
            message = "Native OOXML chart data is cache-only; freshness is unverified, workbooks are not resolved, and visuals are not interpreted"
            if message not in self.warnings:
                self.warnings.append(message)
            self._publish(problems)
        return blocks

    def from_worksheet(self, worksheet: ET.Element, part: str, name: str) -> list[dict]:
        blocks = []
        for drawing in worksheet.iter(_S + "drawing"):
            self.drawing_references += 1
            if self.drawing_references > MAX_DRAWING_REFERENCES:
                self._fail("OOXML drawing references exceed local limit")
            problems = []
            target = self._target(part, drawing.get(_R + "id"), "drawing", problems)
            self._publish(problems)
            if target is not None:
                blocks.extend(self.from_host(self._load(target), target, document_part=part, sheet_name=name))
        return blocks
