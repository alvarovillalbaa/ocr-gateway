# Optional PDF consumers — first invocation failed

13 November 2026. Overall **FAILED** at source
`32e8994c615645591755c642c0a05e1338de1a63`, tree
`317ccccee7b814c71b61f4e03529be78d847e06d` (82 files /2,758,627 bytes).
The actual installed Python/PyMuPDF P01 case passed; Node P02 failed an observer
expectation. P03/P04 were not reached. Do not relabel this as a four-case pass.

[Run43398625299](https://github.com/alvarovillalbaa/ocr-gateway/actions/runs/43398625299),
job131795605410, activation `5be9c62c810c76b09ef75b83f877f9423d6b9050`,
completed with failure. Its unchanged public Node/Python archives and pinned
PyMuPDF1.26.6 wheel were anonymously downloaded, hash verified, freshly installed
and checked against all original archive members. Existing closed suites were
not rerun. No local app/parser/test/install/build, provider, account or paid call.

P01 observed the exact four authored texts on two real PDF pages, actual
300x400-point page dimensions, in-page text bounding boxes and no invented
confidence. Original page/block output is retained. P02 then observed six
normalized text blocks: four content blocks plus two `\n\n` gap blocks. The
checker wrongly required only four blocks and stopped at that assertion.
`src/normalize.ts` explicitly preserves source-text gaps as blocks/citations.
This is a consumer-expectation defect, not evidence of a product parser defect.
Later P02 citation/chunk assertions and P03/P04 remain unverified here.

The [original artifact ZIP](optional-pdf-consumers-attempt-1.zip), artifact
14024026935, is128,806 bytes, SHA-256
`35afb4d86ffe03d6ec9d41af07a531b56cd71ba0f3b683a2bf3e1b9759d94eb0`.
It has one member `ocr-optional-pdf-43398625299.json`, exactly the
[retained raw JSON](optional-pdf-consumers-attempt-1.json),413,534 bytes, SHA-256
`30e20b848d610c8bb0e274c84c1932b5f957302221850def6311135b8c9f8d8f`.
Fourteen original gzip streams from seven commands independently decode to
their exact byte counts/hashes. Exits were0/0/0/0/0/0/1; all leaders reaped,
output descriptors closed and observed groups absent. The Node stderr retains
the full assertion and actual/expected arrays.

Four full82-file source/index/native guards passed, including after failure
and owned shutdown/root removal. All seven direct groups were observed absent;
no attributed owned descendants remained. The nonce/device/inode/uid root and
its internal leaf inventory were verified and removed/read back absent.
Owned leaf-vector SHA-256 is
`c200f3cf6bb762d5f06a22d20a4e6ad789a966f759b8b209a75a37d4a4b9f77e`.
These scoped observations do not trace every short-lived detached child or
attest whole-host disposal. Failure before the final acceptance phase is not
another successful unchanged-installed-payload check.

Workflow417076693 was read back `disabled_manually`. The exact QA ref
`qa/ocr-optional-pdf-20261113-1` was SHA-verified at5be9c62c, deleted and read
back as an empty matching-ref set after the original artifact was retained.

The concrete changed control requires six exact normalized blocks/citations,
including both gap texts with no invented bounding boxes. Four nonempty boxes,
all quotes/page provenance and chunks still require actual checks. It carries
P01 only after original report/14 streams, parent source, unchanged Python
program, runtime/archive and fresh fixture identity checks. Execute only
unfinished P02/P03/P04 in the next isolated job, preserving this failure and
all original product/release bytes. No single four-case execution is implied.
