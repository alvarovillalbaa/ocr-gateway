// T2 integration: unchanged installed Node SDK/CLI -> actual local raster OCR.
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createOCRGateway} from '@alvarovillalbaa/ocr-gateway/core';
import {createLocalProvider} from '@alvarovillalbaa/ocr-gateway/local';

const installed = process.env.RASTER_NODE_PACKAGE;
assert.equal(fileURLToPath(import.meta.resolve('@alvarovillalbaa/ocr-gateway/core')), path.join(installed, 'dist/core.js'));
assert.equal(JSON.parse(await readFile(path.join(installed, 'package.json'), 'utf8')).version, '0.2.0');
const protocol = JSON.parse(await readFile(process.env.RASTER_PROTOCOL, 'utf8'));
const expected = protocol.fixtures;
const action = process.argv[2];
let result;
if (action === 'R02') {
  const bytes = await readFile(path.join(process.env.RASTER_FIXTURES, 'authored.png'));
  const gateway = createOCRGateway({providers: [createLocalProvider({python: process.env.OCR_GATEWAY_PYTHON})], enabledProviders: ['local']});
  result = await gateway.parse({document: {name: 'authored.png', mimeType: 'image/png', dataBase64: bytes.toString('base64')}, providers: ['local'], mode: 'single'});
} else if (action === 'R03') result = JSON.parse(await readFile(process.env.RASTER_CLI_RESULT, 'utf8'));
else throw new Error('Unknown authored raster identity');
assert.deepEqual(result.errors, []);
const doc = result.primary;
assert.equal(doc.provider, 'local');
assert.deepEqual(doc.text.split(/\s+/).filter(Boolean), expected.first_lines.join(' ').split(/\s+/));
assert.equal(doc.pages.length, 1);
const page = doc.pages[0];
assert.equal(page.width, action === 'R02' ? expected.width : expected.pdf_page_points[0]);
assert.equal(page.height, action === 'R02' ? expected.height : expected.pdf_page_points[1]);
assert.equal(page.pageNumber, action === 'R02' ? undefined : 1);
const texts = page.blocks.filter(b => b.kind === 'text' && b.text.trim());
assert.equal(texts.length, 1);
assert.equal(texts[0].text, doc.text);
if (action === 'R03') {
  assert.equal(texts[0].metadata.source, 'tesseract-page-raster');
  assert.equal(doc.warnings.some(w => w.includes('scanned OCR requires')), false);
}
const images = page.blocks.filter(b => b.kind === 'image');
assert.equal(images.length, 1);
assert.equal(images[0].metadata.source, action === 'R02' ? 'input-image' : 'embedded-image');
assert.equal(images[0].metadata.visualInterpretation, false);
assert.equal(images[0].mimeType, 'image/png');
assert.ok(Buffer.from(images[0].imageBase64, 'base64').length > 0);
if (action === 'R02') assert.deepEqual(Buffer.from(images[0].imageBase64, 'base64'), await readFile(path.join(process.env.RASTER_FIXTURES, 'authored.png')));
for (const block of page.blocks) {
  assert.equal(block.bbox, undefined);
  assert.equal(block.confidence, undefined);
}
assert.equal(doc.citations.length, page.blocks.length);
for (const citation of doc.citations) {
  assert.equal(doc.text.slice(citation.start, citation.end), citation.quote);
  assert.equal(citation.quote, page.blocks.find(b => b.id === citation.blockId).text);
  assert.equal(citation.pageNumber, page.pageNumber);
  assert.equal(citation.bbox, undefined);
}
assert.ok(doc.chunks.length > 0);
for (const chunk of doc.chunks) {
  assert.equal(doc.text.slice(chunk.start, chunk.end), chunk.text);
  assert.ok(chunk.citationIds.length > 0);
  assert.ok(chunk.citationIds.every(id => doc.citations.some(c => c.id === id)));
}
console.log(JSON.stringify({identity: action, passed: true, result, inputImageSha256: action === 'R02' ? createHash('sha256').update(await readFile(path.join(process.env.RASTER_FIXTURES, 'authored.png'))).digest('hex') : undefined}));
