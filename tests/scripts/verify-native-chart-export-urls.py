#!/usr/bin/env python3
"""Read-only correction of one URL observer, using retained CI originals only.

No controller module, application, package, subprocess or network is executed.
The reviewed pure URL validator alone is selected from controller source by AST.
"""

import ast
import base64
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
RECEIPT = "docs/results/2026/11-08/native-ooxml-charts-attempt-2.json"
LOG = "docs/results/2026/11-08/native-ooxml-charts-attempt-2.log"
PINS = {RECEIPT: (1019389, "7fd94704dc30237d17b8492da2300e05f7b6d0cc6131b4493114fa7870aee249"),
        LOG: (1036785, "d70e0288879b6e3bac6a4aeee28e2d5cd3920112b991fba6e4db1e5326bda2cb")}
CONTROLLER = "tests/scripts/run-native-ooxml-charts.py"
CONTROLLER_SHA = "60e0c700248d0c1349f2b26e4dd9ddd61035cad9b8c8b9eed13e4e2438c78462"
HELPER_SHA = "f844c58f7cb2dd866fdbac8d3a0a1729442d5f9b67c5b41b777b42209395c78c"
EXECUTED_CONTROLLER_SHA = "8649cdd564f9576dff543b00754b94970469431fe7f8a5399438c660d1fef1b1"
SOURCE_COMMIT = "18cb187c70a3f3e8ca4c622c8e4a5862484cb74d"
INSTALLED_ROOT = "/home/runner/work/_temp/ocr-native-charts-94adxsig/consumer/node_modules/@alvarovillalbaa/ocr-gateway"
TARGETS = {".": "index", "/core": "core", "/local": "local", "/server": "server", "/react": "react"}
RESOLUTION_CODE = "console.log(JSON.stringify(Object.fromEntries(['','/core','/local','/server','/react'].map(s=>[s||'.',import.meta.resolve('@alvarovillalbaa/ocr-gateway'+s)]))))"
PREFIX = b"OCR_NATIVE_OOXML_CHARTS_RESULT="
MAX_STREAM = 1024 ** 2


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unique_object(items):
    result = {}
    for key, value in items:
        need(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def parse(data):
    return json.loads(data, object_pairs_hook=unique_object)


def checked_original(name):
    size, digest = PINS[name]
    path = ROOT / name
    need(not path.is_symlink() and path.stat().st_size == size, "original_type_or_size:" + name)
    data = path.read_bytes()
    need(len(data) == size and sha(data) == digest, "original_sha256:" + name)
    return data


def stream(record):
    need(record["complete"] is True and record["eof"] is True and record["descriptorClosed"] is True,
         "incomplete_original_stream")
    packed = base64.b64decode(record["gzipBase64"], validate=True)
    need(len(packed) <= MAX_STREAM + 4096, "compressed_stream_bound")
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as source:
        raw = source.read(MAX_STREAM + 1)
    need(len(raw) <= MAX_STREAM and len(raw) == record["bytes"] == record["observedBytes"]
         and sha(raw) == record["sha256"] == record["observedSha256"], "original_stream_length_or_hash")
    return raw


def validator():
    path = ROOT / CONTROLLER
    source = path.read_bytes()
    need(not path.is_symlink() and len(source) < 128 * 1024 and sha(source) == CONTROLLER_SHA, "reviewed_controller_pin")
    tree = ast.parse(source)
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "validate_export_urls"]
    need(len(selected) == 1 and not selected[0].decorator_list and not selected[0].args.defaults, "pure_helper_selection")
    text = ast.get_source_segment(source.decode("utf-8"), selected[0])
    need(sha(text.encode()) == HELPER_SHA, "reviewed_helper_pin")
    namespace = {}
    # This executes only a hash-pinned function definition. Controller imports,
    # admission, main and runtime methods are absent from the compiled AST.
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<reviewed-export-url-validator>", "exec"), namespace)
    return namespace["validate_export_urls"]


def data_cases(validate):
    root = "/owned/consumer/node_modules/@alvarovillalbaa/ocr-gateway"
    baseline = {key: "file://" + root + "/dist/" + name + ".js" for key, name in TARGETS.items()}
    expected = {key: value.removeprefix("file://") for key, value in baseline.items()}
    need(validate(baseline, root) == expected, "plain_at_positive_case")
    need(validate({key: value.replace("@", "%40") for key, value in baseline.items()}, root) == expected,
         "encoded_at_positive_case")
    value = baseline["."]
    mutations = {
        "non_string": None, "wrong_scheme": value.replace("file:", "https:", 1),
        "remote_authority": value.replace("file:///", "file://elsewhere/", 1),
        "localhost_authority": value.replace("file:///", "file://localhost/", 1),
        "credentials": value.replace("file:///", "file://user:pass@elsewhere/", 1),
        "query": value + "?value=1", "empty_query": value + "?",
        "fragment": value + "#value", "empty_fragment": value + "#",
        "backslash": value.replace("/dist/", "/dist\\"), "control": value + "\n", "space": value + " ",
        "encoded_slash": value.replace("/dist/", "/dist%2F"),
        "encoded_backslash": value.replace("/dist/", "/dist%5c"),
        "malformed_escape": value.replace("index", "%4Gindex"),
        "invalid_utf8": value.replace("index", "%FFindex"), "encoded_nul": value.replace("index", "%00index"),
        "dot_alias": value.replace("/dist/", "/dist/../dist/"),
        "encoded_dot_alias": value.replace("/dist/", "/dist/%2e%2e/dist/"),
        "duplicate_separator": value.replace("/dist/", "/dist//"),
        "escaped_unreserved_alias": value.replace("index", "%69ndex"),
        "wrong_filename": value.replace("index.js", "elsewhere.js"),
        "wrong_root": value.replace("/owned/", "/elsewhere/"), "wrong_case": value.replace("index.js", "INDEX.js"),
        "trailing_separator": value + "/", "extra_leading_separator": value.replace("file:///", "file:////", 1),
    }
    cases = [(name, dict(baseline, **{".": changed}), root) for name, changed in mutations.items()]
    cases.extend([("missing_key", {key: value for key, value in baseline.items() if key != "/react"}, root),
                  ("extra_key", dict(baseline, extra=value), root), ("non_object", list(baseline), root),
                  ("root_alias", baseline, root.replace("/owned/", "/owned/../owned/"))])
    refused = []
    for name, candidate, expected_root in cases:
        try:
            validate(candidate, expected_root)
        except ValueError:
            refused.append(name)
        else:
            raise ValueError("validator_accepted_negative_case:" + name)
    return {"positiveCases": ["plain_at", "encoded_at"], "refusedCases": refused,
            "applicationTests": False, "allPassed": True}


def verify():
    need(len(sys.argv) == 1, "fixed_read_only_inputs")
    original = checked_original(RECEIPT)
    log = checked_original(LOG)
    frames = [line.split(PREFIX, 1)[1] for line in log.splitlines() if PREFIX in line]
    need(len(frames) == 1 and frames[0] + b"\n" == original, "log_receipt_exact_byte_binding")
    receipt = parse(original)
    need(receipt["repository"] == "alvarovillalbaa/ocr-gateway" and receipt["sourceCommit"] == SOURCE_COMMIT
         and receipt["sourceVector"][CONTROLLER]["sha256"] == EXECUTED_CONTROLLER_SHA
         and receipt["status"] == "failed" and receipt["error"] == "public_export_origin", "original_observer_failure")
    need(receipt["cleanup"]["verified"] is True and receipt["cleanup"]["rootAbsent"] is True
         and receipt["cleanup"]["ownedProcessesRemaining"] == 0 and not receipt["ownedSignals"]
         and "interruptedBySignal" not in receipt, "original_lifecycle_closure")
    commands = receipt["commands"]
    need(len(commands) == 26 and len({row["id"] for row in commands}) == 26, "original_command_identity")
    originals = {}
    for row in commands:
        need(row["exitCode"] == 0 and not any(key in row for key in ("error", "terminationError", "streamTruncated")),
             "original_command_did_not_complete:" + row["id"])
        originals[row["id"]] = {name: stream(row[name]) for name in ("stdout", "stderr")}
    strict, resolution_command = commands[-2:]
    need(strict["id"] == "strict-installed-consumer" and strict["argv"] ==
         ["$OWNED/export/node_modules/.bin/tsc", "-p", "$OWNED/consumer/tsconfig.json"]
         and originals[strict["id"]] == {"stdout": b"", "stderr": b""}, "strict_consumer_command_binding")
    need(resolution_command["id"] == "public-export-resolution" and resolution_command["argv"] ==
         ["node", "--input-type=module", "-e", RESOLUTION_CODE]
         and originals[resolution_command["id"]]["stderr"] == b"", "resolution_command_exact_argv")
    raw_urls = originals[resolution_command["id"]]["stdout"]
    resolution = parse(raw_urls)
    need(receipt["checks"]["artifactInstall"]["passed"] is True
         and receipt["checks"]["artifactInstall"]["npmRoot"] == INSTALLED_ROOT, "installed_root_binding")
    validate = validator()
    cases = data_cases(validate)
    paths = validate(resolution, INSTALLED_ROOT)
    target_hashes = {}
    for key, name in TARGETS.items():
        installed_key = "consumer/node_modules/@alvarovillalbaa/ocr-gateway/dist/" + name + ".js"
        installed = receipt["frozen"]["consumer/node_modules"][installed_key]
        artifact = receipt["artifactManifests"]["npm"]["package/dist/" + name + ".js"]
        built = receipt["frozen"]["export/dist"]["export/dist/" + name + ".js"]
        need(installed["type"] == built["type"] == "file"
             and installed["bytes"] == built["bytes"] == artifact["bytes"]
             and installed["sha256"] == built["sha256"] == artifact["sha256"], "frozen_export_artifact_binding:" + key)
        target_hashes[key] = artifact
    former = {key: Path(value).as_uri() for key, value in paths.items()}
    need(all(resolution[key] != former[key] and resolution[key].replace("@", "%40") == former[key] for key in TARGETS),
         "exact_at_encoding_diagnosis")
    # The audit is read-only, including the original failed outcome.
    need(checked_original(RECEIPT) == original and checked_original(LOG) == log, "originals_changed_during_audit")
    return {"schemaVersion": 1, "kind": "ocr-gateway.export-url-observation-correction", "status": "verified",
            "applicationReexecuted": False, "newRuntimeExecution": False, "originalCIStatus": "failed",
            "originalCIError": "public_export_origin", "originalSourceCommit": SOURCE_COMMIT,
            "executedControllerSha256": EXECUTED_CONTROLLER_SHA, "correctedControllerSha256": CONTROLLER_SHA,
            "validatorSourceSha256": HELPER_SHA, "verifierSha256": sha(Path(__file__).read_bytes()),
            "inputPins": {name: {"bytes": size, "sha256": digest} for name, (size, digest) in PINS.items()},
            "originalCommandsIntegrityChecked": 26, "strictTypeScriptConsumerExitCode": 0,
            "resolutionCommandExitCode": 0, "resolutionStdout": {"bytes": len(raw_urls), "sha256": sha(raw_urls)},
            "resolvedURLs": resolution, "decodedNativePaths": paths, "frozenArtifactTargets": target_hashes,
            "formerStringComparisonExpectedURLs": former, "diagnosis": "literal_@_versus_percent_encoded_%40",
            "validatorDataCases": cases, "reactScope": "resolution_only", "originalCIStatePreserved": True,
            "limits": "Verifies retained data and the corrected URL observer; does not rerun the application or make the failed CI job green."}


if __name__ == "__main__":
    try:
        result = verify()
    except Exception as error:
        print(json.dumps({"schemaVersion": 1, "status": "refused", "error": str(error)}, sort_keys=True))
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
