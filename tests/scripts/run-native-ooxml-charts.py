#!/usr/bin/env python3
"""Fixed public-CI installed-artifact check. Refuse local execution; stdlib only."""

import ast
import base64
import ctypes
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import secrets
import select
import selectors
import signal
import socket
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile


REPOSITORY = "alvarovillalbaa/ocr-gateway"
BRANCH = "refs/heads/qa/ocr-native-charts-20261108-1"
BASE = "68f97a0e3ce08afb16042f6ffabaab0bc8bd9997"
ACTIVE = ".github/workflows/native-ooxml-charts.yml"
INERT_SHA = "4dc2b9131619930e92ad603c52959cc6557d225ec00eca2435acd5d064ac29ab"
CONTROLLER = "tests/scripts/run-native-ooxml-charts.py"
PY_TEST = "tests/integration/test_native_ooxml_charts.py"
JS_TEST = "tests/integration/native-ooxml-charts.test.mjs"
FIXTURE = "tests/helpers/ooxml_chart_fixtures.py"
TEST_HASHES = {
    FIXTURE: "76e5c114c72808d508a055682f9a6500cc88bb89324404f4086b9d269de4d2ff",
    PY_TEST: "74a6a67e87102d95dfbaea9d5d1cac5c198e61793ccaf09c1629ff27e7f61981",
    JS_TEST: "1116bb4e7eb1d4b7153c35c00665e5b9978d07b04fe93b31d02cd6a318976c36",
}
ADDED = {ACTIVE, CONTROLLER, FIXTURE, PY_TEST, JS_TEST, "tests/README.md",
         "python/ocr_gateway/ooxml_charts.py", "docs/native-ooxml-charts.md",
         "docs/proposals/native-ooxml-chart-checks.md",
         "docs/proposals/native-ooxml-charts.workflow.yml.example",
         "docs/references/native-ooxml-chart-sources.md"}
MODIFIED = {"AGENTS.md", "README.md", "PROVIDERS.md", "API.md", "docs/architecture.md",
            "python/README.md", "package.json", "python/pyproject.toml", "src/server.ts",
            "src/cli.ts", "python/ocr_gateway/local.py", "src/core.ts", "src/index.ts",
            "src/types.ts", "src/local.ts", "scripts/generate-openapi.mjs"}
PREFIX = "OCR_NATIVE_OOXML_CHARTS_RESULT="
MIB = 1024 ** 2
MAX_STORAGE = 1024 * MIB
MAX_STREAM = MIB
MAX_GZIP = 8 * MIB
MAX_REPORT = 16 * MIB


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    need(name and not path.is_absolute() and ".." not in path.parts and "\\" not in name
         and all(ord(char) >= 32 and ord(char) != 127 for char in name), "unsafe_path")
    return name


def identity(path):
    value = path.lstat()
    return [value.st_dev, value.st_ino, value.st_uid, stat.S_IMODE(value.st_mode)]


class Check:
    def __init__(self):
        self.checkout = Path.cwd().resolve()
        self.report = {"schemaVersion": 1, "repository": REPOSITORY, "status": "failed",
                       "executed": True, "commands": [], "checks": {}, "cleanup": {"verified": False}}
        self.root = None
        self.known = None
        self.frozen = {}
        self.processes = {}
        self.direct = {}
        self.adopted_statuses = []
        self.ports = set()
        self.groups = set()
        self.signals = []
        self.report["ownedSignals"] = self.signals
        self.compressed = 0
        self.max_bytes = 0
        self.max_rss = 0
        self.max_processes = 0
        self.interrupted = None
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(number, self.interrupt)
        self.source = None
        self.start = time.monotonic()
        self.work_end = self.start + 900
        self.cleanup_end = self.start + 990
        self.env = {key: os.environ[key] for key in ("PATH", "HOME", "LANG", "LC_ALL") if key in os.environ}
        self.env.update({"CI": "true", "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_NOSYSTEM": "1",
                         "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                         "PIP_NO_INPUT": "1", "npm_config_audit": "false", "npm_config_fund": "false",
                         "NODE_OPTIONS": "--max-old-space-size=512"})

    def interrupt(self, number, _frame):
        self.interrupted = number
        self.report["interruptedBySignal"] = number

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.checkout, env=self.env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
        need(result.returncode == 0 and len(result.stdout) < 16 * MIB and len(result.stderr) < MAX_STREAM,
             "git_guard_failed:" + args[0])
        return result.stdout

    def guard(self, first=False):
        head = self.git("rev-parse", "HEAD").decode().strip()
        need(head == self.commit, "checkout_head_changed")
        need(not self.git("status", "--porcelain=v1", "--untracked-files=all", "--ignored"), "checkout_not_clean")
        tree = self.git("ls-tree", "-rz", "--full-tree", "HEAD").split(b"\0")
        index = self.git("ls-files", "--stage", "-z").split(b"\0")
        expected_index, vector = [], {}
        for entry in tree:
            if not entry:
                continue
            metadata, raw_name = entry.split(b"\t", 1)
            mode, kind, oid = metadata.split()
            name = safe_name(raw_name.decode("utf-8"))
            need(kind == b"blob" and mode in (b"100644", b"100755"), "source_nonregular_entry")
            path = self.checkout / name
            need(path.is_file() and not path.is_symlink(), "source_type_changed")
            need(identity(path)[2:] == [os.getuid(), 0o755 if mode == b"100755" else 0o644], "source_mode_or_owner")
            data = path.read_bytes()
            need(len(data) <= 4 * MIB and blob(data).encode() == oid, "source_blob_changed:" + name)
            expected_index.append(mode + b" " + oid + b" 0\t" + raw_name)
            vector[name] = {"blob": oid.decode(), "sha256": sha(data), "bytes": len(data), "identity": identity(path)}
        need(sorted(filter(None, index)) == sorted(expected_index), "index_tree_mismatch")
        need(sum(row["bytes"] for row in vector.values()) < 16 * MIB, "source_bound")
        need(vector[ACTIVE]["sha256"] == INERT_SHA, "inert_workflow_changed")
        if first:
            need(self.git("rev-list", "--parents", "-n", "1", head).decode().strip().split() == [head, BASE], "source_not_direct_child")
            changes = self.git("diff", "--name-status", BASE, head).decode().splitlines()
            need({tuple(row.split("\t")) for row in changes} == ({("A", p) for p in ADDED} | {("M", p) for p in MODIFIED}), "source_scope_changed")
            for name, expected in TEST_HASHES.items():
                need(vector[name]["sha256"] == expected, "test_source_pin:" + name)
            self.source = vector
            self.index = sha((self.checkout / ".git/index").read_bytes())
            self.report.update({"sourceCommit": head, "canonicalBaseCommit": BASE, "sourceVector": vector,
                                "inertWorkflowSha256": INERT_SHA, "indexSha256": self.index})
        else:
            need(vector == self.source and sha((self.checkout / ".git/index").read_bytes()) == self.index, "source_vector_changed")

    def admit(self):
        need(sys.platform == "linux" and os.environ.get("CI") == "true" and os.environ.get("GITHUB_ACTIONS") == "true", "public_ci_only")
        need(os.environ.get("GITHUB_REPOSITORY") == REPOSITORY and os.environ.get("GITHUB_REF") == BRANCH
             and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch", "workflow_scope")
        event_path = Path(os.environ["GITHUB_EVENT_PATH"])
        need(event_path.stat().st_size < MIB, "event_bound")
        event = json.loads(event_path.read_bytes())
        need(event["repository"]["private"] is False and event["repository"]["full_name"] == REPOSITORY, "public_repository_required")
        need(os.environ.get("GITHUB_WORKFLOW_REF") == REPOSITORY + "/" + ACTIVE + "@" + BRANCH, "workflow_ref_mismatch")
        self.report["github"] = {name: os.environ.get(name) for name in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA", "GITHUB_WORKFLOW_SHA", "GITHUB_WORKFLOW_REF", "GITHUB_REF")}
        need(len(sys.argv) == 3 and sys.argv[1] == "--source-commit" and re.fullmatch(r"[0-9a-f]{40}", sys.argv[2]), "fixed_source_argument")
        self.commit = sys.argv[2]
        need(os.environ.get("SOURCE_COMMIT") == self.commit, "source_env_mismatch")
        job_start = int(os.environ["OCR_CHART_JOB_STARTED_MS"]) / 1000
        elapsed = time.time() - job_start
        need(0 <= elapsed < 120, "job_start_or_checkout_bound")
        remaining = 1200 - elapsed - 30
        need(remaining >= 990, "insufficient_job_budget")
        self.cleanup_end = min(self.cleanup_end, self.start + remaining)
        self.guard(first=True)
        need(ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0, "subreaper_unavailable")
        runner = Path(os.environ["RUNNER_TEMP"]).resolve()
        need(runner.is_dir() and not runner.is_relative_to(self.checkout), "runner_temp_scope")
        os.umask(0o077)
        self.root = Path(tempfile.mkdtemp(prefix="ocr-native-charts-", dir=runner))
        self.root_identity = identity(self.root)
        self.nonce = secrets.token_hex(24)
        self.write("owner", self.nonce.encode())
        self.owner_identity = identity(self.root / "owner")
        for name in ("export", "cache", "tmp", "xdg", "artifacts", "consumer", "fixtures"):
            (self.root / name).mkdir(mode=0o700)
        self.write("npm-user.conf", b"")
        self.write("npm-global.conf", b"")
        self.env.update({"OCR_CHART_OWNER": self.nonce, "TMPDIR": str(self.root / "tmp"),
                         "XDG_CACHE_HOME": str(self.root / "xdg"), "XDG_CONFIG_HOME": str(self.root / "xdg"),
                         "XDG_DATA_HOME": str(self.root / "xdg"), "npm_config_cache": str(self.root / "cache"),
                         "npm_config_userconfig": str(self.root / "npm-user.conf"), "npm_config_globalconfig": str(self.root / "npm-global.conf"),
                         "PIP_CONFIG_FILE": "/dev/null"})
        self.known = self.snapshot()

    def write(self, name, data):
        path = self.root / safe_name(name)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with path.open("xb") as output:
            output.write(data)
        return path

    def snapshot(self):
        need(identity(self.root) == self.root_identity and self.root_identity[2:] == [os.getuid(), 0o700], "owner_root_changed")
        if hasattr(self, "owner_identity"):
            need(identity(self.root / "owner") == self.owner_identity and (self.root / "owner").read_text() == self.nonce, "owner_marker_changed")
        rows, total = {}, 0
        for parent, directories, files in os.walk(self.root, followlinks=False):
            for name in sorted(directories + files):
                path = Path(parent) / name
                rel = path.relative_to(self.root).as_posix()
                value = path.lstat()
                need(value.st_uid == os.getuid() and (stat.S_ISLNK(value.st_mode) or not stat.S_IMODE(value.st_mode) & 0o022), "owned_mode_or_uid:" + rel)
                row = {"identity": identity(path)}
                if stat.S_ISLNK(value.st_mode):
                    target = os.readlink(path)
                    resolved = path.resolve()
                    allowed_python = rel.startswith("venv/bin/python") and resolved.is_file() and str(resolved).startswith(("/usr/", "/opt/"))
                    need(resolved.is_relative_to(self.root) or allowed_python, "escaping_owned_symlink:" + rel)
                    row.update(type="symlink", target=target)
                elif stat.S_ISDIR(value.st_mode):
                    row["type"] = "directory"
                else:
                    need(stat.S_ISREG(value.st_mode) and value.st_nlink == 1, "owned_nonregular:" + rel)
                    total += value.st_size
                    need(value.st_size <= 512 * MIB and total <= MAX_STORAGE, "owned_storage_bound")
                    row.update(type="file", bytes=value.st_size, sha256=sha(path.read_bytes()))
                rows[rel] = row
                need(len(rows) <= 60_000, "owned_entry_bound")
        self.max_bytes = max(self.max_bytes, total)
        for prefix, frozen in self.frozen.items():
            need({p: row for p, row in rows.items() if p == prefix or p.startswith(prefix + "/")} == frozen, "frozen_owned_changed:" + prefix)
        return rows

    def freeze(self, prefix):
        rows = self.snapshot()
        selected = {name: row for name, row in rows.items() if name == prefix or name.startswith(prefix + "/")}
        need(bool(selected), "empty_freeze:" + prefix)
        self.frozen[prefix] = selected
        self.report.setdefault("frozen", {})[prefix] = selected
        self.known = rows

    def sample(self, enforce=True):
        rows = {}
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                if path.stat().st_uid != os.getuid():
                    continue
                parts = (path / "stat").read_text().rsplit(")", 1)[1].split()
                pid, parent, group, started = int(path.name), int(parts[1]), int(parts[2]), parts[19]
                environment = (path / "environ").read_bytes()
                cwd = os.readlink(path / "cwd")
                owned = b"OCR_CHART_OWNER=" + self.nonce.encode() + b"\0" in environment or cwd == str(self.root) or cwd.startswith(str(self.root) + "/")
                rows[pid] = (started, parent, group, owned, path)
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        changed = True
        while changed:
            changed = False
            for pid, (started, parent, group, owned, path) in list(rows.items()):
                if owned or self.processes.get(pid) == started or (parent in rows and rows[parent][3]):
                    if not owned:
                        rows[pid] = (started, parent, group, True, path)
                        changed = True
                    self.processes[pid] = started
        live, rss, sockets = [], 0, set()
        for pid, (started, parent, group, owned, path) in rows.items():
            if not owned:
                continue
            live.append(pid)
            self.groups.add(group)
            try:
                rss += int((path / "statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
                for descriptor in (path / "fd").iterdir():
                    try:
                        target = os.readlink(descriptor)
                        if target.startswith("socket:["):
                            sockets.add(target[8:-1])
                    except (FileNotFoundError, PermissionError):
                        pass
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                pass
        for name in ("tcp", "tcp6"):
            for line in (Path("/proc/net") / name).read_text().splitlines()[1:]:
                fields = line.split()
                if fields[3] == "0A" and fields[9] in sockets:
                    self.ports.add((name, int(fields[1].split(":")[1], 16)))
        self.max_rss, self.max_processes = max(self.max_rss, rss), max(self.max_processes, len(live))
        if enforce:
            need(rss <= 2 * 1024 * MIB and len(live) <= 64, "owned_process_resource_bound")
        return live

    def kill_owned(self):
        end = min(self.cleanup_end, time.monotonic() + 10)
        for sig in (signal.SIGTERM, signal.SIGKILL):
            for pid in self.sample(enforce=False):
                try:
                    # Recheck the Linux process start identity before signalling.
                    current = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()[19]
                    if self.processes.get(pid) == current:
                        os.kill(pid, sig)
                        need(len(self.signals) < 256, "owned_signal_receipt_bound")
                        self.signals.append({"pid": pid, "startIdentity": current, "signal": int(sig)})
                except (FileNotFoundError, ProcessLookupError):
                    pass
            until = min(end, time.monotonic() + 2)
            while time.monotonic() < until:
                self.reap()
                if not self.sample(enforce=False):
                    return
                time.sleep(0.05)
        need(not self.sample(enforce=False), "owned_process_survived")

    def reap(self):
        # Popen owns each direct leader's wait status. Generic waitpid(-1)
        # could steal it and make a later Popen.wait incorrectly report zero.
        for child in self.direct.values():
            child.poll()
        children = Path("/proc/self/task") / str(os.getpid()) / "children"
        for value in children.read_text().split():
            pid = int(value)
            if pid in self.direct:
                continue
            try:
                reaped, status = os.waitpid(pid, os.WNOHANG)
                if reaped:
                    need(len(self.adopted_statuses) < 256, "adopted_process_bound")
                    self.adopted_statuses.append({"pid": pid, "waitStatus": status})
            except ChildProcessError:
                pass

    def run(self, label, args, cwd=None, extra=None, timeout=180):
        need(not self.interrupted, "signal_interruption")
        need(time.monotonic() < self.work_end, "work_deadline")
        self.guard()
        self.known = self.snapshot()
        before = time.monotonic()
        record = {"id": label, "argv": [str(x).replace(str(self.root), "$OWNED") for x in args]}
        self.report["commands"].append(record)
        streams = {"stdout": bytearray(), "stderr": bytearray()}
        observed = {name: {"bytes": 0, "hash": hashlib.sha256(), "eof": False} for name in streams}
        env = dict(self.env, **(extra or {}))
        def limits():
            for key, bound in ((resource.RLIMIT_CPU, 600), (resource.RLIMIT_FSIZE, 512 * MIB),
                               (resource.RLIMIT_NOFILE, 256), (resource.RLIMIT_CORE, 0)):
                resource.setrlimit(key, (bound, bound))
        need(not self.interrupted, "signal_interruption")
        child = subprocess.Popen([str(x) for x in args], cwd=cwd or self.root / "export", env=env,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True, preexec_fn=limits)
        self.direct[child.pid] = child
        selector = selectors.DefaultSelector()
        for name in streams:
            stream = getattr(child, name)
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, name)
        failure = None
        deadline = min(self.work_end, before + timeout)
        def capture(key, enforce=True):
            try:
                data = os.read(key.fd, 65_536)
            except BlockingIOError:
                return
            name = key.data
            if not data:
                observed[name]["eof"] = True
                selector.unregister(key.fileobj)
                key.fileobj.close()
                return
            observed[name]["bytes"] += len(data)
            observed[name]["hash"].update(data)
            room = MAX_STREAM - len(streams[name])
            streams[name].extend(data[:max(0, room)])
            if len(data) > room:
                record["streamTruncated"] = True
                if enforce:
                    need(False, "stream_bound:" + label)
        try:
            last_storage = before
            while selector.get_map() or child.poll() is None:
                need(not self.interrupted, "signal_interruption")
                need(time.monotonic() < deadline, "command_timeout:" + label)
                self.sample()
                if time.monotonic() - last_storage > 1:
                    # Size-only sampling avoids repeatedly hashing compiler/dependency trees.
                    total = 0
                    for parent, dirs, files in os.walk(self.root, followlinks=False):
                        for name in files:
                            path = Path(parent) / name
                            try:
                                value = path.lstat()
                                if not stat.S_ISLNK(value.st_mode):
                                    total += value.st_size
                            except FileNotFoundError:
                                pass
                        need(total <= MAX_STORAGE, "owned_storage_bound")
                    self.max_bytes = max(self.max_bytes, total)
                    last_storage = time.monotonic()
                for key, _ in selector.select(0.05):
                    capture(key)
            record["exitCode"] = child.wait(timeout=1)
            need(not self.sample(), "command_left_owned_processes:" + label)
            need(record["exitCode"] == 0, "command_failed:" + label)
        except BaseException as error:
            failure = error
            record["error"] = str(error)[:512]
            try:
                self.kill_owned()
                child.wait(timeout=3)
            except Exception as stop_error:
                record["terminationError"] = str(stop_error)[:512]
            # Preserve the primary failure. An uncertain writer cannot force an
            # unbounded drain or turn EAGAIN into a replacement error.
            drain_end = min(self.cleanup_end, time.monotonic() + 3)
            while selector.get_map() and time.monotonic() < drain_end:
                for key, _ in selector.select(0.05):
                    capture(key, enforce=False)
            record["exitCode"] = child.returncode
        finally:
            for key in list(selector.get_map().values()):
                selector.unregister(key.fileobj)
                key.fileobj.close()
            selector.close()
            for name, data in streams.items():
                packed = gzip.compress(bytes(data), mtime=0)
                self.compressed += len(packed)
                need(self.compressed <= MAX_GZIP, "originals_gzip_bound")
                record[name] = {"bytes": len(data), "sha256": sha(data), "gzipBase64": base64.b64encode(packed).decode(),
                                "observedBytes": observed[name]["bytes"], "observedSha256": observed[name]["hash"].hexdigest(),
                                "eof": observed[name]["eof"], "descriptorClosed": getattr(child, name).closed,
                                "complete": observed[name]["eof"] and observed[name]["bytes"] == len(data)}
            record["elapsedSeconds"] = round(time.monotonic() - before, 3)
            self.reap()
            self.guard()
            if not self.sample(enforce=False):
                self.known = self.snapshot()
        if failure:
            raise failure
        return bytes(streams["stdout"])

    def retain(self, name, path):
        data = path.read_bytes()
        packed = gzip.compress(data, mtime=0)
        self.compressed += len(packed)
        need(len(data) <= 4 * MIB and self.compressed <= MAX_GZIP, "retained_bytes_bound")
        self.report.setdefault("retainedOriginals", {})[name] = {"bytes": len(data), "sha256": sha(data),
                                                                  "gzipBase64": base64.b64encode(packed).decode()}

    def export(self):
        copied = []
        for name in self.source:
            # Preserve package-selected maintained docs; never copy older evidence trees.
            selected = (name.startswith(("src/", "python/", "examples/", "scripts/"))
                        or (name.startswith("docs/") and not name.startswith("docs/results/") and name != "docs/publication.json")
                        or name in {"package.json", "package-lock.json", "tsconfig.json", ".npmignore", ".env.example",
                                    "README.md", "LICENSE", "PROVIDERS.md", "API.md", "SECURITY.md", "openapi.json", FIXTURE, PY_TEST, JS_TEST})
            if selected:
                data = (self.checkout / name).read_bytes()
                source = self.source[name]
                need(len(data) == source["bytes"] and sha(data) == source["sha256"] and blob(data) == source["blob"], "export_source_binding:" + name)
                target = self.write("export/" + name, data)
                need(target.read_bytes() == data, "export_written_bytes:" + name)
                copied.append(name)
        need(sum(self.source[name]["bytes"] for name in copied) < 16 * MIB, "export_bound")
        self.report["exportPaths"] = copied
        self.known = self.snapshot()
        for prefix in ("export/src", "export/scripts", "export/python/ocr_gateway", "export/tests"):
            self.freeze(prefix)

    def packages(self):
        export = self.root / "export"
        node_version = self.run("node-version", ["node", "--version"]).decode().strip()
        need(re.fullmatch(r"v\d+\.\d+\.\d+", node_version) and int(node_version.split(".")[0][1:]) >= 22, "node_22_required")
        npm_version = self.run("npm-version", ["npm", "--version"]).decode().strip()
        tooling = json.loads(self.run("python-build-tooling", ["python3", "-I", "-B", "-c",
            "import importlib.metadata,json,sys;print(json.dumps({'python':sys.version,'setuptools':importlib.metadata.version('setuptools'),'wheel':importlib.metadata.version('wheel'),'pip':importlib.metadata.version('pip')}))"]))
        need(int(tooling["setuptools"].split(".")[0]) >= 77, "preinstalled_setuptools_77_required")
        self.report["tooling"] = dict(tooling, node=node_version, npm=npm_version)
        package = json.loads((export / "package.json").read_bytes())
        original_lock = json.loads((export / "package-lock.json").read_bytes())
        original_schema = json.loads((export / "openapi.json").read_bytes())
        need(package["version"] == "0.2.0", "package_version")
        self.run("lock-version", ["npm", "version", "0.2.0", "--allow-same-version", "--no-git-tag-version", "--ignore-scripts"])
        need(json.loads((export / "package.json").read_bytes()) == package, "package_semantic_change")
        lock = json.loads((export / "package-lock.json").read_bytes())
        need(original_lock["version"] == original_lock["packages"][""]["version"] == "0.1.0", "original_lock_version")
        expected_lock = json.loads(json.dumps(original_lock))
        expected_lock["version"] = expected_lock["packages"][""]["version"] = "0.2.0"
        need(lock == expected_lock, "dependency_graph_changed")
        self.retain("package-lock.json", export / "package-lock.json")
        self.freeze("export/package-lock.json")
        self.freeze("export/package.json")
        self.run("npm-ci", ["npm", "ci", "--ignore-scripts", "--cache", self.root / "cache"], timeout=240)
        self.freeze("export/node_modules")
        self.run("typescript-check", ["npm", "run", "check"])
        self.run("typescript-build", ["npm", "run", "build"])
        self.freeze("export/dist")
        self.run("openapi-generation", ["npm", "run", "schema"])
        schema = json.loads((export / "openapi.json").read_bytes())
        expected_schema = json.loads(json.dumps(original_schema))
        need(expected_schema["info"]["version"] == "0.1.0", "original_schema_version")
        expected_schema["info"]["version"] = "0.2.0"
        info = schema["components"]["schemas"]["ProviderInfo"]
        mapping = info["properties"]["featureMimeTypes"]
        expected_mapping = {"type": "object", "properties": {name: {"type": "array", "items": {"type": "string"}}
                            for name in ("tables", "images", "charts", "diagrams", "equations")},
                            "required": [], "additionalProperties": False,
                            "description": "Optional MIME-pattern restrictions for declared features. An absent feature entry inherits mimeTypes; an empty list supports no formats. This map cannot add a feature absent from features."}
        need("featureMimeTypes" not in info.get("required", []) and mapping == expected_mapping, "optional_format_map_schema")
        expected_schema["components"]["schemas"]["ProviderInfo"]["properties"]["featureMimeTypes"] = expected_mapping
        need(schema == expected_schema, "unexpected_generated_schema_change")
        self.retain("openapi.json", export / "openapi.json")
        self.freeze("export/openapi.json")
        packed = json.loads(self.run("npm-pack", ["npm", "pack", "--ignore-scripts", "--json", "--pack-destination", self.root / "artifacts"]))
        need(len(packed) == 1 and packed[0]["filename"] == "alvarovillalbaa-ocr-gateway-0.2.0.tgz", "npm_archive_name")
        self.tgz = self.root / "artifacts" / packed[0]["filename"]
        self.run("wheel-build", ["python3", "-m", "pip", "wheel", "./python", "--no-index", "--no-deps", "--no-build-isolation", "--wheel-dir", self.root / "artifacts"])
        self.wheel = self.root / "artifacts/ocr_gateway_client-0.2.0-py3-none-any.whl"
        need(self.wheel.is_file() and sorted(p.name for p in (self.root / "artifacts").iterdir()) == sorted([self.wheel.name, self.tgz.name]), "artifact_set")
        self.inspect_archives(package)
        self.freeze("artifacts")
        self.run("venv-create", ["python3", "-m", "venv", self.root / "venv"])
        self.python = self.root / "venv/bin/python"
        self.run("wheel-install", [self.python, "-m", "pip", "install", self.wheel, "--no-index", "--no-deps", "--no-compile"])
        paths = json.loads(self.run("python-installed-origin", [self.python, "-I", "-B", "-c",
            "import json,sysconfig,ocr_gateway.local,ocr_gateway.ooxml_charts;print(json.dumps([sysconfig.get_path('purelib'),ocr_gateway.local.__file__,ocr_gateway.ooxml_charts.__file__]))"]))
        self.site = Path(paths[0])
        need(self.site.is_relative_to(self.root / "venv") and all(Path(p).is_relative_to(self.site) for p in paths[1:]), "wheel_import_origin")
        self.write("consumer/package.json", canonical({"name": "authored-installed-consumer", "version": "1.0.0", "private": True, "type": "module"}))
        self.run("npm-consumer-install", ["npm", "install", self.tgz, "--ignore-scripts", "--omit=dev", "--omit=optional", "--offline", "--cache", self.root / "cache"], cwd=self.root / "consumer")
        self.node_root = self.root / "consumer/node_modules/@alvarovillalbaa/ocr-gateway"
        need(json.loads((self.node_root / "package.json").read_bytes()) == package, "installed_npm_metadata")
        for name, row in self.report["artifactManifests"]["npm"].items():
            installed = self.node_root / name.removeprefix("package/")
            need(installed.is_file() and not installed.is_symlink() and sha(installed.read_bytes()) == row["sha256"], "installed_npm_archive_mismatch")
        for name, row in self.report["artifactManifests"]["wheel"].items():
            if not name.endswith(".dist-info/RECORD"):
                installed = self.site / name
                need(installed.is_file() and not installed.is_symlink() and sha(installed.read_bytes()) == row["sha256"], "installed_wheel_archive_mismatch")
        need({path.relative_to(self.root / "consumer/node_modules").as_posix() for path in (self.root / "consumer/node_modules").rglob("package.json")}
             == {"@alvarovillalbaa/ocr-gateway/package.json"}, "unexpected_consumer_dependency")
        self.freeze("consumer/node_modules")
        self.freeze("venv")
        self.test_env = {"OCR_GATEWAY_NODE_PACKAGE_ROOT": str(self.node_root), "OCR_GATEWAY_PYTHON_PACKAGE_ROOT": str(self.site),
                         "OCR_GATEWAY_TEST_PYTHON": str(self.python), "OCR_GATEWAY_PYTHON": str(self.python)}
        self.report["checks"]["artifactInstall"] = {"passed": True, "pythonOrigins": paths, "npmRoot": str(self.node_root)}

    def inspect_archives(self, package):
        manifests = {}
        with tarfile.open(self.tgz, "r:gz") as archive:
            members = archive.getmembers()
            need(len(members) <= 512 and sum(m.size for m in members) <= 8 * MIB, "npm_expansion_bound")
            rows = {}
            for member in members:
                safe_name(member.name)
                need(member.isfile() and member.name.startswith("package/") and member.name not in rows, "npm_archive_entry")
                data = archive.extractfile(member).read()
                rows[member.name] = {"bytes": len(data), "sha256": sha(data)}
                source_path = self.root / "export" / member.name.removeprefix("package/")
                need(source_path.is_file() and data == source_path.read_bytes(), "npm_archive_source_mismatch")
            for value in package["exports"].values():
                for target in value.values():
                    need("package/" + target.removeprefix("./") in rows, "npm_missing_public_export")
            need("package/dist/cli.js" in rows and "package/openapi.json" in rows, "npm_missing_runtime")
            manifests["npm"] = rows
        with zipfile.ZipFile(self.wheel) as archive:
            need(len(archive.infolist()) <= 64 and sum(m.file_size for m in archive.infolist()) <= 4 * MIB, "wheel_expansion_bound")
            rows = {}
            for member in archive.infolist():
                safe_name(member.filename)
                need(not member.is_dir() and member.filename not in rows and not member.flag_bits & 1, "wheel_entry")
                data = archive.read(member)
                rows[member.filename] = {"bytes": len(data), "sha256": sha(data)}
                if member.filename.startswith("ocr_gateway/"):
                    need(data == (self.root / "export/python" / member.filename).read_bytes(), "wheel_source_mismatch")
            need("ocr_gateway/local.py" in rows and "ocr_gateway/ooxml_charts.py" in rows, "wheel_missing_runtime")
            metadata = archive.read("ocr_gateway_client-0.2.0.dist-info/METADATA").decode()
            need("\nVersion: 0.2.0\n" in metadata and "\nName: ocr-gateway-client\n" in metadata, "wheel_metadata")
            manifests["wheel"] = rows
        self.report["artifactManifests"] = manifests
        self.retain(self.tgz.name, self.tgz)
        self.retain(self.wheel.name, self.wheel)

    def tests(self):
        export = self.root / "export"
        tree = ast.parse((export / PY_TEST).read_text())
        classes = [node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "NativeOOXMLChartIntegrationTier2Tests"]
        need(len(classes) == 1, "python_test_class")
        ids = sorted("test_native_ooxml_charts.NativeOOXMLChartIntegrationTier2Tests." + node.name for node in classes[0].body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"))
        need(len(ids) == len(set(ids)) == 27, "python_case_count")
        wrapper = '''import importlib.util,json,pathlib,sys,unittest
path=pathlib.Path(sys.argv[1]);spec=importlib.util.spec_from_file_location('test_native_ooxml_charts',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
class Result(unittest.TextTestResult):
 def startTest(self,test):
  self.ids.append(test.id());super().startTest(test)
 def __init__(self,*args,**kwargs):
  super().__init__(*args,**kwargs);self.ids=[]
suite=unittest.defaultTestLoader.loadTestsFromTestCase(module.NativeOOXMLChartIntegrationTier2Tests)
result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
print(json.dumps({'ids':result.ids,'testsRun':result.testsRun,'failures':[t.id() for t,_ in result.failures],'errors':[t.id() for t,_ in result.errors],'skipped':[t.id() for t,_ in result.skipped],'expectedFailures':[t.id() for t,_ in result.expectedFailures],'unexpectedSuccesses':[t.id() for t in result.unexpectedSuccesses]}))
sys.exit(0 if result.wasSuccessful() else 1)
'''
        runner = self.write("python-cases.py", wrapper.encode())
        result = json.loads(self.run("python-27-installed-cases", [self.python, "-I", "-B", runner, export / PY_TEST], extra=self.test_env))
        need(result == {"ids": ids, "testsRun": 27, "failures": [], "errors": [], "skipped": [], "expectedFailures": [], "unexpectedSuccesses": []}, "python_exact_results")
        self.report["checks"]["pythonCases"] = result
        titles = re.findall(r"^test\('([^']+)'", (export / JS_TEST).read_text(), re.M)
        need(len(titles) == len(set(titles)) == 18, "node_case_count")
        output = self.run("node-18-installed-cases", ["node", "--test", "--test-reporter=tap", export / JS_TEST], extra=self.test_env).decode()
        passed = re.findall(r"^ok \d+ - (.*)$", output, re.M)
        need(passed == titles and not re.search(r"^not ok|# (?:SKIP|TODO)\b", output, re.M), "node_exact_results")
        for key, value in (("tests", 18), ("pass", 18), ("fail", 0), ("cancelled", 0), ("skipped", 0), ("todo", 0)):
            need(re.search(r"^# " + key + " " + str(value) + r"$", output, re.M), "node_summary:" + key)
        self.report["checks"]["nodeCases"] = {"ids": titles, "testsRun": 18, "passed": 18}

    def cli(self):
        spec = importlib.util.spec_from_file_location("authored_chart_fixtures", self.root / "export" / FIXTURE)
        fixtures = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixtures)
        results = {}
        for kind, titles in (("docx", ["Revenue 🚀"]), ("pptx", ["First slide 🚀", "Second slide"]),
                             ("xlsx", ["Drawing 9", "Drawing 3", "Drawing 2"])):
            extension, data = fixtures.named_fixture(kind)
            need(extension == kind and len(data) <= 128 * 1024, "fixture_zip_bound")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                need(len(archive.infolist()) <= 64 and sum(m.file_size for m in archive.infolist()) <= 512 * 1024, "fixture_expansion_bound")
            path = self.write("fixtures/authored." + kind, data)
            original = self.run("installed-cli-" + kind, ["node", self.node_root / "dist/cli.js", "parse", "--file", path, "--local", "--providers", "local"], extra=self.test_env)
            output = json.loads(original)
            document = output["primary"]
            charts = [block for page in document["pages"] for block in page["blocks"] if block["kind"] == "chart"]
            need([block["metadata"]["title"] for block in charts] == titles, "cli_chart_order:" + kind)
            for block in charts:
                need(block["inferred"] is False and block["metadata"]["source"] == "ooxml-chart-cache"
                     and block["metadata"]["status"] == "complete" and block["metadata"]["cacheFreshness"] == "unverified"
                     and block["metadata"]["workbookResolved"] is False and block["metadata"]["visualInterpretation"] is False, "cli_native_provenance")
                need("bbox" not in block and "confidence" not in block, "cli_invented_geometry_or_confidence")
            if kind == "pptx":
                need([page["pageNumber"] for page in document["pages"]] == [1, 2]
                     and [block["metadata"]["documentPart"] for block in charts] == ["ppt/slides/slide9.xml", "ppt/slides/slide2.xml"], "cli_slide_manifest_order")
            else:
                need(all("pageNumber" not in page for page in document["pages"])
                     and all("pageNumber" not in item for item in document["citations"])
                     and all(not item["pageNumbers"] for item in document["chunks"]), "cli_invented_page")
            if kind == "docx":
                need(document["pages"][0]["blocks"][0]["text"] == "Before 🧭" and document["pages"][0]["blocks"][-1]["text"] == "After the chart", "cli_body_order")
            if kind == "xlsx":
                need([block["metadata"]["sheetName"] for block in charts] == ["First 🧭", "First 🧭", "Second"], "cli_sheet_order")
            text = document["text"].encode("utf-16-le", errors="surrogatepass")
            citations = {item["id"]: item for item in document["citations"]}
            for page in document["pages"]:
                for block in page["blocks"]:
                    citation = citations[block["citationId"]]
                    need(text[2 * block["start"]:2 * block["end"]].decode("utf-16-le", errors="surrogatepass") == block["text"]
                         and citation["quote"] == block["text"] and citation["inferred"] is False
                         and text[2 * citation["start"]:2 * citation["end"]].decode("utf-16-le", errors="surrogatepass") == citation["quote"], "cli_utf16_anchor")
            need(bool(document["chunks"]), "cli_chunks_missing")
            for chunk in document["chunks"]:
                need(text[2 * chunk["start"]:2 * chunk["end"]].decode("utf-16-le", errors="surrogatepass") == chunk["text"] and chunk["blockIds"]
                     and all(value in citations for value in chunk["citationIds"]), "cli_chunk_provenance")
            results[kind] = {"passed": True, "titles": titles, "fixtureSha256": sha(data), "stdoutSha256": sha(original), "stdoutBytes": len(original)}
        self.report["checks"]["installedCli"] = results

    def consumer(self):
        source = '''import {OCRGateway,type ProviderAdapter,type ProviderInfo,type ParseRequest} from '@alvarovillalbaa/ocr-gateway';
import {createOCRGateway} from '@alvarovillalbaa/ocr-gateway/core';
import {createLocalProvider} from '@alvarovillalbaa/ocr-gateway/local';
import {createGatewayServer} from '@alvarovillalbaa/ocr-gateway/server';
const local:ProviderAdapter=createLocalProvider();
const map:NonNullable<ProviderInfo['featureMimeTypes']>={charts:['application/*']};
const adapter:ProviderAdapter={...local,featureMimeTypes:map};
const request:ParseRequest={document:{name:'authored.docx',dataBase64:'YQ=='},features:['charts']};
const gateway=createOCRGateway({providers:[adapter]});
const server=createGatewayServer({gateway,authenticate:()=>undefined});
void [new OCRGateway({baseUrl:'http://127.0.0.1:1'}),request,server];
'''
        self.write("consumer/consumer.ts", source.encode())
        options = {"compilerOptions": {"strict": True, "noEmit": True, "target": "ES2023", "module": "NodeNext", "moduleResolution": "NodeNext",
                   "lib": ["ES2023", "DOM", "DOM.Iterable"], "types": ["node", "react"], "typeRoots": [str(self.root / "export/node_modules/@types")],
                   "skipLibCheck": False}, "files": ["consumer.ts"]}
        self.write("consumer/tsconfig.json", canonical(options))
        self.run("strict-installed-consumer", [self.root / "export/node_modules/.bin/tsc", "-p", self.root / "consumer/tsconfig.json"], cwd=self.root / "consumer")
        code = "console.log(JSON.stringify(Object.fromEntries(['','/core','/local','/server','/react'].map(s=>[s||'.',import.meta.resolve('@alvarovillalbaa/ocr-gateway'+s)]))))"
        resolution = json.loads(self.run("public-export-resolution", ["node", "--input-type=module", "-e", code], cwd=self.root / "consumer"))
        for key, value in resolution.items():
            expected = {".": "index", "/core": "core", "/local": "local", "/server": "server", "/react": "react"}[key]
            need(value == (self.node_root / ("dist/" + expected + ".js")).as_uri(), "public_export_origin")
        self.report["checks"]["strictConsumer"] = {"passed": True, "resolved": resolution}

    def cleanup(self):
        if self.root is None:
            self.report["cleanup"] = {"verified": True, "created": False}
            return
        self.kill_owned()
        self.reap()
        need(not self.sample(), "owned_processes_remain")
        for path in Path("/proc").iterdir():
            if path.name.isdigit():
                try:
                    parts = (path / "stat").read_text().rsplit(")", 1)[1].split()
                    need(int(parts[2]) not in self.groups, "owned_process_group_remains")
                except (FileNotFoundError, ProcessLookupError):
                    pass
        for name, port in self.ports:
            family = socket.AF_INET6 if name == "tcp6" else socket.AF_INET
            with socket.socket(family, socket.SOCK_STREAM) as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                probe.bind(("::1" if name == "tcp6" else "127.0.0.1", port))
        self.guard()
        rows = self.snapshot()
        need(rows == self.known, "unregistered_owned_entries_or_changes")
        removed = 0
        for name in sorted(rows, key=lambda value: (value.count("/"), value), reverse=True):
            need(time.monotonic() < self.cleanup_end, "cleanup_deadline")
            path = self.root / name
            row = rows[name]
            need(identity(path) == row["identity"], "cleanup_identity_changed:" + name)
            if row["type"] == "file":
                need(sha(path.read_bytes()) == row["sha256"], "cleanup_bytes_changed:" + name)
            elif row["type"] == "symlink":
                need(os.readlink(path) == row["target"], "cleanup_symlink_changed")
            path.rmdir() if row["type"] == "directory" else path.unlink()
            removed += 1
        need(identity(self.root) == self.root_identity and not list(self.root.iterdir()), "cleanup_root_changed")
        self.root.rmdir()
        self.guard()
        self.report["cleanup"] = {"verified": True, "created": True, "removedEntries": removed,
                                  "observedListeningPorts": [{"family": name, "port": port} for name, port in sorted(self.ports)],
                                  "observedProcessGroups": sorted(self.groups), "observedProcessIdentities": len(self.processes),
                                  "adoptedProcessStatuses": self.adopted_statuses,
                                  "ownedProcessesRemaining": 0, "rootAbsent": not self.root.exists()}

    def execute(self):
        try:
            self.admit()
            self.export()
            self.packages()
            self.tests()
            self.cli()
            self.consumer()
            self.guard()
            self.known = self.snapshot()
            need(not self.interrupted, "signal_interruption")
            self.report["status"] = "passed"
        except BaseException as error:
            self.report["error"] = str(error)[:1024]
        finally:
            try:
                self.cleanup()
            except Exception as error:
                self.report["cleanup"]["error"] = str(error)[:1024]
                self.report["status"] = "failed"
            if self.interrupted or self.signals:
                self.report["status"] = "failed"
                self.report.setdefault("error", "signal_interruption" if self.interrupted else "owned_process_required_termination")
            self.report["resources"] = {"maxOwnedBytes": self.max_bytes, "storageBound": MAX_STORAGE,
                "maxOwnedRssBytes": self.max_rss, "maxOwnedProcesses": self.max_processes,
                "compressedOriginalBytes": self.compressed, "elapsedSeconds": round(time.monotonic() - self.start, 3),
                "workBudgetSeconds": 900, "cleanupBudgetSeconds": 90, "nodeOldSpaceMiB": 512, "addressSpaceLimitApplied": False}
            payload = canonical(self.report)
            need(len(payload) <= MAX_REPORT, "report_bound")
            # A closed/blocked runner log transport cannot outlive our terminal
            # budget. No Python buffered flush remains after this direct write.
            output = memoryview(PREFIX.encode() + payload + b"\n")
            descriptor = sys.stdout.fileno()
            previous = os.get_blocking(descriptor)
            os.set_blocking(descriptor, False)
            terminal_end = min(self.cleanup_end + 5, time.monotonic() + 5)
            try:
                while output:
                    need(time.monotonic() < terminal_end, "receipt_write_deadline")
                    if select.select([], [descriptor], [], 0.05)[1]:
                        try:
                            output = output[os.write(descriptor, output):]
                        except BlockingIOError:
                            pass
            except (OSError, RuntimeError):
                return 1
            finally:
                os.set_blocking(descriptor, previous)
        return 0 if self.report["status"] == "passed" and self.report["cleanup"]["verified"] and not self.interrupted and not self.signals else 1


if __name__ == "__main__":
    sys.exit(Check().execute())
