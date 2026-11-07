# H3 joined-source qualification and unresolved contract

This is a **qualification-only artifact**, outside the native builder and installer. It is not an accepted runtime cohort. Its original H2 member qualification at a88488670bc99f7156eff193101b76795c16733f retains identical four-member pre/postimages; current complete native manifests and their changed surrounding parent are in installation-map.md. Do not select or install this H3 experiment.

## Exact reconstruction

Upstream H3 is Macro `ef95049fa2e1f8c981497c8a21b643fcbe59f25b`, `research/h3_expiration_account_admission/native.patch`, SHA256 `a494cb84d86c5592527943d8bb119726949efec62919def65f75cd31701e6ef8`. All sixteen declared preimages matched the current candidate sources. The original three output hashes were reproduced exactly before composition. No fuzz, guessed original or historical repinning was used.

The attached zero-context forward patch requires whole-file preimage authentication before application (`git apply --unidiff-zero`); both exact postimages were independently reconstructed from its hunks. It is against the **actual emitted H2** broker `100d6bff060ded3e8606d94cd9a3453b062bf2063f844bbb98b4d709e604d85e` and quota reader `91c89d4197d791a078e804db9c591c4cddc197f1e35f54f46fba95fe7b27a9a5`. The semantic conflict resolution retains H2 `quota_config_generation`/`quota_recovery_json` and H3 `account_admission_json`/`account_admission_digest` together in the same 19-value lease insert. The reader merged without conflict. Their exact postimages and byte lengths are in `h3-h2-composition-result.json`.

The original H3 `test_expiry_account_admission.py` ran against a disposable copy of the complete H2 HTTP stage with those two exact replacements: **32 tests, exit 0**, 3.127 seconds. Its existing offline boundary prohibited network, subprocess and credential effects. Synthetic data and receipts are not upstream capacity attestations.

## Five discriminating counterexamples

`h3-unqualified-boundaries.json` records additional probes using the original H3 fixture and actual joined Broker/SQLite owner. All effects were confined to disposable files, and no provider call occurred.

| Probe | Observed behavior | Missing contract |
| --- | --- | --- |
| Pending outer H2 refresh | H3 granted a lease from the retained inner admission envelope | Pending lineage must refuse admission |
| Failed outer H2 refresh | H3 granted | Original failure must invalidate the child envelope |
| Terminal outer refusal | H3 granted | Refusal must survive reading old child evidence |
| Changed outer configuration binding | H3 granted | Account, endpoint and current configuration must bind the admission envelope |
| One-unit request reservation, two-step APPLICATION grant | Two dispatch records were prepared after synthetic settlement of the first | Actual total billable steps must be reserved or enforced in every native meter |

The last probe sets both required windows to a claim maximum of one request and the existing application grant to two steps. No second provider request was sent. The two prepared dispatch records demonstrate that `budget_ref` is provenance, not consumption enforcement. Native harness code also explicitly distinguishes one harness invocation from internal provider attempts. A request-count ceiling therefore cannot be inferred for all native CLI transports.

These are qualification failures in the proposed H3 join, not regressions in the selected production generation and not evidence that H2 alone grants expiry admission. H3 remains excluded from all selectable artifacts.

## Existing-owner fence decision

The consistent order is publication lock → physical `active/.admission.lock` → Broker lease lock → SQLite. Quota publication takes physical admission before its existing cache lock, with network activity outside both.

The existing `support_bundle._policy_open_scope`, `_policy_handles_current` and `_policy_close_scope` implement physical custody checks and should own the common fence. Native enrollment currently takes publication then Broker; selection takes publication alone. All releases alias the same incumbent `active` directory. The actual placements are both enrollment transactions outside `_service_broker_lock`, shared `native_generation._select_locked`, Broker acquisition/application transactions before Broker lock, and H2 `_update_cache` before cache lock. Final digest rereads alone do not serialize those writers.

A safe implementation must also qualify the complete launcher/helper contract: `native_go_entry.MODULES` now preloads quota_remote and glm_keys, but not support_bundle; remote support closures do not include support_bundle itself; the launcher is separately sealed. A bare import or conditional no-op fallback would break source custody. Load verified target-release bytes for selection and the explicitly sealed native helper for new consumers. Require the existing physical lock before first selection of a fenced cohort. The original lane/policy owners can create that lock; the selector currently does not.

Current config/credential writers outside that physical fence remain an explicit census and participation gate. H2 currently checks config after provider response but before cache publication; that check must move inside the common critical section while retaining original refresh lineage. Fresh account documents, policy, observations and selected-source context must remain valid through lease commit. Do not invalidate or reassign original unsettled effects after a selection change.

## Exact outstanding inputs and acceptance

1. Original provider/Capacity owner supplies qualified physical product/account identity, endpoint/configuration generation, every binding window, exact native integer quantities, shared membership and settlement coverage. Percentage views must remain NOT_EVALUATED for entitlement/no-overage/admission.
2. Existing execution owners supply or enforce all billable continuations/retries in each actual meter; a configured ceiling/reference alone is insufficient.
3. Complete the shared-fence cohort, including all participating writers, immutable helper/launcher qualification and original rollback/drain custody. Exercise publication between choice/commit and competing claims on the actual owner paths.
4. Extend the existing GoRouter refresh/store projection with original successful observation time, binding and failure. Current `status()` omits `snapshot_at`; H2's qualified live reader intentionally supports GLM/MiniMax only. Preserve the original Go401 stop and absent APPLICATION activation; no alternate poller or authentication replay.
5. Supply H5 the role-authorized derived view and real sanitized observation, and H4 an actually qualified account/operation envelope. Runtime grants, first useful primary/tool acceptance and broader programme journeys remain open.

The assigned integration session owns this continuation. Original final carriers remain #2175/#10740 and the live gateway/TUI/J/reload effects remain under their existing identities. This artifact neither creates a new final branch nor transfers a live effect.


## Three outer invalidation guards qualified without activation

Reconciled the existing guard from Macro71cdb94bbad746fc7e39e8c37e58bfa7159b022c,
research/h6_account_publication/native.patch, Git blob4196345588cb35537f562acd19bed95c3a9be393.
Only the quota reader's outer pending, refresh-error and terminal-refusal check
is carried. The broader patch's Broker-first/nonblocking-admission lock sequence
is not imported; it does not replace the accepted publication → admission →
Broker → SQLite contract.

Apply h3-outer-invalidation-only.patch only after authenticating the exact joined
quota preimage8218b1f98e4b20c1dbe4f34b2d9525532865f98f09954278cd28ad32a4deaa7a.
It is a zero-context forward delta requiring git apply --unidiff-zero, followed
by exact postimage verification. The broker remains760a4432 unchanged. The exact
postimage, patch digest and independent apply/reverse proof are in
h3-outer-invalidation-qualification.json.

Four targeted cases passed on the original H3 fixture and real joined Broker/
SQLite owner with the existing offline boundary. All three invalidated records
refused both a new claim and a new APPLICATION turn. Every case retained its
original lease byte-for-byte in SQLite, with no extra lease, turn or request.
The clean synthetic observation still admitted its prior source behavior.

The prior five-counterexample receipt is historical baseline evidence. Three
rejection defects are now closed only in this qualification delta. The changed
outer physical/configuration binding, whole-operation meter enforcement,
publication serialization, real quantities and settlement coverage remain open.
No selectable native source, builder, installer or selected generation changed.
