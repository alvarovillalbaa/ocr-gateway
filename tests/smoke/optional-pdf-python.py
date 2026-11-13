"""T2 installed optional-PDF consumer; independently authored PDF syntax."""
import base64
import importlib.metadata
import json
import os
from pathlib import Path
import sys


LINES = (("Harbor ledger", "First page owns these words."),
         ("Quarry register", "Second page keeps a separate anchor."))


def pdf(pages):
    """Minimal authored PDF/xref writer; no parser or product encoder."""
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in pages:
        number = len(objects) + 1
        kids.append(f"{number} 0 R")
        objects.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Resources << /Font << /F1 3 0 R >> >> /Contents {number + 1} 0 R >>").encode())
        stream = b"\n".join((f"BT /F1 12 Tf 1 0 0 1 36 {350 - index * 40} Tm ({line}) Tj ET").encode("ascii") for index, line in enumerate(lines)) + b"\n"
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"endstream")
    objects[1] = (f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>").encode()
    data = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend((f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode())
    return bytes(data)


action = sys.argv[1]
directory = Path(os.environ["PDF_FIXTURES"])
if action == "create-fixtures":
    for name, body in {"two-pages.pdf": pdf(LINES), "blank.pdf": pdf([()]),
                       "invalid.pdf": b"%PDF-1.7\nAUTHORED_PRIVATE_FAILURE_MARKER\nnot a document"}.items():
        with (directory / name).open("xb") as handle:
            handle.write(body)
    print(json.dumps({"authoredFixturesCreated": 3, "generator": "independent minimal PDF syntax; no PDF/product library"}))
    raise SystemExit(0)

import ocr_gateway
import pymupdf
from ocr_gateway.local import parse_local

origin = Path(ocr_gateway.__file__).resolve()
assert origin.is_relative_to(Path(sys.prefix).resolve()) and "site-packages" in origin.parts
assert importlib.metadata.version("ocr-gateway-client") == "0.2.0"
assert importlib.metadata.version("PyMuPDF") == "1.26.6"
assert Path(pymupdf.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())


def parse(name):
    return parse_local({"name": name, "mimeType": "application/pdf", "dataBase64": base64.b64encode((directory / name).read_bytes()).decode()})


if action == "P01":
    result = parse("two-pages.pdf")
    assert len(result["pages"]) == 2
    observations = []
    for index, page in enumerate(result["pages"]):
        assert page["pageNumber"] == index + 1 and page["width"] == 300 and page["height"] == 400
        blocks = page["blocks"]
        assert [b["text"] for b in blocks] == list(LINES[index])
        assert page["text"] == "\n\n".join(LINES[index])
        for block in blocks:
            box = block["bbox"]
            assert block["kind"] == "text" and "confidence" not in block
            assert box["unit"] == "point" and abs(box["x"] - 36) < .01
            assert 0 <= box["y"] < 400 and 0 < box["width"] <= 264 and 0 < box["height"] < 40
            assert box["x"] + box["width"] <= 300 and box["y"] + box["height"] <= 400
        assert blocks[0]["bbox"]["y"] < blocks[1]["bbox"]["y"]
        observations.append({"pageNumber": page["pageNumber"], "text": page["text"], "blocks": blocks})
    print(json.dumps({"identity": "P01", "passed": True, "installedVersion": "0.2.0", "optionalVersion": "1.26.6", "pages": observations}))
elif action == "P03":
    import shutil
    assert shutil.which("tesseract") is None
    result = parse("blank.pdf")
    assert len(result["pages"]) == 1
    page = result["pages"][0]
    assert page["pageNumber"] == 1 and page["width"] == 300 and page["height"] == 400
    assert page["text"] == "" and page["blocks"] == []
    assert "PDF page 1 has no native text; scanned OCR requires Pillow and tesseract" in result["warnings"]
    print(json.dumps({"identity": "P03", "passed": True, "page": page, "warnings": result["warnings"], "positiveScannedOcrClaim": False}))
else:
    raise ValueError("Unknown authored PDF identity")
