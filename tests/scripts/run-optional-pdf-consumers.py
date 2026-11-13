#!/usr/bin/env python3
"""Public CI only: four new installed optional-PDF identities, no old suite."""
import ast
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import signal
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

REPO = "alvarovillalbaa/ocr-gateway"
BRANCH = "qa/ocr-optional-pdf-20261113-1"
PARENT = "81d4b71c6757f19c6c7be356f71aa39401565cb7"
SUPPORT_SHA = "311cdf102efe1162be64bebad16b9c875371404b9539ac88bfc9cf7c130668f9"
BASE = "https://github.com/" + REPO + "/releases/download/v0.2.0-native-charts.1/"
ASSETS = {
    "alvarovillalbaa-ocr-gateway-0.2.0.tgz": (83978, "4775f9503ac09d94e9c2a39ea9381c162b7f41e527c8516e1e8d381e500890d4"),
    "ocr_gateway_client-0.2.0-py3-none-any.whl": (26079, "f7b32a418cfb3b4a872b25a582fc8941dd070dfe957f2aeb36fb936a0b996ded"),
}
PDF_WHEEL = "pymupdf-1.26.6-cp310-abi3-manylinux_2_28_x86_64.whl"
PDF_URL = "https://files.pythonhosted.org/packages/4f/bf/6e02e3d84b32c137c71a0a3dcdba8f2f6e9950619a3bc272245c7c06a051/" + PDF_WHEEL
ASSETS[PDF_WHEEL] = (24115381, "7777d0b7124c2ebc94849536b6a1fb85d158df3b9d873935e63036559391534c")
repo = Path.cwd()
source = os.environ.get("SOURCE_COMMIT", "")
sha = lambda raw: hashlib.sha256(raw).hexdigest()
MAX_STREAM = 1024 * 1024
root = None
baseline = {}
groups = []
deadline = time.monotonic() + max(0, 900 - (time.time() - float(os.environ.get("PDF_STARTED_EPOCH", "0"))))
report = {"schemaVersion": 1, "repository": REPO, "sourceCommit": source, "canonicalParent": PARENT,
          "startedAt": time.time(), "checks": {}, "commands": [], "sourceGuards": [], "cleanup": {},
          "closedSuitesRerun": False, "productOrReleaseBytesChanged": False}

# Reuse only these hash-bound operational definitions, never the old main/body.
support = (repo / "tests/scripts/run-fresh-public-consumers.py").read_bytes()
if sha(support) != SUPPORT_SHA:
    raise RuntimeError("Support source changed before execution")
names = {"need", "capture", "vector", "guard", "group_live", "archive_name", "inventory", "owned_descendants"}
parsed = ast.parse(support)
definitions = [node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name in names]
if {node.name for node in definitions} != names:
    raise RuntimeError("Trusted support definition set")
exec(compile(ast.Module(body=definitions, type_ignores=[]), "hash-bound-operational-support", "exec"), globals())


class AnonymousRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        target = urlsplit(newurl)
        need(target.scheme == "https" and target.hostname in ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "files.pythonhosted.org")
             and target.port in (None, 443) and not target.username and not target.password and not target.fragment, "Unexpected public artifact redirect")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download(name):
    url = PDF_URL if name == PDF_WHEEL else BASE + name
    expected_bytes, digest = ASSETS[name]
    start = time.monotonic()
    raw = bytearray()
    with build_opener(ProxyHandler({}), AnonymousRedirect()).open(Request(url, headers={"User-Agent": "OCR-optional-PDF-consumer"}), timeout=20) as response:
        need(response.status == 200, "Artifact response status")
        while True:
            need(time.monotonic() - start < 90 and time.monotonic() < deadline, "Artifact total deadline")
            part = response.read(min(65536, expected_bytes + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
            need(len(raw) <= expected_bytes, "Artifact byte bound")
        need(len(raw) == expected_bytes and sha(raw) == digest, "Artifact identity")
        final_host = urlsplit(response.url).hostname
    with (artifacts / name).open("xb") as handle:
        handle.write(raw)
    return {"name": name, "url": url, "bytes": len(raw), "sha256": digest, "authorizationSent": False,
            "bodyEOFObserved": True, "responseClosed": True, "finalHost": final_host}


def run(argv, *, env=None, stdin=None, expected_exit=0, timeout=90):
    row = {"argv": argv, "expectedExit": expected_exit, "startedAt": time.time()}
    report["commands"].append(row)
    output, errors = root / f"command-{len(report['commands'])}.out", root / f"command-{len(report['commands'])}.err"
    seen = {}
    with output.open("xb") as stdout, errors.open("xb") as stderr:
        os.chmod(output, 0o600)
        os.chmod(errors, 0o600)
        process = subprocess.Popen(argv, cwd=consumer, env=env or bootstrap, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, start_new_session=True)
        groups.append(process)
        row["pid"] = process.pid
        if stdin is not None:
            process.stdin.write(stdin)
            process.stdin.close()
        end = min(deadline, time.monotonic() + timeout)
        while process.poll() is None:
            for observation in owned_descendants():
                need("inspectionDenied" not in observation, "Owned process inspection denied")
                seen[(observation["pid"], observation["startTime"])] = observation
            if time.monotonic() >= end:
                row["timedOut"] = True
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                break
            time.sleep(.05)
        process.wait(timeout=5)
    row.update({"exitCode": process.returncode, "reaped": True, "outputDescriptorsClosed": True,
                "stdout": capture(output.read_bytes()), "stderr": capture(errors.read_bytes()), "observedProcesses": list(seen.values())})
    end = time.monotonic() + 2
    pgids = {process.pid} | {r["pgid"] for r in seen.values()}
    while any(group_live(pgid) for pgid in pgids) and time.monotonic() < end:
        time.sleep(.05)
    row["observedGroupsAbsent"] = all(not group_live(pgid) for pgid in pgids)
    print("OCR_PDF_COMMAND", json.dumps({"ordinal": len(report["commands"]), "exitCode": process.returncode}), flush=True)
    need(row["observedGroupsAbsent"] and row["stdout"]["complete"] and row["stderr"]["complete"], "Command stream/process closure")
    need(process.returncode == expected_exit and not row.get("timedOut"), "Unexpected command exit")
    return output.read_bytes(), errors.read_bytes()


status = 1
try:
    need(os.environ.get("CI") == "true" and os.environ.get("GITHUB_REPOSITORY") == REPO, "Public CI only")
    need(os.environ.get("GITHUB_EVENT_NAME") == "create" and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH, "Exact event/ref")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    need(event["ref_type"] == "branch" and event["ref"] == BRANCH and event["repository"]["private"] is False, "Public creation event")
    need(len(source) == 40 and subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == source, "Pinned source")
    need(subprocess.check_output(["git", "rev-parse", "HEAD^"], text=True).strip() == PARENT, "Exact canonical parent")
    need((repo / "AGENTS.md").read_bytes().startswith(subprocess.check_output(["git", "show", PARENT + ":AGENTS.md"])), "Append-only instructions")
    changed = set(subprocess.check_output(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], text=True).splitlines())
    need(changed == {"AGENTS.md", "tests/scripts/run-optional-pdf-consumers.py", "tests/smoke/optional-pdf-python.py", "tests/smoke/optional-pdf-node.mjs",
                     "docs/proposals/optional-pdf-consumers.md", "docs/proposals/optional-pdf-consumers.workflow.yml.example"}, "Only approved source paths")
    need(sys.version_info[:2] == (3, 12), "Frozen Ubuntu Python profile")
    need(shutil.disk_usage(os.environ["RUNNER_TEMP"]).free >= 8 * 1024**3, "Runner storage admission")
    report["sourceFiles"] = vector()
    report["support"] = {"sha256": SUPPORT_SHA, "definitionsOnly": sorted(names), "oldMainExecuted": False}
    root = Path(tempfile.mkdtemp(prefix="ocr-optional-pdf-", dir=os.environ["RUNNER_TEMP"]))
    os.chmod(root, 0o700)
    identity = (root.stat().st_dev, root.stat().st_ino, root.stat().st_uid)
    nonce = secrets.token_hex(16)
    (root / ".owner").write_text(nonce)
    report["ownedRoot"] = {"path": str(root), "identity": list(identity), "nonce": nonce}
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                if entry.stat().st_uid == os.getuid():
                    baseline[entry.name] = (entry / "stat").read_text().rpartition(") ")[2].split()[19]
            except (FileNotFoundError, ProcessLookupError):
                pass
    consumer, artifacts, guards, fixtures = (root / name for name in ("consumer", "artifacts", "guards", "fixtures"))
    for directory in (consumer, artifacts, guards, fixtures, root / "cache", root / "config", root / "empty-bin"):
        directory.mkdir(mode=0o700)
    for name in ("npmrc", "npm-global"):
        (root / name).write_text("")
    (consumer / "package.json").write_text(json.dumps({"name": "authored-optional-pdf-consumer", "version": "0.0.0", "private": True, "type": "module"}))
    bootstrap = {key: os.environ[key] for key in ("PATH", "HOME", "RUNNER_TEMP")}
    bootstrap.update({"CI": "true", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1",
                      "npm_config_cache": str(root / "cache/npm"), "npm_config_userconfig": str(root / "npmrc"), "npm_config_globalconfig": str(root / "npm-global"),
                      "npm_config_update_notifier": "false", "PIP_CONFIG_FILE": "/dev/null", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                      "XDG_CACHE_HOME": str(root / "cache"), "XDG_CONFIG_HOME": str(root / "config"), "PDF_FIXTURES": str(fixtures)})
    node = shutil.which("node")
    report["runtime"] = {"python": sys.version, "node": run([node, "--version"])[0].decode().strip()}
    need(report["runtime"]["node"] == "v24.21.0", "Pinned Node profile")
    guard("before-downloads")
    report["downloads"] = [download(name) for name in ASSETS]
    run([sys.executable, "-m", "venv", "--copies", str(root / "venv")])
    python = str(root / "venv/bin/python")
    wheel = "ocr_gateway_client-0.2.0-py3-none-any.whl"
    run([python, "-m", "pip", "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", str(artifacts / wheel), str(artifacts / PDF_WHEEL)], timeout=120)
    tgz = "alvarovillalbaa-ocr-gateway-0.2.0.tgz"
    run([shutil.which("npm"), "install", "--ignore-scripts", "--no-audit", "--no-fund", "--omit=peer", str(artifacts / tgz)], timeout=120)
    installed = consumer / "node_modules/@alvarovillalbaa/ocr-gateway"
    expected = {}
    with tarfile.open(artifacts / tgz, "r:gz") as archive:
        for item in archive:
            parts = archive_name(item.name).parts
            need(parts[0] == "package" and (item.isfile() or item.isdir()), "Node archive type")
            if item.isfile():
                name = str(PurePosixPath(*parts[1:]))
                need(name not in expected and item.size < 4 * 1024**2, "Node archive bounds")
                data = archive.extractfile(item).read()
                expected[name] = {"bytes": len(data), "sha256": sha(data)}
    need(inventory(installed) == expected, "Installed Node archive bytes")
    site = root / "venv/lib/python3.12/site-packages"
    for name in (wheel, PDF_WHEEL):
        count = total = 0
        with zipfile.ZipFile(artifacts / name) as archive:
            for item in archive.infolist():
                member = str(archive_name(item.filename))
                if item.is_dir() or member.endswith(".dist-info/RECORD"):
                    continue
                need(item.file_size <= 128 * 1024**2, "Wheel member bound")
                data = archive.read(item)
                count += 1
                total += len(data)
                need(count < 1000 and total < 256 * 1024**2, "Wheel expansion bound")
                need((site / member).is_file() and sha((site / member).read_bytes()) == sha(data), "Installed wheel bytes")
        report.setdefault("installedWheels", {})[name] = {"members": count, "bytes": total, "allOriginalMembersMatched": True}
    installed_before = {"node": inventory(installed), "pythonSite": inventory(site)}
    report["installedBefore"] = installed_before
    for source_name, target_name in (("tests/smoke/optional-pdf-python.py", "optional-pdf.py"), ("tests/smoke/optional-pdf-node.mjs", "optional-pdf.mjs")):
        shutil.copyfile(repo / source_name, consumer / target_name)
    for source_name, target_name in (("tests/helpers/fresh-consumer-sitecustomize.py", "sitecustomize.py"), ("tests/helpers/fresh-consumer-network.cjs", "network.cjs")):
        shutil.copyfile(repo / source_name, guards / target_name)
    run([python, "optional-pdf.py", "create-fixtures"])
    report["fixtures"] = inventory(fixtures)
    runtime = {**bootstrap, "PATH": str(root / "empty-bin"), "FRESH_ROOT": str(root), "FRESH_NETWORK_AUDIT": str(root / "network.jsonl"),
               "NODE_OPTIONS": "--require=" + str(guards / "network.cjs"), "PYTHONPATH": str(guards), "PDF_NODE_PACKAGE": str(installed), "OCR_GATEWAY_PYTHON": python}
    guard("before-new-pdf-identities")
    for identity_name, argv in (("P01", [python, "optional-pdf.py", "P01"]), ("P02", [node, "optional-pdf.mjs"]), ("P03", [python, "optional-pdf.py", "P03"])):
        observation = json.loads(run(argv, env=runtime)[0])
        need(observation["identity"] == identity_name and observation["passed"] is True, "PDF identity result")
        report["checks"][identity_name] = observation
    request = {"name": "invalid.pdf", "mimeType": "application/pdf", "dataBase64": base64.b64encode((fixtures / "invalid.pdf").read_bytes()).decode()}
    stdout, stderr = run([python, "-m", "ocr_gateway.local"], env=runtime, stdin=json.dumps(request).encode(), expected_exit=1)
    need(stdout == b"" and json.loads(stderr) == {"error": {"code": "LOCAL_PARSE_ERROR", "message": "Local document parsing failed"}}, "Malformed PDF generic refusal")
    need(b"AUTHORED_PRIVATE_FAILURE_MARKER" not in stderr, "Malformed PDF contents leaked")
    report["checks"]["P04"] = {"identity": "P04", "passed": True, "expectedExit": 1, "originalStderr": json.loads(stderr), "documentMarkerNotEchoed": True}
    need(inventory(fixtures) == report["fixtures"] and {"node": inventory(installed), "pythonSite": inventory(site)} == installed_before, "Runtime inputs changed")
    need(all(sha((artifacts / name).read_bytes()) == digest for name, (_, digest) in ASSETS.items()), "Public archive changed")
    report["runtimeNetwork"] = [json.loads(line) for line in (root / "network.jsonl").read_text().splitlines()] if (root / "network.jsonl").exists() else []
    need(report["runtimeNetwork"] == [], "Unexpected runtime networking")
    need(shutil.disk_usage(root).free >= 2 * 1024**3, "Runner reserve")
    guard("after-new-pdf-identities")
    status = 0
except BaseException as error:
    report["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
finally:
    if root is not None:
        try:
            report["cleanup"]["directGroups"] = [{"pid": process.pid, "reaped": process.poll() is not None, "liveAbsent": not group_live(process.pid)} for process in groups]
            remaining = owned_descendants()
            report["cleanup"]["ownedDescendants"] = remaining
            need(not remaining and all(r["reaped"] and r["liveAbsent"] for r in report["cleanup"]["directGroups"]), "Owned process remains; scratch preserved")
            guard("after-owned-shutdown")
            need((root.stat().st_dev, root.stat().st_ino, root.stat().st_uid) == identity and (root / ".owner").read_text() == nonce, "Root ownership")
            leaves = []
            for path in sorted(root.rglob("*")):
                info = path.lstat()
                need(info.st_uid == os.getuid(), "Unexpected owned-tree uid")
                if path.is_symlink():
                    need(path.resolve().is_relative_to(root), "External installed symlink")
                    leaves.append({"path": str(path.relative_to(root)), "symlink": os.readlink(path)})
                elif path.is_file():
                    body = path.read_bytes()
                    leaves.append({"path": str(path.relative_to(root)), "bytes": len(body), "sha256": sha(body)})
                else:
                    need(path.is_dir(), "Special scratch file")
            need(sum(row.get("bytes", 0) for row in leaves) < 1024**3 and len(leaves) < 10000, "Owned tree budget")
            report["cleanup"]["ownedLeafVector"] = leaves
            report["cleanup"]["ownedLeafVectorSha256"] = sha(json.dumps(leaves, sort_keys=True, separators=(",", ":")).encode())
            shutil.rmtree(root)
            report["cleanup"]["rootAbsent"] = not root.exists()
            guard("after-owned-root-removal")
        except BaseException:
            report["cleanup"]["failure"] = traceback.format_exc()
            status = 1
    report["finishedAt"] = time.time()
    report["exitCode"] = status
    report["accepted"] = status == 0 and set(report["checks"]) == {"P01", "P02", "P03", "P04"} and report["cleanup"].get("rootAbsent") is True
    report["limits"] = ["Four authored PDF cases on one pinned Linux/Python/PyMuPDF profile; no image/scanned OCR quality or arbitrary-PDF safety claim.",
                        "Runtime network tripwires are application observations, not a kernel sandbox.",
                        "Owned process samples and normal closures do not independently trace every short-lived descendant or attest whole-host disposal.",
                        "No live provider/model, registry, browser, paid service, database, product dependency or release change."]
    output = Path(os.environ["RUNNER_TEMP"]) / ("ocr-optional-pdf-" + os.environ["GITHUB_RUN_ID"] + ".json")
    raw = json.dumps(report, separators=(",", ":"), ensure_ascii=True).encode()
    need(len(raw) <= 8 * 1024**2, "Receipt bound")
    with output.open("xb") as handle:
        handle.write(raw)
    print("OCR_PDF_RECEIPT", json.dumps({"path": str(output), "bytes": len(raw), "sha256": sha(raw), "accepted": report["accepted"]}), flush=True)
raise SystemExit(status)
