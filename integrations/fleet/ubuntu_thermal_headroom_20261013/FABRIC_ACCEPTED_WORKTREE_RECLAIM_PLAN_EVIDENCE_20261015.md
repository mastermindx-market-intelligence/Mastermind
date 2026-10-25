# Original Fabric accepted-worktree release: source-only provenance bridge

**Evidence date:** October 15, 2026 UTC. **Status:** tested source patch; not installed, merged, provider-qualified or enabled for deletion.

## Capability and original owner

The original M2 Fabric `remote_sub.sh` receives an explicitly new Macro workspace request only after the existing orchestrator's root/parent, provider and host admission. An additive log statement records the exact immutable intent `FABRIC_NEW_MACRO_WORKTREE run=<run> commit=<sha40> root=<root> parent=<parent>` under the existing `remote_sub` log and selected Ubuntu host. The message intentionally does **not** attest successful mint: only the original host's existing physical `LaneLease` and reviewed Macro helper can do so.

The original `fabric_task.py` gets an additive **read-only** `reclaim-plan <run-id> --root <root> --parent <parent> --pinned-sha <sha40>` command. The plan requires:

- Exact current original `inspect_run` terminal result: return code zero, signal `ok`, available result, accepted outcome, an incumbent verified acceptance role (deterministic/reviewer), original root and parent equality.
- Exactly one well-formed and intact original launcher log line, identifying the same run, root, parent and SHA, with the host constrained to Ubuntu 0–3.
- A second, consistent original acceptance observation and byte-identical second bounded log read.

The returned JSON names the only candidate host, checkout `~/lanes/wt/<run-id>`, expected `lane/<run-id>` branch and initial pinned source SHA. Crucially it has **`cleanup_authorized:false`** and state `HOST_WORKTREE_SOURCE_AND_LIVENESS_PROOF_REQUIRED`. The plan is NOT a Git deletion command, new ledger, publication promise or acceptance substitute.

## Implementation compatibility and verification

This patch applies **after** the existing combined sparse + CPU source patch on [Fleet PR #1404](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1404) using strict `patch -p1 --fuzz=0`. It changes only the same original `fabric_task.py` and `remote_sub.sh` entrypoints in the *source candidate*, and leaves legacy runs unchanged.

- Base reviewed combined helper blob is the newer fail-closed Macro `75297acb10d0cef4d01730a59fdcad19c7cfd3e6` from [Macro #9194](https://github.com/mastermindx-market-intelligence/macro/pull/9194).
- Addendum patch SHA-256 **`7c413e08a671c53b214ce69e1cc622e61ad18b088b2f185a45def2ee703713ef`**.
- Combined preimage `fabric_task.py`: `fd6b3c316089324d4b51478861a89a11702c5264d924f6dd29244d9ffe8a6349`; patched `ca2eda17c76fb7af899501c40f2fa0450391079612d6d56c7d138eb2914624c2`.
- Combined preimage `remote_sub.sh`: `85e4502a0040089cd4e0d59e99bd2af4ab7b1db8881393ffe305057348e8f999`; patched `7527fb87e46b3ec99f4a645fb636a6ecee5b0e82bb198dae5f2b854719aef131`.
- All nine preexisting combined source integration script suites **passed** after layering this addendum. New fixture suite **21 passed** (positive accepted plan, 10 refused acceptance/lineage state variations, seven missing/duplicate/spoofed source log proofs, changes during observation, no-SSH/Git side effects).
- The addendum was dry-run and applied on copies of its exact combined source preimages with **no fuzz**; postimages were byte-identical to staged source. No existing M2 source or provider process was altered.

## How to rerun

Copy the published fixture `tests/accepted_reclaim_plan_fixture.py` into the directory containing the **composed** `fabric_task.py` as `test_reclaim_plan.py`, ensure that original Fabric dependencies are available on `PYTHONPATH`, and run `python3 -m pytest test_reclaim_plan.py -q`. Full existing combined-source verification is described by the previous Fleet #1404 evidence.

## Explicit unfinished release path

The original Fabric parent remains the **only** owner of worker acceptance and release. The next release phase must integrate the new exact-target upstream [Macro GC #9430](https://github.com/mastermindx-market-intelligence/macro/pull/9430) into the original parent *only after* verifying: same original run/root/parent and selected host; successful physical sparse mint with this accepted source; durable result and publication/merge proof for the current checkout HEAD; expected registered `lane/<run-id>` branch; no active worker lease, process cwd/open FD, unknown or resumed human state. Call the existing GC in a narrowly scoped one-run context; never globally arm Ubuntu report-only timers. A remote write with uncertain effects must freeze its original carrier for reconciliation, not be retried on another host.

**NOT INSTALLED:** This source patch does not yet cause automatic deletion and does not cure the separate BIOS/Ubuntu1 power-profile authorization gate. There is no native paid-worker/live-host acceptance evidence from these tests.
