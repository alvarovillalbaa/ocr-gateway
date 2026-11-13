#!/usr/bin/env python3
"""Public-CI-only real raster OCR qualification; no closed suite replay."""
import ast
import base64
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import secrets
import shutil
import signal
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
PARENT = "3eaf9945c474aff9b76ad65a16da26c57d597394"
PRIOR_SOURCE = "0a6f41376597e47a4f8abde8f3d59432e0971824"
SECOND_SOURCE = "98b2892f93d1128c05167cd429a50c7bc18dc16f"
BRANCH = "qa/ocr-raster-local-20261113-4"
PRIOR_RECEIPT_SHA = "a37184b3936dea954fa5f49f3afd87adec852685bcdddabda8dea250a024c86b"
THIRD_RECEIPT_SHA = "2fc8f90b47f407dab9b95360b7cbde58037d7fca2655577fb6da2c9ec1abce72"
RUNTIME_SHA = "d128d3ee5410c8a1ee8c2ccc188259ba25ead0a873f4c961678ec1f9c1f1a316"
PROTOCOL_SHA = "ec97ea9368b06251030887705f1ab62661c6fd594355ef0e39a489dc25999f29"
R01_CAPTURE = """import json,runpy,sys
try:
    runpy.run_path('raster-local.py',run_name='__main__')
except BaseException:
    current=sys.exc_info()[2]
    while current is not None:
        if current.tb_frame.f_code.co_filename.endswith('raster-local.py') and 'result' in current.tb_frame.f_locals:
            print('OCR_RASTER_RETURNED_RESULT='+json.dumps(current.tb_frame.f_locals['result'],ensure_ascii=True),flush=True)
            break
        current=current.tb_next
    raise
"""
MAX_STREAM = 1024 * 1024
repo = Path.cwd()
source = os.environ.get("SOURCE_COMMIT", "")
root = None
groups, baseline, owned_processes, leader_starts = [], {}, {}, {}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
deadline = time.monotonic() + max(0, 900 - (time.time() - float(os.environ.get("RASTER_STARTED_EPOCH", "0"))))
report = {"schemaVersion": 1, "repository": REPO, "sourceCommit": source, "parent": PARENT, "startedAt": time.time(),
          "checks": {}, "commands": [], "sourceGuards": [], "downloads": [], "cleanup": {}, "closedCasesReplayed": False}

# Load only explicit hash-bound operational definitions, never either old body.
for path, expected, names in (
    ("tests/scripts/run-fresh-public-consumers.py", "311cdf102efe1162be64bebad16b9c875371404b9539ac88bfc9cf7c130668f9",
     {"need", "capture", "vector", "guard", "group_live", "archive_name", "inventory"}),
):
    raw = (repo / path).read_bytes()
    if sha(raw) != expected:
        raise RuntimeError("Trusted operational source changed: " + path)
    nodes = [node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef) and node.name in names]
    if {node.name for node in nodes} != names:
        raise RuntimeError("Operational definition set changed")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(repo / path), "exec"), globals())


def process_row(entry):
    fields = (entry / "stat").read_text().rpartition(") ")[2].split()
    return {"pid": int(entry.name), "parentPid": int(fields[1]), "pgid": int(fields[2]),
            "sessionId": int(fields[3]), "startTime": fields[19], "state": fields[0]}


def owned_descendants():
    """Attribute public process metadata by anchored ancestry/groups, never environ."""
    rows, fatal = {}, []
    known_leaders = {process.pid for process in groups}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            if entry.stat().st_uid != os.getuid():
                continue
            row = process_row(entry)
            if baseline.get(entry.name) != row["startTime"]:
                rows[row["pid"]] = row
        except (FileNotFoundError, ProcessLookupError):
            pass
        except PermissionError as error:
            diagnostic = {"pid": int(entry.name), "surface": "public-stat", "error": str(error)}
            report.setdefault("processObservationErrors", []).append(diagnostic)
            if int(entry.name) in known_leaders or int(entry.name) in owned_processes:
                fatal.append({**diagnostic, "inspectionDenied": True})
    attributed = {pid for pid, row in rows.items()
                  if leader_starts.get(pid) == row["startTime"] or owned_processes.get(pid) == row["startTime"]}
    while True:
        expanded = attributed | {pid for pid, row in rows.items()
                                 if row["parentPid"] == os.getpid() or row["parentPid"] in attributed
                                 or row["pgid"] in attributed or row["sessionId"] in attributed}
        if expanded == attributed:
            break
        attributed = expanded
    result = []
    for pid in sorted(attributed):
        row = rows[pid]
        owned_processes[pid] = row["startTime"]
        if row["state"] != "Z":
            result.append({key: value for key, value in row.items() if key != "state"})
    return result + fatal


def run(argv, *, env=None, stdin=None, expected_exit=0, timeout=90):
    row = {"argv": argv, "expectedExit": expected_exit, "startedAt": time.time()}
    report["commands"].append(row)
    output, errors = root / f"command-{len(report['commands'])}.out", root / f"command-{len(report['commands'])}.err"
    seen, observer_error = {}, None
    process = None
    try:
        with output.open("xb") as stdout, errors.open("xb") as stderr:
            os.chmod(output, 0o600)
            os.chmod(errors, 0o600)
            process = subprocess.Popen(argv, cwd=consumer, env=env or bootstrap, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            groups.append(process)
            row["pid"] = process.pid
            try:
                started = process_row(Path("/proc") / str(process.pid))
                leader_starts[process.pid] = started["startTime"]
                row["startTime"] = started["startTime"]
            except (FileNotFoundError, ProcessLookupError):
                row["startTimeObservation"] = "already absent"
            except PermissionError:
                observer_error = traceback.format_exc()
            if stdin is not None:
                process.stdin.write(stdin)
                process.stdin.close()
            end = min(deadline, time.monotonic() + timeout)
            while process.poll() is None:
                if observer_error is None:
                    try:
                        for observation in owned_descendants():
                            need("inspectionDenied" not in observation, "Owned public process metadata denied")
                            seen[(observation["pid"], observation["startTime"])] = observation
                    except BaseException:
                        # Preserve the actual child outcome before any observer refusal.
                        # Do not retry a denied surface during this command.
                        observer_error = traceback.format_exc()
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
    finally:
        if process is not None and process.poll() is not None:
            row.update({"exitCode": process.returncode, "reaped": True, "outputDescriptorsClosed": True,
                        "stdout": capture(output.read_bytes()), "stderr": capture(errors.read_bytes()),
                        "observedProcesses": list(seen.values()), "observerError": observer_error})
    end = time.monotonic() + 2
    pgids = {process.pid} | {observation["pgid"] for observation in seen.values()}
    while any(group_live(pgid) for pgid in pgids) and time.monotonic() < end:
        time.sleep(.05)
    row["observedGroupsAbsent"] = all(not group_live(pgid) for pgid in pgids)
    print("OCR_RASTER_COMMAND", json.dumps({"ordinal": len(report["commands"]), "exitCode": process.returncode}), flush=True)
    need(observer_error is None, "Owned process observer refused after retaining child originals")
    need(row["observedGroupsAbsent"] and row["stdout"]["complete"] and row["stderr"]["complete"], "Command stream/process closure")
    need(process.returncode == expected_exit and not row.get("timedOut"), "Unexpected command exit")
    return output.read_bytes(), errors.read_bytes()


class AnonymousRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        target = urlsplit(newurl)
        need(target.scheme == "https" and target.hostname in ("github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com", "files.pythonhosted.org")
             and target.port in (None, 443) and not target.username and not target.password and not target.fragment, "Unexpected artifact redirect")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch(name, url, limit, *, expected_sha=None, expected_bytes=None):
    parts = urlsplit(url)
    need(parts.scheme == "https" and parts.hostname in ("github.com", "files.pythonhosted.org", "pypi.org", "archive.ubuntu.com")
         and not parts.username and not parts.password and parts.port in (None, 443) and not parts.query and not parts.fragment, "Public download origin")
    start, body = time.monotonic(), bytearray()
    with build_opener(ProxyHandler({}), AnonymousRedirect()).open(Request(url, headers={"User-Agent": "OCR-Gateway-authored-raster"}), timeout=20) as response:
        need(response.status == 200, "Download status")
        while True:
            need(time.monotonic() - start <= 90 and time.monotonic() < deadline, "Download total bound")
            chunk = response.read(min(65536, limit + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
            need(len(body) <= limit, "Download size bound")
    raw = bytes(body)
    need(expected_sha is None or sha(raw) == expected_sha, "Download SHA256")
    need(expected_bytes is None or len(raw) == expected_bytes, "Download exact size")
    with (artifacts / name).open("xb") as handle:
        handle.write(raw)
    report["downloads"].append({"name": name, "url": url, "bytes": len(raw), "sha256": sha(raw), "authorizationSent": False, "bodyEOFObserved": True, "responseClosed": True})
    return raw


def leaf_vector(directory):
    rows = []
    for path in sorted(directory.rglob("*")):
        info = path.lstat()
        need(info.st_uid == os.getuid(), "Owned tree uid")
        if path.is_symlink():
            need(path.resolve().is_relative_to(root), "External owned-tree symlink")
            rows.append({"path": str(path.relative_to(directory)), "symlink": os.readlink(path)})
        elif path.is_file():
            body = path.read_bytes()
            rows.append({"path": str(path.relative_to(directory)), "bytes": len(body), "sha256": sha(body)})
        else:
            need(path.is_dir(), "Special owned-tree leaf")
    need(len(rows) <= 20000 and sum(row.get("bytes", 0) for row in rows) <= 2 * 1024**3, "Owned tree budget")
    return rows


def prepare_apt():
    apt = root / "apt"
    for name in ("etc/parts", "etc/sources", "state/lists/partial", "cache/archives/partial", "log"):
        (apt / name).mkdir(parents=True, mode=0o700)
    (apt / "state/status").write_text("")
    source_line = "deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble main universe\n"
    need(runtime_supplement["additional_signed_sources"] == [{"archive": "https://archive.ubuntu.com/ubuntu", "suite": "noble-updates", "components": ["main"], "signed_by": "/usr/share/keyrings/ubuntu-archive-keyring.gpg"}], "Exact supplementary signed source")
    source_line += "deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble-updates main\n"
    (apt / "etc/sources.list").write_text(source_line)
    options = {
        "Dir": str(apt), "Dir::Etc": str(apt / "etc"), "Dir::Etc::main": "/dev/null", "Dir::Etc::parts": str(apt / "etc/parts"),
        "Dir::Etc::sourcelist": str(apt / "etc/sources.list"), "Dir::Etc::sourceparts": str(apt / "etc/sources"),
        "Dir::State": str(apt / "state"), "Dir::State::lists": str(apt / "state/lists"), "Dir::State::status": str(apt / "state/status"),
        "Dir::Cache": str(apt / "cache"), "Dir::Cache::archives": str(apt / "cache/archives"), "Dir::Log": str(apt / "log"),
        "Dir::Bin::Methods": "/usr/lib/apt/methods", "Dir::Bin::dpkg": "/usr/bin/dpkg", "Dir::Bin::gpgv": "/usr/bin/gpgv",
        "Acquire::Languages": "none", "Acquire::Retries": "0", "Acquire::https::Timeout": "30", "Acquire::http::Timeout": "30",
        "Acquire::AllowInsecureRepositories": "false", "Acquire::AllowDowngradeToInsecureRepositories": "false", "APT::Get::AllowUnauthenticated": "false",
        "Acquire::IndexTargets::deb::DEP-11::DefaultEnabled": "false", "Acquire::IndexTargets::deb::CNF::DefaultEnabled": "false",
    }
    config = "\n".join(key + " " + json.dumps(value) + ";" for key, value in options.items()) + "\n"
    (apt / "apt.conf").write_text(config)
    apt_env = {**bootstrap, "APT_CONFIG": str(apt / "apt.conf")}
    dump = run(["apt-config", "dump"], env=apt_env)[0].decode()
    need("Post-Invoke" not in dump and "Pre-Invoke" not in dump, "Unexpected global APT hooks")
    run(["apt-get", "update", "--error-on=any"], env=apt_env, timeout=180)
    report["apt"] = {"privateConfiguration": config, "sources": source_line, "globalHooksLoaded": False, "installOrMaintainerScriptExecuted": False,
                     "authenticatedUpdateCommand": len(report["commands"]) - 1, "indexes": leaf_vector(apt / "state/lists"),
                     "ubuntuArchiveKeyringSha256": sha(Path("/usr/share/keyrings/ubuntu-archive-keyring.gpg").read_bytes()), "packages": []}
    for expected in protocol["apt"]["packages"] + runtime_supplement["additional_packages"]:
        raw = run(["apt-cache", "show", expected["name"] + "=" + expected["version"]], env=apt_env)[0]
        stanzas = [part for part in raw.decode().strip().split("\n\n") if part.strip()]
        need(len(stanzas) == 1, "One exact signed-index package record")
        fields = dict(line.split(": ", 1) for line in stanzas[0].splitlines() if line and not line[0].isspace() and ": " in line)
        need(fields["Package"] == expected["name"] and fields["Version"] == expected["version"] and fields["Architecture"] == expected["architecture"], "Exact predeclared package version/architecture")
        filename = str(archive_name(fields["Filename"]))
        need(filename.startswith("pool/") and re.fullmatch(r"[a-f0-9]{64}", fields["SHA256"]), "Signed package identity fields")
        size = int(fields["Size"])
        if expected["name"] in prior_packages:
            prior_package = prior_packages[expected["name"]]
            need(prior_package["filename"] == filename and prior_package["sha256"] == fields["SHA256"] and prior_package["bytes"] == size,
                 "Previously observed exact native package identity")
        else:
            need(expected == {"name": "libgif7", "version": "5.2.2-1ubuntu1.2", "architecture": "amd64"}, "Only fixed GIF decoder addition")
        previous = third_packages[expected["name"]]
        need(previous["filename"] == filename and previous["sha256"] == fields["SHA256"] and previous["bytes"] == size,
             "All six prior observed native identities unchanged")
        need(0 < size < 32 * 1024**2, "Package size bound")
        name = PurePosixPath(filename).name
        fetch(name, "https://archive.ubuntu.com/ubuntu/" + filename, size, expected_sha=fields["SHA256"], expected_bytes=size)
        run(["dpkg-deb", "--extract", str(artifacts / name), str(native)])
        report["apt"]["packages"].append({**expected, "filename": filename, "bytes": size, "sha256": fields["SHA256"], "metadataOriginalCommand": len(report["commands"]) - 2})
    return native / "usr/bin/tesseract"


def installed_wheel(name):
    count = total = 0
    with zipfile.ZipFile(artifacts / name) as archive:
        for item in archive.infolist():
            member = str(archive_name(item.filename))
            if item.is_dir() or member.endswith(".dist-info/RECORD"):
                continue
            need(item.file_size <= 128 * 1024**2, "Wheel member bound")
            body = archive.read(item)
            count += 1
            total += len(body)
            need(count < 2000 and total < 256 * 1024**2 and (site / member).is_file() and sha((site / member).read_bytes()) == sha(body), "Original installed wheel member")
    report.setdefault("installedWheels", {})[name] = {"members": count, "bytes": total, "allOriginalMembersMatched": True}


status = 1
try:
    need(os.environ.get("CI") == "true" and os.environ.get("GITHUB_REPOSITORY") == REPO, "Public CI only")
    need(os.environ.get("GITHUB_EVENT_NAME") == "create" and os.environ.get("GITHUB_REF") == "refs/heads/" + BRANCH, "Exact event/ref")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    need(event["ref_type"] == "branch" and event["ref"] == BRANCH and event["repository"]["private"] is False, "Public branch event")
    need(subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip() == source and subprocess.check_output(["git", "rev-parse", "HEAD^"], text=True).strip() == PARENT, "Exact prepared source/parent")
    repair_paths = {"AGENTS.md", "tests/scripts/run-raster-local.py", "docs/proposals/raster-local-v1.md", "docs/proposals/raster-local-v1.workflow.yml.example",
                    "tests/helpers/raster_fixtures.py", "docs/results/2026/11-13/raster-local-attempt-3.json", "docs/results/2026/11-13/raster-local-attempt-3.zip",
                    "docs/results/2026/11-13/raster-local-attempt-3.md"}
    changes = set(subprocess.check_output(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"], text=True).splitlines())
    need(changes == repair_paths, "Exact changed control/evidence paths only")
    need((repo / "AGENTS.md").read_bytes().startswith(subprocess.check_output(["git", "show", PARENT + ":AGENTS.md"])), "Append-only instructions")
    previous_helper = subprocess.check_output(["git", "show", PARENT + ":tests/helpers/raster_fixtures.py"])
    need(previous_helper.count(b'"authored.tiff").open("xb")') == 1 and
         (repo / "tests/helpers/raster_fixtures.py").read_bytes() == previous_helper.replace(b'"authored.tiff").open("xb")', b'"authored.tiff").open("x+b")'),
         "Exclusive read/write TIFF handle is the only fixture-writer change")
    need(sys.version_info[:2] == (3, 12) and platform.machine() == "x86_64", "Predeclared Python/platform")
    protocol_raw = (repo / "docs/studies/raster-local-v1.json").read_bytes()
    need(sha(protocol_raw) == PROTOCOL_SHA, "Predeclared raster protocol bytes")
    protocol = json.loads(protocol_raw)
    runtime_raw = (repo / "docs/studies/raster-runtime-v2.json").read_bytes()
    need(sha(runtime_raw) == RUNTIME_SHA, "Frozen runtime supplement")
    runtime_supplement = json.loads(runtime_raw)
    need(runtime_supplement["raster_protocol_sha256"] == PROTOCOL_SHA and runtime_supplement["additional_packages"] == [{"name": "libgif7", "version": "5.2.2-1ubuntu1.2", "architecture": "amd64"}], "Exact runtime-only addition")
    second_raw = (repo / "docs/results/2026/11-13/raster-local-attempt-2.json").read_bytes()
    need(sha(second_raw) == runtime_supplement["observed_failure"]["receipt_sha256"], "Original second failed receipt")
    second = json.loads(second_raw)
    need(second["sourceCommit"] == SECOND_SOURCE and second["accepted"] is False and second["checks"] == {} and "recognitionFreeze" not in second,
         "No prior model/case result carried")
    third_raw = (repo / "docs/results/2026/11-13/raster-local-attempt-3.json").read_bytes()
    need(sha(third_raw) == THIRD_RECEIPT_SHA, "Original third failed receipt")
    third = json.loads(third_raw)
    need(third["sourceCommit"] == PARENT and third["accepted"] is False and third["checks"] == {} and "recognitionFreeze" not in third,
         "No third recognition/case result carried")
    third_packages = {row["name"]: row for row in third["apt"]["packages"]}
    need(set(third_packages) == {row["name"] for row in protocol["apt"]["packages"] + runtime_supplement["additional_packages"]}, "Exact six native identities")
    previous_png = next(row for row in third["cleanup"]["ownedLeafVector"] if row["path"] == "fixtures/authored.png")
    prior_raw = (repo / "docs/results/2026/11-13/raster-local-attempt-1.json").read_bytes()
    need(sha(prior_raw) == PRIOR_RECEIPT_SHA, "Original first failed receipt")
    prior = json.loads(prior_raw)
    need(prior["sourceCommit"] == PRIOR_SOURCE and prior["accepted"] is False and prior["checks"] == {} and "recognitionFreeze" not in prior,
         "No prior OCR case or result carried")
    prior_packages = {row["name"]: row for row in prior["apt"]["packages"]}
    need(set(prior_packages) == {row["name"] for row in protocol["apt"]["packages"]}, "Exact prior native package set")
    need(shutil.disk_usage(os.environ["RUNNER_TEMP"]).free >= 8 * 1024**3, "Runner storage admission")
    report["sourceFiles"] = vector()
    report["protocol"] = {"sha256": PROTOCOL_SHA, "original": capture(protocol_raw)}
    report["runtimeSupplement"] = {"sha256": RUNTIME_SHA, "original": capture(runtime_raw)}
    report["priorMetadataBinding"] = {"originalReceiptSha256": PRIOR_RECEIPT_SHA, "actualOcrCasesCarried": 0, "packages": prior_packages}
    report["fixtureIoRepair"] = {"originalReceiptSha256": THIRD_RECEIPT_SHA, "nativePackages": third_packages,
                                 "previousPng": previous_png, "actualOcrCasesCarried": 0, "onlyChange": "TIFF exclusive read/write file handle"}
    root = Path(tempfile.mkdtemp(prefix="ocr-raster-local-", dir=os.environ["RUNNER_TEMP"]))
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
    consumer, artifacts, guards, fixtures, native = (root / name for name in ("consumer", "artifacts", "guards", "fixtures", "native"))
    for directory in (consumer, artifacts, guards, fixtures, native, root / "cache", root / "config", root / "temp"):
        directory.mkdir(mode=0o700)
    for name in ("npmrc", "npm-global"):
        (root / name).write_text("")
    (root / "protocol.json").write_bytes(protocol_raw)
    (consumer / "package.json").write_text(json.dumps({"name": "authored-raster-integration", "version": "0.0.0", "private": True, "type": "module"}))
    bootstrap = {key: os.environ[key] for key in ("PATH", "HOME", "RUNNER_TEMP")}
    bootstrap.update({"CI": "true", "LANG": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1", "NO_COLOR": "1", "TMPDIR": str(root / "temp"),
                      "FRESH_ROOT": str(root), "npm_config_cache": str(root / "cache/npm"), "npm_config_userconfig": str(root / "npmrc"),
                      "npm_config_globalconfig": str(root / "npm-global"), "npm_config_update_notifier": "false", "PIP_CONFIG_FILE": "/dev/null", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                      "XDG_CACHE_HOME": str(root / "cache"), "XDG_CONFIG_HOME": str(root / "config")})
    node, npm = shutil.which("node"), shutil.which("npm")
    report["runtime"] = {"python": sys.version, "node": run([node, "--version"])[0].decode().strip(), "platform": platform.platform()}
    need(report["runtime"]["node"] == "v24.21.0", "Pinned Node profile")
    guard("before-public-inputs")
    base = "https://github.com/" + REPO + "/releases/download/v0.2.0-native-charts.1/"
    tgz, wheel = "alvarovillalbaa-ocr-gateway-0.2.0.tgz", "ocr_gateway_client-0.2.0-py3-none-any.whl"
    fetch(tgz, base + tgz, 83978, expected_bytes=83978, expected_sha="4775f9503ac09d94e9c2a39ea9381c162b7f41e527c8516e1e8d381e500890d4")
    fetch(wheel, base + wheel, 26079, expected_bytes=26079, expected_sha="f7b32a418cfb3b4a872b25a582fc8941dd070dfe957f2aeb36fb936a0b996ded")
    pdf_wheel = "pymupdf-1.26.6-cp310-abi3-manylinux_2_28_x86_64.whl"
    fetch(pdf_wheel, "https://files.pythonhosted.org/packages/4f/bf/6e02e3d84b32c137c71a0a3dcdba8f2f6e9950619a3bc272245c7c06a051/" + pdf_wheel,
          24115381, expected_bytes=24115381, expected_sha=protocol["pymupdf"]["sha256"])
    pillow_meta = fetch("pillow-metadata.json", protocol["pillow"]["metadata_url"], 262144)
    meta = json.loads(pillow_meta)
    matches = [row for row in meta["urls"] if row["filename"] == protocol["pillow"]["filename"]]
    need(meta["info"]["version"] == protocol["pillow"]["version"] and len(matches) == 1, "Exact Pillow version/file")
    selected = matches[0]
    need(selected["digests"]["sha256"] == protocol["pillow"]["sha256"] and not selected["yanked"] and selected["size"] <= protocol["pillow"]["max_bytes"], "Pinned Pillow metadata")
    pillow_wheel = selected["filename"]
    need(urlsplit(selected["url"]).hostname == "files.pythonhosted.org" and urlsplit(selected["url"]).path.endswith("/" + pillow_wheel), "Pillow file origin")
    fetch(pillow_wheel, selected["url"], selected["size"], expected_bytes=selected["size"], expected_sha=protocol["pillow"]["sha256"])
    report["pillowMetadataOriginal"] = capture(pillow_meta)
    executable = prepare_apt()
    run([sys.executable, "-m", "venv", "--copies", str(root / "venv")])
    python = str(root / "venv/bin/python")
    run([python, "-m", "pip", "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", *[str(artifacts / name) for name in (wheel, pdf_wheel, pillow_wheel)]], timeout=120)
    run([npm, "install", "--ignore-scripts", "--no-audit", "--no-fund", "--omit=peer", str(artifacts / tgz)], timeout=120)
    installed, site = consumer / "node_modules/@alvarovillalbaa/ocr-gateway", root / "venv/lib/python3.12/site-packages"
    expected_node = {}
    with tarfile.open(artifacts / tgz, "r:gz") as archive:
        for item in archive:
            parts = archive_name(item.name).parts
            need(parts[0] == "package" and (item.isfile() or item.isdir()), "Node archive type")
            if item.isfile():
                name = str(PurePosixPath(*parts[1:]))
                need(name not in expected_node and item.size < 4 * 1024**2, "Node archive bounds")
                body = archive.extractfile(item).read()
                expected_node[name] = {"bytes": len(body), "sha256": sha(body)}
    need(inventory(installed) == expected_node, "Original installed Node payload")
    for name in (wheel, pdf_wheel, pillow_wheel):
        installed_wheel(name)
    for source_name, target in (("tests/helpers/raster_fixtures.py", "raster_fixtures.py"), ("tests/integration/raster-local-python.py", "raster-local.py"), ("tests/integration/raster-local-node.mjs", "raster-local.mjs")):
        shutil.copyfile(repo / source_name, consumer / target)
    for source_name, target in (("tests/helpers/fresh-consumer-sitecustomize.py", "sitecustomize.py"), ("tests/helpers/fresh-consumer-network.cjs", "network.cjs")):
        shutil.copyfile(repo / source_name, guards / target)
    recognition_env = {**bootstrap, "PATH": str(native / "usr/bin"), "LD_LIBRARY_PATH": str(native / "usr/lib/x86_64-linux-gnu"),
                       "TESSDATA_PREFIX": str(native / "usr/share/tesseract-ocr/5/tessdata"), "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"}
    report["nativeDependencyOriginalCommand"] = len(report["commands"])
    ldd = run(["ldd", str(executable)], env={**recognition_env, "PATH": bootstrap["PATH"]})[0].decode()
    need("not found" not in ldd, "Resolved native dependencies")
    for library in ("libtesseract.so.5", "liblept.so.5", "libgif.so.7"):
        match = re.search(re.escape(library) + r"\s+=>\s+([^\s]+)", ldd)
        need(match is not None and Path(match.group(1)).resolve().is_relative_to(native), "Pinned private OCR library binding")
    libraries = sorted(set(re.findall(r"(?:=>\s+)?(/[^\s()]+)", ldd)))
    report["nativeDependencies"] = [{"path": str(Path(p).resolve()), "bytes": Path(p).stat().st_size, "sha256": sha(Path(p).read_bytes())} for p in libraries]
    version_command_index = len(report["commands"])
    version_out, version_err = run([str(executable), "--version"], env=recognition_env)
    need((version_out + version_err).decode().splitlines()[0] == "tesseract 5.3.4", "Actual pinned Tesseract")
    fixture_out = run([python, "raster_fixtures.py", str(fixtures), str(root / "protocol.json")], env=recognition_env)[0]
    report["fixtureAdmission"] = json.loads(fixture_out)
    need(report["fixtureAdmission"]["nativePdfText"] == "" and report["fixtureAdmission"]["pdfFonts"] == 0 and report["fixtureAdmission"]["pdfImages"] == 1, "Image-only PDF admission")
    report["fixtures"] = inventory(fixtures)
    need(report["fixtures"]["authored.png"] == {key: previous_png[key] for key in ("bytes", "sha256")}, "Previously rendered PNG bytes unchanged")
    report["fixtureOriginals"] = {}
    for name, identity_row in report["fixtures"].items():
        body = (fixtures / name).read_bytes()
        packed = gzip.compress(body, mtime=0)
        need(len(body) <= 4 * 1024**2 and len(packed) <= 1024**2 and sha(body) == identity_row["sha256"], "Full authored fixture retention bound")
        report["fixtureOriginals"][name] = {"encoding": "gzip-base64", "bytes": len(body), "sha256": sha(body), "compressedBytes": len(packed),
                                           "data": base64.b64encode(packed).decode(), "complete": True, "retained": True}
    installed_before = {"node": inventory(installed), "pythonSite": inventory(site)}
    native_before = leaf_vector(native)
    need(any(row["path"].endswith("eng.traineddata") for row in native_before), "Actual English traineddata")
    report["recognitionFreeze"] = {"beforeAnyRecognition": True, "utcEpoch": time.time(), "protocolSha256": PROTOCOL_SHA,
                                   "runtimeSupplementSha256": RUNTIME_SHA,
                                   "nativeVector": native_before, "installed": installed_before, "fixtures": report["fixtures"],
                                   "tesseractVersionOriginalCommand": version_command_index,
                                   "engineAndEnglishModelIdentityPolicy": "Exact predeclared versions from authenticated Ubuntu indexes; actual package/binary/model hashes frozen before the first OCR result, not claimed predeclared."}
    runtime = {**recognition_env, "FRESH_NETWORK_AUDIT": str(root / "network.jsonl"), "NODE_OPTIONS": "--require=" + str(guards / "network.cjs"),
               "PYTHONPATH": str(guards), "RASTER_FIXTURES": str(fixtures), "RASTER_PROTOCOL": str(root / "protocol.json"),
               "RASTER_NODE_PACKAGE": str(installed), "OCR_GATEWAY_PYTHON": python}
    guard("before-recognition")
    for case, argv in (("R01", [python, "-c", R01_CAPTURE]), ("R02", [node, "raster-local.mjs", "R02"])):
        observation = json.loads(run(argv, env=runtime)[0])
        need(observation["identity"] == case and observation["passed"] is True, "Actual raster identity")
        report["checks"][case] = observation
    cli_out = run([node, str(installed / "dist/cli.js"), "parse", "--file", str(fixtures / "scanned.pdf"), "--local", "--providers", "local", "--mode", "single"], env=runtime)[0]
    with (consumer / "scanned-cli.json").open("xb") as handle:
        handle.write(cli_out)
    report["scannedCliOriginalCommand"] = len(report["commands"]) - 1
    observation = json.loads(run([node, "raster-local.mjs", "R03"], env={**runtime, "RASTER_CLI_RESULT": str(consumer / "scanned-cli.json")})[0])
    need(observation["identity"] == "R03" and observation["passed"] is True and observation["result"] == json.loads(cli_out), "Actual installed CLI result bound")
    report["checks"]["R03"] = observation
    request = {"name": "invalid.png", "mimeType": "image/png", "dataBase64": base64.b64encode((fixtures / "invalid.png").read_bytes()).decode()}
    stdout, stderr = run([python, "-m", "ocr_gateway.local"], env=runtime, stdin=json.dumps(request).encode(), expected_exit=1)
    need(stdout == b"" and json.loads(stderr) == {"error": {"code": "LOCAL_PARSE_ERROR", "message": "Local document parsing failed"}} and b"AUTHORED_PRIVATE_RASTER_FAILURE_MARKER" not in stderr, "Actual malformed image refusal")
    report["checks"]["R04"] = {"identity": "R04", "passed": True, "actualExit": 1, "originalError": json.loads(stderr), "documentMarkerNotEchoed": True}
    need(inventory(fixtures) == report["fixtures"] and leaf_vector(native) == native_before and {"node": inventory(installed), "pythonSite": inventory(site)} == installed_before, "Recognition inputs/payloads unchanged")
    need((root / "protocol.json").read_bytes() == protocol_raw and all(sha((artifacts / row["name"]).read_bytes()) == row["sha256"] for row in report["downloads"]), "Frozen protocol/downloads unchanged")
    report["runtimeNetwork"] = [json.loads(line) for line in (root / "network.jsonl").read_text().splitlines()] if (root / "network.jsonl").exists() else []
    need(report["runtimeNetwork"] == [] and shutil.disk_usage(root).free >= 2 * 1024**3, "Network/reserve boundary")
    guard("after-recognition")
    status = 0
except BaseException as error:
    report["failure"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
finally:
    if root is not None:
        try:
            report["cleanup"]["directGroups"] = [{"pid": process.pid, "reaped": process.poll() is not None, "liveAbsent": not group_live(process.pid)} for process in groups]
            remaining = owned_descendants()
            report["cleanup"]["ownedDescendants"] = remaining
            need(not remaining and all(row["reaped"] and row["liveAbsent"] for row in report["cleanup"]["directGroups"]), "Owned process remains; scratch preserved")
            guard("after-owned-shutdown")
            need((root.stat().st_dev, root.stat().st_ino, root.stat().st_uid) == identity and (root / ".owner").read_text() == nonce, "Owned root identity")
            leaves = leaf_vector(root)
            report["cleanup"]["ownedLeafVector"] = leaves
            report["cleanup"]["ownedLeafVectorSha256"] = sha(json.dumps(leaves, sort_keys=True, separators=(",", ":")).encode())
            shutil.rmtree(root)
            report["cleanup"]["rootAbsent"] = not root.exists()
            guard("after-owned-root-removal")
        except BaseException:
            report["cleanup"]["failure"] = traceback.format_exc()
            status = 1
    report["exitCode"], report["finishedAt"] = status, time.time()
    report["accepted"] = status == 0 and set(report["checks"]) == {"R01", "R02", "R03", "R04"} and report["cleanup"].get("rootAbsent") is True
    report["limits"] = ["Real local Tesseract/English traineddata recognition on four authored cases; no hosted provider/model API or paid call.",
                        "Owned process attribution uses public stat ancestry/groups and stable PID start times; no process environ/cwd/cmdline reads. Unattributed metadata errors do not establish whole-host absence.",
                        "Original supervisor streams/application OCR text are retained; unchanged product suppresses native engine diagnostics and strips output-file edges. No complete native-engine transcript.",
                        "Simple fixed English raster fixtures do not establish general OCR accuracy, arbitrary-file security, visual understanding or all platforms.",
                        "Package identities are observed from authenticated signed indexes; hashes are frozen before recognition, not all predeclared before download.",
                        "Process/teardown samples do not trace every short-lived descendant or attest whole-host disposal; network tripwires are not a kernel sandbox."]
    raw = json.dumps(report, separators=(",", ":"), ensure_ascii=True).encode()
    need(len(raw) <= 8 * 1024**2, "Receipt size bound")
    output = Path(os.environ["RUNNER_TEMP"]) / ("ocr-raster-local-" + os.environ["GITHUB_RUN_ID"] + ".json")
    with output.open("xb") as handle:
        handle.write(raw)
    print("OCR_RASTER_RECEIPT", json.dumps({"path": str(output), "bytes": len(raw), "sha256": sha(raw), "accepted": report["accepted"]}), flush=True)
raise SystemExit(status)
