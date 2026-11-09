## C2 Personal v12 -> v20 selection prepared (source-only, 2026-11-02)

The legacy C2 Personal M2 seat now selects exact v12 (bridge
`82bc7f2d...`) on the sealed 12-file closed-publisher generation, so the
historical v10 -> v12 admission above can never fire for it again. The running
catalog keeps `accepted_for_write=false` for Paper 0.5.18 and the Business-seat
v20 rollout does not update this consumer, so the installer's
`paper-runtime-upgrade` operation now recognizes this one exact cohort and
selects the accepted immutable v20 generation through the identical single-use
manifest-CAS transaction. Every other admission — both C2 accounts and C4 —
remains the unchanged v10 -> v12 selection, and the global runtime pin stays
v12.

Admission pins for the new path: freshly observed predecessor manifest CAS
`c5cdba867972f547aaefa7dbfc5840467d2961c7f4d346e8de1f1ba575686ef6`; sealed
non-Paper configuration
`201288e64eadeb25e16306e737831fb828ce638a54b0e41c16945bd1c737eb08`; the
installed 12-file cohort re-derived from the reviewed closed-publisher patch
plus unchanged fleet modules (no byte identity invented); and target bridge
`1a73ab002e89c87b489e8cee9f5c821530929a5b701eb0aaac7eed03a5a22ced`, whose
directory remains owned by `runtime_stage.py`'s immutable v20 staging. The
node/backend/dependency identity is inherited from the seat's sealed C2
predecessor because the publisher patch changed only module bytes; a live
manifest that disagrees refuses closed and requires fresh observation of the
exact differing identity fields before any source change. Both the retained
v12 runtime and the staged v20 generation must pass the existing verifier
before any write.

Prepared operator sequence (independently reviewed release only; not executed
here): stage and verify v20 with the `runtime_stage.py` owner, run the
read-only preflight with
`--account chatgpt2-personal --expected-manifest-sha256
<fresh-observed-manifest-sha256> --preflight-only`, then stop the seat with the
accepted helper and repeat without `--preflight-only` from a carrier that
survives stopping C2 — never a self-cutover through this gateway. Only
`paperDesign` and the manifest `configHash` change; every module byte, plist,
node/backend/dependency seal and source pointer is preserved, and pre-commit
failures restore the original bytes while post-commit failures stay
EFFECT_UNKNOWN with no replay. A stale CAS, changed profile, wrong cohort or
identity, invalid v20 receipt/bridge/python, loaded service or concurrent
drift is a gate. As with the proposal below, this source readiness is not
deployment acceptance: the v20 BUILT_NOT_PROVEN receipts (independent review,
protected merge, real exact-target edit, readback, screenshot and reconnect)
remain outstanding before any live selection.

## P00 pre-dispatch requalification repair (source candidate; not installed)

P00's inspection of the existing #1011 path observed Paper Desktop 0.5.18
catalog `16e6b93f...` accepted under `TOOL_SCOPED_CONTRACT_V1`. The historical
whole-catalog mismatch is resolved on that observed direct path; do not change
the expected upstream digest or repeat the already accepted v20 installation.

An independent offline source assessment found a remaining ordering gap: an
edit or snapshot-guarded read qualified its requested tool, invoked the vendor
`get_basic_info` guard, then dispatched the requested tool using the earlier
qualification. A material descriptor change during that intervening RPC could
therefore reach Paper. The proposed immutable v21 bridge rechecks the live
server/getter contract, the requested tool and its outgoing inputs after the
guard and immediately before dispatch. The shared validator also rechecks
HTML versus legacy text payloads if the vendor changes between reviewed
profiles. Pre-dispatch refusal remains a refusal with no requested mutation;
post-dispatch verification uncertainty remains `EFFECT_UNKNOWN`, never replay.

The v2-v20 pins remain byte-for-byte historical identities. V21 is only a source
candidate until independent original-owner review, required hosted checks,
protected release, and an admitted same-service activation occur. Do not
hotpatch an installed bundle, select a new runtime, restart a service or change
credentials from this source receipt. Accepted v20 direct-path evidence stays
preserved, with this newly found condition carried into the next review.

This repair does not broaden the allowlists. Folder creation/resource moves/
archive/unarchive remain blocked. `create_file` still requires an exact guarded
source or clone file and rejects `parentId`; file rename still excludes folders.
The published app's older file-creation/focus/exclusive-file wording must be
refreshed through the same app's normal approved action publication, not through
a source rewrite or alternate carrier. No new whole-file or page-wide lock is
introduced. Qualification cannot guarantee atomic vendor behavior between the
final catalog read and call; it removes the deterministic intervening-RPC gap.

## Upgrade-resilient tool-scoped Paper compatibility (proposed source, 2026-11-02)

PROBLEM: the historic full-catalog SHA admission rule made every
otherwise-working Paper edit unavailable when any upstream tool was
added/removed or when an unrelated description changed. Paper's release
version has already been diagnostic-only; it is NOT a version-equality bug.
Previous reviewed full-catalog digests remain recorded as historical
provenance, but they are no longer the normal whole-service write gate
in this proposed bridge 0.1.8.

DECISION: derive reviewed, per-tool input contracts from the four retained
full-catalog fixtures (0.5.14/0.5.15/0.5.16/0.5.18). For each vendor call,
enumerate the live catalog on the incumbent loopback client and compare
the requested operation's JSON-schema structure and safety annotations
against those source-owned contracts. Ignore harmless presentation fields,
required/enum ordering, unrelated new/removed vendor tools, and new optional
top-level inputs that have no default (the bridge rejects callers supplying
such newly added optional inputs before dispatch). Vendor version is logged
only. Do NOT auto-admit a new tool name or a changed required parameter,
type, nested input schema, constraint, default or destructive/read-only
annotation. The source-owned bridge allowlists remain unchanged.

FAILURE ISOLATION: a material mismatch in one writing tool returns
TOOL_SCHEMA_CHANGED for that tool only, before any upstream dispatch.
Other still-qualified edits and read-only access continue. The critical
get_basic_info document/snapshot schema and paper-desktop server identity
must remain compatible for any write, since unsafe targeting would affect
every operation. All existing explicit fileId/snapshot/operation-ID,
per-desktop mutex, guarded file management, no replay and EFFECT_UNKNOWN
requirements are unchanged. paper_catalog reports catalog_policy,
full_catalog_known, compatible_write_tools, incompatible_write_tools,
optional_vendor_inputs_ignored, and marks held operations edit_held_schema.
paper_prepare readiness means at least one write tool is compatible, not
that every edit is permitted; the actual chosen tool is revalidated on its
own paper_edit call.

SELF-HEALING BOUNDARY: benign changes are accepted automatically at the
very next tool call without a daemon, restart, new tunnel, new auth plane or
release-hash hotpatch. Material semantic changes still require an explicit
reviewed source update for only the affected operation; no software can
prove unchanged behavior solely from an input schema. Immutable
v17 and v18 remain historical, rejected-for-release candidates: the
later source review found unqualified reads and unsafe verification
under mid-operation vendor descriptor drift. Proposed immutable v20
requalifies each reviewed read/write tool and its outgoing arguments,
including implicit get_basic_info and the post-edit verification getter.
In addition, after the FIRST get_basic_info read it requalifies the
critical live getter again before any SECOND file-only snapshot call;
unsafe drift refuses without dispatching the second getter. If
post-write verification cannot safely proceed, retain EFFECT_UNKNOWN
with no replay, not an invented successful receipt. v19 is now a
preserved but superseded, release-ineligible runtime generation.

The v20 source remains BUILT_NOT_PROVEN until a new independent exact-head
review, required hosted CI, protected merge of the #1925 -> #1935 ->
#1942 chain, original Ryan same-label installer selection, and a real
exact-target scratch edit, readback, screenshot and reconnect receipt.
Synthetic tests and read-only live catalog checks are not deployment
acceptance. Preserve prior immutable runtime generations and do not
select or overwrite v17/v18/v19 candidates.

## M1 Paper 0.5.16 exact catalog compatibility candidate - 2026-11-02

This source-only follow-up is based on PR #1925's unchanged semantic source head
e7016693f602f9f8c2dc52c99ac7111d4a641773, not on a deployed v15
runtime. M1 Studio was independently observed running Paper Desktop 0.5.16
and canonical full 37-tool SHA256
955e92cd0477027dcc5fe666810e49393f42f453c1c362e64cd0f3b3ab9f10cf.
The complete observed catalog is checked in at
tests/fixtures/paper_desktop/955e92_full_catalog.json.

Compared to approved 37-tool 1b9aff baseline, no tools were added or removed.
Exactly six descriptors changed: get_comment_thread, get_jsx, get_node_info,
set_text_content, update_styles, write_html. Like the independently reviewed
M2 Paper 0.5.18 41-tool catalog, M1 requires updates[].html rather than legacy
textContent. New bridge 0.1.7 admits only this reviewed full digest as an
additional explicit alternative, keeps the old approved catalogs, blocks
all prior four M1 resource tools, rejects obsolete text edits before upstream
dispatch, and proposes new immutable v16 pin without mutating v2-v15.

This is NOT a review, merged source, Paper app update, M1 deployment or
production write receipt. The actual M1 active v12/v14 runtime remains
unchanged pending its own independent review, accepted release and real
exact-file guarded editing/visual proof. Never silently use the M2 digest for
M1 version 0.5.16.

## Paper 0.5.18 exact-catalog compatibility candidate - 2026-11-01

The M2 Paper Desktop has two installations: /Applications/Paper.app v0.5.11
and the intended ~/Applications/Paper.app v0.5.18. A graceful transition to
the latter restored a direct paper_inspect CONNECTED response for explicit
MASTERMIND PAGES file 01M2WGNCX9475G79JRKJTCM08P. This is a connection
receipt, not a live write or restart-resilience acceptance result.

The captured 0.5.18 41-tool full catalog is retained as
tests/fixtures/paper_desktop/16e6b_full_catalog.json; its canonical SHA-256 is
16e6b93f0c51a1574ba8acee4df732052898707a04731d3817530971a88fdefd.
Compared to accepted 37-tool 1b9aff..., no names were removed; the four new
resource tools archive_resources, create_folder, move_resources and
unarchive_resources stay uncallable. Ten existing descriptors changed,
including rich HTML set_text_content (updates[].html replaces
updates[].textContent), get_jsx styling default, and optional resource
parameters. The guarded successor bridge 0.1.6 admits this exact full-catalog
digest and refuses obsolete text-edit payloads before dispatch, retaining
all file/snapshot/operation/unknown-effect constraints. Historical catalog
receipts remain accepted. Any future descriptor drift fails closed.

This is a source-only candidate, not a live activation. Immutable
runtime_stage.py v15 is proposed as a new hash-pinned generation; do not alter
v2-v14. After an independent non-author review, accepted source release, and
installer-controlled seat replacement with original manifest/seat identity,
prove on the same direct carrier: accepted live schema, exact scratch-file read
and prepare, a bounded guarded edit using updates[].html, same-file post-read,
screenshot, and reconnect without duplicate clients. Never manually repin the
installed v13 bridge or claim deployment from green synthetic tests.

# Paper.design integration - bounded local and web design capability

## Guarded file/page administration candidate (2026-10-22; NOT installed)

### Paper 0.5.15 exact-catalog compatibility candidate (stacked successor, not active)

Read-only inspection of M1 Paper Desktop 0.5.15 observed upstream catalog SHA-256 `f3483e001d4f07f5a49144ca52a4f9e14ba046e35546dda05d6cd37c9d2b4728` with exactly 37 tools. Compared with Paper 0.5.14, only `get_jsx` changed: its default styling format became `inline-styles`, with enum ordering `inline-styles,tailwind` and a corresponding description change. All other 36 descriptors, including file and page operations, were identical.

The stacked v14 bridge admits only the two reviewed complete-catalog digests and retains server identity, source file guards, operation IDs, write permission, and fail-closed drift handling. JSX readers should provide an explicit `format` if the default matters. V13 remains immutable and usable for M2; staging v14 does not select any live runtime or update a workspace plugin. Paper 0.5.15 still has no native whole-page transfer/deletion method.


Current exact Paper 0.5.14 catalog includes `list_resources`, `create_file`, `rename_resource`, `arrange_pages`, and `update_pages`, which the prior v12 bridge intentionally blocked. The bounded candidate admits `list_resources` as read and `arrange_pages`/`update_pages` as guarded edits. It adds `create_file`/`rename_resource` to the existing modifying `paper_edit` action so the already-published five-tool MCP surface remains unchanged; internally these receive extra file-management validation. It preserves full-catalog SHA pin, existing file snapshot, operation id, desktop mutex, no replay and unknown-effect rules. In this candidate, create_file requires either `cloneFileId` (copy entire file) or `sourceFileId` (guarded context for creating an empty file), plus a name; `sourceFileId` is a bridge-only guard and is never forwarded to Paper. Renaming accepts only exact Paper file IDs, never arbitrary folders. An observed create-file response is explicitly `RESPONSE_OBSERVED_REQUIRES_TARGET_VERIFICATION` until the returned new file ID is separately read and checked; neither a clone nor a successful response means a cross-file page migration occurred.

**Crucial limitation:** Paper's reviewed 37-tool MCP schema does not expose a native move-page-between-files, delete-page, or delete-file operation. The candidate **does not** delete originals or reconstruct pages from JSX and claim a lossless transfer. For the 63-page MASTERMIND PAGES cleanup, make a source inventory, create destinations and whole-file preservation clones, verify every destination's ID and contents, then move a page only through a subsequently verified lossless vendor operation or explicit attended Paper UI transaction with source/destination readback. Preserve original pages pending verification, with no speculative deletion or raw database edits. This candidate pins immutable v13 bridge source separately from the installed v12 runtime. The existing MCP five-tool surface remains unchanged; action-description refresh may still be necessary for individual ChatGPT seats. v13 staging alone is not activation, an Executive grant, a scratch-file canary, or production acceptance. No current Paper pages have been moved or deleted.


## Mission and frozen boundary

Chairman direction, 2026-09-13: make Paper ready for local agents and ChatGPT Web,
without buying a plan. The useful end-state is brief -> editable Paper design ->
screenshot/review -> JSX -> integrated, browser-proven product, not merely an MCP entry.

Procedure source: Mastermind protected master
`55473bb43c3ae1908f53ddd4ccfe724643dd6c69`, Sol Skillpack 1.0.1 / bootstrap 1.
Paper official plugin reference: `paper-design/agent-plugins` at
`f6d4f13343dd924fabaadd0898725f1b8718459d`.
No production lifecycle, queue, identity, credential or authentication store is added.
The only shared runtime file is a per-OS-user advisory mutex for the Paper desktop.
It is not an ownership lease, Job state, deduplication ledger or authorization token.

## Direct Business migration — issue #1011

Chairman direction, 2026-09-26: build the private **Mastermind Paper** direct route first, reuse one
existing tunnel, and leave credentials, Business workspace enrollment, activation and live canary
until the final attended setup. See `docs/PAPER_DIRECT_CHATGPT.md` for installation and acceptance.

Target normal Business path: private Mastermind Paper app -> OpenAI Secure MCP Tunnel -> existing
guarded stdio `mcp_server.py` -> the same `bridge.py` -> fixed Paper loopback. The direct app exposes
no generic workstation tools and does not depend on Studio Direct/DC for normal Paper calls.
The previous blanket dedicated-app prohibition is superseded for this commissioned migration.
It does not authorize public publication, duplicate tunnels, unattended account changes, or a second
Paper guard/auth/retry owner. The direct build uses Paper's explicit-file contract: `paper_prepare`
validates one target by bare `fileId` and returns that target's snapshot without requiring the
user-active file to switch or exposing arbitrary host/raw `open_file` control. Subsequent direct
edits validate and post-read the same explicit target file.

Staging and local stdio proof are not enrollment or cutover. After the actual Business app and
scratch-file path are accepted, retire Studio Direct's primary Paper-Web requirement for that
workspace. Other seats retain their legacy route until separately migrated. No denial or unknown
effect ever authorizes a carrier/account/model switch. A migration canary is an explicit single-carrier operation. That carrier/effect fence is scoped to
that logical canary; it is not a file-wide writer lease for unrelated Paper edits.

Direct target-binding qualification — 2026-09-27: live Paper 0.5.12 evidence showed that raw vendor
`open_file` can return the requested file's `get_basic_info` while the user-active file remains
unchanged. A separate read-only probe proved `get_basic_info(fileId=...)` succeeds for a recent file
that is not open, without changing the active file. All 12 guarded edit schemas require `fileId`.
Therefore UI focus is not a write-safety prerequisite for the direct route; exact target identity and
target snapshot are. Legacy Studio `paper_prepare` publication behavior remains a separate client path.
The resulting target-aware bridge is immutable runtime generation **v6**, SHA-256
`938c45356f95f3a57df2290e2da045eae9a6c4a0c3507dfff81c40a87e85b72a`. Legacy Studio Direct
remains pinned to runtime v5 until separately selected for upgrade; the Business direct canary may
stage v6 without moving that legacy carrier.

### Direct Business multi-seat transport — 2026-09-27

The direct route may serve multiple ChatGPT accounts/workspaces concurrently without multiplying the
Paper control plane. Each Business seat owns one exact tunnel-client process, loopback health endpoint,
private bundle state and seat-specific transport singleton/launchd label. Every seat's MCP child still
loads the same guarded bridge implementation and all Paper calls contend on the existing per-OS-user
`desktop.lock`. Ordinary same-host overlap waits on that local mutex for at most 30 seconds before any
Paper call is sent; prolonged contention fails closed as `DESKTOP_BUSY`. This preserves one Paper Desktop
execution plane and one shared safety/effect contract while allowing C1/C2/C3/C4/admin ChatGPT transports
to remain connected simultaneously. The bounded lock wait is not a retry owner or persistent queue, and no
transport seat creates a Paper user identity, document lease or second auth plane.

Seat-aware install schema v3 requires a safe stable `seat_id`; legacy v2 bundles remain backward
compatible. v3 local binding requires the exact tunnel ID but does not require a guessed backend
workspace ID. When an exact workspace ID is independently observed it may be recorded; otherwise the
OpenAI tunnel/workspace association is proven through attended account setup and direct app discovery.

## Architecture — shared adapter and legacy/non-migrated clients

Local Claude/Codex/Cursor/OpenCode/VS Code client -> approved project-scoped MCP
configuration -> `mcp_server.py` (official MCP SDK, stdio) -> `bridge.py` ->
Paper's fixed loopback MCP `http://127.0.0.1:29979/mcp`.

ChatGPT Web -> existing Studio Direct private Secure MCP Tunnel -> Studio Direct
gateway-owned `paper_inspect` / `paper_catalog` / `paper_read` / `paper_prepare` /
`paper_edit` tools -> the SAME SHA-pinned `bridge.py` -> Paper's fixed loopback endpoint.
Screenshots remain native MCP image blocks. The Web caller cannot provide an
arbitrary host path, Paper endpoint, account or credential.

Studio Direct is the existing legacy Web gateway/auth/transport owner; Paper does not get a
second public gateway. It is the preferred attended-Web carrier for non-migrated seats when the
Paper tool family is actually exposed. Remote Desktop Commander is also a direct-host client of the
**same guarded bridge**, but Studio Direct absence grants it no authority. RDC may be
selected for a Paper effect only when the current Chairman assignment/delegation or
accepted canonical placement independently authorizes that exact host carrier and
Paper action, current host permission is observed, no explicit denial applies, and no
conflicting or unknown Paper effect exists. Otherwise the session stops at the exact
carrier gate. This is not a second gateway, auth plane, write authority, or permission
fallback. The current protected `private_service.py` runtime/schema/SHA pins, not folder recency
or an old installation receipt, determine the exact bridge that Desktop Commander may
invoke. Do not expose the raw unauthenticated Paper port through a public tunnel, add
another OAuth service, or put design tools into Executive OS's bounded CEO-admission API.

Capability discovery is action-specific. A session that sees Studio Direct filesystem/
process tools but has not checked for `paper_inspect`, `paper_catalog`, `paper_read`
and `paper_edit` has **not** established Paper unavailability. `paper_inspect` now
returns `gateway_surface`, which declares the exact Paper tool family the current gateway
is built to advertise. If that contract includes `paper_prepare` while the ChatGPT client
surface omits it, classify the mismatch as publication/surface drift: `STUDIO_TOOL_PUBLICATION_DRIFT / EFFECT_NONE`. Current-file
reads/edits may remain available, but exact-file transition is held until the same Studio
Direct app's **workspace-approved action snapshot** is current and `paper_prepare` is directly
surfaced. OpenAI documents that approved MCP apps use a frozen tool/input snapshot and do not
auto-update when the server changes. Business and Enterprise/Edu workspace admins with
management permission and a valid connection can **Refresh the existing published custom
MCP app's tool definitions without recreation**, review/publish the changed actions,
and start a new conversation. Developer-mode connections use Refresh; Plugin Directory
plugins use continuous tool review/rescan. If Refresh is unavailable for the exact app,
hold at the workspace admin gate rather than creating a duplicate app or tunnel. Do not reproduce
prepare with generic Studio `start_process`/filesystem tools, RDC, raw upstream `open_file`,
shell, or UI automation. This keeps file transition inside the reviewed narrow action instead
of silently broadening workstation authority.
A proven pre-dispatch absence that remains after current same-Studio publication recovery
may make an **independently authorized** RDC carrier eligible under the separate carrier
law; absence itself never supplies permission. After edit dispatch, timeout/lost response
remains `EFFECT_UNKNOWN` on the original carrier and forbids cross-carrier replay.

### Paper 0.5.14 catalog qualification — 2026-10-01

Paper Desktop 0.5.14 later changed its full canonical catalog from accepted
`8cd27488a3adfc19c6c36d4349b75feebc71c159253c47f8a0f8d50c27043deb` to
`ac18857df0aa6323646333368e5798e7c28de7b4d5f5dc3cb320276e3535daa9`. Qualification used
the complete live 36-tool dictionary plus durable accepted `ca90...`/`8cd...` receipts. Rebuilding
the 34-tool predecessor by removing `rename_pages`, `list_resources`, `rename_resource` and restoring
the exact historical `list_files` descriptor reproduces `ca90...` exactly; adding the current
`rename_pages` descriptor reproduces accepted `8cd...` exactly. The current full map independently
reproduces `ac18857...`. Thus the accepted-to-current delta is exactly: remove `list_files`, add
blocked `list_resources`, add blocked `rename_resource`; no surviving descriptor changed.

Bridge 0.1.4 keeps the same 12 edit tools, reduces the read allowlist from 17 to 16 by removing
`list_files`, and does not expose either new resource tool. Immutable runtime generation v10 owns
bridge SHA-256 `7d810c458a53e00e21014fd7375ac338dc9c1421b30f823feb4d34184f9d08fc`; v9 remains unchanged.
Exact target, snapshot, token-delete, desktop mutex, and EFFECT_UNKNOWN/no-replay guards are preserved.
Evidence: `docs/evidence/paper_desktop/20261001_0514_catalog_compatibility.json`.

### Reviewed v11 selector predecessor — 2026-10-17

The preceding canonical Studio Direct release selected immutable Paper runtime **v11**,
bridge SHA-256 `6d28be62b21bff12dc04ae1bdc50f12a4ff55fdb8261bdd6923bac2804fecf7c`.
That generation is already qualified in `runtime_stage.py`; its exact full-catalog
pin is `48b2587455d839a57b4b78f5cfdb2e75df8d530ad8059a3ad6af303c0d37224f`.
This closes the release gap in which the canonical bridge supported the observed
Paper catalog while Studio Direct still installed v10 and refused design writes.

Existing installations remain on their current generation until the normal owner
stages v11, stops the explicitly selected seat, upgrades it with its existing
account/node/backend/port and preserved capability profile, then starts and reads
back that same seat. No live config or immutable v10 file is edited in place. The
catalog equality check, exact file/snapshot binding, desktop mutex, operation
identity and unknown-effect rules are unchanged. Source selection is not a live
rollout receipt; selected-seat catalog/read/edit proof is recorded separately.

### Paper 0.5.14 catalog successor: v12 — 2026-10-17

A fresh read before C2 activation observed a second catalog change within Paper
Desktop 0.5.14. The complete 37-tool dictionary independently reproduces SHA-256
`1b9afff4c9bcf6f11f5ca2db301bf25ccdc442025344e2ec402459cedcd6a2db` and is preserved in
`tests/fixtures/paper_desktop/1b9aff_full_catalog.json`. Compared with the qualified
`48b258...` predecessor, 32 surviving descriptors are unchanged. The three changed
survivors are `create_page`, `get_basic_info`, and `get_jsx`; blocked `rename_pages`
is removed, and blocked `arrange_pages` and `update_pages` are added.

Every existing property, required field, schema constraint, annotation, and access
classification of the 28 admitted tools is retained. Additions are the optional
decorative `create_page.icon` enum and optional `get_jsx.includeNodeIds` and
`get_jsx.includeRootPositioning` booleans. Page metadata can now contain divider
entries; their IDs are not page IDs. The bridge does not derive a target page from
that array. JSX remains a read-only pass-through; callers can request clean exported
code explicitly, while root canvas positioning is omitted by the new default.

The canonical selector now targets immutable **v12**, bridge SHA-256
`82bc7f2d75aec423711922198b68f317618a83de177bf4934b73d7b418a6ecfb`.
Its bridge changes only the exact reviewed catalog pin. All blocked-tool,
file/snapshot, mutex, operation-identity, and unknown-effect rules remain active.
`runtime_stage.py` preserves every v2–v11 source pin and never rewrites their
immutable directories. The previously staged v11 was not activated on C2.

### C2 fleet installation: Paper-only runtime selection — 2026-10-17

The attended C2 Personal gateway has an existing sealed V2 manifest with an exact
11-file fleet/tailnet bundle. It predates the 12-file ChatGPT1 compatibility cohort
and is not the current protected `STAGE_FILES` bundle. The prior installer rejected
this cohort as `corrupt manifest` before any effect; inspection established that all
11 installed files matched their recorded hashes. The historical source-directory
pointer is retained provenance, not a safe instruction to restage its current bytes.

The canonical private installer owns the bounded `paper-runtime-upgrade` operation.
The C2 Personal case recognizes that reviewed account and exact installed file digests, verifies
the existing node/backend/dependency seal and plist, and requires a caller-supplied
compare-and-swap digest of the current manifest. Admission is restricted to the
canonical digests of the reviewed original manifest and its planned v12 successor;
a self-consistent but different profile is not enrolled. Its separately pinned
non-Paper configuration identifies the observed capability profile. Generic
whole-bundle upgrade remains guarded for both historical fleet cohorts.

This operation selects the installer-owned, verified immutable v12 Paper runtime.
It preserves every gateway/module byte, the original source pointer, launchd plist,
binary and dependency hashes, account/port, fleet routes, concurrency settings and
all other configuration. Only `paperDesign` and the manifest's `configHash` change.
It does not copy draft fleet source, enable capabilities, alter a tunnel or switch
the Paper carrier.

The Paper transaction, start, stop and seal commands share a nonblocking per-account
lifecycle mutex, held across verification, effects and any recovery. The private
`state/private-service.lifecycle.lock` file remains in place so concurrent commands
always contend on the same inode. Read-only preflight does not create or acquire it.
Service absence requires launchctl's exact code 113, empty stdout and missing-service
diagnostic naming the requested label and current user's GUI domain. Other errors or
malformed successful output are indeterminate and cannot authorize a lifecycle effect.

The assigned operator uses the exact reviewed release helper:

1. Stage and verify v12 with the existing `runtime_stage.py` owner.
2. Run the read-only preflight while the original service remains available:

   ```sh
   python3 <accepted-release>/integrations/studio_direct_mcp/private_service.py \
     paper-runtime-upgrade --account chatgpt2-personal \
     --expected-manifest-sha256 <fresh-observed-manifest-sha256> --preflight-only
   ```

3. Confirm the original seat has no in-flight work or unresolved effect, then stop
   that exact seat with the same accepted helper.
4. Repeat the same Paper operation and manifest digest without `--preflight-only`.
   The installer writes configuration atomically and the manifest last, and verifies
   the retained runtime seal. Dependency reinstallation is not part of this change.
5. Start the same seat through the installer, then observe a new gateway generation,
   v12's exact accepted catalog, preparation of the intended file, and an explicitly
   requested guarded edit with readback. These live receipts are distinct from source
   or runtime-stage readiness.

A stale manifest, changed profile, unrecognized bundle, unsafe file, invalid runtime,
concurrent lifecycle command or loaded-service refusal is a gate, not an invitation
to edit JSON manually. The transaction reconciles observed bytes before rollback;
an unknown effect requires reconciliation through this same owner before restart
or replay. Existing Paper
snapshot, file-writer, operation-id and no-cross-carrier-replay rules still apply.

### C4 exact-cohort qualification — 2026-10-18

The C4 installation uses account `chatgpt4`, port `45024` and launchd label
`com.mastermind.studio-direct-private.chatgpt4`. A read-only host census verified all
eleven installed module hashes, the Node/backend hashes, plist, the two-pass
dependency seal, and the original non-Paper configuration. Although its eleven
module bytes equal the reviewed C2 bundle, its manifest, configuration and dependency
pins are independent. The new C4 predicate admits only its original manifest and the
planned v12 successor. Existing C2 account eligibility and pins are preserved.

This proposal composes incumbent PR #1603 at
`12fe3d9a7f5ed7deff75b1e8c9101227a92d0aa8` in an isolated source branch; it does not
modify that source branch or adopt a C2 live rollout. Review found that the existing
C2 Business compatibility updater can write the same manifest as the Paper updater.
Its modifying dispatch now takes the same account lifecycle mutex across validation,
writes and recovery. The genuine Business read-only preflight remains lock-free,
and its account, source, module, capability and manifest admission rules are unchanged.

Source `0ef1aa2c1900ee5b0141c2e6357dac20187de3e2` passed all **148** installer tests.
Ten new tests exercise the actual C4 command paths, including ambiguous service
absence, both pre-commit and post-commit uncertain effects, safe rollback, lifecycle
contention and replay refusal. Four sibling-writer tests prove mutual exclusion at
real configuration/module write boundaries and during recovery. Both public command
intents independently pass real preflight in the same sealed fixture before re-entry;
the mutex itself is not mocked.

Protected master then advanced to `d5cce731a23588ddbf4df806bd9e8dcfa5eecf24`
(PR #1604), which adds a separately admitted C2 Personal publisher operation.
Integrated source `b442c550dde1fe4136f93806516b108b0ef20590` preserves that protected
operation and its admission rules. Both C2 compatibility applies take their existing
account lifecycle mutex, while genuine read-only preflights stay lock-free.
The integrated suite passes **153** tests, including two new Personal publisher
contention/recovery cases. This does not select or apply either C2 publisher operation.

The real C4 `--preflight-only` invocation then returned `NOT_APPLIED`, preserving
configuration, manifest and plist bytes and creating no lifecycle lock. It proposes
original manifest `849e0af6b498408eba843bcbf2c9c500e199c218db06f00db9cb13b54303b071`
to target `5b7e4ea4b83d1cff6f371dc1ccb3862762222336ba9bb24c0444ad42d3d959c9`.
The immutable v12 runtime was already present and passed the protected verifier.

Evidence is retained in
[the C4 verification directory](verification/paper-c4-runtime-20261018/verification.json).
These receipts prove source tests and read-only planning. Live selection follows the
existing accepted-release stop / Paper upgrade / start sequence above with the exact
C4 account and freshly observed manifest. Acceptance still requires a new gateway
generation, the qualified catalog, exact-file preparation, and a requested guarded
edit with visual readback on the same Studio Direct carrier.

### Paper release-version compatibility ruling — 2026-09-30

Paper Desktop's reported release version is now **observational metadata, not a write-admission
boundary**. The guarded bridge still requires the exact `paper-desktop` server identity and the
reviewed full tool-catalog digest before a write. A release-number change by itself therefore does
not force Paper into read-only mode when the effective catalog is byte-for-byte compatible.

Live Studio observation on 2026-09-30 reported Paper **0.5.14** with catalog digest
`8cd27488a3adfc19c6c36d4349b75feebc71c159253c47f8a0f8d50c27043deb`, exactly the already
reviewed catalog qualified below for 0.5.12. Runtime **v9** / bridge **0.1.3**
(`a784fefceb7b1bb1164289700b22a6f53d09ae60d007f506ac015ebaca8c3725`) encodes that policy. If the server identity changes or the catalog digest changes,
writes still fail closed as `UPSTREAM_SCHEMA_UNREVIEWED` until that schema is reviewed. Do not
weaken this to tool-name subset matching or auto-accept a changed catalog.

This fixes compatibility admission only. Existing installed v5/v8/direct bundles do not become v9
merely because source changed; normal immutable-runtime staging/deployment and route readback remain
separate effects. Because the public Paper action schemas are unchanged, a version-only runtime
upgrade does not by itself require a duplicate app/tunnel or an action-snapshot republish.

### Paper 0.5.12 catalog drift qualification — 2026-09-26

A later Paper 0.5.12 observation changed the full upstream catalog digest from
`ca90a537ee97f3e371ac945a8a3b9a928ba7fac9ffaeb67e31491075a0790570` to
`8cd27488a3adfc19c6c36d4349b75feebc71c159253c47f8a0f8d50c27043deb`.
The release owner compared the exact current name-keyed tool dictionaries with the
durable prior raw catalog. Tool count changed **34 -> 35**; `rename_pages` was the
only added tool; no tool was removed and **no existing tool definition changed**.
The bridge therefore keeps the same 17 read and 12 edit allowlists and leaves
`rename_pages` blocked alongside `create_file`, `delete_nodes`, exports and raw
`open_file`. Exact full-catalog pinning remains fail closed rather than weakening to
a subset/schema-family check.

The compatible bridge is version `0.1.1`, SHA-256
`d3301a1466d46ae081ded963f438c019fabf39c9bccfc8c669f16562a52bf7f6`,
owned by immutable Paper runtime generation `v5`. This source qualification is not a
deployment or write canary; installed `v4` seats remain valid historical runtimes
until the normal release owner moves an explicitly selected canary. Evidence:
`docs/evidence/paper_desktop/20260926_0512_catalog_compatibility.json`.

No MCP tool is disguised as read-only to bypass client write permissions.
`paper_edit` is explicitly modifying/destructive/non-idempotent; it exists only
when the local server is started with `--allow-write`.

## Team/account and seat model - 2026-09-18

Use **one real signed-in Paper editor identity as the agent execution seat**, not
one Paper user account per ChatGPT/local agent. Agents are software clients behind
the governed bridge; they do not need Paper member identities merely to call MCP.
Paper's current Terms prohibit password/account sharing, false identities, creating
accounts for someone else, and holding more than one account at a time. Do not
accept pending agent-email invitations into fabricated Paper user accounts.

Human collaborators should use their own real member identities. Paper currently
makes unlimited editors/viewers free on the Free team. On Pro, billing is explicitly
per editor seat while viewers remain free, so separate agent-editor memberships
would create unnecessary paid seats. Pro advertises 1M MCP tool calls/week, but its
public pricing page does not state whether that allowance is pooled per team or
measured per editor; keep quota scope UNKNOWN until Paper exposes it authoritatively.

Paper 0.5.11 supports multiple desktop tabs, and Paper's August 2026 build log says
agents may work across multiple open files, including background tabs. That makes a
single real Paper editor identity/seat compatible with multiple governed agent workflows without
credential sharing between fake Paper members. Our bridge serializes individual calls
from one OS user through `desktop.lock`; that local call mutex is not a document lease
and does not make one designer the owner of a Paper file.

### Multi-writer collaboration boundary - 2026-09-27

The same real Paper editor identity may back governed Paper Desktop processes on M1, M2,
and other admitted hosts; do not buy or fabricate separate Paper members merely because
another agent session runs on another owned Mac. Each host remains a separate local MCP
process and may work on the same or a different Paper file in parallel.

Concurrency is **target-scoped, not file-scoped**. Multiple modifying sessions/hosts may
work on the same exact `fileId`, including the same Paper page. Prefer disjoint
board/artboard/node target sets. Same-board editing is allowed when target sets are
partitioned; if overlap is known or suspected, re-read the current target and coordinate
or re-plan the next operation rather than acquiring a file-wide or page-wide lease.
This contract is advertised as `MULTI_WRITER_PER_FILE_TARGET_SCOPED`.

The local per-OS-user mutex remains only a bridge-call serialization primitive. Its
bounded acquisition wait absorbs transient same-host session overlap before dispatch; it
does not provide a distributed lock, effect retry, or persistent queue. `paper_prepare`
does not mint ownership or replace the existing Capacity/routing owner. A fresh exact-target
snapshot is optimistic evidence for one bounded edit, not a global revision or collaboration lock. Every logical mutation still
binds to one carrier + operation identity until its effect is reconciled; `EFFECT_UNKNOWN`
remains original-carrier sticky.

## Existing harness integration boundary

Protected `control_plane/executive_agent_capabilities.py` already owns named MCP,
skill and plugin grants, exact schemas and profile digests. Its default policy
`config/executive_agent_capabilities.json` currently has `production_armed:false`.
Sealed workers deliberately clear ambient MCP/plugins/skills. Adding a personal
MCP config does NOT enroll an Executive worker or grant a Job new powers.

This candidate stages actual client config files in a NEW isolated workspace:
`.mcp.json`, `.cursor/mcp.json`, `.codex/config.toml`, `.vscode/mcp.json`, and
`opencode.json`. Provider-account homes and running worker processes are untouched.
Qwen/MiniMax/GLM/Grok access follows the tools supported by their hosting harness;
a model subscription alone is not evidence of MCP execution support.

Next Executive integration is an additive reviewed stdio grant in the EXISTING
registry, bound to the exact installed runtime/SDK and observed adapter tool-schema
digest. Use the existing resource/placement owner for one active design operator
per Paper desktop. Do not loosen the current HTTPS validation to point the whole
fleet at localhost, invent a parallel policy file, auto-arm production, or fabricate
a schema digest before a real `initialize` + `tools/list` capture. This candidate
has NOT changed that registry and must not be described as routed-production-ready.

## Installation and user gates

The CLI requires Python 3.9+ and no packages. The optional MCP server requires
Python 3.10+ and `mcp==1.30.0`; use a dedicated virtual environment, not system pip.
The dependency pin intentionally stays on the documented maintenance-line SDK API.
Transitive dependency resolution must be captured/reviewed before an immutable
Executive grant. Current configuration staging is not such a sealed installation.

Run `install.py --destination <new-path> --python <venv-python> --allow-write` for a
dry run, then the same command with `--apply`. Existing destinations refuse rather
than overwrite. It creates runtime files, actual isolated project configurations,
and `INSTALLATION.json`. This receipt is installation evidence, not runtime authority.

Launch Paper and sign in through its normal UI. The private Studio Direct host pins
`~/Applications/Paper.app`; a Web caller cannot supply another application path, URL,
account or credential. When the exact Paper file ID is known, `paper_prepare(file_id)`
may launch/focus that pinned app through the observed `paper://file/<id>` desktop URL,
then repeatedly observes the guarded bridge until the exact file identity is proven.
If the transition cannot be proven, it returns
`PAPER_DOCUMENT_TRANSITION_UNCONFIRMED`, performs no automatic replay, and exposes no
content edit capability. When the file is already active, prepare skips the desktop
launch entirely and returns the current snapshot plus write-schema qualification.
The reviewed 0.5.14 catalog no longer exposes `list_files`, and resource discovery remains blocked.
When the file ID is unknown, obtain the exact identity from accepted task context or stop at a typed
binding gap; do not guess a file or substitute `list_resources`.

No paid plan is needed for initial smoke proof. Paper 0.5.11 returns a compact
structured file header plus a richer JSON text block from `get_basic_info`; the
adapter merges them only when file identities/names agree, preserving provider file
ID plus page/artboard state. Every stable-ID edit must also pass that exact `fileId`.
Legacy artboard-anchor fallback remains fail-closed for older supported shapes.
Unknown/conflicting shapes still refuse as `DOCUMENT_SCHEMA_UNVERIFIED`.

Native clients must open/trust the new workspace and approve the MCP connection
according to their own rules. Do not automatically trust a workspace, disable
sandboxing or enable arbitrary tools across all worker accounts.

The staged install now emits `ENROLLMENT.md` with exact per-client gates. Codex
loads project `.codex/config.toml` only after the exact workspace is marked trusted
in the user-level Codex config. Claude Code separately requires project-MCP approval.
Neither ceremony is performed by `install.py`; both remain visible account/client
authorization boundaries.

## Deterministic behavior and limits

`status` observes server/document; `catalog` discovers real upstream input schemas;
`read` allows the documented inspection/screenshot/JSX tools; the Studio Direct
`paper_prepare` wrapper performs only a bounded host-pinned desktop/file transition
and exact-file verification; `edit` requires an explicit opt-in, operation ID and
immediately compared basic-info snapshot hash.
Paper validates its current input schema. Safe Paper 0.5.11 reads additionally include file listing, node search, tokens and
comment inspection. Guarded edits additionally cover page creation, token create/
update and comment-resolution state; token deletion is explicitly refused.
Cross-team `create_file`, the raw upstream document-transition `open_file`, native
path-writing exports and consequential node deletion remain excluded. Studio Direct
uses only its separately bounded `paper_prepare` wrapper for file focus; callers cannot
forward an arbitrary Paper URL or application path. Image artifacts accept only PNG/JPEG into an
explicit private output directory, content-addressed and never overwritten.

A snapshot is NOT a revision, identity credential, authorization or full content
hash. `get_basic_info` may not change after an inner text/style edit. It cannot
prove serializable isolation. The mutex serializes bridge calls from one OS user,
not manual UI edits, raw Paper clients, other OS users or whole multi-call tasks.
The artboard anchor is an observed guard, not globally proven file identity.
Multiple designers may be assigned to the same Paper file across hosts, including the
same page. Partition work by board/artboard/node where practical; for known same-board
overlap, use disjoint node targets and fresh re-read/re-plan before the next bounded edit.
Do not advertise a file-wide or page-wide modifying lease.

Reads and edits are bounded, with no proxy environment, arbitrary URL, redirects,
background polling, automatic replay or resumable mutation transport. A missing
reply or error after edit dispatch is `EFFECT_UNKNOWN`, even when it might be an
input error, because partial effects are possible. Inspect the original document
and reconcile on the same carrier. `operation_id` is a correlation label, NOT an
exactly-once guarantee. This component stores no alternate retry state.

`APPLIED_RESPONSE_OBSERVED` means a successful response and matching post-read
context, not visual correctness or production acceptance. Keep screenshot/browser
acceptance separate. Plan and remaining quota are UNKNOWN unless observed from an
authoritative source; do not subtract a guessed allowance into another quota DB.
Use the existing routing/usage owner for real usage events when integrating it.

## Model workflow and token budget

Deterministic components own transport, bounds, locking and refusal. A capable
least-scarce design agent owns visual reasoning; a reviewer checks the screenshot
and user journey. Fable is not required for a census or routine MCP calls. Budget
one catalog discovery per workflow and deliberate screenshots at meaningful changes;
no idle loops. Every guarded edit currently costs three Paper tool calls (pre-read,
edit, post-read); plan this explicitly on the 100-call Free tier.

For a Paper-canvas assignment, an HTML prototype or review package may support reasoning but cannot
replace the required Paper effect while either lawful Paper route remains unprobed. If both routes
are genuinely blocked, label the artifact `NOT_APPLIED_TO_PAPER` and preserve the exact carrier/
permission/file-transition gate instead of reporting the canvas as updated.

## Figma migration

Keep Figma as a read-only reference/archive until representative journeys pass.
Migrate our own tokens, typography, spacing, components and content; rebuild original
layouts with Paper's web-native structure. Paper documents a Figma token workflow
and known conversion limits (SVG overrides, spacing, code-connected components).
Do not promise a lossless import or cancel Figma based on an MCP connection alone.

Prove one real Mastermind screen through: all meaningful states -> Paper screenshot
-> JSX -> existing frontend components/tokens -> responsive browser review. Design
code output is a starting point, not automatic tested production implementation.

## Acceptance and continuation

1. Exact source runtime installed without changing other worker homes.
2. Native MCP initialize/list and real CLI read against Paper after login/file-open.
3. Approved scratch edit, screenshot, JSX extraction; no wrong-document changes.
4. Fresh ChatGPT Web session runs `paper_inspect` and confirms its
   `gateway_surface` names the five exact Paper actions. When another file is needed, the
   **client surface itself** must expose `paper_prepare`; resolve a known exact `fileId` from accepted
   task context -> direct `paper_prepare(file_id)` -> exact-file read/edit/screenshot/JSX. If no exact
   file identity is known, stop rather than guessing or invoking blocked resource discovery. Generic
   host-command emulation does not satisfy this acceptance.
   Tunnel health alone is not the design-journey proof.
5. Existing capability registry attests a bounded worker; no second control plane.
6. One real product design-to-code/browser journey before Figma retirement.

Stop at login, app approval, absent host transport, unknown effects or an unproven
sealed-worker grant. Do not turn synthetic fixtures, downloads, PRs or config
staging into PROVEN_LIVE. Continue at the first unmet item, retaining this carrier.

## Sources checked through 2026-10-02

- https://paper.design/docs/mcp - endpoint, tools, current-file context, code export, migration.
- https://paper.design/downloads - desktop distribution.
- https://paper.design/pricing - Free 100 MCP calls/week; Pro 1M/week,
  $20/editor/month monthly or $16/month billed yearly. No purchase performed.
- https://help.openai.com/en/articles/12584461 and
  https://developers.openai.com/plugins/deploy/connect-chatgpt - current MCP app/tool-update
  lifecycle. Developer-mode MCP connections support an explicit **Refresh** after tool names,
  descriptions, schemas, annotations, auth, or UI resources change; confirm refreshed metadata
  and start a new conversation. Published Plugin Directory definitions use continuous review/rescan.
  Current OpenAI Help Center guidance (updated October 2026) permits Business and
  Enterprise/Edu admins to **Refresh published custom workspace MCP app tool definitions
  in place** from workspace settings, with app-management permission and a valid connection.
  The admin reviews and publishes the update; Enterprise/Edu Action control also
  supports individual action Refresh. Prefer the existing tunnel/backend and do not
  turn an older chat's tool text into a file lease or duplicate app. Only a separately
  verified platform requirement and approved owner transition justify replacement.
- https://github.com/openai/tunnel-client - private outbound Secure MCP Tunnel, stdio support.
- https://modelcontextprotocol.io/specification/2025-03-26/basic/transports - HTTP/SSE/session rules.
- https://pypi.org/project/mcp/1.30.0/ - pinned official SDK maintenance line.

## Observed native proof - 2026-09-18

Overall capability remains **PARTIAL** because sealed Executive worker enrollment,
fresh-session repeat and one real product design-to-code/browser journey are still
owed. The local Paper design path on the authorized Mac Mini is now proven live.

Paper was upgraded in place on the same carrier from 0.5.9 to signed/notarized
**0.5.11**; the prior application is retained as `Paper.app.prev-0.5.9`.
The official ARM64 DMG SHA-256 is
`03a027b2b1bc1df2e54f8db3d4cd5c1c404bf56994926113efe223e0b2a27079`.
Paper 0.5.11 listened on 127.0.0.1:29979 and a scratch file was created/opened
through the normal Paper UI.

The live 0.5.11 wire exposed a compact structured file header and a richer detail
block. That falsified the original parser assumption and produced
`DOCUMENT_SCHEMA_UNVERIFIED` despite a valid stable file ID. The same installed
bridge was repaired to reconcile agreeing shapes, preserve page/artboard state, and
require an exact file ID on every stable-ID edit.

Live canary effects on the scratch file were all observed on this original carrier:
a 900x560 artboard was created, incremental Inter typography was written, a JPEG
screenshot was returned and saved privately, JSX was extracted from the same
artboard, and Paper's required `finish_working_on_nodes` call returned OK.
No edit returned `EFFECT_UNKNOWN`; no operation was replayed. Screenshot SHA-256:
`d200166b831f154bcef7e59883c0193225961ed73b52c17b83d445a7fd195200`.
The JSX read contains "Native design tooling is live." with the expected dimensions,
Inter typography and colors.

Installed SHA-256 after hardening:
`bridge.py=cd34f98c1647ba52f392fb93aa9d7aed24eb39aac90d7de75bce39021444740d`;
wrapper/server and requirement pins are unchanged. This proves the local
read/write/screenshot/JSX substrate, not fleet production or visual product quality.

At this historical native-proof checkpoint, ChatGPT Web reused the Studio Direct Secure MCP
Tunnel and gateway-owned Paper tools. The former blanket dedicated-app prohibition is superseded
only by the explicit Business migration above, not merely by existence of the stdio projection. Remote Desktop Commander remains
an authorized host-diagnostic/local-ops carrier, not the normal design product path.

### Observed local-client enrollment

The authorized Mac Mini now has an explicit Codex trust entry for only the isolated
Paper workspace; the previous user config was preserved as
`~/.codex/config.toml.pre-paper-20260918`. From that workspace, `codex mcp list`
shows `mastermindPaper` enabled and points at the guarded stdio adapter. A real
`codex exec` attempt then stopped at a distinct provider-authentication gate:
the stored ChatGPT refresh token is invalid (HTTP 401). The MCP configuration itself
is visible; exact human recovery is `codex logout` followed by interactive
`codex login`, then repeat the read-only Paper canary.

Claude Code independently sees `mastermindPaper` from the same workspace but reports
`Pending approval (run claude to approve)`. That approval is intentionally not bypassed.
Launch interactive Claude in the isolated workspace and approve only that project MCP,
then repeat the same Paper inspection canary.

These two account/client ceremonies are the remaining native-human gates; they are
not reasons to create additional Paper user accounts or another MCP gateway.

### C4 composition with protected Fabric release

The C4 proposal integrates protected master `89cf2399c47da20c0c23826266e52984f88c27e7`.
Its installer code at `7347c319db18c86b4f6f6dc5a0714e0aebca56c3` retains the dedicated
Fabric owner and its stage/upgrade/seal/start/stop decorators. The shared mutex admits
the union of the qualified Paper accounts and that exact Fabric account; the separate
decorator predicates prevent double acquisition. Dedicated Paper inspections still
request positive service-state evidence, while generic C2 Business behavior is preserved.

The combined installer and backend-release suites pass 162 tests. A fresh actual C4
preflight with this installer remains `NOT_APPLIED`: installed configuration, manifest,
plist and lock existence are unchanged. See `paper-c4-integrated-preflight.json` and the
current integration entry in `verification.json`. No Fabric runtime action was performed.

The current Portfolio mission adopts the exact inherited #1603 source
`12fe3d9a7f5ed7deff75b1e8c9101227a92d0aa8` into the owned #1611 composition, including
the independently reviewed shared-writer lock correction. Normal acceptance of the
combined source dispositions that inherited component; the original branch remains
untouched. A protected-commit comparison must establish what landed. C2 runtime
selection and publisher operations retain their separate release and live-proof scope.

The C4 stop/select/start operator must remain available after C4 stops. Use the existing
accepted installer from an independently authorized local or RDC host installation
context, checking each stage before the next. A command launched through the C4 backend
itself is not a qualified self-cutover mechanism. The subsequent Paper prepare/edit and
visual readback remain on Studio Direct C4.

## Source readiness and named-seat diagnostics (v22; not installed)

The reconciled #1409 source adds early write-readiness reporting to
`paper_inspect` while retaining the current `TOOL_SCOPED_CONTRACT_V1` policy.
Its `write_schema` reports compatible and incompatible write tools separately.
An incompatible unrelated writer does not disable qualified operations; a
connected document can also report no compatible writers. The live critical
`get_basic_info` contract is still checked before its implicit call. Catalog
failure remains a typed refusal and is never converted into `CONNECTED`.

Named v3/v4 direct-service receipts additionally expose only
`schema`, `seat_id`, `source_revision` and `bridge_sha256` under
`transport_diagnostic`. The stdio projection validates the exact key set and
value formats. Legacy unnamed bundles omit this field. These verified-install
diagnostics identify source provenance, confer no authority and do not enter
snapshot hashes, execution bindings, write permission or retry decisions.
Refusals and unknown-effect receipts retain their original state and operation.

The additive source generation is **v22**, bridge SHA-256
`af03759abbb493155ba32802a769b27699c672be716c1d29b1cab5b3b68a778b`. Every existing generation remains immutable,
including v12 `82bc7f2d75aec423711922198b68f317618a83de177bf4934b73d7b418a6ecfb`
and v21 `dfbf0b11c49a595610d1ac0e663d95f7291b500cb84d31ef8169bc3b909a2eaa`.
The old #1409 proposal to replace the v12 binding or restore whole-catalog-only
write admission is superseded by the accepted protected implementation.

This is source integration only. It changes no installed selector, service,
tunnel or design. The historical #1409 staging denial remains unreplayed;
another generation name is not permission to repeat that action. An authorized
runtime release and same-carrier real-app acceptance remain separate.
