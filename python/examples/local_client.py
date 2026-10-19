"""Synthetic SDK example: local HTTP gateway, no provider keys/network fetches.

From the repository root, after npm run build:
    PYTHONPATH=python python3 python/examples/local_client.py

The example can also run with an installed wheel by replacing PYTHONPATH.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import secrets
import selectors
import subprocess
import sys
import tempfile

from ocr_gateway import AsyncOCRGateway, OCRGateway, utf16_slice


async def async_example(url: str, key: str) -> dict:
    client = AsyncOCRGateway(url, api_key=key, timeout=30)
    return await client.parse(
        {"text": "Synthetic asynchronous report", "mime_type": "text/plain"},
        providers=["local"], mode="single", provider_options={"local": {}},
    )


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    key = secrets.token_urlsafe(32)
    script = """
import {createOCRGateway} from CORE;
import {createGatewayServer} from SERVER;
import {createLocalProvider} from LOCAL;
const synthetic={id:'synthetic',name:'Synthetic URL fixture',mimeTypes:['application/pdf'],features:[],requiresKey:false,supportsUrl:true,
  async parse(document,context){
    if(context.options.retain_empty_cells!==true) throw new Error('Provider options were not preserved');
    return {pages:[{text:'Synthetic tool extraction; URL was not fetched'}],warnings:['Synthetic transport fixture, no provider extraction']};
  }};
const gateway=createOCRGateway({providers:[createLocalProvider({python:process.env.OCR_GATEWAY_PYTHON}),synthetic],enabledProviders:['local','synthetic']});
const server=createGatewayServer({gateway,authenticate:key=>key===process.env.OCR_EXAMPLE_KEY?{id:'example',name:'Synthetic example',providers:['local','synthetic'],requestsPerMinute:30}:undefined});
server.on('error',error=>{console.error(error.message);process.exit(1);});
server.listen(0,'127.0.0.1',()=>console.log(server.address().port));
"""
    for marker, filename in (("CORE", "core.js"), ("SERVER", "server.js"), ("LOCAL", "local.js")):
        script = script.replace(marker, json.dumps((root / "dist" / filename).as_uri()))
    env = {**os.environ, "OCR_EXAMPLE_KEY": key, "OCR_GATEWAY_PYTHON": sys.executable}
    # The package used by this example must also be importable by the subprocess.
    env["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(str(Path(path).resolve()) for path in sys.path if path))
    with tempfile.TemporaryDirectory(prefix="ocr-sdk-example-") as directory:
        with open(Path(directory) / "gateway.stderr", "w+b") as stderr:
            process = subprocess.Popen(["node", "--input-type=module", "-e", script], cwd=root, env=env, stdout=subprocess.PIPE, stderr=stderr, text=True)
            try:
                assert process.stdout is not None
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    if not selector.select(timeout=10):
                        raise RuntimeError("Synthetic gateway did not start within 10 seconds")
                    line = process.stdout.readline().strip()
                if not line.isdigit():
                    stderr.seek(0)
                    detail = stderr.read(3000).decode("utf-8", errors="replace")
                    raise RuntimeError("Synthetic gateway did not start; run npm run build first. " + detail)
                url = "http://127.0.0.1:" + line
                client = OCRGateway(url, api_key=key, timeout=30)
                result = client.parse(
                    {"text": "<h1>Example 😀</h1><table><tr><td>Revenue</td><td>42</td></tr></table>", "mime_type": "text/html"},
                    providers=["local"], mode="single", chunking={"max_characters": 100, "overlap": 10},
                )
                assert any(block["kind"] == "table" for page in result["primary"]["pages"] for block in page["blocks"])
                for citation in result["primary"]["citations"]:
                    assert utf16_slice(result["primary"]["text"], citation["start"], citation["end"]) == citation["quote"]
                path = Path(directory) / "report.txt"
                path.write_text("Synthetic file report", encoding="utf-8")
                file_result = client.parse_file(path, providers=["local"], mode="single")
                assert file_result["primary"]["text"] == "Synthetic file report"
                async_result = asyncio.run(async_example(url, key))
                assert async_result["primary"]["text"] == "Synthetic asynchronous report"
                tool_result = client.execute_tool(
                    {"url": "https://example.com/report.pdf", "name": "report.pdf"},
                    defaults={"providers": ["synthetic"], "mode": "single", "provider_options": {"synthetic": {"retain_empty_cells": True}}},
                )
                assert tool_result["primary"]["provider"] == "synthetic"
                try:
                    client.execute_tool({"url": "https://example.com/report.pdf", "providers": ["local"]})
                except ValueError:
                    pass
                else:
                    raise AssertionError("Model policy argument was accepted")
                print(json.dumps({"syncProvider": result["primary"]["provider"], "asyncProvider": async_result["primary"]["provider"], "fileProvider": file_result["primary"]["provider"], "toolProvider": tool_result["primary"]["provider"], "citations": len(result["primary"]["citations"]), "paidCalls": 0}))
            finally:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
