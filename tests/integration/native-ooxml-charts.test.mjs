// Tier 2: actual gateway -> Python local subprocess -> normalization, no paid calls.
import {after, test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {once} from 'node:events';
import {join, resolve} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const sourceRoot = fileURLToPath(new URL('../../', import.meta.url));
const packageRoot = process.env.OCR_GATEWAY_NODE_PACKAGE_ROOT ? resolve(process.env.OCR_GATEWAY_NODE_PACKAGE_ROOT) : sourceRoot;
const {createOCRGateway} = await import(pathToFileURL(join(packageRoot, 'dist/core.js')).href);
const {createLocalProvider} = await import(pathToFileURL(join(packageRoot, 'dist/local.js')).href);
const {OCRGateway} = await import(pathToFileURL(join(packageRoot, 'dist/index.js')).href);
const {createGatewayServer} = await import(pathToFileURL(join(packageRoot, 'dist/server.js')).href);
const python = process.env.OCR_GATEWAY_TEST_PYTHON ?? 'python3';
const previousEnvironment = new Map(['PYTHONPATH', 'PYTHONDONTWRITEBYTECODE'].map(key => [key, process.env[key]]));
process.env.PYTHONPATH = process.env.OCR_GATEWAY_PYTHON_PACKAGE_ROOT ?? join(sourceRoot, 'python');
process.env.PYTHONDONTWRITEBYTECODE = '1';
after(() => { for (const [key, value] of previousEnvironment) value === undefined ? delete process.env[key] : process.env[key] = value; });

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const PPTX = 'application/vnd.openxmlformats-officedocument.presentationml.presentation';
const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const options = {concurrency: false, timeout: 20_000};
const noNetwork = async () => { throw new Error('Unexpected network request from authored local fixture'); };
const pdf = () => ({name: 'private-name-must-not-reach-router.pdf', mimeType: 'application/pdf', dataBase64: Buffer.from('authored bytes, not a real PDF').toString('base64')});

function fixture(name) {
  const result = spawnSync(python, ['-I', '-B', '-S', join(sourceRoot, 'tests/helpers/ooxml_chart_fixtures.py'), name],
    {encoding: 'utf8', timeout: 5000, maxBuffer: 512 * 1024});
  assert.equal(result.error, undefined);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(result.stderr, '');
  return JSON.parse(result.stdout);
}

function localCounter() {
  const actual = createLocalProvider({python});
  const calls = [];
  return {calls, adapter: {...actual, async parse(document, context) { calls.push({document, features: context.features}); return actual.parse(document, context); }}};
}

function authoredProvider(id = 'authored-vision', overrides = {}) {
  const calls = [];
  return {calls, adapter: {id, name: 'Authored fixture provider', mimeTypes: ['application/pdf', 'image/*'], features: ['charts'], requiresKey: false,
    async parse(document) { calls.push(document); return {pages: [{text: 'Authored alternative output'}]}; }, ...overrides}};
}

function gateway(providers, extra = {}) {
  return createOCRGateway({providers, enabledProviders: providers.map(provider => provider.id), fetch: noNetwork, ...extra});
}

function chartBlocks(result) { return result.primary.pages.flatMap(page => page.blocks).filter(block => block.kind === 'chart'); }

function assertAnchors(document) {
  assert.ok(document.citations.length > 0);
  for (const page of document.pages) for (const block of page.blocks) {
    assert.equal(document.text.slice(block.start, block.end), block.text);
    const citation = document.citations.find(item => item.id === block.citationId);
    assert.ok(citation);
    assert.equal(citation.quote, block.text);
    assert.equal(document.text.slice(citation.start, citation.end), citation.quote);
    assert.equal(citation.inferred, false);
  }
  for (const chunk of document.chunks) {
    assert.equal(document.text.slice(chunk.start, chunk.end), chunk.text);
    assert.ok(chunk.blockIds.length > 0);
    assert.ok(chunk.citationIds.every(id => document.citations.some(citation => citation.id === id)));
  }
}

async function withServer(gatewayInstance, policy, work) {
  const server = createGatewayServer({gateway: gatewayInstance, authenticate: key => key === 'authored-loopback-token' ? policy : undefined});
  server.listen(0, '127.0.0.1');
  try {
    await once(server, 'listening');
    const address = server.address();
    assert.ok(address && typeof address === 'object');
    await work(`http://127.0.0.1:${address.port}`);
  } finally {
    server.closeAllConnections();
    await new Promise((resolveClose, reject) => server.close(error => error ? reject(error) : resolveClose()));
    assert.equal(server.listening, false);
  }
}

test('DOCX cached charts survive actual Python dispatch with exact UTF-16 citations and chunks', options, async () => {
  const local = localCounter();
  const result = await gateway([local.adapter]).parse({document: fixture('docx'), features: ['charts'], providers: ['local'], chunking: {maxCharacters: 100, overlap: 17}});
  assert.equal(local.calls.length, 1);
  assert.deepEqual(local.calls[0].features, ['charts']);
  const [chart] = chartBlocks(result);
  assert.ok(chart);
  assert.equal(chart.metadata.title, 'Revenue 🚀');
  assert.equal(chart.metadata.source, 'ooxml-chart-cache');
  assert.equal(chart.metadata.status, 'complete');
  assert.equal(chart.inferred, false);
  assert.equal(chart.start, 'Before 🧭\n\n'.length);
  assert.notEqual(chart.start, [...'Before 🧭\n\n'].length);
  assert.ok(result.primary.chunks.length > 1);
  assert.ok(result.primary.pages.every(page => page.pageNumber === undefined));
  assert.ok(result.primary.chunks.every(chunk => chunk.pageNumbers.length === 0));
  assert.ok(result.primary.citations.every(citation => citation.pageNumber === undefined && citation.bbox === undefined));
  assertAnchors(result.primary);
});

test('PPTX page and chart order follows the actual presentation manifest', options, async () => {
  const result = await gateway([createLocalProvider({python})]).parse({document: fixture('pptx'), features: ['charts']});
  assert.deepEqual(result.primary.pages.map(page => page.pageNumber), [1, 2]);
  assert.deepEqual(chartBlocks(result).map(block => block.metadata.title), ['First slide 🚀', 'Second slide']);
  assert.deepEqual(chartBlocks(result).map(block => block.metadata.documentPart), ['ppt/slides/slide9.xml', 'ppt/slides/slide2.xml']);
  assertAnchors(result.primary);
});

test('XLSX relationship order retains sheet and drawing provenance without rendered pages', options, async () => {
  const result = await gateway([createLocalProvider({python})]).parse({document: fixture('xlsx'), features: ['charts']});
  assert.deepEqual(chartBlocks(result).map(block => block.metadata.title), ['Drawing 9', 'Drawing 3', 'Drawing 2']);
  assert.ok(result.primary.pages.every(page => page.pageNumber === undefined));
  assert.ok(result.primary.chunks.every(chunk => chunk.pageNumbers.length === 0));
  assertAnchors(result.primary);
});

test('all four modes can select the actual local OOXML chart parser', options, async () => {
  const document = fixture('docx');
  for (const mode of ['auto', 'single', 'parallel', 'fallback']) {
    const local = localCounter();
    const result = await gateway([local.adapter]).parse({document, features: ['charts'], mode, providers: ['local'], maxProviders: 1});
    assert.deepEqual(result.routing.providers, ['local']);
    assert.equal(local.calls.length, 1);
    assert.equal(chartBlocks(result).length, 1);
  }
});

test('PDF image ODT and plain-text chart requests are refused before local dispatch in every mode', options, async () => {
  for (const mimeType of ['application/pdf', 'image/png', 'application/vnd.oasis.opendocument.text', 'text/plain']) {
    for (const mode of ['auto', 'single', 'parallel', 'fallback']) {
      const local = localCounter();
      const document = {mimeType, dataBase64: Buffer.from('authored unsupported-format fixture').toString('base64')};
      await assert.rejects(gateway([local.adapter]).parse({document, features: ['charts'], mode}), error => error.code === 'no_provider' && error.status === 503);
      assert.equal(local.calls.length, 0);
    }
  }
});

test('direct local adapter calls refuse unsupported chart formats before spawning Python', options, async () => {
  const local = createLocalProvider({python: '/authored/nonexistent/python-must-not-start'});
  await assert.rejects(local.parse(pdf(), {signal: new AbortController().signal, fetch: noNetwork, options: {}, features: ['charts']}),
    error => error.code === 'local_feature_unsupported');
});

test('custom routing cannot force a format-ineligible local adapter', options, async () => {
  const local = localCounter(), alternative = authoredProvider();
  let observed;
  const parser = gateway([local.adapter, alternative.adapter], {router: {decide: context => { observed = context; return ['local']; }}});
  await assert.rejects(parser.parse({document: pdf(), features: ['charts']}), error => error.code === 'invalid_route');
  assert.deepEqual(observed.candidates.map(item => item.id), ['authored-vision']);
  assert.equal(observed.request.document.dataBase64, undefined);
  assert.equal(observed.request.document.name, undefined);
  assert.equal(local.calls.length, 0);
  assert.equal(alternative.calls.length, 0);
});

test('a matching rule cannot restore a local adapter removed by the format filter', options, async () => {
  const local = localCounter(), alternative = authoredProvider();
  const result = await gateway([local.adapter, alternative.adapter], {router: {rules: [{mimeTypes: ['application/pdf'], providers: ['local']}]}})
    .parse({document: pdf(), features: ['charts']});
  assert.deepEqual(result.routing.providers, ['authored-vision']);
  assert.equal(local.calls.length, 0);
  assert.equal(alternative.calls.length, 1);
});

test('model router receives eligible metadata only and cannot reintroduce local PDF charts', options, async () => {
  const local = localCounter(), first = authoredProvider('authored-a'), second = authoredProvider('authored-b');
  const calls = [];
  const fetcher = async (url, init) => {
    calls.push({url, body: JSON.parse(init.body)});
    return new Response(JSON.stringify({answers: {provider: {type: 'choice', choice: 'local', confidence: 0.99, probabilities: {'authored-a': 0.5, 'authored-b': 0.5}}, breadth: {type: 'noul', noul: 0}}}), {headers: {'content-type': 'application/json'}});
  };
  const result = await gateway([local.adapter, first.adapter, second.adapter], {fetch: fetcher, router: {jevApiKey: 'authored-no-service-key'}})
    .parse({document: pdf(), features: ['charts'], maxProviders: 2});
  assert.equal(calls.length, 1);
  assert.deepEqual(Object.keys(calls[0].body.questions.provider.criteria), ['authored-a', 'authored-b']);
  assert.equal(calls[0].body.state.source, 'bytes');
  assert.ok(!JSON.stringify(calls[0].body).includes('private-name-must-not-reach-router'));
  assert.ok(!JSON.stringify(calls[0].body).includes(pdf().dataBase64));
  assert.equal(result.routing.router, 'heuristic');
  assert.deepEqual(result.routing.providers, ['authored-a', 'authored-b']);
  assert.equal(local.calls.length, 0);
});

test('excluded and disabled local providers cannot be restored by charts or request keys', options, async () => {
  const document = fixture('docx'), local = localCounter(), alternative = authoredProvider();
  await assert.rejects(gateway([local.adapter]).parse({document, features: ['charts'], excludeProviders: ['local']}), error => error.code === 'no_provider');
  await assert.rejects(gateway([local.adapter, alternative.adapter], {enabledProviders: ['authored-vision']})
    .parse({document, features: ['charts'], providers: ['local'], providerKeys: {local: 'authored-not-an-entitlement'}}), error => error.code === 'no_provider');
  assert.equal(local.calls.length, 0);
});

test('legacy custom adapters without format maps keep their existing global feature behavior', options, async () => {
  const custom = authoredProvider();
  const result = await gateway([custom.adapter]).parse({document: pdf(), features: ['charts']});
  assert.equal(result.primary.provider, 'authored-vision');
  assert.equal(custom.calls.length, 1);
});

test('empty feature maps deny formats and a map cannot add an undeclared global feature', options, async () => {
  for (const overrides of [{featureMimeTypes: {charts: []}}, {features: [], featureMimeTypes: {charts: ['application/pdf']}}]) {
    const custom = authoredProvider('authored-map', overrides);
    await assert.rejects(gateway([custom.adapter]).parse({document: pdf(), features: ['charts']}), error => error.code === 'no_provider');
    assert.equal(custom.calls.length, 0);
  }
});

test('format feature maps retain exact type-wildcard and universal-wildcard semantics', options, async () => {
  for (const pattern of ['application/pdf', 'application/*', '*/*']) {
    const custom = authoredProvider('authored-map', {featureMimeTypes: {charts: [pattern]}});
    const result = await gateway([custom.adapter]).parse({document: pdf(), features: ['charts']});
    assert.equal(result.primary.provider, 'authored-map');
  }
  const denied = authoredProvider('authored-map', {featureMimeTypes: {charts: ['image/*']}});
  await assert.rejects(gateway([denied.adapter]).parse({document: pdf(), features: ['charts']}), error => error.code === 'no_provider');
  assert.equal(denied.calls.length, 0);
});

test('local URL input remains excluded before routing or remote fetching', options, async () => {
  const local = localCounter();
  await assert.rejects(gateway([local.adapter]).parse({document: {url: 'https://fixture.invalid/private.docx', mimeType: DOCX}, features: ['charts']}), error => error.code === 'no_provider');
  assert.equal(local.calls.length, 0);
});

test('missing cache stays visibly partial through the actual gateway and remains source-only', options, async () => {
  const result = await gateway([createLocalProvider({python})]).parse({document: fixture('missing-cache'), features: ['charts']});
  const [chart] = chartBlocks(result);
  assert.equal(chart.metadata.status, 'partial');
  assert.equal(chart.metadata.series[0].values.cachePresent, false);
  assert.deepEqual(chart.metadata.series[0].values.points, []);
  assert.equal(chart.metadata.workbookResolved, false);
  assert.equal(chart.metadata.cacheFreshness, 'unverified');
  assert.ok(chart.metadata.warnings.length > 0);
  assertAnchors(result.primary);
});

test('malformed chart XML is a finite local failure without a successful document', options, async () => {
  const local = localCounter();
  await assert.rejects(gateway([local.adapter]).parse({document: fixture('dtd'), features: ['charts']}),
    error => error.code === 'all_providers_failed' && error.message.includes('local:local_parse_error') && !error.message.includes('blocked'));
  assert.equal(local.calls.length, 1);
});

test('authenticated HTTP SDK returns real local charts citations chunks and precise descriptors', options, async () => {
  const local = localCounter();
  await withServer(gateway([local.adapter]), {id: 'authored-local-policy', name: 'Authored local fixture', providers: ['local'], requestsPerMinute: 60}, async baseUrl => {
    const sdk = new OCRGateway({baseUrl, apiKey: 'authored-loopback-token', timeoutMs: 10_000});
    const descriptors = await sdk.providers();
    assert.equal(descriptors.providers.length, 1);
    assert.deepEqual(descriptors.providers[0].featureMimeTypes.charts, [DOCX, PPTX, XLSX]);
    const result = await sdk.parse({document: fixture('docx'), features: ['charts'], chunking: {maxCharacters: 100, overlap: 10}});
    assert.equal(chartBlocks(result).length, 1);
    assertAnchors(result.primary);
    assert.ok(result.primary.chunks.length > 1);
  });
  assert.equal(local.calls.length, 1);
});

test('HTTP key scopes constrain both explicit and implicit routing before local dispatch', options, async () => {
  const local = localCounter(), alternative = authoredProvider();
  await withServer(gateway([local.adapter, alternative.adapter]), {id: 'authored-restricted-policy', name: 'Authored scoped fixture', providers: ['authored-vision'], requestsPerMinute: 60}, async baseUrl => {
    const sdk = new OCRGateway({baseUrl, apiKey: 'authored-loopback-token', timeoutMs: 10_000});
    assert.deepEqual((await sdk.providers()).providers.map(provider => provider.id), ['authored-vision']);
    await assert.rejects(sdk.parse({document: fixture('docx'), providers: ['local'], features: ['charts']}), error => error.code === 'provider_forbidden' && error.status === 403);
    const result = await sdk.parse({document: pdf(), features: ['charts']});
    assert.deepEqual(result.routing.providers, ['authored-vision']);
  });
  assert.equal(local.calls.length, 0);
  assert.equal(alternative.calls.length, 1);
});
