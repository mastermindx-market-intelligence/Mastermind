# experiential53 — MANUAL-only Experiential Labs GLM 5.3 UNCENSORED (native Fabric)

Isolated, source-only contribution: a NEW provider pool `experiential`
carrying exactly one model slug, `glm-5.3-uncensored` (Experiential Labs
GLM 5.3 UNCENSORED), selectable **only** by an explicit manual pin
(pool=experiential AND model=glm-5.3-uncensored) with a strict transport
re-evaluation before any effect — never ambient auto selection, never a
default promotion, never a fallback, never a cross-model/provider retry.

Base: protected `mastermindx-market-intelligence/Mastermind` master
`910803421beca53ca25145392725ab2d84c7a8e9` (Skillpack v1.0.1). This
directory is entirely NEW files; no incumbent file is modified.

## Files

| File | Role |
|---|---|
| `experiential_pin.py` | Typed manual-pin law: exact pool/slug pin, distinctness from the canonical Z.AI glm tier, no-default-promotion, no-fallback, and the ordered fail-closed execution admission. Stdlib only; no network, no credential, no storage access. |
| `experiential_exec.sh` | Fail-closed worker scaffold in the incumbent exec-wrapper shape. Every path ends in a typed refusal (exit 78). Zero writes, zero reads of the packet, zero provider contact. |
| `pools.yaml.experiential.poolblock.yaml` | Declarative registry block for the runtime pool registry owner to merge under `pools:`. Not a patch against moving runtime bytes and NOT installed by this child. |
| `test_experiential_pin_contract.py` | Hermetic deterministic contract suite (unittest; also pytest-collectable). |

## The law this encodes

* **Distinctness.** `glm-5.3-uncensored` is not Z.AI `glm-5.3` and not
  `glm-5.3-flash`; it can never be assigned to, emitted by, or folded into
  the `glm` pool. The canonical GLM model tier (`model_tier.py`) and default
  task routing are untouched.
* **Manual only.** `auto_selection_verdict` returns `NONE
  experiential_manual_only` for every task class; the registry block carries
  `manual_only: true`, `enabled: false` and an empty `task_class_fit`, so no
  scoring or promotion hook exists. Selection emits no `ESCALATE_TO`.
* **Strict pin.** The pin is validated, then re-validated, before anything
  happens (`selection_rechecked_at_request`), mirroring the incumbent
  preview → recheck → `launch-policy` law; at wiring time the incumbent
  transport recheck remains the final owner.
* **Fail-closed execution.** Ordered typed gates: carrier → slug → task
  class → provider enabled → entitlement → retention acknowledgement →
  sensitive-data opt-in → (proprietary code ⇒ independent code-exposure
  opt-in) → account (A stays `HELD_HTTP403`, never retried; B keeps its
  $1/day cap and, with no authenticated quota readback, has UNKNOWN quota —
  unknown quota is not capacity) → verified gateway route → transport.
  In this generation the transport gate always refuses
  (`EXPERIENTIAL_TRANSPORT_NOT_INSTALLED`): no false admission.
* **Retention & sensitivity.** The provider retains prompt/response even
  after settings are disabled or the account is deleted; spend is
  platform-funded only. Execution therefore requires an explicit retention
  acknowledgement and an explicit sensitive-data disclosure opt-in, and
  proprietary code is never exposed automatically (independent opt-in).
* **No new owners.** No key storage, queue, ledger, router or retry
  authority is created here. The approved shared Experiential gateway
  (PR #1849) and the Attempt-owned consumer/transport (PR #1920) remain the
  only route; the existing provider secret owner keeps custody of the
  upstream key.

## Custody respected

* `quota_continuity/source/pick.py` and `candidate/pick.py` have a live
  modifying writer (PR #2029) — not touched by this child.
* PRs #1849 (gateway), #1934 (SystemOne), #1945 (metadata), #1920 (Attempt
  SDK), #1918/#1946 (Brain pool/gateway), #1851 (native Jev), #1938
  (inert model alias), #2020/#2022/#2024 (GLM lease / readiness / manual
  diagnostics) — none of their branches or files are touched.

## Returned gaps (outside this child's authority — owners must wire)

1. **Registry merge**: `orch/fabric/pools.yaml` is host runtime state; the
   registry owner merges the pool block (and only then flips
   `enabled: true`) after the qualification below.
2. **Picker wiring**: `experiential` must be added to `_HOST_POOL_MODES`,
   `launch_policy` mode admission, `hard_filter`, and the manual-pin path of
   `_format_pick` in the incumbent `source/pick.py` — fenced by the live
   writer (PR #2029) until that lands.
3. **Transport wiring**: a `experiential` mode in `remote_sub.sh`/`sub.sh`
   mapping to this exec wrapper, plus `slot.py` cap registration — same
   owners, same fence.
4. **Qualified gateway transport**: an installed, attested loopback
   Experiential gateway route (PR #1849) consumed by the Attempt-owned
   client (PR #1920), qualified on the host, before
   `EXPERIENTIAL_TRANSPORT_NOT_INSTALLED` may be flipped — by the transport
   owner, never by this scaffold.
5. **Account B quota readback**: an authenticated $1/day readback does not
   exist; until an owner provides one, execution stays refused regardless
   of any other gate.

## Running the tests

```sh
python3 ops/native_fabric/experiential53/test_experiential_pin_contract.py
# or: pytest ops/native_fabric/experiential53/test_experiential_pin_contract.py --basetemp <dir>
```

No test contacts a provider, reads credentials or the runtime registry, or
writes outside a temporary directory.
