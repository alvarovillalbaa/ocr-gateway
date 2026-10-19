# Architecture

OCR Gateway normalizes document parsing into pages, typed blocks, citations, visual descriptions, and embedding-ready chunks. TypeScript owns the in-process gateway and authenticated HTTP service. Python offers synchronous/asynchronous HTTP clients and optional local parsing, available to the Node gateway through a bounded subprocess. React uses the browser-safe HTTP client.

Input is exactly one of text, HTTPS URL, or base64 bytes, with a name and MIME type. Remote URLs are passed to upstream providers; the gateway never fetches arbitrary URLs itself. Local parsers only accept bytes/text. Format capability filtering happens before routing.

Auto routing tries a custom decision/rule, Jev, OpenAI Decisions, then deterministic capability scoring. Decisions receive document metadata and requested features, not document contents or keys. All selections are validated against configured, enabled candidates. Parallel results are retained as separate provider documents, with a primary document chosen by configured order; contradictory OCR is never silently merged.

Citations identify extraction provenance and exact text offsets in normalized page/block text. Page numbers and bounding boxes are present only when supplied by the provider or a local parser. Model-generated descriptions are marked inferred; citations are location anchors, not independently verified factual claims. Chunk offsets refer to each provider document's joined text and retain overlapping block/citation IDs.

The self-hosted server hashes scoped gateway API keys and supports revocation, rate limits, body limits, request deadlines, optional request BYOK, and explicit CORS. A gateway key grants access to a deployment; upstream accounts and credits remain necessary. The built-in file key store and rate limits target one server process.

Provider-specific options are allowlisted by adapter. They cannot replace endpoint/authentication/source. Custom adapters are trusted server configuration, never HTTP-supplied code.
