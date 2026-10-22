**REQUEST_CHANGES — two remaining medium-severity findings.**

All **seven supplied SHA-256 digests matched**, both before and after review. Checkout HEAD is exactly `85f34140f3f68c73b046263f1308fef48e4bd8a7`; I reviewed the frozen working-tree changes against that base.

1. **Medium — A complete direct-read request can still prevent clean Executive shutdown through response backpressure.**
   **Location:** [control_plane/executive_service.py:4927](./control_plane/executive_service.py:4927), using the sender at [line 4695](./control_plane/executive_service.py:4695).

   The two-second deadline fixes incomplete incoming frames, but a service peer can submit a valid direct-read frame and then stop reading its large response. When transport backpressure occurs, `await writer.drain()` has no deadline. The handler remains in `_ceo_ingress_tasks`; shutdown waits for that handler and eventually raises “physical service work has not drained; custody retained.” Its final `writer.wait_closed()` is also unbounded, so merely timing out `drain()` and calling `close()` would not fully resolve the problem.

   **Evidence:** An in-memory probe of the extracted frozen sender suspended indefinitely on simulated backpressure after writing a 131,107-byte response, within the new response ceiling. This establishes the unbounded wait; I did not reproduce kernel backpressure with a live socket.

   **Repair:** Bound response delivery and teardown **after** the canonical operation/read has settled, and abort the transport when that delivery deadline expires. Preserve the existing rule against cancelling an in-flight submission or claiming zero effect after mutation. Add coverage for a non-reading peer receiving a large valid direct result.

2. **Medium — The privileged-identity exclusion still permits UID 0 under a non-root Executive.**
   **Location:** [control_plane/executive_service.py:2381](./control_plane/executive_service.py:2381), with UID validation at [line 2032](./control_plane/executive_service.py:2032).

   `peer_uid=0` passes binding validation. The subsequent exclusion covers the Executive effective UID, configured Operator UIDs, C1 and Web/App identities, but does not independently exclude root. Consequently, a host configuration using UID 0 is accepted when those other identities are nonzero and the Operator allowlist omits root. Such an inference App is not isolated: compromise grants OS privileges that can bypass the socket discriminator through identity changes or direct Runtime-file access.

   **Evidence:** An in-memory probe of the actual binding class and constructor validation block accepted UID 0 with synthetic Executive UID 501, C1 UID 502 and an empty Operator allowlist. This is a configuration-validation gap, not evidence that the dormant service is currently running as root.

   **Repair:** Reject UID 0 explicitly and add a non-root-Executive regression case.

The other reviewed fixes appear causally sound within this source scope: the admission wrapper accepts only `None` and rejects/closes returned coroutines; direct reads use the shared qualified Runtime-source helper; the outer transport admits the larger inference frame while retaining each family’s ceiling; accepted duplicates reconcile while disarmed without fresh-admission callbacks; and the new input deadline ends before canonical submission. I found no additional actionable regression in authenticated exact-reference reads or serialization-cap enforcement.

**Verification limits:** All seven files compiled in memory. I did not rerun the reported **106 passed, 1 deselected** suite because its fixtures write files and create sockets/SQLite state. The socket tests explicitly monkeypatch peer UID detection, and the ACL test mocks account lookup and ACL commands; they establish neither real OS identity isolation nor installed ACL/symlink-race behavior. The signed JWT and synthetic completion fixtures remain source-level evidence only.

The referenced ignored `../bot/.../.venv/inference-real-socket-review.md` was not located in the available paths, so I used your supplied five-finding summary and verified current code directly. No files were modified, including the refused Supervisor and Bot repair surfaces; no network/provider calls, delegation, installation or runtime changes were performed.
