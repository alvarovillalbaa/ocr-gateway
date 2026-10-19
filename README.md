# OCR Gateway

One document parsing interface for TypeScript, Python, React and agent tools. Route PDFs, scans, images and office documents across hosted OCR/vision providers or your own local parsers, with location citations and embedding-ready chunks.

Self-hosted, MIT licensed. Node.js 22+; Python 3.11+. Provider accounts and credits are separate. The gateway does not sell a managed universal provider key.

## Install

Install release artifacts (npm/PyPI registry publication is separate):

```bash
npm install https://github.com/alvarovillalbaa/ocr-gateway/releases/download/v0.1.0/alvarovillalbaa-ocr-gateway-0.1.0.tgz
pip install https://github.com/alvarovillalbaa/ocr-gateway/releases/download/v0.1.0/ocr_gateway_client-0.1.0-py3-none-any.whl
```

Or build from source:

```bash
git clone https://github.com/alvarovillalbaa/ocr-gateway.git
cd ocr-gateway
npm ci
npm run build
python3 -m pip install ./python
```

See [provider capabilities, formats and credentials](PROVIDERS.md). Format support depends on the provider: unsupported combinations fail before dispatch. A custom `ProviderAdapter` can support additional document formats or your own scripts.

## Direct TypeScript calls

Run the core in a trusted Node backend:

```ts
import { readFile } from 'node:fs/promises';
import { createOCRGateway, keysFromEnv } from '@alvarovillalbaa/ocr-gateway/core';

const gateway = createOCRGateway({
  providerKeys: keysFromEnv(),
  enabledProviders: ['mistral', 'openai', 'firecrawl'],
  router: {
    jevApiKey: process.env.TYPESAFE_API_KEY,
    openaiApiKey: process.env.OPENAI_API_KEY,
  },
});
const result = await gateway.parse({
  document: {
    name: 'report.pdf', mimeType: 'application/pdf',
    dataBase64: (await readFile('report.pdf')).toString('base64'),
  },
  mode: 'auto', maxProviders: 2,
  features: ['tables', 'charts', 'diagrams'],
  chunking: { maxCharacters: 1600, overlap: 160 },
});
for (const chunk of result.primary.chunks) {
  console.log(chunk.text, chunk.citationIds);
}
```

Input is exactly one of `text`, `dataBase64`, or an HTTPS `url`. Filename/MIME metadata selects capable providers. Maximum decoded file size is 20 MiB; individual providers can impose smaller limits. Legacy/binary formats need a provider that declares them; there is no promise that every provider parses every format.

## One gateway API key

Set upstream keys on the server using [.env.example](.env.example). Provision keys locally:

```bash
node dist/cli.js key create --name my-app --providers mistral,openai --rpm 60
# Save apiKey from the one-time output in your app's secret manager.
node --env-file=.env dist/cli.js serve
```

Installed package commands are `ocr-gateway key create` and `ocr-gateway serve`. The server binds `127.0.0.1:8787`; keys live in `.ocr-gateway/keys.json`, hashed with SHA-256 in a `0600` file. Use `key list`, `key revoke <id>`, and `--store <path>` to manage them. The `/server` export also exposes `createApiKey`, `listApiKeys`, `revokeApiKey`, and `keyStoreAuthenticator`.

```ts
import { OCRGateway } from '@alvarovillalbaa/ocr-gateway';
const client = new OCRGateway({
  baseUrl: process.env.OCR_GATEWAY_URL ?? 'http://127.0.0.1:8787',
  apiKey: process.env.OCR_GATEWAY_API_KEY,
});
const result = await client.parse({
  document: { url: 'https://example.com/report.pdf' },
  providers: ['mistral'],
});
```

Remote SDK connections require HTTPS. Put a TLS proxy in front of `serve --host 0.0.0.0`. Request BYOK is off by default; opt in with `--allow-request-keys` and send `providerKeys` on the call. A valid gateway key and its provider scope still apply. Provider options cannot replace endpoint/auth/source. Configuring one provider never grants access to another disabled provider.

The built-in key store and in-memory rate limiter target one process. For multiple instances use a shared authenticator and external limits. See [operations and security](SECURITY.md).

## Python and local parsing

```python
from ocr_gateway import OCRGateway, AsyncOCRGateway

client = OCRGateway()  # OCR_GATEWAY_URL and OCR_GATEWAY_API_KEY
result = client.parse_file('report.pdf', providers=['mistral'])
print(result['primary']['text'])

# In an async function:
# result = await AsyncOCRGateway().parse_file('report.pdf', mode='auto')
```

The Python client uses the same gateway and preserves camelCase response fields. Request keyword arguments accept snake_case. Its stdlib `http.client` transport uses bounded worker threads; cancellation stops the awaiting coroutine while the transport finishes under its configured deadline.

Local extraction is available from Python directly or as a Node adapter:

```ts
import { createOCRGateway } from '@alvarovillalbaa/ocr-gateway/core';
import { createLocalProvider } from '@alvarovillalbaa/ocr-gateway/local';
const local = createOCRGateway({ providers: [createLocalProvider()], enabledProviders: ['local'] });
const result = await local.parse({ document: { text: 'A native document.' } });
```

```bash
# After installing the Python package:
node dist/cli.js parse --file report.docx --local --providers local
node dist/cli.js serve --local
```

The Python package includes bounded native extraction for text, HTML, structured text and office XML archives. PDF/image OCR needs optional local libraries/tools. Local extraction does not interpret charts and diagrams; use a vision-capable hosted adapter or your own model for those. See [Python setup](python/README.md).

## Citations, visual content and chunks

Every provider result is a separate `ParsedDocument` with `pages`, typed `blocks`, `citations` and `chunks`. `primary` is the first successful selected result in routing order. Parallel OCR is retained in `results`; the gateway does not silently reconcile conflicting outputs.

- Citation quotes exactly match `document.text.slice(start, end)` on their parsed document. Known page numbers and the original source URL in `result.document.url` let applications link back to the source. Offsets for blocks, citations and chunks are document-global UTF-16 code units, as in JavaScript strings. Python users can use the helper documented in the Python README.
- Page numbers, geometry and confidence appear only when supplied by the parser. A provider that returns one undivided document has no invented page number.
- Tables, charts, diagrams, equations and images are typed blocks where the adapter provides them. Some providers return only Markdown or extracted image placeholders; check the capability table and warnings.
- Visual descriptions generated by language models carry `inferred: true`. A location citation proves where the extraction came from, not the factual accuracy of an inferred description.
- Chunks use bounded character windows with overlap, exact text offsets, block/citation IDs and known page numbers. They are ready for your embedding pipeline; the gateway does not generate embeddings or store vectors. `chunking: false` disables them.

Provider page text is preserved when blocks align. If supplementary blocks use a different reading text, normalization retains their text and the original OCR text with a warning. `includeRaw: true` retains provider output for debugging; treat it as sensitive document data.

## Routing and defaults

| Mode | Behavior |
| --- | --- |
| `auto` | Custom function, matching rule, Jev, OpenAI Decisions, then deterministic capability ranking. May select multiple providers. |
| `single` | First eligible selected provider. |
| `parallel` | Concurrent selected providers; successful results survive partial failures. |
| `fallback` | Selected providers in order, stopping at the first nonempty successful extraction. |

`providers` narrows candidates and sets explicit-mode order; `excludeProviders` removes them. Enabled/configured provider policy, format/features and key scope constrain all modes. `maxProviders` is 1–5 (default 2), including fallback. Auto does not retry alternative providers after its chosen providers fail; select `fallback` for that behavior.

Rules run before model routing. Jev uses TypeSafe `/v1/systemone`; low confidence, invalid answers or failure fall back to OpenAI `/v1/decisions`, then deterministic capability ranking. Decision services receive metadata and desired features, never document contents, filenames, URLs or provider keys. Each model router has a 2.5-second budget within the overall request deadline. Confidence defaults to `0.55`; calibrate for your documents. No live model routing accuracy is claimed.

```ts
const gateway = createOCRGateway({
  providerKeys: keysFromEnv(),
  defaults: { timeoutMs: 120_000, chunking: { maxCharacters: 2400, overlap: 240 } },
  router: {
    rules: [{ mimeTypes: ['application/pdf'], providers: ['mistral'] }],
    // Or fully configure selection, receiving metadata and available candidates:
    // decide: ({ candidates }) => candidates.slice(0, 2).map(p => p.id),
  },
});
```

Defaults shallow-merge with each call; supplied nested objects replace defaults. `PRESETS.fast`, `PRESETS.balanced` and `PRESETS.rich` are exported from `/core`. CLI policy can be set through `--config examples/gateway.json`. Per-provider options retain native option names but are allowlisted. Full transport contract: [API](API.md), [OpenAPI](openapi.json).

## React

Use your authenticated application backend as a same-origin proxy. Keep gateway and upstream keys on that backend.

```tsx
import { useMemo } from 'react';
import { OCRGateway, documentFromFile } from '@alvarovillalbaa/ocr-gateway';
import { useOCRGateway } from '@alvarovillalbaa/ocr-gateway/react';

export function DocumentUpload({ baseUrl }: { baseUrl: string }) {
  const client = useMemo(() => new OCRGateway({ baseUrl }), [baseUrl]);
  const { data, loading, error, parse, cancel } = useOCRGateway(client);
  return <section>
    <input type="file" aria-label="Document" disabled={loading} onChange={async e => {
      const file = e.target.files?.[0];
      if (file) try { await parse({ document: await documentFromFile(file) }); } catch {}
    }} />
    {loading && <p role="status">Parsing… <button onClick={cancel}>Cancel</button></p>}
    {error && <p role="alert">Parsing failed. Please try again.</p>}
    {data && <pre>{data.primary.text || 'No readable content.'}</pre>}
  </section>;
}
```

Pass an absolute proxy base URL suitable for your framework. The hook exposes data/loading/error/parse/cancel, aborts superseded requests and ignores stale results. CORS alone does not authenticate application users. Render document content as text or sanitize Markdown/HTML before rendering.

## Tool calls and MCP

```ts
import { createParseTool } from '@alvarovillalbaa/ocr-gateway';
const tool = createParseTool(client, { providers: ['mistral'], maxProviders: 1 });
// Send {type, name, description, parameters} to a function-calling loop.
const result = await tool.execute({ url: 'https://example.com/report.pdf' });
// Anthropic tools use {name, description, input_schema: parameters}.
```

Python provides the equivalent tool definition/executors. Model arguments only contain document URL/name/MIME; provider policy stays in trusted defaults. Your agent owns the conversation loop. Treat extracted content as untrusted input.

The CLI exposes `parse_document` via MCP stdio:

```json
{
  "mcpServers": {
    "ocr-gateway": {
      "command": "ocr-gateway",
      "args": ["mcp", "--base-url", "http://127.0.0.1:8787"],
      "env": { "OCR_GATEWAY_API_KEY": "your-gateway-key" }
    }
  }
}
```

Install the package first. Omit `--base-url` for direct BYOK using environment variables. MCP supports stdio only. Put real secrets in a secret manager or private MCP configuration.

## Development and proof

```bash
npm ci
npm run check
npm run build
npm run demo
npm pack --cache /tmp/ocr-gateway-npm-cache
python3 -m pip wheel ./python --no-deps --wheel-dir /tmp/ocr-gateway-wheels
git diff --check
```

The demo uses synthetic document data and a local adapter, with no upstream API calls. [Verification evidence](docs/verification.md) records what was checked and what remains unverified. No provider accuracy benchmark, paid live-provider execution, hosted service, or npm/PyPI registry publication is implied by a source/package build.
