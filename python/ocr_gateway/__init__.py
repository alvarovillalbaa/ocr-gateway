"""OCR Gateway HTTP clients. Provider credentials stay on your trusted server."""

from .client import (
    AsyncOCRGateway,
    GatewayError,
    OCRGateway,
    PARSE_TOOL,
    ParseOptions,
    document_from_file,
    utf16_slice,
)
from .types import (
    Block, BoundingBox, Chunk, Citation, DocumentInput, Page, ParsedDocument,
    ParseRequest, ParseResult, ProviderBlock, ProviderOutput, ProviderPage,
)

__all__ = [
    "OCRGateway", "AsyncOCRGateway", "GatewayError", "PARSE_TOOL", "ParseOptions",
    "document_from_file", "utf16_slice", "DocumentInput", "ParseRequest", "ParseResult",
    "ParsedDocument", "ProviderOutput", "ProviderPage", "ProviderBlock",
    "Block", "Page", "Citation", "Chunk", "BoundingBox",
]
