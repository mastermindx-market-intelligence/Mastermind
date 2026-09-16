# GitHub Codespaces DevBox — Production Canary

**Capability:** attended ChatGPT Web → authenticated DevBox MCP → one exact GitHub Codespace filesystem/shell/git/test workspace.
**Source owner:** GitHub.
**Lifecycle owner:** Executive OS when a Job/Attempt exists; this canary does not mint one.
**Provider state:** `BUILT_NOT_PROVEN`; Personal Pro observation proof is insufficient to promote the four-tool parent. Claim `PROVEN_LIVE` only after the supported-plan `EXECUTE` traversal completes through the public endpoint and its exact results are read back.

## Hard boundaries

- Codespaces is an execution resource, not a second queue, scheduler, identity store, lifecycle, memory, retry or source-authority plane.
- The model cannot supply a host, Codespace name, repository, cwd, root, environment, account or credential.
- Child command **environments** omit `GITHUB_TOKEN`, `GH_TOKEN`, SSH-agent variables, cloud/API secrets and usable Git credential-helper configuration. V1 does not claim same-UID filesystem or process-memory isolation from other Codespace-owned data.
- The DevBox command profile may change working-tree files and run local git/worktree/test commands. Remote source publication/merge remains owned by the existing GitHub release path.
- A lost modifying response is reconciled by the same `operation_key`; never start process two or fail over to a Mac/other Codespace while effect is unknown.
- Stopping/disconnecting a Codespace never proves a command did not run.
- V1 is attended-only and disposable. Do not use it for untrusted or unattended commands until a separately accepted OS isolation boundary protects service state and host credentials from the child process.

## 1. Qualify the GitHub CLI carrier

The authorized controller must have GitHub Codespaces scope. Inspect first:

```bash
gh auth status
gh codespace list --json name,state,repository,machineName,createdAt,lastUsedAt
```

If GitHub returns a missing-Codespaces-scope refusal, extend the existing GitHub CLI authorization rather than creating a second credential plane:

```bash
gh auth refresh -h github.com -s codespace
```

Complete GitHub's native browser/device authorization if prompted, then rerun `gh auth status` and `gh codespace list`. A successful auth refresh is not DevBox production proof.

## 2. Publish an exact source candidate before creating the Codespace

Create the canary from the exact reviewed candidate branch. Record:

```bash
git rev-parse HEAD
git status --short --branch
```

The lease `committed_head` must equal that exact HEAD. If source moves, issue a fresh lease/generation rather than editing a live lease to follow a moving branch.

## 3. Create one disposable Codespace

Use the smallest qualified machine and aggressive idle/retention bounds. Example shape:

```bash
gh codespace create \
  -R mastermindx-market-intelligence/Mastermind \
  -b <exact-candidate-branch> \
  -m <smallest-qualified-machine> \
  --idle-timeout 30m \
  --retention-period 24h \
  --display-name mmx-devbox-canary
```

Record the returned Codespace name. Do not choose an arbitrary existing Codespace merely because it is online.

Inside the Codespace, GitHub must provide these owner facts:

```bash
test "$CODESPACES" = true
printf '%s\n' "$CODESPACE_NAME"
printf '%s\n' "$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN"
printf '%s\n' "$GITHUB_REPOSITORY"
git rev-parse HEAD
```

The service derives `https://$CODESPACE_NAME-8767.$GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN/mcp`; never hardcode `app.github.dev`.

## 4. Run source/runtime proof before HTTP exposure

Use the repository's qualified Python environment. Run the DevBox suite and a direct runtime canary in the Codespace before opening a public port:

```bash
python -m pytest tests/devbox_mcp -q
python -m compileall -q integrations/devbox_mcp ops/devbox
git diff --check
```

Direct runtime acceptance must prove: clean source admission; dirty-source refusal before the first owned effect; preservation of that gate after a known pre-effect refusal; supervisor import from the reviewed source even when the checkout contains a hostile same-name module; exit 0; intentional exit 7; a process still observable after its start call returns; same-operation reconciliation with no process two; recovery from a lost primary STARTED/terminal receipt replacement through the immutable sidecars; changed-payload conflict; bounded and truthful live stdout/stderr accounting; timeout; exact cancellation with `cancel_requested=true` visible before terminal and preserved through terminal races/output uncertainty; binding drift refusal; typed durable-receipt unavailability; and absence of ambient GitHub/cloud/SSH credential values from the child environment. This is not proof that arbitrary same-UID credential files or process memory are unreadable.

## 5. Mint exact policy + lease outside source control

Do not commit live subject/client digests or current dynamic Codespace resource URLs. Create mode-0600 copies from:

- `config/business_mcp/devbox_policy.example.json`
- `config/business_mcp/devbox_lease.example.json`

Required equality:

```text
policy.resource
= lease.resource
= https://<CODESPACE_NAME>-8767.<GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN>/mcp

policy.required_scopes
= lease.required_scopes
= exactly one of [workbench.observe] or [workbench.execute]

policy.allowed_subject_digests
= [lease.expected_subject_digest]

lease.expected_client_ref
= client_ref_digest(policy.issuer, exact OAuth client_id/azp)

lease.repository
= $GITHUB_REPOSITORY

lease.committed_head
= git rev-parse HEAD
```

Profile mapping is closed:

- `OBSERVE_ONLY`: exact scope `workbench.observe`; tools are exactly `devbox_status` and `read_devbox_process`.
- `EXECUTE`: exact scope `workbench.execute`; tools are exactly all four DevBox tools.

Do not put both scopes in one policy, lease or access token. The existing Auth0 resource server may advertise both permissions, but Auth0 Management API scope updates replace the complete scope list: read the current resource-server state first, submit the complete desired list preserving `workbench.execute` while adding `workbench.observe`, then read it back. Do not create a second Auth0 tenant, application, API/resource server or OAuth client.

Derive the client binding with the same public helper used by JWT verification; do not hand-reimplement the hash:

```bash
python - <<'PY'
from integrations.business_mcp_auth import client_ref_digest

print(
    client_ref_digest(
        issuer="<exact policy.issuer>",
        client_id="<exact accepted OAuth client_id or matching azp>",
    )
)
PY
```

Put only the resulting 64-hex digest in `lease.expected_client_ref`. The accepted access token must carry that exact `client_id` or `azp`; when both are present they must match. `oauth-client-unavailable` is not a valid DevBox lease identity.

`target_ref`, `generation` and `owner_ref` are owner-issued opaque references. They are not Codespace hostnames and must not be model authored.

## 6. Start authenticated DevBox

Use a state root outside the checkout; its parent must already exist. Example:

```bash
mkdir -p "$HOME/.mastermind-devbox-state"
chmod u=rwx,go= "$HOME/.mastermind-devbox-state"
python -m ops.devbox.run_codespace_devbox \
  --repo-root "$PWD" \
  --state-root "$HOME/.mastermind-devbox-state" \
  --policy-file "$HOME/devbox-policy.json" \
  --lease-file "$HOME/devbox-lease.json" \
  --port 8767
```

The service binds `127.0.0.1` inside the Codespace. GitHub's forwarding agent supplies the external TLS URL. The service prints the derived `DEVBOX_MCP` URL but no credential or raw identity.

Before opening the listener, the launcher re-execs itself with Python safe-path mode under a strict environment allowlist. Ambient `GITHUB_TOKEN`, `GH_TOKEN`, `SSH_AUTH_SOCK`, API/cloud secrets, `PYTHONPATH`, and unrelated variables do not survive: the launcher installs only its exact reviewed-source `PYTHONPATH`, `PYTHONSAFEPATH=1`, `PYTHONNOUSERSITE=1`, the bounded Codespace facts, and a private re-exec marker. On the post-exec path it reconstructs that projection and refuses unless the entire environment matches exactly, so pre-setting the marker cannot bypass sanitization. This prevents recovery of those ambient values through the parent service environment; it does not establish filesystem or process-memory isolation between same-UID processes.

## 7. Expose only the exact MCP port

Inspect first:

```bash
gh codespace ports -c <codespace-name> --json sourcePort,visibility,browseUrl
```

Then, only for the attended canary, expose exactly port 8767 if repository/organization policy permits it:

```bash
gh codespace ports visibility 8767:public -c <codespace-name>
```

Public means anyone who knows the URL can reach the HTTP endpoint; Mastermind OAuth/JWT authorization remains mandatory for tool calls. Do not expose any debug/admin port.

## 8. ChatGPT acceptance by exact profile

Use the existing Auth0 tenant, application/client, endpoint resource server, retained Codespace, port `8767`, runtime, target/process authority and public MCP URL. Do not create a parallel app or server. Each service run receives one matching exact-scope policy/lease. To move from observation to execution, stop and rebind the same service plane with the reviewed matching policy/lease and exact target generation; there is no model-visible profile switch or second CLI mode.

ChatGPT uses a reviewed/frozen app tool snapshot. Before each slice, review or republish the exact expected snapshot in the eligible ChatGPT surface; do not assume source-side tool changes automatically update an already approved app.

Treat the Personal Pro and full-MCP workspace snapshots as distinct provider projections over one backend. Do not reuse the two-tool observation snapshot as evidence that four execute actions are enabled. On Business, current product behavior requires recreating and republishing the ChatGPT-side app record when its tool snapshot changes; Enterprise/Edu may refresh and review actions through workspace controls. This provider-side step must preserve the same public MCP URL and existing Auth0 tenant, OAuth client and endpoint resource server, and must not mint a second target/process/auth/lifecycle plane. Record the exact reviewed tool names for each slice.

### 8A. Personal Pro — `OBSERVE_ONLY`

Connect Personal Pro developer mode to the exact `DEVBOX_MCP` resource using a policy/lease whose sole scope is `workbench.observe`.

From the real Personal Pro Web-Sol conversation:

1. confirm discovery lists exactly `devbox_status` and `read_devbox_process`;
2. invoke `devbox_status` and read back exact target/generation/repository/HEAD plus `baseline_working_tree_dirty`, current `working_tree_dirty`, and `working_tree_changed_from_baseline`; the production baseline must be clean;
3. only when an authorized pre-existing process reference was intentionally created through an `EXECUTE` or direct canary, invoke `read_devbox_process` and read its bounded truth;
4. confirm `start_devbox_command` and `cancel_devbox_process` are absent; a direct RPC attempt for either must return `TOOL_NOT_AVAILABLE` and must not reach the bound port or runtime.

Record this as the Personal Pro observation slice only. It does not prove write/modify entitlement and does not promote the four-tool parent capability beyond `BUILT_NOT_PROVEN`.

### 8B. Business or Enterprise/Edu — `EXECUTE`

Use a currently supported full-MCP ChatGPT workspace and a matching policy/lease whose sole scope is `workbench.execute`. Review the frozen app snapshot and confirm it lists exactly all four DevBox tools.

From the real full-MCP Web-Sol conversation, execute in order:

1. `devbox_status` — exact target/generation/repository/HEAD plus `baseline_working_tree_dirty`, current `working_tree_dirty`, and `working_tree_changed_from_baseline`; the production baseline must be clean.
2. `start_devbox_command` with an exit-0 command; read terminal exit 0.
3. Intentional exit 7; read exact exit 7.
4. Start a delayed command; let the initiating tool call return; observe `accounting_complete=false` while it is live, then later observe the same `process_ref` terminal with `accounting_complete=true` and final byte counts.
5. Run one disposable working-tree mutation; observe it with a later git/read command.
6. Replay the same `operation_key` and payload; prove same `process_ref` and `reconciled=true`.
7. Reuse that key with a changed payload; prove `OPERATION_CONFLICT` and no second effect.
8. Run the credential-environment scrub canary; prove ambient `GITHUB_TOKEN`, `GH_TOKEN`, SSH-agent variables, unrelated cloud/API secret variables and usable Git credential-helper configuration are absent from the child environment. Do not report this as arbitrary credential-file isolation.
9. Cancel one sleeping command; prove only the exact process generation terminates.

Only after this `EXECUTE` sequence traverses the supported full-MCP ChatGPT connection may the four-tool parent be classified `PROVEN_LIVE`.

## 9. Recover an exact pre-effect receipt interruption

`PRE_EFFECT_RECEIPT_UNAVAILABLE` is emitted only when the runtime observes an exact empty, same-owner, mode-0700 operation directory with no `record.json` or immutable phase sidecar. The start path never spawns the supervisor before the durable PREPARED receipt, so this exact empty shape proves that operation did not launch a command. It does not authorize broad cleanup.

1. Stop the DevBox service and make no further tool calls.
2. Inspect the exact directory under `<state-root>/operations/`; verify it is a real non-symlink directory, owned by the service UID, mode 0700, and contains zero entries.
3. Remove only that exact empty directory. If any file, temporary entry, sidecar, ownership/mode drift, or uncertainty exists, remove nothing and preserve the operation as unresolved.
4. Restart the same generation and replay the same `operation_key` and payload. Never create a different operation merely to bypass the refusal.

This exact-empty procedure does **not** apply when `record.json` exists in `PREPARED`, `START_RECEIPT_UNAVAILABLE`, or another effect-uncertain phase, or when any sidecar/output/cancel/temp entry exists. Those states may follow a supervisor start. Preserve the complete operation directory, keep the same operation/generation bound, inspect the source and process evidence, and classify unresolved state as `EFFECT_UNKNOWN` / `RECEIPT_UNAVAILABLE`. If exact effect truth cannot be recovered, export the evidence and retire the disposable Codespace/generation without claiming the command was not applied; any later work requires a fresh explicit generation.

## 10. Stop and reconcile

After the canary:

```bash
gh codespace ports visibility 8767:private -c <codespace-name>
gh codespace stop -c <codespace-name>
```

Delete only after source/effect evidence is reconciled:

```bash
gh codespace delete -c <codespace-name>
```

Stopping/deleting infrastructure is not source acceptance. Record the exact source SHA, Codespace identity as private operator evidence, tool/effect receipts, test results, public exposure interval, and final capability state in the existing durable owners.
