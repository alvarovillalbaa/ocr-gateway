"""Data-only audit of original PDF receipts; no product/parser/test imports."""
import base64
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EXPECTED = (
    (1, "32e8994c615645591755c642c0a05e1338de1a63", 82, "43398625299", "35afb4d86ffe03d6ec9d41af07a531b56cd71ba0f3b683a2bf3e1b9759d94eb0", "30e20b848d610c8bb0e274c84c1932b5f957302221850def6311135b8c9f8d8f"),
    (2, "3c485202f50f20878e296ddbe10f757cc476267b", 85, "43399538275", "be1dcde9c18e91ea85186a8727e9a64c28d2535537408f106b747b61739ebbcc", "cae18c169456008f56fa88b086667652f2e2661fc554daa61be3066954c448b6"),
)
LINES = ["Harbor ledger", "First page owns these words.", "Quarry register", "Second page keeps a separate anchor."]


def need(value, label):
    if not value:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


reports, streams, summaries = [], [], []
for attempt, source, files, run, zip_sha, raw_sha in EXPECTED:
    stem = "optional-pdf-consumers-attempt-" + str(attempt)
    raw = (HERE / (stem + ".json")).read_bytes()
    need(sha(raw) == raw_sha, "original raw receipt")
    archive = HERE / (stem + ".zip")
    need(sha(archive.read_bytes()) == zip_sha, "original artifact ZIP")
    with zipfile.ZipFile(archive) as bundle:
        need(bundle.namelist() == ["ocr-optional-pdf-" + run + ".json"], "single original member")
        need(bundle.read(bundle.namelist()[0]) == raw, "ZIP/raw exact equality")
    report = json.loads(raw)
    need(report["sourceCommit"] == source and len(report["sourceFiles"]) == files, "prepared source identity")
    git_tree = {}
    for entry in subprocess.check_output(["git", "ls-tree", "-rz", source], cwd=ROOT).split(b"\0"):
        if entry:
            metadata, path = entry.split(b"\t", 1)
            mode, kind, blob = metadata.decode().split()
            need(kind == "blob", "source tree leaf type")
            git_tree[path.decode()] = (mode, blob)
    need(set(git_tree) == set(report["sourceFiles"]), "complete source paths")
    for path, row in report["sourceFiles"].items():
        need((row["mode"], row["blob"]) == git_tree[path], "source mode/blob")
        body = subprocess.check_output(["git", "cat-file", "blob", row["blob"]], cwd=ROOT)
        need(len(body) == row["bytes"] and sha(body) == row["sha256"], "source original bytes")
    decoded = []
    for command in report["commands"]:
        need(command["reaped"] and command["outputDescriptorsClosed"] and command["observedGroupsAbsent"] and not command.get("timedOut"), "actual command closure")
        channels = {}
        for channel in ("stdout", "stderr"):
            stream = command[channel]
            body = gzip.decompress(base64.b64decode(stream["gzipBase64"], validate=True))
            need(stream["complete"] and len(body) == stream["bytes"] == stream["retainedBytes"] and sha(body) == stream["sha256"], "complete original stream")
            channels[channel] = body
        decoded.append(channels)
    guards = report["sourceGuards"]
    need(len(guards) == (4 if attempt == 1 else 5) and all(g["matches"] and g["files"] == files for g in guards), "source guard outcomes")
    cleanup = report["cleanup"]
    need(cleanup["rootAbsent"] and not cleanup["ownedDescendants"] and all(g["reaped"] and g["liveAbsent"] for g in cleanup["directGroups"]), "owned teardown outcomes")
    leaves = cleanup["ownedLeafVector"]
    need(sha(json.dumps(leaves, sort_keys=True, separators=(",", ":")).encode()) == cleanup["ownedLeafVectorSha256"], "owned leaf vector hash")
    summaries.append({"attempt": attempt, "sourceCommit": source, "sourceFiles": files, "originalReceiptBytes": len(raw), "originalReceiptSha256": raw_sha,
                      "commands": len(decoded), "completeStreams": 2 * len(decoded), "exitCodes": [c["exitCode"] for c in report["commands"]],
                      "sourceGuards": len(guards), "ownedCleanup": {"rootAbsent": True, "leaves": len(leaves), "bytes": sum(x.get("bytes", 0) for x in leaves), "vectorSha256": cleanup["ownedLeafVectorSha256"]}})
    reports.append(report)
    streams.append(decoded)

first, second = reports
need(first["accepted"] is False and first["exitCode"] == 1 and set(first["checks"]) == {"P01"}, "preserved first failure")
need(second["accepted"] is True and second["exitCode"] == 0 and set(second["checks"]) == {"P02", "P03", "P04"}, "new unfinished identities only")
need(len(first["commands"]) == 7 and len(second["commands"]) == 8, "command coverage")
need([c["exitCode"] for c in first["commands"]] == [0] * 6 + [1], "actual first failed Node exit")
need([c["exitCode"] for c in second["commands"]] == [0] * 7 + [1], "actual expected malformed exit")
need(first["fixtures"] == second["fixtures"], "exact independently authored fixture identities")
need(first["runtime"] == second["runtime"], "recorded runtime profile equality")
need(first["downloads"] == second["downloads"], "exact anonymous archive identities")
need(first["installedWheels"] == second["installedWheels"], "reported installed original wheel members")
need(first["installedBefore"]["node"] == second["installedBefore"]["node"], "same installed Node payload")
module_files = lambda r: {k: v for k, v in r["installedBefore"]["pythonSite"].items() if k.startswith(("ocr_gateway/", "pymupdf/", "fitz/"))}
need(module_files(first) == module_files(second), "same actual installed Python/PDF module bytes")
need(first["sourceFiles"]["tests/smoke/optional-pdf-python.py"] == second["sourceFiles"]["tests/smoke/optional-pdf-python.py"], "unchanged P01 program/fixture generator")

p01 = json.loads(streams[0][5]["stdout"])
need(p01 == first["checks"]["P01"] and p01["passed"] and first["commands"][5]["argv"][-1] == "P01", "original passed P01")
carried = second["carriedAcceptedChecks"]["P01"]
need(carried["observation"] == p01 and carried["sourceCommit"] == EXPECTED[0][1] and carried["originalReceiptSha256"] == EXPECTED[0][-1] and carried["executedThisInvocation"] is False, "P01 original carry")
for index, page in enumerate(p01["pages"]):
    need(page["pageNumber"] == index + 1 and page["text"] == "\n\n".join(LINES[index * 2:index * 2 + 2]), "native PDF page text")
    need([b["text"] for b in page["blocks"]] == LINES[index * 2:index * 2 + 2], "native PDF blocks")
    for block in page["blocks"]:
        box = block["bbox"]
        need(all(math.isfinite(box[k]) for k in ("x", "y", "width", "height")) and box["unit"] == "point", "actual finite point box")
        need(abs(box["x"] - 36) < .01 and 0 <= box["y"] < 400 and 0 < box["width"] <= 264 and 0 < box["height"] < 40, "authored position bounds")
        need("confidence" not in block, "no invented confidence")

p02, p03 = (json.loads(streams[1][i]["stdout"]) for i in (5, 6))
need(p02 == second["checks"]["P02"] and p03 == second["checks"]["P03"], "original second observations")
need(p02["passed"] and p03["passed"] and p02["text"] == "\n\n".join(LINES), "normalized text")
pages, citations = p02["pages"], p02["citations"]
need([p["pageNumber"] for p in pages] == [1, 2] and all(p["width"] == 300 and p["height"] == 400 for p in pages), "actual normalized page geometry")
blocks = [b for page in pages for b in page["blocks"]]
need([b["text"] for b in blocks] == [LINES[0], "\n\n", LINES[1], LINES[2], "\n\n", LINES[3]], "exact six source/content/gap blocks")
need(len(citations) == 6 and len({c["id"] for c in citations}) == 6, "six unique citations")
encoded = p02["text"].encode("utf-16-le")
for citation in citations:
    page = next(p for p in pages if any(b["id"] == citation["blockId"] for b in p["blocks"]))
    block = next(b for b in page["blocks"] if b["id"] == citation["blockId"])
    need(encoded[citation["start"] * 2:citation["end"] * 2].decode("utf-16-le") == citation["quote"] == block["text"], "independent exact UTF-16 anchor")
    need(citation["pageNumber"] == page["pageNumber"] and citation.get("bbox") == block.get("bbox") and citation["inferred"] is False, "citation provenance")
    if citation["quote"].strip():
        need(citation["bbox"]["unit"] == "point" and citation["bbox"]["width"] > 0 and citation["bbox"]["height"] > 0, "content geometry")
    else:
        need(citation["quote"] == "\n\n" and "bbox" not in citation and "bbox" not in block, "no invented gap geometry")
need(p02["chunks"], "actual chunks")
for chunk in p02["chunks"]:
    need(encoded[chunk["start"] * 2:chunk["end"] * 2].decode("utf-16-le") == chunk["text"], "independent exact chunk slice")
    need(chunk["citationIds"] and set(chunk["citationIds"]) <= {c["id"] for c in citations}, "chunk citation references")
need(p03["page"] == {"text": "", "blocks": [], "width": 300.0, "height": 400.0, "pageNumber": 1}, "blank page preserved")
need("PDF page 1 has no native text; scanned OCR requires Pillow and tesseract" in p03["warnings"] and p03["positiveScannedOcrClaim"] is False, "missing OCR warning")
need(streams[1][7]["stdout"] == b"" and json.loads(streams[1][7]["stderr"]) == {"error": {"code": "LOCAL_PARSE_ERROR", "message": "Local document parsing failed"}}, "actual malformed PDF generic refusal")
need(b"AUTHORED_PRIVATE_FAILURE_MARKER" not in streams[1][7]["stderr"] and second["checks"]["P04"]["passed"], "no failure-marker leak")
need(second["runtimeNetwork"] == [], "no observed runtime network event")
print(json.dumps({"schemaVersion": 1, "kind": "ocr.optional-pdf-original-receipt-audit", "passed": True, "dataOnly": True,
    "verifierSha256": sha(Path(__file__).read_bytes()), "parserOrFixtureReexecuted": False,
    "distinctAcceptedIdentities": ["P01", "P02", "P03", "P04"], "newIdentitiesByAttempt": {"1": ["P01"], "2": ["P02", "P03", "P04"]},
    "firstOverallFailurePreserved": True, "singleFourCasePassingInvocation": False, "completeOriginalStreams": 30, "sourceGuards": 9,
    "cases": {"P01": "exact native two-page text and real point geometry", "P02": "six exact UTF-16 citations/content/gap provenance and chunks", "P03": "blank page and missing OCR warning", "P04": "actual expected exit1, empty stdout and generic error"},
    "sameInstalledNodePayload": True, "sameInstalledPythonPdfModules": len(module_files(first)), "fixtures": second["fixtures"], "attempts": summaries,
    "limits": ["Original-output arithmetic/hash audit, not new parser execution or independent host attestation.",
               "Runtime/profile and authored ASCII PDFs are narrow; no scanned/image OCR quality or arbitrary-PDF security result.",
               "Owned process samples/teardown observations are not every descendant lifetime or whole-host disposal.",
               "No live provider/model, browser, hosted server, registry or full-product acceptance."]}, indent=2))
