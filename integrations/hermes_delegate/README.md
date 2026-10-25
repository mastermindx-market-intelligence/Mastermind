# Hermes delegation bridge (WP4)

Source-only adapter. `BUILT_NOT_PROVEN` / `PRODUCTION_INERT`. Importing this
package does not admit an Executive Job, start `fabric_task.py`, call Cursor,
or register a tool into the live Hermes profiles.

Hermes built-in toolset `delegation` and tool `delegate_task` stay disabled
(same disabled set as `integrations/hermes_qualification/preflight.py`). The
only delegation tool this package describes is `mmx_delegate` on toolset
`mmx_delegate`. It submits one bounded `implementation`, `watcher`, or
`computer_use` child after an injected Executive admission port accepts the
same carrier the caller named: Subagent Fabric (`fabric_task.py request`) or a
Cursor cloud agent. The parent-local ledger dedupes that child, cancels it
once, surfaces `UNKNOWN` without replay, keeps refusal text verbatim, and
refuses to move a refused or unknown child onto the other carrier. The parent
cannot review its own result. Consume reads the carrier result once, and only
after a different reviewer accepts the sealed sha256.

The default admission port returns `EXECUTIVE_ADMISSION_NOT_BOUND`. Carrier
ports are unbound. A consumed child can carry an `agentos.handoff.v1` draft
for the existing Agent OS writer. This package does not write that store.
`model` must already be one of `fable`, `opus`, `sonnet`, `haiku`, `codex`,
`local`, or `sol`.

```sh
python3 -m unittest discover -s integrations/hermes_delegate/tests -v
python3 -m compileall -q integrations/hermes_delegate
```
