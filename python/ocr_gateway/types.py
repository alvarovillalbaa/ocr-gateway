"""Wire types mirror src/types.ts. Optional locations are never fabricated."""

from typing import Any, Literal, NotRequired, TypedDict

Mode = Literal["auto", "single", "parallel", "fallback"]
Feature = Literal["tables", "images", "charts", "diagrams", "equations"]
BlockKind = Literal["text", "heading", "table", "image", "chart", "diagram", "equation", "code", "list", "unknown"]


class DocumentInput(TypedDict, total=False):
    name: str
    mimeType: str
    url: str
    dataBase64: str
    text: str


class ChunkOptions(TypedDict, total=False):
    maxCharacters: int
    overlap: int


class ParseRequest(TypedDict):
    document: DocumentInput
    mode: NotRequired[Mode]
    providers: NotRequired[list[str]]
    excludeProviders: NotRequired[list[str]]
    maxProviders: NotRequired[int]
    timeoutMs: NotRequired[int]
    features: NotRequired[list[Feature]]
    chunking: NotRequired[ChunkOptions | Literal[False]]
    providerKeys: NotRequired[dict[str, str]]
    providerOptions: NotRequired[dict[str, dict[str, Any]]]
    includeRaw: NotRequired[bool]


class BoundingBox(TypedDict):
    x: float
    y: float
    width: float
    height: float
    unit: Literal["pixel", "normalized", "point"]


class ProviderBlock(TypedDict):
    kind: BlockKind
    text: str
    bbox: NotRequired[BoundingBox]
    confidence: NotRequired[float]
    inferred: NotRequired[bool]
    imageBase64: NotRequired[str]
    mimeType: NotRequired[str]
    metadata: NotRequired[dict[str, Any]]


class ProviderPage(TypedDict):
    pageNumber: NotRequired[int]
    text: str
    blocks: NotRequired[list[ProviderBlock]]
    width: NotRequired[float]
    height: NotRequired[float]


class ProviderOutput(TypedDict):
    pages: list[ProviderPage]
    model: NotRequired[str]
    warnings: NotRequired[list[str]]
    usage: NotRequired[dict[str, Any]]
    raw: NotRequired[Any]


class Citation(TypedDict):
    id: str
    provider: str
    pageNumber: NotRequired[int]
    blockId: str
    start: int
    end: int
    quote: str
    bbox: NotRequired[BoundingBox]
    inferred: bool


class Block(ProviderBlock):
    id: str
    start: int
    end: int
    citationId: str


class Page(TypedDict):
    pageNumber: NotRequired[int]
    text: str
    blocks: list[Block]
    width: NotRequired[float]
    height: NotRequired[float]


class Chunk(TypedDict):
    id: str
    text: str
    start: int
    end: int
    blockIds: list[str]
    citationIds: list[str]
    pageNumbers: list[int]


class ParsedDocument(TypedDict):
    id: str
    provider: str
    model: NotRequired[str]
    text: str
    pages: list[Page]
    citations: list[Citation]
    chunks: list[Chunk]
    warnings: list[str]
    usage: NotRequired[dict[str, Any]]
    raw: NotRequired[Any]


class RoutingDecision(TypedDict):
    router: Literal["explicit", "custom", "rule", "jev", "openai-decisions", "heuristic"]
    providers: list[str]
    reason: str
    confidence: NotRequired[float]


class ResultDocument(TypedDict):
    name: NotRequired[str]
    mimeType: str
    url: NotRequired[str]


class ProviderError(TypedDict):
    provider: str
    code: str
    message: str


class ParseResult(TypedDict):
    id: str
    document: ResultDocument
    primary: ParsedDocument
    results: list[ParsedDocument]
    routing: RoutingDecision
    errors: list[ProviderError]
    warnings: list[str]
    durationMs: float
