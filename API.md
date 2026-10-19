# API

The wire schema is [openapi.json](openapi.json); TypeScript interfaces live in [src/types.ts](src/types.ts). Python request keywords accept snake_case but wire fields and returned records use camelCase. Provider option internals keep native names.

`GET /health` is public. `GET /v1/providers` and `POST /v1/parse` require `Authorization: Bearer <gateway-key>`. Parsing requires `Content-Type: application/json`. The provider list is scoped to the key and exposes enabled/configured status and advertised capabilities.

## Parse request

| Field | Default | Meaning |
| --- | --- | --- |
| `document` | required | Exactly one of `url`, `dataBase64`, `text`; optional `name`, `mimeType`. MIME inferred from known extension or text. |
| `mode` | `auto` | `auto`, `single`, `parallel`, `fallback`. |
| `providers` | all eligible | Candidate IDs; explicit execution order. |
| `excludeProviders` | none | Removed candidate IDs. |
| `features` | `[]` | Required capabilities: tables, images, charts, diagrams, equations. |
| `maxProviders` | `2` | Dispatch cap 1–5, including fallback. |
| `timeoutMs` | `120000` | Overall deadline 100–300000 ms, including routing and polling. |
| `chunking` | size 1600, overlap 160 | `{maxCharacters, overlap}` or `false`; size 100–100000; default overlap `min(160,floor(size/10))`. |
| `providerKeys` | server configured | Per-call credentials; HTTP opt-in only. |
| `providerOptions` | `{}` | Adapter-specific allowlisted native options. |
| `includeRaw` | `false` | Include upstream raw output; potentially sensitive. |

Request bodies reject unknown fields. Unknown provider IDs fail. Each call shallow-merges gateway/client defaults before validation. No provider choices can escape server policy or gateway-key scope.

## Response

`id`, `document`, `primary`, `results`, `routing`, `errors`, `warnings`, `durationMs`.

Each parsed document has `id`, `provider`, optional `model`, joined `text`, `pages`, `citations`, `chunks`, `warnings`, optional `usage`/`raw`. Pages include text and typed blocks; pageNumber/dimensions are optional. Blocks carry exact offsets, a citation ID, content kind and optional geometry/confidence/image payload/metadata. Visual descriptions can be inferred.

Citation and chunk offsets use UTF-16 code units relative to their parsed document's text. Quotes are extraction text. Image-only blocks can use a provider placeholder/description; no invented OCR text or geometry is implied. Page numbers are 1-based where known.

Parallel results are ordered by selected provider order even when completion order differs. Partial failures appear in `errors`; the first successful result becomes `primary`. All-provider failure returns an error instead of an empty successful result.

Extraction is bounded to 500 pages, 20000 blocks and 4000000 combined page/block text characters per provider. Each normalized provider result is limited to 8 MB, and the combined response to 28 MB. Oversized output fails explicitly; split large documents or reduce providers/raw/image output.

Chunking is limited to 10000 chunks and 16000000 aggregate chunk characters per provider document. Excessive overlap fails rather than amplifying memory use without bound.

## Errors

Errors are `{ "error": { "code": "...", "message": "..." } }` with status 400 invalid request, 401 invalid key, 403 origin/scope/BYOK restriction, 404 endpoint, 413 body limit, 415 content type, 429 key rate limit, 499 cancellation, 502 provider/route failure, 503 no provider or concurrency limit, 504 deadline. Sensitive upstream error bodies are omitted. In-process adapters use `GatewayError`; unexpected exceptions are sanitized at the HTTP boundary.
