// T2: installed public package, authored HTML and an owned loopback gateway.
import assert from 'node:assert/strict';
import {readFile, realpath} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {OCRGateway, createParseTool, GatewayError} from '@alvarovillalbaa/ocr-gateway';

const installed = process.env.FRESH_NODE_PACKAGE;
const baseUrl = 'http://127.0.0.1:38473';
assert.ok(installed && path.isAbsolute(installed));
const metadata = JSON.parse(await readFile(path.join(installed, 'package.json'), 'utf8'));
assert.equal(metadata.version, '0.2.0');
function verify(result) {
  assert.equal(result.primary.provider, 'local');
  assert.ok(result.primary.text.includes('Fresh 🚲 delivery'));
  assert.ok(result.primary.text.includes('Café 東京'));
  assert.ok(result.primary.citations.length > 0);
  assert.ok(result.primary.chunks.length > 0);
  for (const citation of result.primary.citations) assert.equal(result.primary.text.slice(citation.start, citation.end), citation.quote);
  for (const chunk of result.primary.chunks) assert.equal(result.primary.text.slice(chunk.start, chunk.end), chunk.text);
  for (const page of result.primary.pages) assert.equal(page.pageNumber, undefined);
  assert.equal(result.errors.length, 0);
  return {provider: result.primary.provider, text: result.primary.text, citations: result.primary.citations.length, chunks: result.primary.chunks.length};
}
const action = process.argv[2];
if (action === 'inventory') {
  const exports = {};
  for (const [entry, filename] of Object.entries({'.': 'index', '/core': 'core', '/server': 'server', '/local': 'local', '/react': 'react'})) {
    const specifier = '@alvarovillalbaa/ocr-gateway' + (entry === '.' ? '' : entry);
    const resolved = fileURLToPath(import.meta.resolve(specifier));
    assert.equal(resolved, path.join(installed, 'dist', filename + '.js'));
    assert.equal(await realpath(resolved), resolved);
    if (entry !== '/react') assert.equal(typeof await import(specifier), 'object');
    exports[entry] = path.relative(installed, resolved);
  }
  console.log(JSON.stringify({identity: 'F02', version: metadata.version, exports, optionalReactResolvedOnly: true}));
} else if (action === 'transport') {
  const client = new OCRGateway({baseUrl, apiKey: process.env.OCR_GATEWAY_API_KEY, timeoutMs: 15_000});
  const discovery = await client.providers();
  assert.deepEqual(discovery.providers.map(p => p.id), ['local']);
  assert.equal(discovery.providers[0].enabled, true);
  assert.equal(discovery.providers[0].configured, true);
  assert.ok(discovery.providers[0].mimeTypes.includes('text/html'));
  const result = verify(await client.parse({document: {name: 'fresh.html', mimeType: 'text/html', text: await readFile(process.env.FRESH_HTML, 'utf8')}, providers: ['local'], mode: 'single'}));
  await assert.rejects(new OCRGateway({baseUrl, timeoutMs: 5000}).providers(), error => error instanceof GatewayError && error.code === 'unauthorized' && error.status === 401);
  const tool = createParseTool(client, {providers: ['local'], mode: 'single'});
  assert.equal(tool.name, 'parse_document');
  assert.deepEqual(tool.parameters.required, ['url']);
  assert.equal(tool.parameters.additionalProperties, false);
  await assert.rejects(tool.execute({url: 'https://example.invalid/authored.txt', mimeType: 'text/plain'}), error => error instanceof GatewayError && error.code === 'no_provider' && error.status === 503);
  console.log(JSON.stringify({identity: 'F04', discovery: discovery.providers.map(p => p.id), result, unauthenticated: 401, localUrlRefused: 503}));
} else if (action === 'revoked') {
  await assert.rejects(new OCRGateway({baseUrl, apiKey: process.env.OCR_GATEWAY_API_KEY, timeoutMs: 5000}).providers(), error => error instanceof GatewayError && error.code === 'unauthorized' && error.status === 401);
  console.log(JSON.stringify({identity: 'F08', revokedRequestStatus: 401}));
} else throw new Error('Unknown consumer identity');
