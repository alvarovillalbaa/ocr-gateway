#!/usr/bin/env python3
"""Public-CI-only delivery verification of unchanged released artifacts."""
import base64
import gzip
import hashlib
import http.client
import io
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import zipfile

REPO = 'alvarovillalbaa/ocr-gateway'
BRANCH = 'qa/ocr-public-consumer-20261113-2'
TAG = 'v0.2.0-native-charts.1'
BASE = 'https://github.com/' + REPO + '/releases/download/' + TAG + '/'
ASSETS = {
    'alvarovillalbaa-ocr-gateway-0.2.0.tgz': (83978, '4775f9503ac09d94e9c2a39ea9381c162b7f41e527c8516e1e8d381e500890d4'),
    'ocr_gateway_client-0.2.0-py3-none-any.whl': (26079, 'f7b32a418cfb3b4a872b25a582fc8941dd070dfe957f2aeb36fb936a0b996ded'),
    'SHA256SUMS': (212, 'b1347d0a3c4e1ae1dfe7d3ebcb4652f75ea5156607c0f285e05e055eece96495'),
}
PORT = 38473
MAX_STREAM = 1024 * 1024
sha = lambda data: hashlib.sha256(data).hexdigest()
repo = Path.cwd()
source = os.environ.get('SOURCE_COMMIT', '')
report = {'schemaVersion': 1, 'repository': REPO, 'sourceCommit': source, 'startedAt': time.time(),
          'release': {'id': 438146413, 'tag': TAG}, 'checks': {}, 'commands': [], 'sourceGuards': [], 'cleanup': {}}
root = None
server = None
groups = []
baseline = {}
deadline = time.monotonic() + 1050
key = None
server_out = server_err = None


def need(value, message):
    if not value:
        raise RuntimeError(message)


def capture(data):
    retained = data[:MAX_STREAM]
    return {'bytes': len(data), 'retainedBytes': len(retained), 'sha256': sha(retained), 'complete': len(data) <= MAX_STREAM,
            'gzipBase64': base64.b64encode(gzip.compress(retained, mtime=0)).decode()}


def vector():
    result = {}
    for item in subprocess.check_output(['git', 'ls-tree', '-rz', '--full-tree', 'HEAD']).split(b'\0'):
        if not item:
            continue
        metadata, raw = item.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        name = raw.decode()
        file = repo / name
        need(kind == 'blob' and mode in ('100644', '100755', '120000'), 'Unexpected tracked mode')
        need(file.is_symlink() if mode == '120000' else file.is_file() and not file.is_symlink(), 'Tracked path kind changed')
        data = os.fsencode(os.readlink(file)) if mode == '120000' else file.read_bytes()
        need(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == blob, 'Tracked bytes changed: ' + name)
        result[name] = {'mode': mode, 'blob': blob, 'bytes': len(data), 'sha256': sha(data)}
    index = {}
    for item in subprocess.check_output(['git', 'ls-files', '--stage', '-z']).split(b'\0'):
        if not item:
            continue
        metadata, raw = item.split(b'\t', 1)
        mode, blob, stage = metadata.decode().split()
        need(stage == '0', 'Unmerged index')
        index[raw.decode()] = {'mode': mode, 'blob': blob}
    need(index == {name: {k: row[k] for k in ('mode', 'blob')} for name, row in result.items()}, 'Index differs')
    need(not subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all', '--ignored']), 'Checkout residue')
    return result


def guard(label):
    need(vector() == report['sourceFiles'], 'Source vector changed')
    report['sourceGuards'].append({'label': label, 'matches': True, 'files': len(report['sourceFiles'])})


def group_live(pgid):
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / 'stat').read_text().rpartition(') ')[2].split()
            if fields[0] != 'Z' and int(fields[2]) == pgid:
                found.append({'pid': int(entry.name), 'startTime': fields[19], 'pgid': pgid})
        except (FileNotFoundError, ProcessLookupError):
            pass
    return found


def stop(process):
    if process.poll() is None or group_live(process.pid):
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        end = time.monotonic() + 8
        while time.monotonic() < end:
            process.poll()
            if not group_live(process.pid):
                break
            time.sleep(.05)
        if group_live(process.pid):
            os.killpg(process.pid, signal.SIGKILL)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return False
    return not group_live(process.pid)


def run(argv, *, env=None, timeout=45, stdin=None, private=False):
    row = {'argv': argv, 'startedAt': time.time()}
    report['commands'].append(row)
    out = root / ('command-' + str(len(report['commands'])) + '.out')
    err = root / ('command-' + str(len(report['commands'])) + '.err')
    start = time.monotonic()
    with out.open('wb') as stdout, err.open('wb') as stderr:
        os.chmod(out, 0o600)
        process = subprocess.Popen(argv, cwd=consumer, env=env or bootstrap, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, start_new_session=True)
        groups.append(process)
        if stdin is not None:
            process.stdin.write(stdin)
            process.stdin.close()
        try:
            process.wait(timeout=max(1, min(timeout, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            row['timedOut'] = True
            stop(process)
    stdout, stderr = out.read_bytes(), err.read_bytes()
    row.update({'stderr': capture(stderr), 'exitCode': process.returncode, 'elapsedSeconds': round(time.monotonic() - start, 3)})
    if private:
        row['redaction'] = {'field': 'apiKey', 'originalBytes': len(stdout), 'originalSha256': sha(stdout)}
        row['stdout'] = capture(b'[one-time key output redacted]')
        try:
            value = json.loads(stdout)
            secret = value.pop('apiKey')
            row['stdout'] = capture(json.dumps({**value, 'apiKey': '[ephemeral bearer redacted]'}).encode())
        finally:
            out.unlink()
    else:
        row['stdout'] = capture(stdout)
        secret = None
    print('OCR_FRESH_COMMAND', json.dumps({'tool': argv[0], 'exitCode': process.returncode, 'seconds': row['elapsedSeconds']}), flush=True)
    need(process.returncode == 0 and not row.get('timedOut'), 'Command failed: ' + argv[0])
    need(row['stdout']['complete'] and row['stderr']['complete'], 'Command output exceeded bound')
    return (value, secret) if private else stdout


class AnonymousRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urlsplit(newurl)
        need(parsed.scheme == 'https' and parsed.hostname in ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com')
             and parsed.port in (None, 443) and not parsed.username and not parsed.password and not parsed.fragment, 'Unexpected asset redirect')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download(name):
    url = BASE + name
    opener = build_opener(ProxyHandler({}), AnonymousRedirect())
    start = time.monotonic()
    with opener.open(Request(url, headers={'User-Agent': 'OCR-Gateway-public-consumer', 'Accept': 'application/octet-stream'}), timeout=30) as response:
        data = response.read(ASSETS[name][0] + 1)
        final = urlsplit(response.url)
        need(response.status == 200 and len(data) == ASSETS[name][0] and sha(data) == ASSETS[name][1], 'Public asset identity mismatch: ' + name)
        need(final.scheme == 'https' and final.hostname in ('github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'), 'Asset final host')
        row = {'url': url, 'status': response.status, 'bytes': len(data), 'sha256': sha(data), 'authorizationSent': False,
               'finalHost': final.hostname, 'elapsedSeconds': round(time.monotonic() - start, 3)}
    (artifacts / name).write_bytes(data)
    return row


def archive_name(name):
    p = PurePosixPath(name)
    need(name and not p.is_absolute() and '..' not in p.parts and '\\' not in name and all(ord(c) >= 32 for c in name), 'Unsafe archive member')
    return p


def inventory(directory):
    result = {}
    for file in sorted(directory.rglob('*')):
        need(not file.is_symlink(), 'Unexpected installed symlink')
        if file.is_file():
            data = file.read_bytes()
            result[str(file.relative_to(directory))] = {'bytes': len(data), 'sha256': sha(data)}
    return result


def verify_result(result):
    doc = result['primary']
    need(doc['provider'] == 'local' and 'Fresh 🚲 delivery' in doc['text'] and 'Café 東京' in doc['text'], 'Installed extraction mismatch')
    need(doc['citations'] and doc['chunks'] and not result['errors'], 'Missing normalized result')
    raw = doc['text'].encode('utf-16-le')
    for citation in doc['citations']:
        need(raw[citation['start'] * 2:citation['end'] * 2].decode('utf-16-le') == citation['quote'], 'CLI citation mismatch')
    return {'provider': doc['provider'], 'citations': len(doc['citations']), 'chunks': len(doc['chunks'])}


def owned_descendants():
    found = []
    prefix = os.fsencode(str(root))
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            fields = (entry / 'stat').read_text().rpartition(') ')[2].split()
            if fields[0] == 'Z' or entry.stat().st_uid != os.getuid():
                continue
            if baseline.get(entry.name) == fields[19]:
                continue  # Pre-existing runner services are not this task's children.
            argv = (entry / 'cmdline').read_bytes().split(b'\0')
            environ = (entry / 'environ').read_bytes().split(b'\0')
            cwd = os.fsencode(os.readlink(entry / 'cwd'))
            if cwd.startswith(prefix + b'/') or any(prefix + b'/' in value for value in argv) or any(value == b'FRESH_ROOT=' + prefix for value in environ):
                found.append({'pid': int(entry.name), 'pgid': int(fields[2]), 'startTime': fields[19]})
        except (FileNotFoundError, ProcessLookupError):
            pass
        except PermissionError:
            found.append({'pid': int(entry.name), 'inspectionDenied': True})
    return found


status = 1
try:
    need(os.environ.get('CI') == 'true' and os.environ.get('GITHUB_REPOSITORY') == REPO, 'Public CI only')
    need(os.environ.get('GITHUB_EVENT_NAME') == 'create' and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH, 'Wrong event/ref')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    need(event['ref_type'] == 'branch' and event['ref'] == BRANCH and event['repository']['private'] is False, 'Wrong public event')
    need(len(source) == 40 and subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == source, 'Wrong pinned source')
    need(sys.version_info[:2] == (3, 12), 'Expected recorded Ubuntu Python 3.12 profile')
    report['sourceFiles'] = vector()
    root = Path(tempfile.mkdtemp(prefix='ocr-public-consumer-', dir=os.environ['RUNNER_TEMP']))
    os.chmod(root, 0o700)
    root_identity = (root.stat().st_dev, root.stat().st_ino, root.stat().st_uid)
    nonce = secrets.token_hex(16)
    (root / '.owner').write_text(nonce)
    report['ownedRoot'] = {'path': str(root), 'identity': list(root_identity), 'nonce': nonce}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid == os.getuid():
                baseline[entry.name] = (entry / 'stat').read_text().rpartition(') ')[2].split()[19]
        except (FileNotFoundError, ProcessLookupError):
            pass
    report['preExistingProcessCount'] = len(baseline)
    consumer, artifacts, guards = root / 'consumer', root / 'artifacts', root / 'guards'
    for p in (consumer, artifacts, guards, root / 'npm-cache', root / 'cache', root / 'config'):
        p.mkdir(mode=0o700)
    (root / 'npmrc').write_text('')
    (root / 'npm-global').write_text('')
    (consumer / 'package.json').write_text(json.dumps({'name': 'ocr-public-consumer', 'version': '0.0.0', 'private': True, 'type': 'module'}))
    bootstrap = {k: os.environ[k] for k in ('PATH', 'RUNNER_TEMP', 'HOME')}
    bootstrap.update({'CI': 'true', 'LANG': 'C.UTF-8', 'TZ': 'UTC', 'NO_COLOR': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                      'npm_config_cache': str(root / 'npm-cache'), 'npm_config_userconfig': str(root / 'npmrc'), 'npm_config_globalconfig': str(root / 'npm-global'),
                      'npm_config_update_notifier': 'false', 'PIP_CONFIG_FILE': '/dev/null', 'PIP_DISABLE_PIP_VERSION_CHECK': '1',
                      'XDG_CACHE_HOME': str(root / 'cache'), 'XDG_CONFIG_HOME': str(root / 'config')})
    report['runtime'] = {'node': run(['node', '--version']).decode().strip(), 'npm': run(['npm', '--version']).decode().strip(), 'python': sys.version}
    need(report['runtime']['node'] == 'v24.21.0', 'Pinned Node version')
    guard('before-anonymous-downloads')
    report['downloads'] = [download(name) for name in ASSETS]
    checksums = dict((parts[1], parts[0]) for parts in (line.split() for line in (artifacts / 'SHA256SUMS').read_text().splitlines()))
    need(checksums == {name: digest for name, (_, digest) in ASSETS.items() if name != 'SHA256SUMS'}, 'Checksum manifest mismatch')
    report['checks']['F01'] = {'passed': True, 'assets': 3, 'anonymous': True}
    expected_node = {}
    with tarfile.open(artifacts / next(name for name in ASSETS if name.endswith('.tgz')), 'r:gz') as archive:
        for item in archive:
            parts = archive_name(item.name).parts
            need(parts[0] == 'package' and (item.isfile() or item.isdir()), 'Unexpected tar member')
            if not item.isfile():
                continue
            name = str(PurePosixPath(*parts[1:]))
            need(name not in expected_node and item.size < 4 * 1024 * 1024, 'Duplicate/oversized tar member')
            data = archive.extractfile(item).read()
            expected_node[name] = {'bytes': len(data), 'sha256': sha(data)}
    need(len(expected_node) < 256, 'Package member bound')
    run(['npm', 'install', '--ignore-scripts', '--no-audit', '--no-fund', '--omit=peer', BASE + next(name for name in ASSETS if name.endswith('.tgz'))], timeout=180)
    installed = consumer / 'node_modules/@alvarovillalbaa/ocr-gateway'
    need(inventory(installed) == expected_node, 'Installed npm payload differs from anonymous archive')
    cli = consumer / 'node_modules/.bin/ocr-gateway'
    need(cli.is_symlink() and cli.resolve() == installed / 'dist/cli.js' and os.access(cli, os.X_OK), 'Installed CLI entry mismatch')
    package = json.loads((installed / 'package.json').read_text())
    need(package['version'] == '0.2.0' and not package.get('dependencies'), 'Installed npm metadata')
    run([sys.executable, '-m', 'venv', '--copies', str(root / 'venv')], timeout=60)
    python = str(root / 'venv/bin/python')
    wheel_name = next(name for name in ASSETS if name.endswith('.whl'))
    run([python, '-m', 'pip', 'install', '--no-index', '--no-deps', '--no-compile', '--no-cache-dir', BASE + wheel_name], timeout=120)
    site = root / f'venv/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages'
    expected_python = {}
    with zipfile.ZipFile(artifacts / wheel_name) as archive:
        for item in archive.infolist():
            name = str(archive_name(item.filename))
            if item.is_dir():
                continue
            need(name not in expected_python and item.file_size < 4 * 1024 * 1024, 'Duplicate/oversized wheel member')
            if name.endswith('.dist-info/RECORD'):
                continue
            data = archive.read(item)
            expected_python[name] = {'bytes': len(data), 'sha256': sha(data)}
            need((site / name).is_file() and sha((site / name).read_bytes()) == sha(data), 'Installed wheel payload mismatch')
    direct = json.loads((site / 'ocr_gateway_client-0.2.0.dist-info/direct_url.json').read_text())
    need(direct['url'] == BASE + wheel_name and direct['archive_info']['hashes']['sha256'] == ASSETS[wheel_name][1], 'Installed wheel direct URL/digest')
    shutil.copyfile(repo / 'tests/helpers/fresh-consumer-network.cjs', guards / 'network.cjs')
    shutil.copyfile(repo / 'tests/helpers/fresh-consumer-sitecustomize.py', guards / 'sitecustomize.py')
    shutil.copyfile(repo / 'tests/smoke/fresh-public-node.mjs', consumer / 'fresh-public-node.mjs')
    shutil.copyfile(repo / 'tests/smoke/fresh-public-python.py', consumer / 'fresh-public-python.py')
    fixture = root / 'fresh.html'
    fixture.write_text('<h1>Fresh 🚲 delivery</h1><p>Café 東京 — a public archive, private local parsing.</p><table><tr><td>Budget</td><td>42</td></tr></table>', encoding='utf8')
    runtime = {**bootstrap, 'FRESH_ROOT': str(root), 'FRESH_NODE_PACKAGE': str(installed), 'FRESH_HTML': str(fixture), 'FRESH_NETWORK_AUDIT': str(root / 'network.jsonl'),
               'NODE_OPTIONS': '--require=' + str(guards / 'network.cjs'), 'PYTHONPATH': str(guards), 'OCR_GATEWAY_PYTHON': python}
    node_before = inventory(installed)
    python_before = {str(p.relative_to(site)): inventory(p) for p in (site / 'ocr_gateway', site / 'ocr_gateway_client-0.2.0.dist-info')}
    report['installedNodePayload'] = node_before
    report['installedWheelPayload'] = expected_python
    report['checks']['F02'] = {'passed': True, 'installedFromPublicURL': True, 'observation': json.loads(run(['node', 'fresh-public-node.mjs', 'inventory'], env=runtime))}
    observation = json.loads(run([python, '-c', "import json,ocr_gateway,sys,importlib.metadata;from pathlib import Path;p=Path(ocr_gateway.__file__).resolve();assert p.is_relative_to(Path(sys.prefix).resolve());assert importlib.metadata.version('ocr-gateway-client')=='0.2.0';print(json.dumps({'version':'0.2.0','withinVenv':True,'origin':str(p.relative_to(sys.prefix))}))"], env=runtime))
    report['checks']['F03'] = {'passed': True, 'installedFromPublicURL': True, 'observation': observation, 'directURL': direct}
    metadata, key = run([str(cli), 'key', 'create', '--store', str(root / 'keys.json'), '--name', 'authored-public-consumer', '--providers', 'local', '--rpm', '60'], env=runtime, private=True)
    need(stat.S_IMODE((root / 'keys.json').stat().st_mode) == 0o600 and key not in (root / 'keys.json').read_text(), 'Private hashed key store')
    listed = json.loads(run([str(cli), 'key', 'list', '--store', str(root / 'keys.json')], env=runtime))
    need(len(listed) == 1 and listed[0]['id'] == metadata['id'] and listed[0]['providers'] == ['local'], 'Installed CLI key metadata')
    runtime['OCR_GATEWAY_API_KEY'] = key
    probe = socket.socket()
    try:
        need(probe.connect_ex(('127.0.0.1', PORT)) != 0, 'Port already occupied')
    finally:
        probe.close()
    server_out, server_err = (root / 'server.out').open('wb'), (root / 'server.err').open('wb')
    server = subprocess.Popen([str(cli), 'serve', '--local', '--providers', 'local', '--host', '127.0.0.1', '--port', str(PORT), '--store', str(root / 'keys.json')],
                              cwd=consumer, env=runtime, stdin=subprocess.DEVNULL, stdout=server_out, stderr=server_err, start_new_session=True)
    groups.append(server)
    end = time.monotonic() + 15
    while time.monotonic() < end:
        need(server.poll() is None, 'Installed server exited before readiness')
        connection = http.client.HTTPConnection('127.0.0.1', PORT, timeout=.5)
        try:
            connection.request('GET', '/health')
            response = connection.getresponse()
            body = response.read(4096)
            if response.status == 200 and json.loads(body) == {'status': 'ok', 'version': '0.2.0'}:
                break
        except OSError:
            time.sleep(.05)
        finally:
            connection.close()
    else:
        raise RuntimeError('Installed gateway readiness timed out')
    report['checks']['F04'] = {'passed': True, 'privateHashedStore': True, 'actualCLIService': True,
                              'observation': json.loads(run(['node', 'fresh-public-node.mjs', 'transport'], env=runtime))}
    report['checks']['F05'] = {'passed': True, 'observation': json.loads(run([python, 'fresh-public-python.py'], env=runtime))}
    parsed = json.loads(run([str(cli), 'parse', '--file', str(fixture), '--base-url', 'http://127.0.0.1:38473', '--providers', 'local', '--mode', 'single'], env=runtime))
    report['checks']['F06'] = {'passed': True, 'observation': verify_result(parsed)}
    messages = [
        {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'authored-consumer', 'version': '1'}}},
        {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
        {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'parse_document', 'arguments': {'url': 'https://example.invalid/authored.txt', 'mimeType': 'text/plain'}}},
    ]
    mcp = [json.loads(line) for line in run([str(cli), 'mcp', '--base-url', 'http://127.0.0.1:38473'], env=runtime,
                                         stdin=('\n'.join(json.dumps(m) for m in messages) + '\n').encode()).splitlines()]
    need([m['id'] for m in mcp] == [1, 2, 3] and mcp[0]['result']['serverInfo']['version'] == '0.2.0', 'Installed MCP initialization')
    tool = mcp[1]['result']['tools'][0]
    need(tool['name'] == 'parse_document' and tool['inputSchema']['required'] == ['url'] and tool['inputSchema']['additionalProperties'] is False, 'Installed MCP schema')
    need(mcp[2]['result']['isError'] is True and 'No enabled, configured provider supports' in mcp[2]['result']['content'][0]['text'], 'Installed MCP local-URL refusal')
    report['checks']['F07'] = {'passed': True, 'observation': mcp, 'positiveURLProviderClaim': False}
    run([str(cli), 'key', 'revoke', metadata['id'], '--store', str(root / 'keys.json')], env=runtime)
    revoked = json.loads(run(['node', 'fresh-public-node.mjs', 'revoked'], env=runtime))
    need(inventory(installed) == node_before and {str(p.relative_to(site)): inventory(p) for p in (site / 'ocr_gateway', site / 'ocr_gateway_client-0.2.0.dist-info')} == python_before, 'Installed payload changed during runtime')
    need(all(sha((artifacts / name).read_bytes()) == digest for name, (_, digest) in ASSETS.items()), 'Downloaded artifacts changed')
    report['network'] = [json.loads(line) for line in (root / 'network.jsonl').read_text().splitlines()]
    need(report['network'] and all(not event['event'].endswith('_denied') for event in report['network']), 'Runtime network tripwire fired')
    report['checks']['F08'] = {'passed': False, 'revocation': revoked, 'installedPayloadUnchanged': True, 'downloadedArtifactsUnchanged': True}
    guard('after-installed-consumers')
    status = 0
except BaseException as error:
    report['failure'] = {'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()}
finally:
    if root is not None:
        report['cleanup']['groups'] = []
        for process in reversed(groups):
            try:
                closed = stop(process)
                report['cleanup']['groups'].append({'pid': process.pid, 'liveAbsent': closed})
                if not closed:
                    status = 1
            except BaseException:
                report['cleanup']['groups'].append({'pid': process.pid, 'liveAbsent': False, 'error': traceback.format_exc()})
                status = 1
        try:
            if server_out:
                server_out.close()
                server_err.close()
                report['server'] = {'stdout': capture((root / 'server.out').read_bytes()), 'stderr': capture((root / 'server.err').read_bytes())}
            remaining = owned_descendants()
            report['cleanup']['ownedDescendants'] = remaining
            connection = socket.socket()
            try:
                report['cleanup']['portClosed'] = connection.connect_ex(('127.0.0.1', PORT)) != 0
            finally:
                connection.close()
            if remaining or not report['cleanup']['portClosed']:
                status = 1
            if (root / 'network.jsonl').exists():
                report['network'] = [json.loads(line) for line in (root / 'network.jsonl').read_text().splitlines()]
            guard('after-owned-shutdown')
            need((root.stat().st_dev, root.stat().st_ino, root.stat().st_uid) == root_identity and (root / '.owner').read_text() == nonce, 'Root ownership changed')
            need(not remaining, 'Owned descendants remain; scratch removal refused')
            need(all(group['liveAbsent'] for group in report['cleanup']['groups']), 'Direct group remains; scratch removal refused')
            shutil.rmtree(root)
            report['cleanup']['rootAbsent'] = not root.exists()
        except BaseException:
            report['cleanup']['failure'] = traceback.format_exc()
            status = 1
    report['finishedAt'] = time.time()
    report['exitCode'] = status
    if status == 0:
        report['checks']['F08'].update({'passed': True, 'ownedCleanupVerified': True})
    raw = json.dumps(report, separators=(',', ':'), ensure_ascii=True).encode()
    encoded = base64.b64encode(gzip.compress(raw, mtime=0)).decode()
    print('OCR_FRESH_RECEIPT_BEGIN', json.dumps({'bytes': len(raw), 'sha256': sha(raw)}), flush=True)
    for at in range(0, len(encoded), 24000):
        print('OCR_FRESH_RECEIPT_DATA ' + encoded[at:at + 24000], flush=True)
    print('OCR_FRESH_RECEIPT_END', flush=True)
raise SystemExit(status)
