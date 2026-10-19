"""Bounded local extraction; JSON DocumentInput on stdin, ProviderOutput on stdout.

This is an extraction baseline, not a chart/diagram understanding model. No URLs
are fetched and no data leaves the host. PDF/image support is optional.
"""

from __future__ import annotations

import base64
import binascii
import csv
from contextvars import ContextVar
from html.parser import HTMLParser
import io
import json
import mimetypes
import os
from pathlib import PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from typing import Any

MAX_INPUT = 32 * 1024 * 1024
MAX_STDIN = 46 * 1024 * 1024
MAX_OUTPUT = 16 * 1024 * 1024
MAX_TEXT = 4 * 1024 * 1024
MAX_PAGES = 500
MAX_ZIP_ENTRIES = 3000
MAX_ZIP_TOTAL = 128 * 1024 * 1024
MAX_ZIP_ENTRY = 16 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_IMAGE_BYTES = 2 * 1024 * 1024
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_BUDGET: ContextVar[dict[str, int] | None] = ContextVar("local_output_budget", default=None)


class LocalParseError(ValueError):
    pass


def _text(value: str) -> str:
    value = value.strip()
    if len(value) > MAX_TEXT:
        raise LocalParseError("Extracted text exceeds local limit")
    return value


def _block(kind: str, text: str, **extra: Any) -> dict[str, Any]:
    block = {"kind": kind, "text": _text(text), **extra}
    budget = _BUDGET.get()
    if budget is not None:
        budget["blocks"] += 1
        budget["bytes"] += len(json.dumps(block, ensure_ascii=False).encode("utf-8"))
        if budget["blocks"] > 100_000 or budget["bytes"] > MAX_OUTPUT - 65536:
            raise LocalParseError("Extracted blocks exceed local output limit")
    return block


def _page(blocks: list[dict[str, Any]], number: int | None = None, **extra: Any) -> dict[str, Any]:
    text = _text("\n\n".join(block["text"] for block in blocks if block["text"]))
    value: dict[str, Any] = {"text": text, "blocks": blocks, **extra}
    budget = _BUDGET.get()
    if budget is not None:
        budget["bytes"] += len(json.dumps(text, ensure_ascii=False).encode("utf-8"))
        if budget["bytes"] > MAX_OUTPUT - 65536:
            raise LocalParseError("Extracted pages exceed local output limit")
    if number is not None:
        value["pageNumber"] = number
    return value


def _xml(data: bytes) -> ET.Element:
    if len(data) > MAX_ZIP_ENTRY:
        raise LocalParseError("XML entry exceeds local limit")
    try:
        # Office package XML is UTF-8. Reject DTD/entity declarations before
        # parsing; do not permit external references or entity expansion.
        source = data.decode("utf-8-sig")
        if "<!DOCTYPE" in source.upper() or "<!ENTITY" in source.upper():
            raise LocalParseError("DTD/entity declarations are not supported")
        root = ET.fromstring(source)
        if sum(1 for _ in root.iter()) > 200_000:
            raise LocalParseError("XML element count exceeds local limit")
        return root
    except (UnicodeDecodeError, ET.ParseError) as exc:
        raise LocalParseError("Invalid or unsupported XML encoding") from exc


class _Package:
    def __init__(self, data: bytes):
        try:
            self.archive = zipfile.ZipFile(io.BytesIO(data))
            entries = self.archive.infolist()
            if len(entries) > MAX_ZIP_ENTRIES:
                raise LocalParseError("Office package has too many entries")
            total = 0
            names: set[str] = set()
            for entry in entries:
                path = PurePosixPath(entry.filename)
                if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or entry.filename in names:
                    raise LocalParseError("Unsafe or duplicate office package entry")
                names.add(entry.filename)
                if entry.flag_bits & 1:
                    raise LocalParseError("Encrypted office packages are not supported")
                if entry.file_size > MAX_ZIP_ENTRY:
                    raise LocalParseError("Office package entry exceeds local limit")
                if entry.file_size > 1024 * 1024 and entry.file_size > max(1, entry.compress_size) * 1000:
                    raise LocalParseError("Office package compression ratio exceeds local limit")
                total += entry.file_size
            if total > MAX_ZIP_TOTAL:
                raise LocalParseError("Expanded office package exceeds local limit")
            self.names = names
        except (zipfile.BadZipFile, NotImplementedError) as exc:
            raise LocalParseError("Invalid or unsupported office ZIP package") from exc

    def read(self, name: str) -> bytes:
        try:
            with self.archive.open(name) as source:
                result = source.read(MAX_ZIP_ENTRY + 1)
            if len(result) > MAX_ZIP_ENTRY:
                raise LocalParseError("Expanded entry exceeds local limit")
            return result
        except (KeyError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
            raise LocalParseError("Missing or corrupt office package entry") from exc

    def xml(self, name: str) -> ET.Element:
        return _xml(self.read(name))

    def close(self) -> None:
        self.archive.close()


def _relationships(package: _Package, base: str, rel_name: str) -> dict[str, str]:
    if rel_name not in package.names:
        return {}
    result = {}
    for item in package.xml(rel_name):
        if item.get("TargetMode") == "External":
            continue
        target = item.get("Target", "")
        if target.startswith("/"):
            path = target.lstrip("/")
        else:
            parts: list[str] = list(PurePosixPath(base).parts)
            for part in PurePosixPath(target).parts:
                if part == "..":
                    if not parts:
                        raise LocalParseError("Unsafe relationship path")
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            path = "/".join(parts)
        if path in package.names:
            result[item.get("Id", "")] = path
    return result


def _office_images(root: ET.Element, relationships: dict[str, str], package: _Package) -> list[dict[str, Any]]:
    result = []
    for blip in root.iter(_A + "blip"):
        target = relationships.get(blip.get(_R + "embed", ""))
        if target and package.archive.getinfo(target).file_size <= MAX_IMAGE_BYTES:
            image = package.read(target)
            result.append(_block("image", "", imageBase64=base64.b64encode(image).decode("ascii"), mimeType=mimetypes.guess_type(target)[0] or "application/octet-stream", metadata={"source": "embedded-image", "name": PurePosixPath(target).name, "visualInterpretation": False}))
    return result


def _paragraph(root: ET.Element) -> str:
    pieces = []
    for node in root.iter():
        if node.tag in {_W + "t", _A + "t"}:
            pieces.append(node.text or "")
        elif node.tag in {_W + "tab", _A + "tab"}:
            pieces.append("\t")
        elif node.tag in {_W + "br", _A + "br"}:
            pieces.append("\n")
    return "".join(pieces)


def _table(rows: list[list[str]], **metadata: Any) -> dict[str, Any]:
    return _block("table", "\n".join("\t".join(cell.replace("\t", " ").replace("\n", " ") for cell in row) for row in rows), metadata={"rows": rows, **metadata})


def _docx(package: _Package) -> list[dict[str, Any]]:
    root = package.xml("word/document.xml")
    body = root.find(_W + "body")
    if body is None:
        raise LocalParseError("DOCX has no document body")
    relationships = _relationships(package, "word", "word/_rels/document.xml.rels")
    blocks = []
    for item in body:
        if item.tag == _W + "p":
            text = _paragraph(item)
            if text.strip():
                style = item.find(".//" + _W + "pStyle")
                heading = style is not None and style.get(_W + "val", "").lower().startswith("heading")
                blocks.append(_block("heading" if heading else "text", text))
            blocks.extend(_office_images(item, relationships, package))
        elif item.tag == _W + "tbl":
            rows = [["\n".join(_paragraph(p) for p in cell.findall(_W + "p")) for cell in row.findall(_W + "tc")] for row in item.findall(_W + "tr")]
            blocks.append(_table(rows))
    return [_page(blocks)]


def _pptx(package: _Package) -> list[dict[str, Any]]:
    root = package.xml("ppt/presentation.xml")
    relationships = _relationships(package, "ppt", "ppt/_rels/presentation.xml.rels")
    slide_ids = root.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}sldId")
    if len(slide_ids) > MAX_PAGES:
        raise LocalParseError("Slide count exceeds local limit")
    pages = []
    for number, slide_id in enumerate(slide_ids, 1):
        path = relationships.get(slide_id.get(_R + "id", ""))
        if path is None:
            raise LocalParseError("PPTX slide relationship is missing")
        slide = package.xml(path)
        blocks = []
        for shape in slide.findall(".//{http://schemas.openxmlformats.org/presentationml/2006/main}sp"):
            text = "\n".join(_paragraph(p) for p in shape.iter(_A + "p"))
            if text.strip():
                blocks.append(_block("text", text))
        for table in slide.iter(_A + "tbl"):
            rows = [["\n".join(_paragraph(p) for p in cell.iter(_A + "p")) for cell in row.findall(_A + "tc")] for row in table.findall(_A + "tr")]
            blocks.append(_table(rows))
        base = str(PurePosixPath(path).parent)
        rel_name = base + "/_rels/" + PurePosixPath(path).name + ".rels"
        blocks.extend(_office_images(slide, _relationships(package, base, rel_name), package))
        pages.append(_page(blocks, number))
    return pages


def _xlsx(package: _Package) -> list[dict[str, Any]]:
    strings = []
    if "xl/sharedStrings.xml" in package.names:
        strings = ["".join(node.text or "" for node in item.iter(_S + "t")) for item in package.xml("xl/sharedStrings.xml")]
    root = package.xml("xl/workbook.xml")
    relationships = _relationships(package, "xl", "xl/_rels/workbook.xml.rels")
    sheets = root.findall(".//" + _S + "sheet")
    if len(sheets) > MAX_PAGES:
        raise LocalParseError("Sheet count exceeds local limit")
    pages = []
    cells = 0
    for sheet in sheets:
        path = relationships.get(sheet.get(_R + "id", ""))
        if path is None:
            raise LocalParseError("XLSX sheet relationship is missing")
        rows = []
        references = []
        row_numbers = []
        for row in package.xml(path).iter(_S + "row"):
            values = []
            refs = []
            for cell in row.findall(_S + "c"):
                cells += 1
                if cells > 200_000:
                    raise LocalParseError("Spreadsheet cell count exceeds local limit")
                value = cell.findtext(_S + "v", "")
                if cell.get("t") == "s":
                    try:
                        index = int(value)
                        if index < 0:
                            raise ValueError("negative shared string index")
                        value = strings[index]
                    except (ValueError, IndexError) as exc:
                        raise LocalParseError("Invalid shared string index") from exc
                elif cell.get("t") == "inlineStr":
                    value = "".join(node.text or "" for node in cell.iter(_S + "t"))
                reference = cell.get("r")
                match = re.fullmatch(r"([A-Z]{1,3})[1-9][0-9]*", reference or "")
                if match:
                    column = 0
                    for letter in match[1]:
                        column = column * 26 + ord(letter) - ord("A") + 1
                    if column > 16384 or column <= len(values):
                        raise LocalParseError("Invalid spreadsheet cell ordering/reference")
                    gap = column - len(values) - 1
                    cells += gap
                    if cells > 200_000:
                        raise LocalParseError("Expanded spreadsheet cell count exceeds local limit")
                    values.extend([""] * gap)
                    refs.extend([None] * gap)
                values.append(value)
                refs.append(reference)
            rows.append(values)
            references.append(refs)
            row_numbers.append(row.get("r"))
        # A worksheet is not a rendered page: retain the sheet name and source
        # cell references, while deliberately omitting a page number.
        pages.append(_page([_table(rows, sheetName=sheet.get("name", ""), cellReferences=references, sourceRowNumbers=row_numbers, values="cached-values-no-formula-evaluation")]))
    return pages


def _odt(package: _Package) -> list[dict[str, Any]]:
    text_ns = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
    table_ns = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
    root = package.xml("content.xml")
    blocks = []
    office_text = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:office:1.0}text")
    if office_text is None:
        raise LocalParseError("ODT has no document text")

    def visit(node: ET.Element) -> None:
        if node.tag in {text_ns + "p", text_ns + "h"}:
            value = "".join(node.itertext())
            if value.strip():
                blocks.append(_block("heading" if node.tag == text_ns + "h" else "text", value))
        elif node.tag == table_ns + "table":
            rows = [[" ".join(cell.itertext()).strip() for cell in row if cell.tag in {table_ns + "table-cell", table_ns + "covered-table-cell"}] for row in node.iter(table_ns + "table-row")]
            blocks.append(_table(rows, repeatedCells="not-expanded"))
        else:
            for child in node:
                visit(child)

    visit(office_text)
    return [_page(blocks)]


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict[str, Any]] = []
        self.current: list[str] = []
        self.kind = "text"
        self.hidden = 0
        self.rows: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def flush(self) -> None:
        text = "".join(self.current).strip()
        if text:
            self.blocks.append(_block(self.kind, text))
        self.current = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
            return
        if self.hidden:
            return
        if tag == "table" and self.rows is None:
            self.flush()
            self.rows = []
        elif tag == "tr" and self.rows is not None:
            self.row = []
        elif tag in {"td", "th"} and self.rows is not None:
            self.cell = []
        elif tag == "img":
            self.flush()
            alt = dict(attrs).get("alt") or ""
            self.blocks.append(_block("image", alt, metadata={"source": "html-alt-text", "visualInterpretation": False}))
        elif tag in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre"} and self.rows is None:
            self.flush()
            self.kind = "heading" if tag.startswith("h") and len(tag) == 2 else "list" if tag == "li" else "code" if tag == "pre" else "text"
        elif tag == "br":
            self.handle_data("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self.hidden = max(0, self.hidden - 1)
            return
        if self.hidden:
            return
        if tag in {"td", "th"} and self.cell is not None:
            if self.row is None:
                self.row = []
            self.row.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None and self.rows is not None:
            self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.rows is not None:
            self.blocks.append(_table(self.rows))
            self.rows = None
        elif tag in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "pre"} and self.rows is None:
            self.flush()

    def handle_data(self, data: str) -> None:
        if self.hidden:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.rows is None:
            self.current.append(data)


def _ocr_image(image: Any) -> str:
    executable = shutil.which("tesseract")
    if executable is None:
        raise LocalParseError("Image OCR requires the local tesseract executable")
    if image.width * image.height > MAX_PIXELS:
        raise LocalParseError("Image pixel count exceeds local limit")
    with tempfile.TemporaryDirectory(prefix="ocr-gateway-") as directory:
        source = os.path.join(directory, "input.png")
        target = os.path.join(directory, "output")
        image.convert("RGB").save(source)
        try:
            # Use files rather than captured stdout so OCR cannot accumulate an
            # unbounded Python byte buffer. The Node adapter also kills deadline
            # violations for the complete local process group.
            with open(os.devnull, "wb") as devnull:
                completed = subprocess.run([executable, source, target, "-l", "eng"], stdout=devnull, stderr=devnull, timeout=30, check=False)
            if completed.returncode:
                raise LocalParseError("Tesseract could not extract this image")
            with open(target + ".txt", "rb") as handle:
                value = handle.read(MAX_TEXT + 1)
            if len(value) > MAX_TEXT:
                raise LocalParseError("Image OCR text exceeds local limit")
            return value.decode("utf-8", errors="replace").strip()
        except subprocess.TimeoutExpired as exc:
            raise LocalParseError("Tesseract exceeded the per-image 30 second limit") from exc


def _image(data: bytes, mime: str) -> list[dict[str, Any]]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise LocalParseError("Image OCR requires the Pillow optional dependency and tesseract executable") from exc
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    pages = []
    with Image.open(io.BytesIO(data)) as image:
        count = getattr(image, "n_frames", 1)
        if count > MAX_PAGES:
            raise LocalParseError("Image frame count exceeds local limit")
        for index in range(count):
            image.seek(index)
            if image.width * image.height > MAX_PIXELS:
                raise LocalParseError("Image pixel count exceeds local limit")
            text = _ocr_image(image)
            blocks = [_block("text", text)] if text else []
            if count == 1 and len(data) <= MAX_IMAGE_BYTES:
                blocks.append(_block("image", "", imageBase64=base64.b64encode(data).decode("ascii"), mimeType=mime, metadata={"source": "input-image", "visualInterpretation": False}))
            # A single standalone image has a known frame, but no document page.
            pages.append(_page(blocks, index + 1 if count > 1 else None, width=image.width, height=image.height))
    return pages


def _pdf(data: bytes, warnings: list[str]) -> list[dict[str, Any]]:
    try:
        import pymupdf
    except ImportError as exc:
        raise LocalParseError("PDF extraction requires the PyMuPDF optional dependency") from exc
    pages = []
    with pymupdf.open(stream=data, filetype="pdf") as document:
        if document.needs_pass:
            raise LocalParseError("Encrypted PDF requires decryption before local parsing")
        if len(document) > MAX_PAGES:
            raise LocalParseError("PDF page count exceeds local limit")
        for number, page in enumerate(document, 1):
            blocks = []
            for item in page.get_text("blocks", sort=True):
                if len(item) >= 7 and item[6] == 0 and item[4].strip():
                    x0, y0, x1, y1 = item[:4]
                    blocks.append(_block("text", item[4], bbox={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0, "unit": "point"}))
            if not blocks:
                if shutil.which("tesseract"):
                    try:
                        from PIL import Image
                        scale = min(2.0, (MAX_PIXELS / max(1, page.rect.width * page.rect.height)) ** 0.5)
                        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
                        text = _ocr_image(Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples))
                        if text:
                            blocks.append(_block("text", text, metadata={"source": "tesseract-page-raster"}))
                    except ImportError:
                        warnings.append(f"PDF page {number} has no native text; scanned OCR requires Pillow")
                else:
                    warnings.append(f"PDF page {number} has no native text; scanned OCR requires Pillow and tesseract")
            for image_info in page.get_images(full=True)[:100]:
                if image_info[2] * image_info[3] > MAX_PIXELS:
                    warnings.append(f"An embedded image on PDF page {number} exceeded the pixel limit")
                    continue
                try:
                    image = document.extract_image(image_info[0])
                    image_bytes = image.get("image", b"")
                    if image_bytes and len(image_bytes) <= MAX_IMAGE_BYTES:
                        blocks.append(_block("image", "", imageBase64=base64.b64encode(image_bytes).decode("ascii"), mimeType="image/" + image.get("ext", "png"), metadata={"source": "embedded-image", "visualInterpretation": False}))
                except (ValueError, RuntimeError):
                    warnings.append(f"An embedded image on PDF page {number} could not be extracted")
            pages.append(_page(blocks, number, width=page.rect.width, height=page.rect.height))
    warnings.append("PDF tables remain reading-order text; native text OCR does not infer table cells or visual chart/diagram meaning")
    return pages


def _parse_local(document: dict[str, Any]) -> dict[str, Any]:
    """Extract a DocumentInput locally. URLs and ambiguous source fields fail."""
    if not isinstance(document, dict) or set(document) - {"name", "mimeType", "text", "dataBase64", "url"}:
        raise LocalParseError("Expected a DocumentInput object")
    if any(not isinstance(value, str) for value in document.values()):
        raise LocalParseError("DocumentInput fields must be strings")
    if sum(key in document for key in ("text", "dataBase64", "url")) != 1:
        raise LocalParseError("Exactly one text or dataBase64 source is required")
    if "url" in document:
        raise LocalParseError("Local parsing never fetches remote URLs; supply text or dataBase64")
    if "text" in document:
        data = document["text"].encode("utf-8")
    else:
        try:
            data = base64.b64decode(document["dataBase64"], validate=True)
        except (binascii.Error, ValueError) as exc:
            raise LocalParseError("Invalid base64 document") from exc
    if len(data) > MAX_INPUT:
        raise LocalParseError("Input exceeds local 32 MiB limit")
    mime = document.get("mimeType") or mimetypes.guess_type(document.get("name", ""))[0] or ("text/plain" if "text" in document else "application/octet-stream")
    mime = mime.split(";", 1)[0].strip().lower()
    warnings: list[str] = ["Local extraction does not interpret charts, diagrams, equations, or image meaning; embedded images and HTML alt text are source artifacts"]
    office = {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": _docx,
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": _pptx,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _xlsx,
        "application/vnd.oasis.opendocument.text": _odt,
    }
    if mime in office:
        package = _Package(data)
        try:
            pages = office[mime](package)
        finally:
            package.close()
        warnings.append("Office layout is extracted without rendering; only PPTX slide order has known page numbers. Spreadsheet values are cached and formulas are not evaluated")
    elif mime == "application/pdf":
        pages = _pdf(data, warnings)
    elif mime.startswith("image/"):
        pages = _image(data, mime)
        warnings.append("Tesseract uses installed English language data; image table cells, layout, and confidence are not reconstructed")
    else:
        try:
            value = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise LocalParseError("Text extraction requires UTF-8 input") from exc
        if mime == "text/html":
            parser = _HTML()
            parser.feed(value)
            parser.close()
            parser.flush()
            pages = [_page(parser.blocks)]
        elif mime in {"text/csv", "application/csv", "text/tab-separated-values"}:
            csv.field_size_limit(MAX_TEXT)
            rows = []
            cells = 0
            for row in csv.reader(io.StringIO(value), delimiter="\t" if mime == "text/tab-separated-values" else ","):
                cells += len(row)
                if len(rows) >= 100_000 or cells > 200_000:
                    raise LocalParseError("CSV row/cell count exceeds local limit")
                rows.append(row)
            pages = [_page([_table(rows)])]
        elif mime in {"application/json", "text/json"}:
            parsed = json.loads(value)
            pages = [_page([_block("code", json.dumps(parsed, ensure_ascii=False, indent=2), metadata={"language": "json"})])]
        elif mime in {"application/xml", "text/xml"}:
            root = _xml(data)
            pages = [_page([_block("text", " ".join(part.strip() for part in root.itertext() if part.strip()))])]
        elif mime in {"text/plain", "text/markdown", "text/x-markdown", "text/x-rst"}:
            pages = [_page([_block("text", value)])]
        else:
            raise LocalParseError(f"Unsupported local MIME type: {mime}")
    if not pages:
        pages = [_page([])]
    if len(pages) > MAX_PAGES or sum(len(page["text"]) for page in pages) > MAX_TEXT:
        raise LocalParseError("Extracted document exceeds local page/text limit")
    output = {"pages": pages, "model": "local-extraction-v1", "warnings": list(dict.fromkeys(warnings))}
    if len(json.dumps(output, ensure_ascii=False).encode("utf-8")) > MAX_OUTPUT:
        raise LocalParseError("Extracted document exceeds local output limit")
    return output


def parse_local(document: dict[str, Any]) -> dict[str, Any]:
    """Extract a bounded document, with an independent per-call output budget."""
    token = _BUDGET.set({"bytes": 0, "blocks": 0})
    try:
        return _parse_local(document)
    finally:
        _BUDGET.reset(token)


def _resource_limits() -> None:
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_OUTPUT, MAX_OUTPUT))
        if sys.platform.startswith("linux"):
            resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024, 1024 * 1024 * 1024))
    except (ImportError, ValueError, OSError):
        pass


def main() -> int:
    _resource_limits()
    try:
        data = sys.stdin.buffer.read(MAX_STDIN + 1)
        if len(data) > MAX_STDIN:
            raise LocalParseError("JSON input exceeds local limit")
        output = parse_local(json.loads(data))
        sys.stdout.write(json.dumps(output, ensure_ascii=False, allow_nan=False) + "\n")
        return 0
    except Exception as exc:
        # Do not echo document contents, base64, filesystem paths, or stack traces.
        message = str(exc) if isinstance(exc, LocalParseError) else "Local document parsing failed"
        sys.stderr.write(json.dumps({"error": {"code": "LOCAL_PARSE_ERROR", "message": message}}) + "\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
