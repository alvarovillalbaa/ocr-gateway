# Fresh public consumers attempt 1

**Failed; no complete consumer profile is accepted.**
[Run 43328188649](https://github.com/alvarovillalbaa/ocr-gateway/actions/runs/43328188649),
job `131565901545`, source `92ed919a1002142fb9dce1f59c6c76e69556121d`.
Logs show successful npm public-URL installation, venv/wheel public-URL
installation, installed export/import inspection and key create/list commands.
The first Node transport invocation exited 1. Cleanup then attempted to inspect
a pre-existing runner process's protected `/proc/1076/environ` and raised
PermissionError before the in-memory receipt/command stderr could be emitted.
The original SDK exception is unobserved; cleanup/scratch absence is unverified.

[Original job log](fresh-public-consumers-attempt-1.log): 20,498 bytes, SHA-256
`00bc99a8c96dd795f9cce75d953b406416c4079373e9cd002a440c7c6ad6ad26`.
Do not invent the missing receipt or accept F01–F03 as a complete profile.
Source review independently finds a consumer assertion for `supportsUrl`, which
the published discovery DTO does not expose. Replace it with the actual
enabled/configured/MIME contract; retain the explicit real URL-refusal checks.
That is a source-based diagnosis, not the recovered original exception.

The changed control snapshots pre-existing PID/start-time identities before
launch, inspects only new task candidates, fails closed on new inspection denials
and always emits failure evidence even when cleanup fails. It does not weaken
permissions or change the SDK/archive. Execute the eight new delivery identities
afresh; old closed parser/React cases remain untouched. No paid/model call,
account, local runtime or production change was performed.
