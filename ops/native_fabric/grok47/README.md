# Grok Build 4.7 — immutable Fabric release candidate

**Capability state: BUILT_NOT_PROVEN.** This is source for one existing
Subagent Fabric native-generation release, not permission to select a new live
generation, create workers, change routing policy, or use provider credentials.

## One authoritative release target

- **Candidate stage:** `/Volumes/Mastermind/agent-workspaces/fabric-grok47-stage-20261022-sol-009`
- **Canonical code manifest SHA256:** `6d318305654f2f8478a4e24f2478b1a148b62a44f64f5d68277edc5d4b3235af`
- **Predicted native-generation identity:** `09b1ff4204c49acc71bb228751c4efefc22c70c89092734d9ea2fafe3fff1a49`
- **Release source:** original `mastermindx-market-intelligence/Mastermind`
  PR #1691, subject to current protected-master merge and release admission
- **Installed M2 generation before release:**
  `3a1bbcf121e9ec63ffba7a035ca67a380736608023ad3d74c2f0a67325255178`,
  `CURRENT.json` sequence 15 at last verified read
- **Historical stages:** `-001` through `-008` are superseded and must **never**
  be published or selected. Historical proof remains in PR #1691 comments
  and the transition research; it is not a second release source.

These exact values come from the new 85-file qualification. The selected
generation must still equal the above incumbent before any owner-run
compare-and-swap. Requalify and update this section on source drift. If another accepted Fabric
fix has been published, rebuild from that generation instead.

## Implemented, not yet accepted in production

The reviewed overlay consists of nine exact installed-generation files:

`ext/pick.py`, `ext/native_remote.py`, `ext/sub.sh`,
`ext/remote_sub.sh`, `ext/remote_sub_exec.py`,
`ext/remote_sub_helpers.py`, `ext/artifact_delivery.py`,
`ext/fabric_operator_client.py`, `ext/fabric_operator_contract.py`.

The Grok Build picker defaults new unpinned jobs to `grok-4.7` and preserves
explicit `grok-4.6` and `grok-4.7` pins through the advisory selector and
native launch policy. The local shell also pins unqualified-default Build
calls explicitly before economic/admission checks. Both models are valid for
historical reconciliation and scoped operator model grant validation.

Cursor's legacy `cursor-grok-4.6-high` path remains separate, with only
that established alias and `composer-2.5` forwarded from the local Cursor
shell. The new Cursor `grok-4.7-high` / `grok-4.7-xhigh` defaults and
priority routing are **not activated**: the earlier platform refusal
continues to govern those modifying actions. A Cursor quota or binary
catalog entry is not authorization to bypass that restriction.

New `mastermind.grok_usage.v2` records distinguish the requested model from
a nullable, self-reported native-final model. An explicit mismatch fails
closed before optional text, usage or session parsing and never passes
private response JSON to the parent. The existing `v1` receipt validator
stays backward readable. The remote controller passes its exact selected
mode/model to usage validation; wrong-model usage is not counted. Supported
Codex-native, Go-Codex, GLM-Codex and MiniMax-Codex usage continue to validate.

No authenticated paid Grok 4.7 worker response, independently attested
served model, monthly Cursor budget amount, live original-parent consumption,
or Mastermind OS-launched native principal has yet been proven. The existing
model-specific R22 quality floor has too few adjudicated Grok 4.7 outcomes
to establish a reliable first-pass acceptance rate; an explicit bounded
real-worker pilot and independent adjudication remain required.

## Policy compatibility is a release gate

The existing signed policy is `<kit>/orch/fabric/pools.yaml`. Its
`pools.grok.default_model`, if set, precedes the source fallback default.
The live M2 policy inspected on October 22 had **no** such field; its
observed full-file SHA256 was
`db4e4b1768809bd991003ef045568b480cdb42ea0715a6b73ea5353930bf90d8`.

Use the **read-only** original-source preflight:

```bash
python3 ops/native_fabric/grok47/qualify_installed_generation.py \
  --installed-store "$KIT/native-code-releases" --policy-preflight-only
```

It refuses malformed, symlinked, missing, or conflicting policy. An existing
`grok-4.6` default blocks publication; do **not** ignore or overwrite the
policy fingerprint. Rerun this check immediately before any selection and
reconcile changes in the incumbent policy digest through its existing owner.
A default absent from the incumbent remains governed by the code's 4.7
fallback; this does not itself change the policy file. The incumbent
policy-preflight accepted the observed digest above, with no 4.6 override.

This source is rebased onto the already selected generation from merged
Fabric PR #1730. It **preserves** its three sealed changes in
`ext/lane_runtime.py`, `ext/run_observation_delivery.py` and `ext/slot.py`
while applying the nine Grok overlays only where their original reviewed
preimages are unchanged. A new overlapping installed generation causes the
qualifier to refuse instead of overwriting its fixes.

## Verification and protected publication

Local/offline verification (does not admit or run a worker):

```bash
python3 -m unittest discover -s ops/native_fabric/grok47 -p 'test_*.py' -v
python3 -m pytest -q tests/test_native_fabric_grok47.py
bash -n ops/native_fabric/grok47/overlay/sub.sh
bash -n ops/native_fabric/grok47/overlay/remote_sub.sh
```

The existing `qualify_installed_generation.py` verifies all 85 source hashes,
assembles the nine approved overlays, runs an isolated original-owner
publish/verify/select, exercises exact predecessor CAS and stale-CAS
refusal, and imports the complete native executor. With `--release-stage`
it writes a **fresh** candidate under the approved workspace root, without
touching the installed native store. It also validates the incumbent
policy model default as above.

**Only after** the PR is reviewed, all required current-head CI/security
checks pass, the source is accepted on protected master, and the incumbent
runtime/policy preflight still matches, may the original native release
owner use `native_generation.py publish`, `verify`, and exact-predecessor
`select --expect`. Reconcile any concurrent native generation owner first.
Do not select a draft branch, older manifest, or stage based on a stale
incumbent. The original launchers select immutable code once and reject
source-directory mixing.

The independent reviewer of prior head `86aef280` returned
**CHANGES_REQUESTED**. This updated candidate repairs its explicit 4.6-pin
regression, removes conflicting current-stage claims, and makes the
incumbent-policy override an explicit release preflight. The old head also
had a failing CodeQL alert on a generic CLI output sink, caused by
printing a Bailian account alias from the credential-source list. The
current candidate no longer emits **any** account alias from `pool pick`;
its output always says `KEY=-`, and the incumbent broker alone selects
accounts at admission. This eliminates the sensitive flow rather than
suppressing the security check. **A hosted CodeQL PASS is still required**. This
document, local tests and the previous review are not approvals for the
changed head.

A protected merge and successful CAS are still **not production acceptance**.
Finish a real policy-admitted Grok 4.7 native worker, source/result checks,
original assigning-parent consumption, and later an OS-initiated native
principal workflow with preserved session identity. Keep the old generation
and already-started workers intact during transition.

## External release dependencies

Fabric PR #1730 (uncertain cleanup) has **merged** and its resulting
installed generation is the pinned incumbent at sequence 15. This candidate
preserves those accepted source changes. PR #1720 (provider-outcome
qualification) remains open: if it publishes a newer selected generation,
the exact predecessor CAS for stage -009 must refuse and qualification must
be repeated against the new owner. PR #1365's model-host selector overlaps
`pick.py` semantically and requires original-owner review before combining
those policy effects.

This document is the single current stage reference. The separate
`NATIVE_HARNESS_TRANSITION_20261022.md` records historical research and the
longer OS/Executive/Fabric delivery plan; its older stage names are
superseded evidence, not publication instructions.

## Account-alias non-disclosure (stage -009)

The advisory selector previously included a Bailian key/account alias in
`KEY=<alias>`, even though the result is not an account lease. That
unnecessary flow was flagged by CodeQL as clear-text logging of sensitive
data. The source now emits fixed `KEY=-` for every pool. It does not
read credentials or select an account; the existing Capacity broker still
owns account binding. A regression injects a credential-shaped alias and
asserts it cannot appear in the selected result. All 50 tests pass
locally; hosted CodeQL must independently qualify the current head.


## Subsequent exact-model failover integrity repair

Post-selection source follow-up, NOT included in the already selected
generation-16 release: a request explicitly pinned to `grok-4.6` or
`grok-4.7` must not become `cursor-grok-4.6-high` on weekly exhaustion.
The previous router disclosed `MODEL_CHANGED=true`, but disclosure alone
does not fulfill an exact-model task contract. This repair returns the
original truthful Grok refusal for pinned jobs and preserves the
Grok-to-monthly-Cursor affinity route for **unpinned** jobs. Unit tests
cover both paths and the non-Grok-alias case. Deploy only through
protected master, original-owner native-generation publication/verification
and exact-predecessor selection; the initial stage -009 manifest is
historical evidence for generation 16, not a source for these new changes.
