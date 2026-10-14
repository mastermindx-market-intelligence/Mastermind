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


## Full refresh owned by the application

The selected composition now delegates an explicit full refresh to the same
Macro provider. Its application lifespan owns one periodic task, defaulting to
30 seconds and capped by the reuse window. The existing MCP lifespan starts
first; refresh settles before that lifespan closes, and its yielded state is
preserved. Neither readiness nor HTTP delivery initiates qualification.

A started synchronous refresh retains ownership through repeated cancellation
of the lifespan or background task. No replacement can overlap it. Failure is
counted without retaining private provider diagnostics; ordinary source guards
continue to determine whether a previously qualified selection is usable. The
normal launcher still supplies no selected options and enables none of this.
The factory also rejects a pinned provider without refresh support before store
construction. A causal test reached the store on the earlier source and now
refuses cleanly.

Validation accounts for 564 distinct MCP tests: 562 initial broad-run passes,
one environment-corrected Uvicorn child-import test, and the new capability test.
The final 22 factory/lifecycle tests pass. The actual Macro-source synthetic HTTP
probe covers expired selection refusal with zero source reads, automatic full
requalification, restored search through one store/service, and drained shutdown.
Its source overlay and synthetic authority are not production release proof.
Independent lifecycle review remains on its original retained operation; no
review acceptance or runtime installation is claimed.
