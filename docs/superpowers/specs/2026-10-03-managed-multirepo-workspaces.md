# Managed multi-repository attended workspaces

## Assignment and outcome

The Chairman explicitly approved the design and assigned this Web CEO the orphaned mmx-workspace project and its Studio Direct/Workbench integration on 2026-10-03. The operation remains `agent-environment-storage-admission-20260915-sol-001`, on the existing #685 branch and workspace. Recovery and source scope are recorded in #685/comment5966606194. Protected procedure/source pin: `bdf2a972e68a70270c24d4b5d61a4d60edc4f288`.

A Web CEO must be able to acquire one managed workspace for Mastermind, Macro or Terminal, edit and test its assigned source, publish the exact candidate, and safely preserve/release it without choosing an arbitrary filesystem path or buying another VM. Completion requires real installed consumer evidence; source/tests/merge alone are not completion.

## Existing owners and compatibility

- `mmx-workspace` remains the only attended workspace allocator, backed by `control_plane.executive_workspace`. No new lifecycle, lease database or allocator.
- The installed launcher remains the host configuration boundary. Repository mappings are immutable shell-quoted installation inputs, not a new runtime registry.
- Preserve the default Mastermind invocation, operation, branch, lock and workspace path. Explicit repository selection is additive.
- Native Claude/Codex/Executive sessions keep the workspace their harness assigned. Credentialless private worker clones remain separate.
- Retain #929 storage-policy metadata, APFS, shell quoting and package dependency repairs, and #1099 sparse-before-hydration behavior. Do not reimplement either.
- #1014 owns additional published-branch release evidence. Do not discard or silently import its held candidate. Main-branch release semantics may be composed only after its current source custody is reconciled; conservative preservation is preferable to false deletion.

## Closed repository binding

Closed aliases: `mastermind`, `macro`, `terminal`.

Canonical identities: `mastermindx-market-intelligence/Mastermind` (master), `mastermindx-market-intelligence/macro` (main), `mastermindx-market-intelligence/mastermind-terminal` (master). A host installation explicitly binds each enabled alias to a local Git top-level and its Git common directory. The installer validates the exact canonical origin. Missing optional targets remain unenrolled, never implicitly redirected to Mastermind.

The installed wrapper overwrites any ambient mapping/source/root/policy environment. Runtime callers supply only the alias, existing operation identity, exact base SHA and closed lane. No tool accepts a source directory, remote URL, branch, credential, interpreter or arbitrary shell. The implementation payload remains an administrative/test seam, not the production invocation.

Before any selected-repository effect, re-observe its configured top-level, common directory and exact canonical origin. Fail before allocation on missing, changed, ambiguous or unapproved binding. Read-only `repositories` projects the currently installed choices; it creates no workspace, reservation or lease and performs no network fetch.

## Workspace layout and storage

Mastermind keeps `<host-root>/<lane>/<operation>`. Macro and Terminal use `<host-root>/<alias>/<lane>/<operation>`. The branch remains operation-derived (`sol/web-<operation>` in the Web lane); repository separation makes the same operation identity safe across independent Git stores. No runtime path selector exists.

Validate the existing storage policy against the shared host root before allocation, not against its per-repository subdirectory. Preserve UUID, mount, writable-volume and free-space checks. A missing mount does not fall back. Do not change the reserve or retrofit/sparsify an active workspace. Reuse must preserve dirty files. Release remains fail-closed for dirty/unpublished work and never deletes the branch.

## Web transport

Add bounded acquisition/description through Studio Direct as a thin consumer of the installed owner. Repository-aware publication must reuse the existing publisher, preserve exact HEAD and same-branch destination fencing, and never invent a second Git implementation. Existing Mastermind-only tool calls retain their behavior. New calls include the closed alias and resolve everything else through host-owned configuration and owner receipts.

Acquisition is honestly modifying. A lost/ambiguous acquisition response must be reconciled against the same repository/operation before any retry. Status/description are genuinely read-only. Effects remain NOT_APPLIED, APPLIED or EFFECT_UNKNOWN; transport success is not completion.

Workbench operates inside an assigned workspace; it does not allocate one. Bind only from an independently verified owner receipt through its existing host configuration/runtime boundary. Never retarget a live channel with unresolved actions or let two Web conversations share one mutable workspace by changing an account-global root. Existing fixed-project C3 transport restoration and later per-operation binding are distinct proof obligations.

## Required tests and proof

1. Legacy Mastermind acquisition, reuse, status and preservation/release remain compatible.
2. Real synthetic Git repositories exercise all three aliases, same-operation separation and exact reuse.
3. Unenrolled aliases, unknown alias, wrong origin/common directory, invalid base and changed host binding refuse before workspace/branch creation.
4. Installer preserves shell-literal paths and argv; hostile ambient mappings cannot retarget the installed launcher.
5. Storage observes the host root; sparse construction uses the selected repository's pinned profile.
6. Publication uses the correct source/default branch/remote and exact HEAD without relaxing existing destination/ref fences.
7. Read-only discovery creates no workspace and is not a health/admission promise.
8. Actual installed acquire -> edit/test -> commit -> push -> readback journeys are separately required for Macro and Terminal. No real production source or foreign writer is used as a disposable probe.
9. Workbench restoration requires its exact channel/lease/artifact readback and native tool proof; no cross-carrier replay or fabricated success.

## Non-goals and release

No VM/VPS/Docker provisioning, scheduler, provider dispatch bypass, credential migration, arbitrary repo selection, deletion sweeper, portfolio logic, or takeover of the options/chart writers in the screenshot. Independent exact-head review, required CI, existing source-continuity/release rules and host installation gates remain. A remaining gate must name an actual next action and owner rather than send the Chairman back to a ghost conversation.
