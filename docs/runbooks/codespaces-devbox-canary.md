# GitHub Codespaces DevBox — Production Canary

**Capability:** attended ChatGPT Web → authenticated DevBox MCP → one exact GitHub Codespace filesystem/shell/git/test workspace.
**Source owner:** GitHub.
**Lifecycle owner:** Executive OS when a Job/Attempt exists; this canary does not mint one.
**Provider state:** do not claim `PROVEN_LIVE` until the Personal Pro custom-MCP call completes through the public endpoint and its exact results are read back.

## Hard boundaries

- Codespaces is an execution resource, not a second queue, scheduler, identity store, lifecycle, memory, retry or source-authority plane.
- The model cannot supply a host, Codespace name, repository, cwd, root, environment, account or credential.
- Child commands receive no `GITHUB_TOKEN`, `GH_TOKEN`, SSH agent, cloud/API secrets or usable Git credential helper from the service environment.
- The DevBox command profile may change working-tree files and run local git/worktree/test commands. Remote source publication/merge remains owned by the existing GitHub release path.
- A lost modifying response is reconciled by the same `operation_key`; never start process two or fail over to a Mac/other Codespace while effect is unknown.
- Stopping/disconnecting a Codespace never proves a command did not run.

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

Direct runtime acceptance must prove: exit 0, intentional exit 7, a process still observable after its start call returns, same-operation reconciliation with no process two, changed-payload conflict, bounded stdout/stderr, timeout, exact cancellation, binding drift refusal, and absence of ambient GitHub/cloud/SSH credentials in child execution.

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
= [workbench.execute]

policy.allowed_subject_digests
= [lease.expected_subject_digest]

lease.repository
= $GITHUB_REPOSITORY

lease.committed_head
= git rev-parse HEAD
```

`target_ref`, `generation` and `owner_ref` are owner-issued opaque references. They are not Codespace hostnames and must not be model authored.

## 6. Start authenticated DevBox

Use a state root outside the checkout; its parent must already exist. Example:

```bash
mkdir -m 700 -p "$HOME/.mastermind-devbox-state"
python -m ops.devbox.run_codespace_devbox \
  --repo-root "$PWD" \
  --state-root "$HOME/.mastermind-devbox-state" \
  --policy-file "$HOME/devbox-policy.json" \
  --lease-file "$HOME/devbox-lease.json" \
  --port 8767
```

The service binds `127.0.0.1` inside the Codespace. GitHub's forwarding agent supplies the external TLS URL. The service prints the derived `DEVBOX_MCP` URL but no credential or raw identity.

Before opening the listener, the launcher re-execs itself under a strict environment allowlist. `GITHUB_TOKEN`, `GH_TOKEN`, `SSH_AUTH_SOCK`, API/cloud secrets, `PYTHONPATH`, and other ambient variables do not survive into the long-lived DevBox service process. This is required in addition to child-command credential stripping so a same-user command cannot recover the Codespace token from the parent service environment.

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

## 8. Personal Pro acceptance

Connect the existing approved Personal Pro custom-MCP surface to the exact `DEVBOX_MCP` resource using the existing accepted OAuth/app mechanism. Personal Pro write capability is a proven account fact for the Chairman seat; this canary is proving the new Codespaces backend, not re-proving generic plan entitlement.

From the real Web-Sol conversation, execute in order:

1. `devbox_status` — exact target/generation/repository/HEAD only.
2. `start_devbox_command` with an exit-0 command; read terminal exit 0.
3. Intentional exit 7; read exact exit 7.
4. Start a delayed command; let the initiating tool call return; later observe the same `process_ref` to terminal.
5. Run one disposable working-tree mutation; observe it with a later git/read command.
6. Replay the same `operation_key` and payload; prove same `process_ref` and `reconciled=true`.
7. Reuse that key with a changed payload; prove `OPERATION_CONFLICT` and no second effect.
8. Run the credential scrub canary; prove ambient `GITHUB_TOKEN`, `GH_TOKEN`, SSH agent and unrelated cloud/API secrets are unavailable to the child.
9. Cancel one sleeping command; prove only the exact process generation terminates.

Only after these calls traverse the actual Personal Pro custom-MCP connection may this slice be classified `PROVEN_LIVE`.

## 9. Stop and reconcile

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
