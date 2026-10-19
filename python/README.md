# OCR Gateway Python

Python 3.11+ SDK for a self-hosted [OCR Gateway](https://github.com/alvarovillalbaa/ocr-gateway), with synchronous and asynchronous HTTP clients, tool execution, and optional local document extraction. The distribution is `ocr-gateway-client`; the import is `ocr_gateway`.

```sh
pip install ./python
# Optional PDF/native image support (Tesseract is a separate system executable):
pip install './python[local]'
```

After registry publication the equivalent install is `pip install ocr-gateway-client`. Registry publication is separate from creating the GitHub repository.

```python
from ocr_gateway import OCRGateway, utf16_slice

# Defaults: OCR_GATEWAY_URL or http://localhost:8787;
# OCR_GATEWAY_API_KEY supplies the deployment's scoped gateway key.
client = OCRGateway("https://ocr.example.com", api_key="your-gateway-key")
result = client.parse_file(
    "report.pdf",
    mode="auto",
    exclude_providers=["openai"],
    chunking={"maxCharacters": 1600, "overlap": 160},
    timeout_ms=60_000,
)
print(result["primary"]["text"])
for citation in result["primary"]["citations"]:
    assert utf16_slice(result["primary"]["text"], citation["start"], citation["end"]) == citation["quote"]
```

The gateway owns upstream routing and extraction; this HTTP client does not call providers directly. Provider account access and usage charges are separate. BYOK is available in trusted Python application code using `provider_keys={"mistral": "..."}`. Avoid storing provider keys in tool arguments or browser code.

```python
import asyncio
from ocr_gateway import AsyncOCRGateway

async def main():
    client = AsyncOCRGateway(timeout=90)
    result = await client.parse(
        {"text": "Synthetic quarterly report", "mime_type": "text/plain"},
        providers=["local"],
        mode="single",
        provider_options={"local": {}},
    )
    print(result["primary"]["chunks"])

asyncio.run(main())
```

Only structural request fields accept Python aliases (`mime_type`, `data_base64`, `exclude_providers`, `max_providers`, `timeout_ms`, `provider_keys`, `provider_options`, `include_raw`, and chunking `max_characters`). Camel-case wire fields also work. Provider IDs, provider option maps, and arbitrary nested provider options are preserved exactly. Results use the shared camel-case wire contract and typed dictionaries. Citation, block, and chunk offsets count JavaScript UTF-16 code units across the complete normalized provider document text. Python string slicing uses Unicode code points; use `utf16_slice` or the citation's supplied `quote` for non-BMP characters such as emoji. Citations identify extracted source locations; they do not independently verify factual claims.

For an agent tool, supply `client.tool` to your model and execute its returned function arguments:

```python
tool_schema = client.tool  # Flat OpenAI Responses function definition
result = client.execute_tool(
    {"url": "https://example.com/report.pdf", "name": "report.pdf"},
    defaults={"providers": ["mistral"], "mode": "single", "timeout_ms": 60_000},
)
# AsyncOCRGateway provides await client.execute_tool(arguments) as well.
```

`PARSE_TOOL` is also exported. Tool arguments contain only an HTTPS `url`, optional `name`, and optional `mimeType`. Routing, providers, credentials, and budget remain trusted application defaults passed through `defaults`; model arguments cannot replace them. For Chat Completions, adapt the flat definition with `{"type": "function", "function": {key: value for key, value in client.tool.items() if key != "type"}}`. The local parser does not fetch URLs, so this URL tool needs a configured URL-capable provider. Regular client calls also accept text/base64 documents.

`GatewayError` exposes `code` and optional HTTP `status`. The default transport deadline is 305 seconds, covering the gateway's maximum 300-second request plus transport overhead; `timeout_ms` sets a tighter request/client deadline and constructor `timeout` can set another cap. Caller deadlines include DNS and body transfer; late system operations may finish in bounded daemon workers (maximum 16 simultaneous transport workers per Python process). Async cancellation stops the awaiting task; its transport worker finishes under the configured deadline. Connections do not follow redirects. HTTPS is required except for loopback development addresses. Local file uploads are capped at 20 MiB by default, matching the gateway's decoded document limit. Request and response sizes are also bounded; the server can impose stricter limits.

## Optional local extraction

The Node gateway opts in with `createLocalProvider()` or CLI `serve --local`. Install this Python package into the Python interpreter selected by the gateway (`OCR_GATEWAY_PYTHON` for the CLI). The adapter invokes `python3 -m ocr_gateway.local`; no local parser fetches URLs.

Dependency-free formats: UTF-8 plain text, Markdown, HTML, CSV/TSV, JSON, XML, DOCX, PPTX, XLSX, and ODT. ZIP formats are extracted without office rendering. DOCX/PPTX/HTML/CSV/XLSX/ODT expose table blocks where structural tables are present. DOCX/PPTX and PDF expose bounded embedded image artifacts where available; HTML exposes supplied alt text. Only PDF pages, PPTX slide order, and multiframe image frames have known page numbers. Worksheets and flowing text deliberately omit page numbers. Spreadsheet extraction uses cached cell values, preserves sparse-cell references, and does not execute formulas. ODT repeated cell declarations are not expanded.

PDF extraction requires optional PyMuPDF. Scanned PDF pages and image OCR require Pillow and the separately installed `tesseract` executable with English language data. Native PDF text retains supplied point-coordinate text bounding boxes; raster OCR returns text without fabricated boxes or confidence. PDF table cells are not reconstructed. The parser does not interpret image meaning, charts, diagrams, or equations and reports these limits in warnings. Provider-specific capabilities remain the route for visual understanding.

Run a synthetic local example without a gateway or paid call:

```sh
PYTHONPATH=python python3 -m ocr_gateway.local <<'JSON'
{"name":"example.html","mimeType":"text/html","text":"<h1>Example</h1><table><tr><td>Revenue</td><td>42</td></tr></table>"}
JSON
```

The local CLI reads a single JSON `DocumentInput` from stdin and writes one `ProviderOutput` JSON object to stdout. Errors go to stderr as JSON and return a nonzero status. Limits include 32 MiB decoded input, 46 MiB stdin, 16 MiB output, 4 MiB extracted text, 500 pages/slides/frames, 3,000 ZIP entries, 16 MiB per expanded ZIP entry, 128 MiB total expanded ZIP, 200,000 XML elements per entry, and 40 million pixels per image. Output accumulation is bounded while blocks are created. The CLI sets available CPU/file limits and Linux address-space limits; the Node adapter adds cancellation, a five-minute maximum subprocess deadline, and kills the process group. In-process `parse_local` callers should supply their own process isolation for untrusted files.

Build a wheel from this directory with `python -m pip wheel --no-deps .`. The SDK has no runtime HTTP dependencies. Local extraction extras are optional and are never installed automatically.

For a complete synthetic HTTP example, run `npm run build` at the repository root, followed by `PYTHONPATH=python python3 python/examples/local_client.py`. It starts and stops an isolated authenticated loopback gateway, parses synthetic HTML/text through the real local adapter using synchronous, asynchronous, and file calls, and checks Unicode citation slicing. A clearly labeled synthetic URL adapter demonstrates tool dispatch and provider-option preservation without fetching the URL or invoking a hosted provider. The example generates an ephemeral key in memory and does not print or persist it.
