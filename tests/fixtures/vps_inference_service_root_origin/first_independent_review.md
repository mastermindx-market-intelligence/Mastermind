**REQUEST_CHANGES — two P1 availability defects remain in the root-origin repair.** Both can cause a valid service root to invalidate the entire workspace/CEO root mapping.

All **five supplied SHA-256 hashes matched**, both at the start and at the final check. Local `HEAD` is `da868d8aaa47ef81ec01653c82a71a4e3166e10d`; local `origin/master` is `9a8e9b50b6158eb38af78a5b867eedba1719b908`. This review binds to the supplied worktree file hashes, including the uncommitted repair, rather than to either commit alone.

1. **P1 — Valid maintenance grounding still poisons the complete root map.**
   **Location:** [control_plane/runtime_root_origin.py:232](./control_plane/runtime_root_origin.py:232), especially the exact-key comparison at line 236.

   **Concrete input:** Take a normal `svc-site-maintenance` request and add:
   ```json
   "boot_packet_schema": "mastermind.ceo_boot_packet.v1"
   ```
   to its existing `grounding` object.

   The public `executive_service_principal.derive_intent()` accepts this request, and the canonical sink explicitly permits that optional grounding field in [ceo_intent.py:426](./control_plane/ceo_intent.py:426). The repair nevertheless requires maintenance grounding to contain **exactly the two revision fields**, so it raises `service creation grounding is not closed`.

   I reproduced the validator/classifier disagreement using source functions and memory-only objects. The production caller propagates that failure into the whole-map unavailable result through [workspace_source_join.py:190](./control_plane/workspace_source_join.py:190).

   **Required correction:** Match the maintenance grounding contract actually admitted by the canonical sink. The two observed fixture shapes do not establish two exclusive producer contracts. Add a regression covering maintenance grounding with the optional boot-packet field.

2. **P1 — Legitimately narrower service grants are rejected as forged provenance.**
   **Locations:** [control_plane/runtime_root_origin.py:254](./control_plane/runtime_root_origin.py:254) and the fixed Job-authority equality at [line 276](./control_plane/runtime_root_origin.py:276).

   **Concrete input:** Submit an otherwise valid registered `svc-site-maintenance` envelope directly through the existing sink with:
   ```json
   "execution_contract": {
     "requested_authorities": ["READ"],
     "authority_level": "A0",
     "attempt_limit": 1
   }
   ```
   `["RESEARCH"]` produces the same disagreement.

   The sink’s [service ceiling at ceo_intent.py:616](./control_plane/ceo_intent.py:616) permits any nonempty subset of `{READ, RESEARCH}`. Its provenance producer preserves that requested subset in both authority fields. The repository’s actual authority policy also authorizes each subset; I verified that read-only.

   The classifier instead calls the emitter’s `validate_provenance()`, which requires the emitter’s **full** registered profile grant, and subsequently requires the Job to contain exactly `["READ", "RESEARCH"]`. A valid, less-privileged sink-created root therefore fails classification and disables the complete mapping.

   **Required correction:** Validate the durable grant against the sink’s admitted ceiling and require agreement between requested, effective, and Job authorities. Preserve the closed principal/actor binding and empty write authority. Keep rejecting the existing forged case where only `effective_authorities` is reduced while the request and Job remain broader.

The other challenges produced these bounded results:

- **Privilege and shape checks:** All 28 additional memory-only negative cases were refused, covering Job authority/seat widening, write paths, validation commands, orchestration metadata, missing provenance fields, extra nested keys, and malformed inference values. A valid service `workstream` still returned `NON_CEO` with null provenance; it did not cause CEO adoption.
- **Fingerprint and durable-Event integrity remain limited:** A substituted lowercase `"0"*64` fingerprint, an Event actor changed to `ceo-sol`, and a non-`svc-` intent ID with a matching command ID all still returned `NON_CEO`. Thus the repair does **not** establish fingerprint-content integrity, Event-actor integrity, or complete service-ID-domain validation. I have not classified these probes as demonstrated authority escalation: they supplied altered durable-record objects, and classification itself grants no execution authority. The existing uppercase-fingerprint test establishes a format check only.
- **Imports and bounds:** A cold classifier-first call successfully loaded the principal validator without a circular-import failure. A 40 KB request and a valid v2 inference request classified successfully. The existing 64-root, 128-statement/row, 256 KiB-cell, 2 MiB-total, and 200,000-SQLite-VM-step limits remain intact. These probes do not prove worst-case performance or acceptance of every combination within individual request limits.
- **Merge preservation:** AST comparison across all five named semantic-merge paths found no changed or missing functions unique to either parent, and no changes to functions identical in both parents. That is bounded source-preservation evidence, not full integration proof.

I ran no pytest, opened no Runtime or SQLite database, changed no source, delegated no work, and made no network or provider calls. Executable probes used repository source with bytecode disabled and file-write/network effects rejected. The reported 12-test green remains supplied evidence; installed-service behavior, real workers, full merged-source tests, and release acceptance were not verified. The Supervisor request-reader and Bot snapshot repairs remain untouched.
