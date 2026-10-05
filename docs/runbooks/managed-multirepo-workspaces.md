# Managed repository workspaces for attended Web operators

State: source capability; installation and native-account qualification are separate gates. This runbook composes the existing workspace and Studio owners. It does not create a new allocator, registry, lease, publisher, permission service or release path.

## What each component owns

`mmx-workspace` owns one operation-bound linked Git workspace. Studio Direct can acquire that workspace and publish its exact candidate through the existing typed Git publisher. Its permitted filesystem tools operate only within the source assignment. Workbench operates inside its separately configured project binding; it is not an allocator. A VM, Docker container or new VPS is not required for this trusted attended path.

Native Claude/Codex/Executive sessions retain their harness-provided workspaces. The private credentialless worker path is unchanged. A Git lock is source-custody evidence, not authentication of a new user or proof of an Executive grant.

## Host installation from an accepted release

Reconcile the existing launcher and active source/effects first. Use the exact accepted, clean release through the existing host installation owner. Source publication, successful tests and an old review do not authorize installing unaccepted bytes.

The host binds known source checkouts once. These are administrative installer inputs, not Web tool arguments:

```sh
/bin/sh "$RELEASE_ROOT/scripts/install_mastermind_workspace_cli.sh" \
  --repository-source "macro=$MACRO_SOURCE" \
  --repository-source "terminal=$TERMINAL_SOURCE"

"$HOME/.local/bin/mmx-workspace" repositories
"$HOME/.local/bin/mmx-workspace" storage
```

The installer resolves the canonical Mastermind source from its Git common directory. Each additional source must be an existing canonical Git top-level with the exact approved HTTPS fetch/push origin. Aliases are only `mastermind`, `macro`, `terminal`; their default branches are respectively `master`, `main`, `master`. A missing optional repository remains `NOT_ENROLLED`, never redirected to Mastermind.

The wrapper pins the validated source/common-directory map, shared workspace root and existing storage policy as shell literals. It overrides inherited mapping/source/root/policy environment values. Normal reinstall retains earlier bindings from the prior wrapper's literal without executing that wrapper. A changed, malformed, writable, indirect or ambiguous prior wrapper refuses rather than silently dropping targets. Rebinding an optional repository requires an explicit installer selection and current host/source authority.

The existing storage UUID, mount and reserve remain authoritative. They are not changed by repository enrollment. Storage readiness is an admission snapshot, not a reservation or ongoing health guarantee. An enrolled missing volume does not fall back to another drive.

## Attended acquisition and preservation

Use one stable operation identity. The host/source owner makes the exact intended base commit available in the bound local repository; no public tool accepts a fetch URL or arbitrary source location.

```sh
mmx-workspace acquire --repository macro \
  --operation-id "$OPERATION" --base-sha "$MACRO_BASE_SHA" --lane web

mmx-workspace status --repository macro --operation-id "$OPERATION" --lane web
```

Use the returned `workspace_path`; do not construct another worktree, override the launcher environment, or directly invoke its Python payload as a production allocation shortcut. A second acquisition with the identical repository/operation/base/branch identity reuses that exact workspace. A mismatch refuses; it is not permission to reset or duplicate it.

Mastermind retains its original `<host-root>/<lane>/<operation>` layout. Macro and Terminal use `<host-root>/<repository>/<lane>/<operation>`. The same operation name in two repositories therefore cannot silently share a workspace or Git common directory. The Web branch remains operation-derived, `sol/web-<operation>`, inside the selected repository. Sparse construction consumes that repository's profile at the exact base commit and does not retrofit an active checkout.

Implicit legacy Mastermind calls retain their v1 response and old path. Explicit repository calls use v2 with a top-level repository identity. Repository discovery is local and does not allocate/fetch/commit; `READY` describes its currently verified local binding, not execution admission.

## Studio Direct opt-in

The existing private-service installer carries the new consumer module, but old profiles do not silently gain repository tools. After accepted source and stopped-service/reconciliation gates, the existing `stage` or `upgrade` command can add `--enable-repository-workspaces` while keeping its exact account/node/backend/port/source arguments. Existing opted-in settings survive subsequent verified restage/upgrade. Current manifest/file-set/dependency sealing and lifecycle checks are unchanged; bypassing them with a handwritten live config is not installation.

An opted-in gateway advertises:

- `studio_workspace_repositories({})`: closed alias availability, with no private root paths or credentials in the public discovery result.
- `studio_workspace_acquire({repository, operation_id, base_sha})`: one modifying request to the installed owner; no source/path/branch/remote/environment selector.
- Existing `studio_git_publish_status`, `studio_git_commit_current_changes`, and `studio_git_push_current_branch` with an optional closed `repository` alias. Omitting it preserves the exact legacy Mastermind route.

Commit still requires exact expected local HEAD; push still requires a clean workspace and fixed same-branch canonical origin, without force/tags/arbitrary destinations. Repo-aware publication reuses the original implementation and its destination/ref fences. The adapter adds no second Git publisher.

Acquisition is honestly modifying and non-auto-retryable. Its open-world annotation accounts for the existing Git owner's possible retrieval of missing objects from the already-bound canonical origin. Discovery remains non-network. A failed or unqualified return after allocation may have started is `EFFECT_UNKNOWN`; it is not ordinary `NOT_APPLIED`. Only a versioned matching pre-construction repository/storage refusal establishes no allocation effect. Reconcile the same repository/operation through the existing owner before any retry or other effect; a new operation ID does not clear uncertainty.

## Workbench boundary

Restoring the existing Workbench C3 tunnel restores only that channel's existing project/lease/allowed paths. It does not make the channel a general Macro/Terminal editor. Do not retarget an account-global root while other conversations may use it, modify the lease to create source authority, or replay a project action through Studio after uncertain Workbench delivery.

The immediate multi-repository implementation path uses the assigned managed workspace through Studio Direct. A later operation-specific Workbench binding must consume the same verified workspace receipt through Workbench's existing host/configuration and attended-context owners. It requires its own exact channel/project/effect qualification, rather than treating repository discovery as permission.

## Acceptance and release

An accepted installed path separately proves: expected source generation; unchanged host policy; actual tool inventory on the intended account; Macro and Terminal acquire/status/reuse; edits/tests inside each assigned workspace; exact commit/push/readback; foreign source zero-touch; and uncertainty/preservation behavior. Local fixtures establish implementation behavior but not installed account capability. A connected app card does not prove its latest schema is selected.

At terminal completion of the operation, use the same owner:

```sh
mmx-workspace release --repository macro --operation-id "$OPERATION" --lane web
```

Dirty or unpublished work is preserved. A clean releasability observation is not a positive session-completion signal and does not authorize deleting a different or still-attached workspace. Release does not delete the Git branch. Existing published-branch evidence improvements stay with their source owner; conservative preservation is preferable to claiming unsupported recoverability.
