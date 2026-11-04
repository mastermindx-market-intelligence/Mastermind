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
```

Fail-closed verification order: manifest schema → patch digests → output
disjointness → expected-head (stale checkout refuses `STALE_RELEASE_HEAD_REFUSED`)
→ whole-tree content digest (`RELEASE_TREE_MISMATCH`) → per-file preimages
(`RELEASE_PREIMAGE_MISMATCH`) → strict patch application (exact context, no
fuzz) → byte-exact postimage change proofs. `--verify-only` writes nothing.
The composer never writes to the release tree, never touches the installed
native release, and grants no admission (`OVERLAY_MANIFEST.json` records
`status: source_candidate_not_installed`, `admission_granted: false`,
`worker_started: false`).

## Host adapter seam (owned by others; absent today)

The bridge loads the adapter from `<runtime>/experiential53/` or
`<runtime>/ops/native_fabric/experiential53/` and requires the host-owned
context accessor `experiential_host_context.host_owned_context()` to supply
registry entry, platform-funded entitlement, account, authenticated quota
readback and the attested gateway route. Missing ⇒ typed
`EXPERIENTIAL_HOST_ADAPTER_MISSING` / `EXPERIENTIAL_HOST_CONTEXT_UNAVAILABLE`.
Nothing is manufactured: no quota readback, no entitlement, no token, no model.

Tests: `test_experiential_native_bridge.py` (hermetic; 33 passing at
composition time; run `python3 -m pytest test_experiential_native_bridge.py`).
