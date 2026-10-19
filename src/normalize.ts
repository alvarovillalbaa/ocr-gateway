import { createHash } from 'node:crypto';
import type { Block, BoundingBox, Chunk, Citation, Page, ParseRequest, ParsedDocument, ProviderBlock, ProviderOutput, ProviderPage } from './types.js';
import { GatewayError } from './validation.js';

function normalizationError(message: string): GatewayError {
  return new GatewayError('invalid_provider_output', message, 502);
}

function hash(value: string): string {
  return createHash('sha256').update(value).digest('hex').slice(0, 24);
}

function validBox(value: BoundingBox | undefined): BoundingBox | undefined {
  if (!value || !['pixel', 'normalized', 'point'].includes(value.unit) ||
      ![value.x, value.y, value.width, value.height].every(Number.isFinite) ||
      value.x < 0 || value.y < 0 || value.width < 0 || value.height < 0) return undefined;
  if (value.unit === 'normalized' && (value.x + value.width > 1 || value.y + value.height > 1)) return undefined;
  return { ...value };
}

function positive(value: number | undefined): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : undefined;
}

function cleanBlock(block: ProviderBlock): ProviderBlock {
  if (!block || typeof block.text !== 'string' || !['text', 'heading', 'table', 'image', 'chart', 'diagram', 'equation', 'code', 'list', 'unknown'].includes(block.kind)) {
    throw normalizationError('Provider blocks require a known kind and text');
  }
  const confidence = typeof block.confidence === 'number' && Number.isFinite(block.confidence) && block.confidence >= 0 && block.confidence <= 1 ? block.confidence : undefined;
  return {
    kind: block.kind, text: block.text,
    ...(validBox(block.bbox) ? { bbox: validBox(block.bbox) } : {}),
    ...(confidence !== undefined ? { confidence } : {}),
    ...(block.inferred !== undefined ? { inferred: block.inferred === true } : {}),
    ...(typeof block.imageBase64 === 'string' ? { imageBase64: block.imageBase64 } : {}),
    ...(typeof block.mimeType === 'string' ? { mimeType: block.mimeType } : {}),
    ...(block.metadata && typeof block.metadata === 'object' ? { metadata: { ...block.metadata } } : {}),
  };
}

interface CanonicalPage { text: string; blocks: { block: ProviderBlock; start: number; end: number }[] }

function canonicalPage(page: ProviderPage, warnings: string[], index: number): CanonicalPage {
  if (!page || typeof page.text !== 'string' || (page.blocks !== undefined && !Array.isArray(page.blocks))) {
    throw normalizationError('Provider pages require text and an optional block array');
  }
  const blocks = page.blocks?.length ? page.blocks.map(cleanBlock) : [{ kind: 'text' as const, text: page.text }];
  let cursor = 0;
  const located = blocks.map(block => {
    const start = page.text.indexOf(block.text, cursor);
    if (start !== -1) cursor = start + block.text.length;
    return { block, start, end: start + block.text.length };
  });
  if (located.every(block => block.start !== -1)) {
    const complete: CanonicalPage['blocks'] = [];
    let cursor = 0;
    for (const item of located) {
      if (item.start > cursor) complete.push({ block: { kind: 'text', text: page.text.slice(cursor, item.start) }, start: cursor, end: item.start });
      complete.push(item);
      cursor = item.end;
    }
    if (cursor < page.text.length) complete.push({ block: { kind: 'text', text: page.text.slice(cursor) }, start: cursor, end: page.text.length });
    return { text: page.text, blocks: complete };
  }

  const compressed = (value: string) => value.replace(/\s+/g, '');
  const blockText = blocks.map(block => block.text).join('\n\n');
  if (page.text && !compressed(blockText).includes(compressed(page.text))) {
    // Some providers return full OCR text plus supplemental visual descriptions.
    blocks.unshift({ kind: 'text', text: page.text });
    warnings.push(`Page at index ${index}: retained provider page text alongside blocks with different reading text`);
  } else {
    warnings.push(`Page at index ${index}: normalized text follows provider block reading order`);
  }
  cursor = 0;
  const canonical = blocks.map(block => {
    const start = cursor;
    cursor += block.text.length + 2;
    return { block, start, end: start + block.text.length };
  });
  return { text: blocks.map(block => block.text).join('\n\n'), blocks: canonical };
}

function chunks(text: string, pages: Page[], options: ParseRequest['chunking'], documentId: string): Chunk[] {
  if (options === false) return [];
  const max = options?.maxCharacters ?? 1600;
  const overlap = options?.overlap ?? Math.min(160, Math.floor(max / 10));
  if (!Number.isSafeInteger(max) || max < 1 || !Number.isSafeInteger(overlap) || overlap < 0 || overlap >= max) {
    throw new GatewayError('invalid_chunking', 'Chunk maxCharacters must be a positive integer and overlap must be between zero and maxCharacters - 1');
  }
  const result: Chunk[] = [];
  const spans = pages.flatMap(page => page.blocks.map(block => ({ block, pageNumber: page.pageNumber })));
  let start = 0;
  let first = 0;
  let totalCharacters = 0;
  while (start < text.length) {
    const end = Math.min(text.length, start + max);
    if (result.length >= 10_000 || totalCharacters + end - start > 16_000_000) {
      throw new GatewayError('chunk_limit_exceeded', 'Chunk output exceeds 10000 chunks or 16000000 characters; reduce overlap, increase chunk size, or disable chunking', 413);
    }
    totalCharacters += end - start;
    while (first < spans.length && (spans[first]!.block.end < start ||
      (spans[first]!.block.end === start && spans[first]!.block.start !== start))) first++;
    const touched: typeof spans = [];
    for (let index = first; index < spans.length; index++) {
      const item = spans[index]!;
      if (item.block.start >= end && !(end === text.length && item.block.start === end)) break;
      if (item.block.start >= start || item.block.end > start) touched.push(item);
    }
    result.push({
      id: `${documentId}:chunk:${result.length + 1}`,
      text: text.slice(start, end), start, end,
      blockIds: touched.map(({ block }) => block.id),
      citationIds: touched.map(({ block }) => block.citationId),
      pageNumbers: [...new Set(touched.flatMap(({ pageNumber }) => pageNumber === undefined ? [] : [pageNumber]))],
    });
    if (end === text.length) break;
    start = end - overlap;
  }
  return result;
}

export function normalizeDocument(provider: string, output: ProviderOutput, request: ParseRequest): ParsedDocument {
  if (!output || !Array.isArray(output.pages)) throw normalizationError('Provider output requires pages');
  const warnings = [...(output.warnings ?? [])];
  const canonical = output.pages.map((page, index) => canonicalPage(page, warnings, index));
  const id = `doc_${hash(JSON.stringify({ provider, model: output.model, pages: canonical.map((page, index) => ({
    pageNumber: output.pages[index]!.pageNumber, text: page.text, blocks: page.blocks.map(item => item.block),
  })) }))}`;
  const citations: Citation[] = [];
  let offset = 0;
  const pages = canonical.map((page, pageIndex): Page => {
    const original = output.pages[pageIndex]!;
    const pageNumber = Number.isSafeInteger(original.pageNumber) && original.pageNumber! > 0 ? original.pageNumber : undefined;
    const blocks = page.blocks.map((item, blockIndex): Block => {
      const blockId = `${id}:block:${pageIndex + 1}:${blockIndex + 1}`;
      const citationId = `${id}:citation:${pageIndex + 1}:${blockIndex + 1}`;
      const start = offset + item.start;
      const end = offset + item.end;
      citations.push({
        id: citationId, provider, blockId, start, end, quote: item.block.text,
        inferred: item.block.inferred === true,
        ...(pageNumber !== undefined ? { pageNumber } : {}),
        ...(item.block.bbox ? { bbox: item.block.bbox } : {}),
      });
      return { ...item.block, id: blockId, citationId, start, end };
    });
    offset += page.text.length + 2;
    return {
      text: page.text, blocks,
      ...(pageNumber !== undefined ? { pageNumber } : {}),
      ...(positive(original.width) !== undefined ? { width: original.width } : {}),
      ...(positive(original.height) !== undefined ? { height: original.height } : {}),
    };
  });
  const text = canonical.map(page => page.text).join('\n\n');
  return {
    id, provider, text, pages, citations, chunks: chunks(text, pages, request.chunking, id), warnings,
    ...(output.model !== undefined ? { model: output.model } : {}),
    ...(output.usage !== undefined ? { usage: output.usage } : {}),
    ...(request.includeRaw && output.raw !== undefined ? { raw: output.raw } : {}),
  };
}
