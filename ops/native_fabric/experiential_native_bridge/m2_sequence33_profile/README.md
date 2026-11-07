# M2 Experiential manual native profile: exact sequence 33

Status: SOURCE-ONLY / NOT INSTALLED / PROVIDER NOT AUTHORIZED.

This additional immutable profile binds the observed M2 native selection 177118be6675cf5a292524610afaaf4d5afc33dc6a150c22291240e3b6245fcd, sequence 33, as observed on November 5. It preserves the prior accepted sequence-30 profile without altering its pinned selection. A change to CURRENT.json makes this qualifier fail closed rather than downgrading or overwriting an installed generation.

Four exact SHA-256 preimage/patch/postimage sets rebase the approved Experiential manual-only changes onto sequence 33. Existing Ubuntu4 routing and source fixes remain; the single three-way conflict was the CLI qualification-host help line, resolved to retain current Ubuntu4 help while adding the four Experiential consent flags. The unchanged Experiential bridge and owner pin/transport continue to refuse serving in the absence of host-owned account entitlement, quota, privacy, and gateway qualification.

Non-effectful on-host source qualification:
  python3 ops/native_fabric/experiential_native_bridge/m2_sequence33_profile/qualify_m2_sequence33.py --installed-ext PATH_TO_SELECTED_NATIVE_EXT --owner-modules-root ops/native_fabric/experiential53 --output UNUSED_DISPOSABLE_PATH --verify-only

For disposable source candidate generation only, omit --verify-only, and supply an unused disjoint output path. Neither form performs a native publisher selection or restarts a service.

Only the original native publisher may consume qualified bytes after source approval, preserving all unaffected selected code and using its own exact CAS, source/user/writer/effect gates. The candidate is deliberately dark: experiential slot capacity 0, owner TRANSPORT_INSTALLED false, owner ROUTE_QUALIFIED false, and no trusted host context. Do not infer provider entitlement or initiate inference from the candidate.

The modern private Fabric service/tunnel owner must separately install an approved Experiential-capable backend with its normal stop/upgrade/seal/start process, preserving the enrolled tunnel. The ChatGPT app administrator must separately refresh the authorized tool schema. Account A 403, Account B ZDR and cap/entitlement, consent, model eligibility, funding, useful START/result and cost settlement are unresolved. No credentials or live provider calls are needed to qualify this source.
