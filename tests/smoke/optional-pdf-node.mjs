// T2: unchanged released Node adapter invokes the installed optional Python PDF parser.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createOCRGateway} from '@alvarovillalbaa/ocr-gateway/core';
import {createLocalProvider} from '@alvarovillalbaa/ocr-gateway/local';

const installed = process.env.PDF_NODE_PACKAGE;
assert.equal(fileURLToPath(import.meta.resolve('@alvarovillalbaa/ocr-gateway/core')), path.join(installed, 'dist/core.js'));
assert.equal(JSON.parse(await readFile(path.join(installed, 'package.json'), 'utf8')).version, '0.2.0');
const bytes = await readFile(path.join(process.env.PDF_FIXTURES, 'two-pages.pdf'));
const gateway = createOCRGateway({providers: [createLocalProvider({python: process.env.OCR_GATEWAY_PYTHON})], enabledProviders: ['local']});
const result = await gateway.parse({document: {name: 'two-pages.pdf', mimeType: 'application/pdf', dataBase64: bytes.toString('base64')}, providers: ['local'], mode: 'single'});
assert.deepEqual(result.errors, []);
const doc = result.primary;
assert.equal(doc.provider, 'local');
assert.deepEqual(doc.pages.map(p => p.pageNumber), [1, 2]);
const expected = ['Harbor ledger', 'First page owns these words.', 'Quarry register', 'Second page keeps a separate anchor.'];
const blocks = doc.pages.flatMap(p => p.blocks);
assert.deepEqual(blocks.map(b => b.text), expected);
assert.equal(doc.text, expected.join('\n\n'));
assert.equal(doc.citations.length, 4);
for (const citation of doc.citations) {
  assert.equal(doc.text.slice(citation.start, citation.end), citation.quote);
  const page = doc.pages.find(p => p.blocks.some(b => b.id === citation.blockId));
  const block = page?.blocks.find(b => b.id === citation.blockId);
  assert.ok(block);
  assert.equal(citation.quote, block.text);
  assert.deepEqual(citation.bbox, block.bbox);
  assert.equal(citation.pageNumber, page.pageNumber);
  assert.ok([1, 2].includes(citation.pageNumber));
  assert.equal(citation.bbox.unit, 'point');
}
assert.ok(doc.chunks.length > 0);
for (const chunk of doc.chunks) {
  assert.equal(doc.text.slice(chunk.start, chunk.end), chunk.text);
  assert.ok(chunk.citationIds.length > 0);
  assert.ok(chunk.citationIds.every(id => doc.citations.some(c => c.id === id)));
}
assert.equal(blocks.some(b => 'confidence' in b), false);
console.log(JSON.stringify({identity: 'P02', passed: true, provider: doc.provider, pages: doc.pages, text: doc.text, citations: doc.citations, chunks: doc.chunks}));
