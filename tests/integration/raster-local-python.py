"""T2 integration: installed wheel -> real Pillow/Tesseract -> authored TIFF."""
import base64
import importlib.metadata
import json
import os
from pathlib import Path
import sys

import ocr_gateway
from ocr_gateway.local import parse_local

assert importlib.metadata.version("ocr-gateway-client") == "0.2.0"
assert importlib.metadata.version("Pillow") == "13.0.0"
assert importlib.metadata.version("PyMuPDF") == "1.26.6"
assert Path(ocr_gateway.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
fixtures = Path(os.environ["RASTER_FIXTURES"])
protocol = json.loads(Path(os.environ["RASTER_PROTOCOL"]).read_bytes())
expected = protocol["fixtures"]
raw = (fixtures / "authored.tiff").read_bytes()
result = parse_local({"name": "authored.tiff", "mimeType": "image/tiff", "dataBase64": base64.b64encode(raw).decode()})
assert len(result["pages"]) == 2
for index, lines in enumerate((expected["first_lines"], expected["second_lines"])):
    page = result["pages"][index]
    assert page["pageNumber"] == index + 1 and page["width"] == expected["width"] and page["height"] == expected["height"]
    assert page["text"].split() == " ".join(lines).split()
    assert len(page["blocks"]) == 1 and page["blocks"][0]["kind"] == "text"
    assert page["blocks"][0]["text"] == page["text"]
    assert "bbox" not in page["blocks"][0] and "confidence" not in page["blocks"][0]
assert "Tesseract uses installed English language data; image table cells, layout, and confidence are not reconstructed" in result["warnings"]
print(json.dumps({"identity": "R01", "passed": True, "result": result}, ensure_ascii=False))
