"""Runtime-only loopback tripwire, copied as sitecustomize.py in owned CI."""
import json
import os
from pathlib import Path
import socket

audit = Path(os.environ['FRESH_NETWORK_AUDIT'])
assert audit.is_relative_to(Path(os.environ['FRESH_ROOT']))


def record(event):
    if audit.exists() and audit.stat().st_size > 128 * 1024:
        raise RuntimeError('Network audit exceeded its bound')
    with audit.open('a', encoding='utf8') as handle:
        handle.write(json.dumps({'pid': os.getpid(), 'event': event}) + '\n')


def allowed(address):
    return isinstance(address, tuple) and len(address) >= 2 and address[0] in ('127.0.0.1', 'localhost', '::1') and address[1] == 38473


original_socket = socket.socket


class OwnedSocket(original_socket):
    def connect(self, address):
        if not allowed(address):
            record('python_connect_denied')
            raise RuntimeError('Unexpected runtime connection')
        record('python_connect_allowed')
        return super().connect(address)

    def connect_ex(self, address):
        if not allowed(address):
            record('python_connect_denied')
            raise RuntimeError('Unexpected runtime connection')
        record('python_connect_allowed')
        return super().connect_ex(address)


original_getaddrinfo = socket.getaddrinfo


def getaddrinfo(host, port, *args, **kwargs):
    if host not in ('127.0.0.1', 'localhost', '::1') or int(port) != 38473:
        record('python_dns_denied')
        raise RuntimeError('Unexpected runtime DNS')
    return original_getaddrinfo(host, port, *args, **kwargs)


socket.socket = OwnedSocket
socket.getaddrinfo = getaddrinfo
