"""T2: installed public wheel, authored file and real owned loopback transport."""
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import sys

import ocr_gateway
from ocr_gateway import AsyncOCRGateway, GatewayError, OCRGateway, utf16_slice

origin = Path(ocr_gateway.__file__).resolve()
assert origin.is_relative_to(Path(sys.prefix).resolve())
assert 'site-packages' in origin.parts
assert importlib.metadata.version('ocr-gateway-client') == '0.2.0'
base_url = 'http://127.0.0.1:38473'
fixture = Path(os.environ['FRESH_HTML'])


def verify(result):
    doc = result['primary']
    assert doc['provider'] == 'local'
    assert 'Fresh 🚲 delivery' in doc['text'] and 'Café 東京' in doc['text']
    assert doc['citations'] and doc['chunks']
    for citation in doc['citations']:
        expected = doc['text'].encode('utf-16-le')[citation['start'] * 2:citation['end'] * 2].decode('utf-16-le')
        assert utf16_slice(doc['text'], citation['start'], citation['end']) == expected == citation['quote']
    for chunk in doc['chunks']:
        assert utf16_slice(doc['text'], chunk['start'], chunk['end']) == chunk['text']
    assert all('pageNumber' not in page for page in doc['pages'])
    assert not result['errors']
    return {'provider': doc['provider'], 'text': doc['text'], 'citations': len(doc['citations']), 'chunks': len(doc['chunks'])}


sync = OCRGateway(base_url, timeout=15)
first = verify(sync.parse_file(fixture, providers=['local'], mode='single', timeout_ms=10_000))
assert sync.tool['parameters']['additionalProperties'] is False
try:
    sync.execute_tool({'url': 'https://example.invalid/authored.txt', 'mimeType': 'text/plain'}, defaults={'providers': ['local'], 'mode': 'single'})
except GatewayError as error:
    assert error.code == 'no_provider' and error.status == 503
else:
    raise AssertionError('Local URL tool unexpectedly parsed a URL')


async def check_async():
    client = AsyncOCRGateway(base_url, timeout=15)
    return verify(await client.parse_file(fixture, providers=['local'], mode='single', timeout_ms=10_000))


second = asyncio.run(check_async())
assert first == second
print(json.dumps({'identity': 'F05', 'version': importlib.metadata.version('ocr-gateway-client'),
                  'importWithinVenv': True, 'result': first, 'syncAndAsyncEqual': True, 'localUrlRefused': 503}, ensure_ascii=False))
