# Check native instruction completeness without changing permissions

Use the existing on-demand `scripts/audit_execution_instructions.py` when a native
session behaves as though project guidance is missing. It is not a new startup
hook, admission gate, watcher, policy authority or proof of model behavior.

```sh
python3 scripts/audit_execution_instructions.py \
  --codex-home "$HOME/.codex" --repo-root "$PWD" --check
```

The JSON result retains `runtime_verified: false`. `completeness` describes only
the explicitly selected static file chain. Report mode without `--check` preserves
its historical successful exit for a valid diagnostic, including incomplete files.
With `--check`, exit 0 means no static completeness findings, exit 1 means findings
exist, and exit 2 means the arguments/files/configuration could not be inspected.
None of these statuses is an authorization or runtime-acceptance decision.

Findings distinguish project-budget truncation (including omitted byte counts),
incomplete bounded content scans, malformed selected managed blocks, and an
explicitly requested expected brief that is absent, mismatched or not fully eligible.
Unselected additional Markdown remains inspection metadata, not part of the chain.
A legitimate locally adapted brief can differ from an expected source: review the
difference rather than overwriting user policy merely to obtain a matching hash.
No file content is included in the finding summaries.

The CLI reads the selected provider-home configuration. Observe effective profile,
project, session and managed overrides separately through the installed native
`config/read` owner; a file on disk does not prove that an active session uses it.
Codex project instructions share a byte budget. Global guidance is reported
separately. A larger limit fixes omission but increases context cost: prefer concise
reviewed guidance and explicit references long term. Do not remove real controls
or raise limits in intentionally isolated/offline worker homes for apparent parity.

If a configuration correction is justified, use the existing native configuration
writer, exact original file/version, private preimage backup and same-target
readback. Verify unrelated settings remain unchanged. Fresh native configuration
readback and a rerun of this diagnostic establish configuration/file coverage only;
existing sessions and actual tool/model behavior require their own observations.

Reference: https://developers.openai.com/codex/guides/agents-md
Reference: https://developers.openai.com/codex/app-server
