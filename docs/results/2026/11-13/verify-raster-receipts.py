"""Audit retained data only; never import or rerun the product/fixtures/model."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
EXPECTED = [
    ("0a6f41376597e47a4f8abde8f3d59432e0971824", 98, "43403826963", "a0863016d0b342f39252a67fa15ce01a1fbf129fcf2fd26287807aa966a54fc6", "a37184b3936dea954fa5f49f3afd87adec852685bcdddabda8dea250a024c86b"),
    ("98b2892f93d1128c05167cd429a50c7bc18dc16f", 101, "43405738923", "312405dfa6b8b4f6d1108d2ebd04271ddfb0582d907e65344a62d008482336d3", "dddde4bc7046589be580052cdb7ea52a77bd8e3b7350dfe90c20cd3d8d5777cb"),
    ("3eaf9945c474aff9b76ad65a16da26c57d597394", 105, "43410273690", "89bfb28852a59f7a2b4b1face698aaa9f82564a87e5e238769fb366a4d8fe73b", "2fc8f90b47f407dab9b95360b7cbde58037d7fca2655577fb6da2c9ec1abce72"),
    ("291edf87fdf847603dd02c5c9b3bef71e798e2fc", 108, "43411077345", "16cfcb68e76c4b62f6bc473baaff3c786a3c0011b82cde24d8553ff20488b70c", "2bec62a5bd95d1565848c6eb925b1a96e7d7f677fac1bcf851aed114510c4f14"),
]


def need(value, label):
    if not value:
        raise ValueError(label)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def original(row):
    body = gzip.decompress(base64.b64decode(row["gzipBase64"], validate=True))
    need(row["complete"] and len(body) == row["bytes"] == row["retainedBytes"] and sha(body) == row["sha256"], "complete original stream")
    return body


reports, streams, summaries = [], [], []
for attempt, (source, files, run, zip_sha, raw_sha) in enumerate(EXPECTED, 1):
    stem = "raster-local-attempt-" + str(attempt)
    raw = (HERE / (stem + ".json")).read_bytes()
    need(sha(raw) == raw_sha and sha((HERE / (stem + ".zip")).read_bytes()) == zip_sha, "original raw/ZIP hashes")
    with zipfile.ZipFile(HERE / (stem + ".zip")) as archive:
        need(archive.namelist() == ["ocr-raster-local-" + run + ".json"] and archive.read(archive.namelist()[0]) == raw, "one exact original ZIP member")
    r = json.loads(raw)
    need(r["sourceCommit"] == source and len(r["sourceFiles"]) == files, "prepared source identity")
    tree = {}
    for item in subprocess.check_output(["git", "ls-tree", "-rz", source], cwd=ROOT).split(b"\0"):
        if item:
            meta, name = item.split(b"\t", 1)
            mode, kind, blob = meta.decode().split()
            need(kind == "blob", "source leaf")
            tree[name.decode()] = (mode, blob)
    need(set(tree) == set(r["sourceFiles"]), "complete source paths")
    for name, row in r["sourceFiles"].items():
        body = subprocess.check_output(["git", "cat-file", "blob", row["blob"]], cwd=ROOT)
        need((row["mode"], row["blob"]) == tree[name] and len(body) == row["bytes"] and sha(body) == row["sha256"], "exact source mode/blob/size/SHA256")
    decoded = []
    for index, command in enumerate(r["commands"]):
        if attempt == 1 and index == 13:
            need(all(k not in command for k in ("exitCode", "stdout", "stderr")), "first command14 outcome remains unknown")
            decoded.append(None)
            continue
        need(command["reaped"] and command["outputDescriptorsClosed"] and command["observedGroupsAbsent"] and not command.get("timedOut"), "actual command closure")
        need(command.get("observerError") is None, "no observer error on complete row")
        decoded.append({key: original(command[key]) for key in ("stdout", "stderr")})
    need(len(r["sourceGuards"]) == (5 if attempt == 4 else 3) and all(g["matches"] and g["files"] == files for g in r["sourceGuards"]), "source guards")
    cleanup = r["cleanup"]
    need(cleanup["rootAbsent"] and not cleanup["ownedDescendants"] and all(g["reaped"] and g["liveAbsent"] for g in cleanup["directGroups"]), "owned teardown")
    leaves = cleanup["ownedLeafVector"]
    need(sha(json.dumps(leaves, sort_keys=True, separators=(",", ":")).encode()) == cleanup["ownedLeafVectorSha256"], "owned leaf vector hash")
    need(r["accepted"] is (attempt == 4) and r["exitCode"] == (0 if attempt == 4 else 1), "original verdict")
    if attempt < 4:
        need(r["checks"] == {} and "recognitionFreeze" not in r, "no prior recognition result carried")
    summaries.append({"attempt": attempt, "sourceCommit": source, "sourceFiles": files, "rawSha256": raw_sha, "completeOriginalStreams": 2 * sum(x is not None for x in decoded),
                      "commands": len(decoded), "sourceGuards": len(r["sourceGuards"]), "accepted": r["accepted"], "ownedLeaves": len(leaves),
                      "regularBytes": sum(x.get("bytes", 0) for x in leaves), "rootAbsent": True})
    reports.append(r)
    streams.append(decoded)

r, s = reports[3], streams[3]
need(len(s) == 26 and [c["exitCode"] for c in r["commands"]] == [0] * 25 + [1], "26 actual exits including expected R04 refusal")
need(json.loads(s[20]["stdout"]) == r["fixtureAdmission"], "original fixture admission")
for case, index in (("R01", 21), ("R02", 22), ("R03", 24)):
    need(json.loads(s[index]["stdout"]) == r["checks"][case] and r["checks"][case]["passed"], "actual case original")
need(json.loads(s[23]["stdout"]) == r["checks"]["R03"]["result"], "actual installed CLI output")
need(s[25]["stdout"] == b"" and json.loads(s[25]["stderr"]) == {"error": {"code": "LOCAL_PARSE_ERROR", "message": "Local document parsing failed"}}, "actual malformed image refusal")
need(b"AUTHORED_PRIVATE_RASTER_FAILURE_MARKER" not in s[25]["stderr"] and r["checks"]["R04"]["actualExit"] == 1, "no marker leak")
protocol_raw = (ROOT / "docs/studies/raster-local-v1.json").read_bytes()
runtime_raw = (ROOT / "docs/studies/raster-runtime-v2.json").read_bytes()
need(sha(protocol_raw) == "ec97ea9368b06251030887705f1ab62661c6fd594355ef0e39a489dc25999f29" and sha(runtime_raw) == "d128d3ee5410c8a1ee8c2ccc188259ba25ead0a873f4c961678ec1f9c1f1a316", "frozen protocol/runtime")
need(original(r["protocol"]["original"]) == protocol_raw and original(r["runtimeSupplement"]["original"]) == runtime_raw, "original frozen JSONs")
spec = json.loads(protocol_raw)["fixtures"]
fixture_bodies = {}
for name, row in r["fixtureOriginals"].items():
    packed = base64.b64decode(row["data"], validate=True)
    body = gzip.decompress(packed)
    need(row["encoding"] == "gzip-base64" and row["complete"] and row["retained"] and len(packed) == row["compressedBytes"], "full retained fixture")
    need(len(body) == row["bytes"] and sha(body) == row["sha256"] and {k: row[k] for k in ("bytes", "sha256")} == r["fixtures"][name], "exact fixture bytes")
    fixture_bodies[name] = body
need(set(fixture_bodies) == {"authored.png", "authored.tiff", "scanned.pdf", "invalid.png"}, "four exact inputs")
need(r["fixtures"] == r["fixtureAdmission"]["fixtures"] == r["recognitionFreeze"]["fixtures"], "fixture freeze identity")
need(r["fixtureAdmission"]["nativePdfText"] == "" and r["fixtureAdmission"]["pdfFonts"] == 0 and r["fixtureAdmission"]["pdfImages"] == 1, "image-only PDF admission")
need(r["fixtureAdmission"]["actualFontName"] == ["Aileron", "Regular"] and r["fixtureAdmission"]["fontSize"] == 48, "actual fixed font")
for index, page in enumerate(r["checks"]["R01"]["result"]["pages"]):
    need(page["text"].split() == " ".join(spec["first_lines"] if index == 0 else spec["second_lines"]).split(), "ordered TIFF words")
    need(page["pageNumber"] == index + 1 and [page["width"], page["height"]] == [1200, 400] and len(page["blocks"]) == 1, "TIFF frame geometry")
    need(all("bbox" not in b and "confidence" not in b for b in page["blocks"]), "no invented TIFF OCR geometry")
need(len(r["checks"]["R01"]["result"]["pages"]) == 2, "two TIFF frames")
for case in ("R02", "R03"):
    doc = r["checks"][case]["result"]["primary"]
    page = doc["pages"][0]
    need(doc["provider"] == "local" and doc["text"].split() == " ".join(spec["first_lines"]).split() and len(doc["pages"]) == 1, "exact normalized OCR words")
    need([page["width"], page["height"]] == ([1200, 400] if case == "R02" else [600, 200]) and page.get("pageNumber") == (None if case == "R02" else 1), "honest pixel/point/page provenance")
    blocks = {b["id"]: b for b in page["blocks"]}
    need(len(blocks) == 2 and all("bbox" not in b and "confidence" not in b for b in blocks.values()), "text/image blocks without invented geometry")
    image = next(b for b in blocks.values() if b["kind"] == "image")
    pixels = base64.b64decode(image["imageBase64"], validate=True)
    need(pixels.startswith(b"\x89PNG\r\n\x1a\n") and image["metadata"]["visualInterpretation"] is False and image["metadata"]["source"] == ("input-image" if case == "R02" else "embedded-image"), "retained image provenance")
    if case == "R02":
        need(pixels == fixture_bodies["authored.png"] and r["checks"][case]["inputImageSha256"] == sha(pixels), "byte-exact input image")
    else:
        need(next(b for b in blocks.values() if b["kind"] == "text")["metadata"]["source"] == "tesseract-page-raster", "actual scanned OCR provenance")
    text = doc["text"].encode("utf-16-le")
    need(len(doc["citations"]) == 2 and len({c["id"] for c in doc["citations"]}) == 2, "unique block citations")
    for citation in doc["citations"]:
        need(text[2 * citation["start"]:2 * citation["end"]].decode("utf-16-le") == citation["quote"] == blocks[citation["blockId"]]["text"], "exact UTF16 citation")
        need(citation.get("pageNumber") == page.get("pageNumber") and "bbox" not in citation, "citation provenance")
    need(doc["chunks"], "actual chunks")
    for chunk in doc["chunks"]:
        need(text[2 * chunk["start"]:2 * chunk["end"]].decode("utf-16-le") == chunk["text"] and chunk["citationIds"] and set(chunk["citationIds"]) <= {c["id"] for c in doc["citations"]}, "exact chunk anchors/references")

freeze = r["recognitionFreeze"]
need(freeze["beforeAnyRecognition"] and freeze["utcEpoch"] < r["commands"][21]["startedAt"] and freeze["protocolSha256"] == sha(protocol_raw) and freeze["runtimeSupplementSha256"] == sha(runtime_raw), "pre-recognition freeze")
leaves = {x["path"]: {k: v for k, v in x.items() if k != "path"} for x in r["cleanup"]["ownedLeafVector"]}
for row in freeze["nativeVector"]:
    need(leaves["native/" + row["path"]] == {k: v for k, v in row.items() if k != "path"}, "frozen native/model bytes at cleanup")
for label, prefix in (("node", "consumer/node_modules/@alvarovillalbaa/ocr-gateway/"), ("pythonSite", "venv/lib/python3.12/site-packages/")):
    for name, row in freeze["installed"][label].items():
        need(leaves[prefix + name] == row, "frozen installed bytes at cleanup")
for download in r["downloads"]:
    need(leaves["artifacts/" + download["name"]] == {k: download[k] for k in ("bytes", "sha256")}, "download unchanged at cleanup")
for package in r["apt"]["packages"]:
    fields = dict(line.split(": ", 1) for line in s[package["metadataOriginalCommand"]]["stdout"].decode().splitlines() if line and not line[0].isspace() and ": " in line)
    need(fields["SHA256"] == package["sha256"] and int(fields["Size"]) == package["bytes"] and fields["Version"] == package["version"], "original signed-index package record")
need(r["runtimeNetwork"] == [] and r["closedCasesReplayed"] is False, "network observer and no closed-case replay")
print(json.dumps({"schemaVersion": 1, "kind": "ocr.raster-original-receipt-audit", "passed": True, "dataOnly": True,
    "verifierSha256": sha(Path(__file__).read_bytes()), "parserFixtureOrModelReexecuted": False, "acceptedCases": ["R01", "R02", "R03", "R04"],
    "firstCommand14Outcome": "unknown and preserved", "priorFailuresPreserved": True, "originalStreams": sum(x["completeOriginalStreams"] for x in summaries),
    "sourceGuards": sum(x["sourceGuards"] for x in summaries), "attempts": summaries, "fixtures": r["fixtures"],
    "limits": ["Retained-data audit, not a new parser/model execution or independent runner attestation.", "Fixed English integration fixtures do not establish broad OCR quality or arbitrary-file security.",
               "Product suppresses native recognition diagnostics and trims text-file edges; supervisor/application originals are retained.", "Scoped process snapshots and Node/Python tripwires do not attest every child lifetime, whole-host cleanup or native network confinement.",
               "Original installed-member comparisons were performed on the runner; no weights or wheels were downloaded locally."]}, indent=2))
