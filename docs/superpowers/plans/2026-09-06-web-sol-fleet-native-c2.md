# Web-Sol native census C2 implementation plan

> For the assigned implementation worker: use the current execution/TDD/review skills and exact protected Skillpack. This is a proposed source plan, not a receiver assignment or installation release.

**Goal:** Read every in-scope tab in one enrolled profile through the existing native bridge and return useful, bounded machine output without opening the extension popup.

**Architecture:** The existing binding selects the existing native instance/socket. A new closed census request reaches the existing collector through the service worker. One lossless bounded frame returns to the new client and command-line consumer. C3 subsequently integrates multiple profiles into the existing Control Room.

**Tech stack:** Current repository Python, JavaScript MV3, existing native messaging/framing, Node/pytest. No new dependency, browser-control library, network service, database, queue, or model call.

**Spec:** `docs/superpowers/specs/2026-09-06-web-sol-fleet-native-c2-design.md`.

## Global constraints and preflight

- [ ] Pin current protected source and same-SHA Skillpack; read #501, #502, #509, #340, #480, and their exact active carriers. Confirm accepted source/packaging predecessors or an explicitly reviewed stack. Do not inherit their active source assignments.
- [ ] Perform a complete owned-path/open-PR and registered-worktree collision census. Freeze one C2 branch and exact path ceiling before START. Any newly required path returns to Sol rather than silently widening scope.
- [ ] Keep native JSON guard 65,536 bytes, collector cap 128 rows, wire receipt target at most 60 KiB, and no lossy truncation. Profile total is not account quota; generation cue is not execution.
- [ ] Preserve legacy request/receipt semantics, five-second legacy timing, existing private-socket derivation, single action gate, strict identity/challenge/generation validation, and late-reply refusal. No transport fallback or retry.
- [ ] Proposed new generation is package 0.2.0, protocol-major 1, explicit new census capability in a revised fixed digest. A changed current version at pickup is a decision request, not permission to reuse stale constants.
- [ ] Keep all provider model/effort fields null/unverified. No live browser/account/profile/secret action is part of source admission.

## One useful C2 release, not separate foundation PRs

The tasks below are test-sized parts of one native-to-machine capability. Do not ship a standalone schema/codec and call C2 complete.

**Create:** `integrations/chairman_surfaces/web_sol_census_protocol.py` for strict census request/receipt/table validation; `scripts/web_sol_census.py` for a read-only command-line consumer; `tests/test_web_sol_native_census.py` and `tests/web_sol_native_census.test.cjs` for behavior and end-to-end fixtures.

**Modify after existing-owner release:** `web_sol_client.py`, `_web_sol_native_host_impl.py`, and `web_sol_protocol.py` under `integrations/chairman_surfaces/`; existing extension `background.js`, `census_core.js`, `census.js`, and `manifest.json`; existing deployment compatibility assertions only where the new reviewed package generation requires them. Reuse all seven static census assets—do not add an untracked eighth asset or duplicate the bundle renderer.

The exact compatibility-test path set must be derived from the accepted dependency base before START. This research does not authorize edits to currently occupied #502/#509 source paths.

## Task 1 — strict request, compact receipt, unchanged legacy contract

**Interfaces:** `validate_census_request(document) -> dict`, `validate_census_receipt(document) -> dict`, `encode_snapshot(snapshot) -> dict`, and `decode_snapshot(table) -> dict` in the new census protocol module. These are pure validation/transformation functions, not source authentication, filesystem access, or a new transport.

- [ ] RED: assert the following request is valid only through the new family; legacy `validate_request` must still refuse it. Mutate each required field, add an extra field, replace integers with booleans, and assert closed refusal without echoing payloads.

```python
request = {
    "schema": "mastermind.web_sol_census_request.v1",
    "adapter_instance_id": "a" * 64,
    "operation_key": "c2-synthetic-request-001",
    "nonce": "synthetic-nonce-000000001",
    "issued_at": "2026-09-06T00:00:00Z",
    "expires_at": "2026-09-06T00:00:10Z",
}
assert validate_census_request(request) == request
```

- [ ] RED: run the companion real-collector fixtures, use their entire snapshot, encode/decode, and assert structural equality, not just equal counts. Include zero tabs, 128 awake, 128 mixed, 129 with explicit omission, duplicate coordinates, changed inventory, and unavailable query. Mutated count/row relationships and a mismatched inner/outer adapter must fail.
- [ ] RED: construct maximum legal values for every row/header/envelope field and assert the complete native payload is at most 60 KiB. Check 65,536-byte codec acceptance and 65,537-byte refusal separately. A smaller sample passing is not a worst-case proof. Unknown arbitrary model strings must not enter this version.
- [ ] GREEN: implement strict fixed-order packing and reconstruction; keep the research decoder out of production. Do not allow caller-selected columns. Preserve the local schema's uncertainty and every row.
- [ ] Run focused tests, then commit only protocol/test changes. This commit is not the releasable capability by itself.

## Task 2 — one profile-wide broker through the existing bridge

**Interfaces:** `census_via_extension(binding, *, operation_key, issued_at, expires_at, nonce) -> dict` in the existing client; one closed native census dispatch branch; one fixed extension-owned popup refresh message. No free-form instance/socket/profile selector is added to public client arguments.

- [ ] RED: send one valid new-family request through the actual framed client/native fixture and obtain a real collector result from synthetic tabs. The existing dispatcher must fail before implementation. Control INSPECT/FOREGROUND and their unchanged receipt fixtures must continue passing.
- [ ] RED: wrong adapter/nonce, old package/capability, wrong boot generation, unsolicited census data, non-census sender page, content-script sender, subframe, and unconfigured adapter are refused. One generation's late result cannot satisfy another request.
- [ ] RED: use a controlled clock to spend time in handshake, request, collection, and response. CENSUS expires ten seconds from the original start; legacy requests still expire five seconds from that start. Neither timeout resets after a stage. A suspended browser or late response yields unknown/unavailable, never a fresh census.
- [ ] RED: hold eight underlying Chrome probe promises unresolved, then request popup and native refresh concurrently. The second path cannot create eight more probes. Timed-out promises retain their slots until settling; there is no persisted queue or automatic retry.
- [ ] GREEN: move only census admission into the existing worker, reusing `census_core.js`; make the popup a consumer of that broker. Validate popup sender provenance, preserve its refresh-generation guard and row UI, and keep native request/response correlation in the current framing path.
- [ ] GREEN: revise the fixed advertised capability and package-generation constants together with existing generated config/bundle validation. Mixed generations refuse honestly; a successful version/digest handshake is not installed-source attestation.
- [ ] Run the full existing Web-Sol family plus new Node/native fixtures. Diagnose environment failures without weakening sandbox, frame, timeout, identity, or permissions. Commit the cohesive bridge change only after the paired legacy controls pass.

## Task 3 — real machine consumer and complete source proof

**CLI:** `python scripts/web_sol_census.py --bindings <existing-private-bindings-file> --binding-id <exact-binding-id> --json`. These inputs use the existing binding loader and exact ID; no creation/enrollment, arbitrary socket, account, browser, or title selection. Generate bounded request timestamps/nonce once, call `census_via_extension`, validate, and print the closed profile result. Exit nonzero with fixed unavailable/error states; do not leak paths, raw locators, or exception strings.

- [ ] RED: invoke the actual CLI in an isolated fixture against the real native client/host over private test pipes/socket and the real collector with synthetic tab APIs. Prove observable rows/counts and explicit sleeping/duplicate/unknown fields. A test that injects a final precomputed consumer document does not prove the production path.
- [ ] RED: make two synthetic profile bindings resolve to different native instances; validate independent results. Then make one host missing/old-generation and assert it is unavailable, not an empty profile or idle capacity. The CLI must never enumerate a different socket on failure.
- [ ] GREEN: complete the CLI and record reproducible fixture output, exact source/artifact identities, and expected refusal examples. Do not record synthetic URLs or whole tab inventories as organizational authority.
- [ ] Execute the applicable tests from a short, owned temporary root, preserving exact failure output and environment qualifications:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_web_sol_*.py --basetemp=/tmp/wsx-c2-proof
node --test tests/web_sol_native_census.test.cjs
python3 scripts/web_sol_census.py --help
git diff --check
```

- [ ] Ensure `/tmp/wsx-c2-proof` is absent and belongs to this exact test attempt before pytest can replace it. Never reuse another worker's temporary root. Repository CI is separate from these focused commands.
- [ ] Recheck current protected base, all owned/dependency blobs, hosted checks, review threads, and source collisions; publish one Draft/HOLD PR. Obtain one non-author exact-head review through Secretary. No author self-approval, automatic merge, old-review reuse after semantic changes, or installed claim.

## Installed proof and C3 handoff

The existing #340 owner receives the exact bundle generation only after source acceptance and its own resource gates. It proves installed native round trips for two eligible disposable profiles, extension/native interruption, old-generation refusal, missing-profile behavior, rollback, and no provider submit or model selection. The source builder does not perform an unassigned installation.

C3 consumes the accepted C2 client in `control_plane/chairman_control_room.py`, `scripts/chairman_control_room.py`, and the existing `app/static/chairman_control/` assets, using their current caches, security boundaries, qualified freshness, and exact binding source. Its one vertical is the visible multi-profile read and machine projection together. Test the spec's eight-profile/two-in-flight/thirty-second bounds, missing expected profiles, duplicate coordinates, clock/suspend changes, unknown mode, and UI/machine agreement. Preserve partial coverage rather than showing a false complete fleet.

## Worker route and stop condition

PREFERRED_AVENUE: CTO Sol / bounded Codex engineering. WHY NOT FABLE: the accepted plan is a finite JS/Python native-protocol integration; no new company architecture or principal-level program ownership is required. The independent reviewer must not be the source author under another account. Use included non-Pro worker capacity unless a separately valid current exception applies.

Before implementation delivery, re-pin law, freeze exact source scope against current accepted predecessors, resolve a concrete eligible receiver through Secretary, then require actual pickup and a separate START. Until placement, state is WAITING_CAPACITY / needs_placement; a Slack post alone is not execution. This document is not a standing assignment to any idle process or browser tab.

Return one exact source head/tree/owned-path set, RED/GREEN evidence, current-base proof, source review, fixture limitations, and the next #340/C3 action. Stop on a source collision, missing provider/resource gate, incompatible current dependency, impossible size/time bound, unexpected private data, or prior effect uncertainty. Post the result on the exact commission carrier and await explicit parent CONTINUE/STOP; terminal shutdown removes only this child source from any shared watcher.

Completion distinctions remain: source written, local tests, published draft, review, latest-base checks, merge, installation, real browser/native proof, Control Room product proof, and model/effort evidence are separate. The full original goal is not accepted until enrolled-profile visibility is useful end-to-end and every unsupported model/execution field is honestly marked.
