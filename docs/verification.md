# v0.1.0 verification

Date: 2026-10-19. This is a source/SDK release with scoped local evidence. No backend test suites were run, following the user's workspace instructions. No CI workflow, hosted service, or registry release was provisioned.

## Observed

| Surface | Evidence | Boundary |
| --- | --- | --- |
| TypeScript | `npm run check` and `npm run build` pass with strict NodeNext TypeScript | SDK/server compile; no browser runtime check |
| Synthetic direct call | `npm run demo` prints normalized text, exact citation offsets, chunk IDs and routing | Custom synthetic adapter; no OCR/model call |
| npm artifact | `npm pack`, fresh installation with `--ignore-scripts --omit=dev`, imports of root/core/server | Built distribution consumed, not source imports |
| Installed tool call | URL-only `createParseTool` dispatches to a synthetic adapter, retaining source URL and known page 2 | No upstream URL fetch |
| Keys | Fresh temporary scoped key authenticates before revocation and fails after; list returns only metadata | Local file-store lifecycle; no HTTP auth proof |
| MCP | Installed CLI exchanges initialize, tools/list and ping; JSON `null` returns invalid-request; process exits 0 | Stdio protocol and schema; no paid tool execution |
| Local gateway adapter | `PYTHONPATH=python node dist/cli.js parse --file examples/sample.html --local --providers local` returns heading/table blocks, citations and chunks | Actual Node→Python extraction; no invented page for HTML |
| Python | Compilation on Python 3.11.16 and 3.14.7; wheel contents inspected and installed fresh | TypedDict source is not static type-checker proof |
| Installed Python extraction | Installed wheel's `python -m ocr_gateway.local` extracts a synthetic HTML heading/table; UTF-16 helper returns an emoji at supplied UTF-16 offsets | Native PDF/image optional dependencies not exercised in this check |
| Installed DOCX extraction | Minimal synthetic OOXML ZIP produces `Synthetic DOCX`, a paragraph and `Revenue\t42`; heading/text/table kinds retained | Page number correctly absent for flowing DOCX |
| Review | Independent static review of routing, normalization, providers, scope/BYOK restrictions, browser import boundary and resource limits | Review found and corrected undefined metadata, MCP input handling, output/chunk amplification and post-abort dispatch |
| Whitespace | Staged `git diff --check` | No generated/vendor files edited |

The Python wheel was built offline using the installed Python 3.11/setuptools toolchain and `pip wheel --no-deps --no-build-isolation`; the initial isolated build could not resolve PyPI. This does not add runtime dependencies.

## Unverified

- Authenticated HTTP sync/async examples: the sandbox rejected `listen` on `127.0.0.1` with `EPERM`. The example in [python/examples/local_client.py](../python/examples/local_client.py) is ready to run on a host permitting loopback sockets; it was not treated as a passing result.
- Paid/live OCR and vision providers, Jev/Decisions routing responses, provider availability/entitlements, extraction accuracy, and visual interpretation quality. Adapter contracts were inspected against the primary links in [PROVIDERS.md](../PROVIDERS.md).
- Optional PyMuPDF/Tesseract/Pillow runtime extraction: module/executable inspection found all three absent. No optional packages were installed by the bootstrap.
- React/browser behavior, a public gateway deployment, distributed authentication/rate limits, npm registry and PyPI registry publication.

The GitHub release contains installable npm/Python artifacts and checksums. GitHub publication is verified separately from local writes by checking repository/release metadata and the remote commit.
