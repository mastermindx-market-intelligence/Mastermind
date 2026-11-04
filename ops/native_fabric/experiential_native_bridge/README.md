# experiential_native_bridge — source-only composition for the manual Experiential Labs pool

Child: `explabs-manual-20261103-nativebridge01` (task C2 `fix_build`).
Qualified release: protected Mastermind pin `9bbd4ca7f6d8859f28accf76e11d534478dc80e3`
(skillpack `mastermind.sol_skillpack.v1` v1.0.1), release tree
`ops/native_fabric/quota_continuity/source`.

This module takes the VERIFIED immutable native source release (bound by
`release_manifest.json`: expected git head, whole-tree content digest, and
per-file SHA-256 preimages — never guessed, never mutated) and composes a
**disposable exact native overlay** into a temp directory of your choosing:

1. `fabric_task.py` — `request` parses `--experiential-retention-acknowledged`,
   `--experiential-sensitive-data-opt-in`, `--experiential-proprietary-code`,
   `--experiential-code-exposure-opt-in` and `--strict-manual-pin`; the four
   consents plus the exact pin (`--pool experiential --model
   glm-5.3-uncensored`) are mandatory and refused on every other pool
   (including AUTO/default); `preview` returns JSON `PREVIEW_ONLY` with strict
   recheck witnesses ONLY when all owner-qualified route/host/cap gates
   genuinely succeed, otherwise it refuses prelaunch. `request --help`
   lists the flags so the Web MCP can recognize the staged candidate.
2. `remote_sub.sh` / `sub.sh` / `slot.py` — sole manual `experiential` mode:
   exact slug (default dark: no model default), `experiential` lease/ledger
   pool on the EXISTING broker architecture, `slot.py CAPS["experiential"] = 0`
   (zero available until original-owner attestation), support sync and launch
   env additions are experiential-only so every other mode stays
   byte-semantically identical. No Z.AI glm quota, no separate
   queue/ledger/account, no cross-provider fallback, no AUTO promotion.
3. `experiential_bridge.py` — the consumer hook. It resolves the owner
   modules (`experiential53/experiential_pin.py`, `experiential_transport.py`,
   `experiential_host_context.py`) ONLY from trusted host-owned locations
   beside the runtime (regular files, no symlinks, size-bounded; never env
   vars, never caller paths) and performs at most ONE admitted opt-in
   inference through `experiential_transport.run_opt_in_inference` per run.

## Current fail-closed status (unchanged runtime gates)

| Gate | Value | Owner |
| --- | --- | --- |
| `experiential_pin.TRANSPORT_INSTALLED` | `False` (module constant) | PR #2031 branch owner |
| `experiential_transport.ROUTE_QUALIFIED` | `False` (module constant) | PR #2035 branch owner |
| Account A | HTTP 403 HELD, never retried/bypassed | original account owner |
| Account B `$1/day` cap | NOT authenticated (unknown cap ⇒ hard refusal) | original account owner |
| `slot.py` experiential capacity | `0` until owner attestation | slot/lease owners |
| `orch/fabric/pools.yaml` experiential block | owned by PR #2031 | poolblock owner |
| `ops/native_fabric/experiential_picker/` | owned by sibling child | picker01 |
| installed Mac Studio / M2 native release | untouched | installed-release owners |

Because of these holds, every real-runtime path refuses typed and prelaunch
(`EXPERIENTIAL_TRANSPORT_NOT_INSTALLED`, `EXPERIENTIAL_GATEWAY_ROUTE_UNQUALIFIED`,
`QUOTA_READBACK_UNAUTHENTICATED`, `ACCOUNT_A_HELD_HTTP403`, …) **before any
lease, host acquisition, packet effect or provider contact**. The Web plugin
therefore sees the flags in `request --help` (staged candidate), while
dispatch remains held exactly as the owners left it. The mock sandbox in the
tests implements the SAME typed contract and is NOT an admission.

## Composition (dry run — never a live install)

```bash
python3 compose_overlay.py \
  --release-root <path to the verified quota_continuity/source tree> \
  --output <new empty disposable directory>
# Optional: stage the exact owner-controlled pin+transport source together
# with the bridge, only if every owner module matches the sealed manifest:
python3 compose_overlay.py \
  --release-root <verified release source tree> \
  --owner-modules-root <trusted source ops/native_fabric/experiential53> \
  --output <new disposable directory>
```

Fail-closed verification order: manifest schema, exact patch and owner-module
digests, output disjointness, expected native source head, whole-release tree
CAS, per-file preimages, exact-context patch application (no fuzz), and
byte-exact postimage change proofs. The --verify-only option writes nothing.

When --owner-modules-root is provided, the compositor stages ONLY
experiential53/experiential_pin.py and experiential53/experiential_transport.py
from the existing owner-reviewed sources, after verifying the SHA-256 of each
against release_manifest.json. Absent sources, a symlink, an unknown digest or
modified content fail closed before creating the candidate. Without this
optional argument, the candidate remains the original bridge-only dry run.

The compositor never reads, creates or copies host account facts, cap
readbacks, provider keys, gateway bearer tokens or the host-owned
experiential_host_context.py accessor. Every receipt explicitly records
host_context_owner_required: true, status: source_candidate_not_installed,
admission_granted: false and worker_started: false. No effect is admitted.

## Host adapter seam (owned by installed runtime)

The bridge loads its owner pin and transport from
<runtime>/experiential53/ or <runtime>/ops/native_fabric/experiential53/ and
requires an installed owner-provided
experiential_host_context.host_owned_context() accessor for verified registry,
platform-funded entitlement, authenticated account B cap and gateway route.
Missing context is EXPERIENTIAL_HOST_CONTEXT_UNAVAILABLE. The adapter
cannot invent or infer an account, quota, token or model. The independent
owner source constants TRANSPORT_INSTALLED=False and ROUTE_QUALIFIED=False
remain binding until real installed transport and gateway verification.

## Installed runtime compatibility

As of 2026-11-04, installed Ubuntu Fabric fabric_task.py digest 8bedb615...
differs from the reviewed source preimage 8f28799d..., with drift also in
remote_sub.sh and slot.py. A disposable test using the current installed
Linux kit correctly rejects multiple obsolete hunks. DO NOT patch or replace
the installed kit with the old source tree. Qualify the actual installed
generation and reconcile new and existing logic through its source/CAS owner
before any installation. This bundle feature does not clear that hold.

Tests: 52 hermetic cases in test_experiential_native_bridge.py, plus a
disposable integration run of 212 tests with native pin, billing transport
and manual picker. A real owner module bundle was also dry-run composed and
byte-compared. No worker, native install, paid request or provider activation.

## Current Linux installed-generation forward-port

The original four source-overlay preimages are not the current Ubuntu kit.
`linux_current_profile/` provides a **separate exact-hash qualification**
for the observed Ubuntu0/Ubuntu3 installed-generation source, retaining its
newer route and lease semantics. Its checks and generated candidate never
write to installed `~/lanes/ext`; the owner generation publisher and real
gateway/account admission remain binding. Ubuntu1 and M1 have different
source digests and are not automatically admitted. See
`linux_current_profile/README.md` and its 10 hermetic negative/positive
qualification tests.
