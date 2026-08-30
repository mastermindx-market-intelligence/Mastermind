# Executive Capacity H0 Large-Closure Transport v3

**Status:** frozen same-carrier amendment after the first inert native-input build

**Protected implementation base:** `e53f524230ffc4e8730c844f6fc319d50a2050f3`

**Skillpack:** `mastermind.sol_skillpack.v1` version `1.0.1`, bootstrap major `1`,
`docs/sol_skills/INDEX.md` blob `21f45ca6d1d1bbacdb436fe5debd87851e4808a2`

## Outcome and evidence

The accepted Macro commit `dcdd939c45b23abce5ba04f95e330ac914a3904b` produces an
approximately 21 GiB complete reachable Git pack. Transport v2 correctly refuses it because v2 is
an exact ZIP32 profile and Apple Python's effective member limit is below 2 GiB. The privileged H0
repair separately capped its copied input at 4 GiB. The source implementation was merged, but this
made the native ceremony impossible; H0 therefore remains `BUILT_NOT_PROVEN`.

The repair adds one large-envelope version inside the existing transport owner. It does not add a
source root, lifecycle, queue, identity, retry, credential, provider, service, router or control
plane. V2 stays byte-exact and continues refusing ZIP64.

## Frozen v3 wire law

Schema is `mastermind.capacity_source_transport/v3`. The manifest retains exactly the v2 fields and
semantics; only `schema_version` changes. The envelope contains exactly `manifest.json` then
`payload.pack`, stored and unencrypted, with the existing timestamp, ASCII names and `0400` modes.

The wire profile is always ZIP64, including small fixtures:

1. `manifest.json` uses the exact existing ZIP32 local and central records.
2. `payload.pack` uses version 45, classic size sentinels, and exactly one ZIP64 size extra containing
   only the repeated 64-bit uncompressed and compressed sizes.
3. The central directory is followed by one exact ZIP64 EOCD, one exact locator, and one legacy EOCD.
   The legacy EOCD retains exact counts and central size and uses a sentinel only for central offset.
4. Comments, encryption, compression, data descriptors, duplicate/extra members, optional records,
   prefixes, suffixes and trailing bytes refuse.
5. Writer and reader reconstruct every accepted byte-level record. Generic `zipfile` acceptance is
   never canonical proof.
6. Payload reads and extraction are streamed in 1 MiB chunks. The retained payload/archive
   descriptors are revalidated before success; pack SHA-256, CRC-32, object count, semantic object
   inventory and Git pack trailer all bind independently.
7. Materialized worktree modes come only from each validated manifest row: `100755` becomes `0555`
   and `100644` becomes `0444`. A pathname or directory prefix never grants executable mode; in
   particular, a tracked non-executable file below `scripts/` remains non-executable and clean.

An inert disposable proof may be materialized on a separately mounted local APFS volume. The
materializer opens and validates the exact destination parent, retains that descriptor through
verification, and binds the candidate name and repository root beneath that capability. It does not
relax absolute traversal or device-continuity law for any other repository read.

## Privileged bound and recovery

The enclosing v3 file has one finite 32 GiB maximum. The builder, archive validator and privileged
no-follow copy enforce the same bound. Before root creates the staged copy, the retained transport
size must also fit three additional full-carrier copies plus a 2 GiB reserve in the target
filesystem's currently available blocks. The observation is not treated as a reservation; ENOSPC
still refuses and remains same-carrier recoverable. This safely contains the measured 21 GiB carrier
with pack-layout headroom while preventing unbounded root staging.

New native repair uses only v3. Installed-manifest verification dispatches only exact v2 or exact
v3 so a durable pre-intent v2 candidate can still be reconciled. Existing intent fields already bind
the enclosing transport SHA-256, canonical manifest SHA-256, object count and semantic inventory;
no recovery schema changes. Cross-version retry is impossible because both transport and manifest
identities differ.

## Capability and stop state

A merge makes the large authenticated carrier source durable, not native-proven. Acceptance still
requires a v3 build from the full local Macro repository, one bounded administrator ceremony, one
repair receipt, two verify-only receipts, empty stderr and absence of the disposable root carrier.
The terminal outcome remains `H0_INSTALLED_HOST_PASS_NOT_P0_ACCEPTED`; CF2-P0, OAuth, services,
routing and worker execution remain separate gates.
