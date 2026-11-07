# Exact R2 original-review recovery candidate

PATCH_ONLY. No installed collector change, remote observation, worker replay,
lease settlement, result adoption, or acceptance has occurred.

`recovery-scopes.patch` extends installed collector preimage
`89b9acd36608742b62baa4e2366f810f8c1071a51510c3d17d14cdb64dc6e534`
for exactly the two runs in `SCOPES.json`. All four incumbent scopes and the older
Office/refused operations are unchanged. The two additions pin the original
root and parent, host, Qwen mode/requested model, packet path/hash, support/log
hashes, local lease witness and fixed new evidence destination. The small lease
check reads and hashes the local witness only; its contents never leave the
process, and it gives no settlement authority.

`PROVENANCE.json` identifies original native construction and dispatch records.
Both packets were reconstructed from those literal construction recipes and
committed source: composition 03b063a3b, AEAD f8ae20d52. The reconstructions equal
the retained packets byte for byte (76983 and 57337 bytes). This is stronger than
hashing current files alone, but remains retained correlation rather than
producer-root authentication, causal packet-consumption or served-model proof.

89 inert tests pass, including existing artifact/plain compatibility, Qwen
capture, wrong root/parent, packet/support/log/lease drift, cross-run substitution,
drift during capture and before consumption. Transport is mocked. Receipt state
still says lease/controller UNKNOWN, acceptance NOT_RECORDED.

Actual local binding preflight from this source workspace stopped at the existing
directory guard: `/Volumes/Mastermind 2` is mode 0775. No directory mode or guard
was changed, no transport was called, and this does not qualify an actual read.
The Fabric owner retains installation, independent provenance/permission review,
and the permitted actual binding/destination preparation and collection path.

`build_candidate.py` documents the reconstruction and initial scaffold. It does
not launch or collect. The checked candidate includes the subsequent small lease
witness guard; do not regenerate the scaffold over that reviewed candidate.

Test result: `/Volumes/Mastermind/evidence/meta-ceo-r2-20261012-01a13315/r2-plain-scopes-checks.xml`.

Independent source review: MiniMax/Ubuntu3 returned scoped PASS at exact collector
`deb6a0cf463a66bd6a47a8aae345a9ab8c48cf7fc5db7d61bff9d4537e918342`.
The assigning parent checked its concrete findings and original record pins.
The child returned 3945 characters against a 3500-character bound, so its worker
outcome remains NOT_ACCEPTED; the scoped source finding is retained separately.
No installed collection, result acceptance, native authentication or readiness is claimed.
