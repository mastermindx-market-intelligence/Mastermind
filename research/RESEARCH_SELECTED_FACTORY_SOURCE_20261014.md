# Explicit selected Research factory source qualification

The ordinary Research launcher previously always built the unselected Macro
service and omitted the existing selected-delivery operation runner. An explicit
process-local `SelectedReadOptions` now composes a prepared Macro provider through
the same immutable source importer and passes its operation runner to the same
MCP/citation adapter. The ordinary CLI, deployment JSON, environment settings,
grant owner and source-readiness default remain unchanged.

The options name the actual producer commit independently of the reader release.
They require an owner-supplied current writer-policy callback. The factory verifies
the immutable Macro source and module provenance, builds one provider/service pair,
and explicitly prepares the selected generation before constructing HTTP routes.
Invalid preparation refuses; it cannot fall back to the ordinary reader. Macro's
guarded result is translated by field name to the MCP envelope, preserving identity
and final delivery checks. Readiness checks the prepared selection without a new
census. Refresh is an explicit owner action; no new schedule or request-side
preparation is introduced.

The input ceilings preserve the current resource proposal: maximum source age3600s,
reuse300s, corpus192MiB and aggregate image admission768MiB. Defaults remain32MiB
and256MiB. These are image-accounting bounds, not a process RSS reservation or
production memory proof. Actual deployment, writer settlement, full current
generation qualification,95percent coverage and final grants/client acceptance
remain required. There is no CLI switch that activates these options.

Validation at the local source boundary:

- 554 distinct MCP tests pass, zero skipped. The first full run had553 passes and
  one child-process import failure because the invocation omitted `PYTHONPATH=.`;
  that same test passed with the proper environment and no source change.
- Two causal cases against the exact4c64aec43f9817016f6e0b06b50a45cdc520b04e
  launcher preimage fail because it cannot accept the selected owner.
- Actual Macro source89e22931481d83efd01bfd9af0778c41fda734d8, loaded through
  the immutable importer into the actual launcher and MCP path, passes four
  synthetic cases: valid read; catalog movement during final authentication;
  current writer-policy withdrawal; and preparation refusal for an unqualified
  writer. The selected service and adapter are the exact citation bindings.
  The probe uses synthetic SQLite/store/auth and maps the fixed deployment root
  to a local source archive. It does not prove deployment or an actual writer.

Private bounded evidence is retained in the original Research Vault completion
root under `runtime-composition/production-factory-source/`: validation.json,
full.xml, socket.xml, causal-red.log, cross-repo-second.log and the reproducible
source-bound probe. No broker passages, credentials or runtime state are published.
The new-source independent Fabric review remains a separate acceptance gate.
