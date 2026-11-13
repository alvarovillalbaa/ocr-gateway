"""Independently authored raster/PDF fixture writer; never imports product code."""
import hashlib
import json
from pathlib import Path
import sys
import zlib

from PIL import Image, ImageDraw, ImageFont

directory = Path(sys.argv[1])
protocol = json.loads(Path(sys.argv[2]).read_bytes())
spec = protocol["fixtures"]
font = ImageFont.load_default(size=spec["font_size"])
assert isinstance(font, ImageFont.FreeTypeFont)


def render(lines):
    image = Image.new("RGB", (spec["width"], spec["height"]), spec["background"])
    painter = ImageDraw.Draw(image)
    for line, position in zip(lines, spec["line_positions"]):
        painter.text(tuple(position), line, font=font, fill=spec["foreground"])
    return image


def scanned_pdf(image):
    """One image XObject and placement only; no font/text operators or hidden text."""
    width, height = image.size
    points = spec["pdf_page_points"]
    pixels = zlib.compress(image.tobytes(), level=9)
    placement = f"q {points[0]} 0 0 {points[1]} 0 0 cm /Im0 Do Q\n".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {points[0]} {points[1]}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>".encode(),
               f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(pixels)} >>\nstream\n".encode() + pixels + b"\nendstream",
               f"<< /Length {len(placement)} >>\nstream\n".encode() + placement + b"endstream"]
    data = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(data)


first, second = render(spec["first_lines"]), render(spec["second_lines"])
with (directory / "authored.png").open("xb") as handle:
    first.save(handle, format="PNG", dpi=(spec["dpi"], spec["dpi"]))
with (directory / "authored.tiff").open("xb") as handle:
    first.save(handle, format="TIFF", save_all=True, append_images=[second], compression="raw", dpi=(spec["dpi"], spec["dpi"]))
with (directory / "scanned.pdf").open("xb") as handle:
    handle.write(scanned_pdf(first))
with (directory / "invalid.png").open("xb") as handle:
    handle.write(b"AUTHORED_PRIVATE_RASTER_FAILURE_MARKER\nnot an image")
import pymupdf
with pymupdf.open(directory / "scanned.pdf") as document:
    assert len(document) == 1 and document[0].get_text() == "" and document[0].get_fonts() == []
    assert len(document[0].get_images(full=True)) == 1
    pdf_shape = [document[0].rect.width, document[0].rect.height]
rows = {path.name: {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(directory.iterdir())}
assert all(row["bytes"] <= 4 * 1024**2 for row in rows.values())
print(json.dumps({"fixtures": rows, "nativePdfText": "", "pdfFonts": 0, "pdfImages": 1, "pdfPagePoints": pdf_shape,
                  "font": spec["font"], "actualFontName": font.getname(), "fontSize": spec["font_size"],
                  "fontBytesSha256": hashlib.sha256(font.font_bytes).hexdigest(),
                  "expectedLines": [spec["first_lines"], spec["second_lines"]]}))
