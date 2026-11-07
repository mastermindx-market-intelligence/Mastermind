# Exact Linux installed-generation forward-port (source-qualified, not installed)

**Source identity:** original Mastermind #2045 native bridge. This is an
additional *read-only compatibility profile*, not a second source publisher,
admission plane, host installer, queue, lease allocator, credential reader or
worker runner.

The original #2045 four-patch manifest applies to the sealed older
`quota_continuity/source` release. It cannot be applied unchanged to current
Ubuntu Fabric installations. The 2026-11-04 Ubuntu0/Ubuntu3 native kits had
newer code in `fabric_task.py`, `remote_sub.sh`, `sub.sh`, `slot.py`.
This profile forward-ports the new manual-only Experiential route through the
four **observed exact installed preimages**, preserves existing host admission
and routing logic, and keeps the provider disabled. It is a distinct exact
preimage profile; do not reuse it on other hosts or generations.

`profile_manifest.json` binds all four preimages, strict no-fuzz patches,
postimages, the source bridge and digest-sealed owner
`experiential_pin.py`/`experiential_transport.py` modules. The observed
Ubuntu1 kit differs in `slot.py` and `sub.sh`, so Ubuntu1 is intentionally
**not** admitted by this profile. M1 Studio has substantially different
installed source and is excluded as well. Any source drift, symlinked file,
unknown profile, changed patch, missing owner module, output overlap or
existing output refuses before writing. The bundle copies **no** host
credential, key, cap, entitlement, webhook, queue or context assertion.

Qualification (on a disposable, unmodified Ubuntu0/Ubuntu3 source kit):

```bash
python3 qualify_linux_current.py \
  --installed-ext "$HOME/lanes/ext" \
  --owner-modules-root "<trusted Mastermind/ops/native_fabric/experiential53>" \
  --output "/tmp/unique-new-output" \
  --verify-only
```

Omit `--verify-only` to materialize **only a new disposable source
candidate** at the output path. It is never published to
`~/lanes/ext` or the native generation store. The receipt declares
`QUALIFIED_SOURCE_ONLY_NOT_INSTALLED`,
`admission_granted=false`,
`host_context_owner_required=true`, `worker_started=false`.
The existing verified native generation publisher/selector, real account and
gateway attestations remain required for any live install or effect.

For proof: run
`python3 -m pytest -q test_qualify_linux_current.py`.
At qualification 10/10 focused tests passed, and the actual Ubuntu3 profile
successfully produced a candidate whose four file digests matched the bound
postimages. A synthetic dry-run `fabric_task.py request` on that candidate
returned `EXPERIENTIAL_TRANSPORT_NOT_INSTALLED` (exit 75) without any lease,
worker, packet state or provider POST. That refusal is expected and protects
against false activation.

**Important:** Account A's prior HTTP 403 hold remains; Account B's provider
cap/entitlement readback is not authenticated, so no auto-failover, retry,
credential substitution or billing activity is authorized. Platform-funded
retention/consent and native provider qualification are still mandatory.
