# Mastermind Workbench Local MCP + Secure MCP Tunnel

**State: BUILT_NOT_PROVEN.** The pure Personal-Pro local Read profile and the
eleven-tool attended Workbench Action tunnel profile exist in source. Real SDK
stdio initialize/list/call tests pass locally. The attended profile is not
installed or admitted by ChatGPT in this source receipt. C1 validation reuses
the existing dedicated private Workbench tunnel and its one actual Personal
workspace association after a fresh host readback; it must not retarget an
Executive tunnel or create a second C1 Workbench tunnel.

This carrier does not replace Executive OS, Agent OS, RuntimeBinding, Capacity,
Workbench Read, Code Intelligence, process ownership, or effect reconciliation.
It is a tunnel-facing adapter over existing Workbench read primitives.

## Product split

### Personal Pro: `pro_read_prepare`

This is a genuinely non-effectful profile, not a write capability renamed to
look like a read. Its frozen tools are:

1. `workspace_manifest` - inspect the fixed project/profile projection;
2. `read_project_file` - bounded descriptor-relative UTF-8 observation;
3. `preview_text_replace` - read a required exact preimage and compute an
   in-memory unified diff/proposed hash; never write/stage/persist it;
4. `preview_project_command` - render one closed validation recipe as argv;
   never start a process.

Every tool is advertised with `readOnlyHint=true`, `destructiveHint=false`,
`idempotentHint=true`, and `openWorldHint=false`. The adapter contains no
subprocess, socket, file-write, rename, unlink, network-call, durable prepare,
or queue path. Project root, allowed files, committed baseline and lease are
host configuration; they are never model-selected tool arguments.

A Personal-Pro leader that wants an actual effect must use a separately
supported effectful carrier/worker. This MCP never changes its behavior because
a prompt asks it to write.

### Attended action profile: `attended_workbench_f0`

Do not widen the pure four-tool adapter. The fixed-channel Action launcher
composes the borrowed Read port with bounded patch and command ports under one
runtime. Its manifest reports the `attended_workbench_f0` profile and exactly:

1. `workspace_manifest`, `read_project_file`, `preview_text_replace`;
2. `prepare_text_patch`, `commit_text_patch`, `reconcile_text_patch`;
3. `prepare_project_command`, `run_project_command`, `read_action_result`,
   `read_action_artifact`, `reconcile_action`.


Artifact bytes remain in the existing Action artifact store. A command result issues signed, expiring descriptors for retained stdout/stderr; `read_action_artifact` accepts only the descriptor plus a bounded byte range. Text is strict UTF-8 on byte boundaries, complete small PNGs are native MCP images, and other binary ranges are lossless MCP blobs. Never add a project path, host path, arbitrary URI, output-slot override, or media-type override to this tool. Preserve the existing action key and artifact directory across ordinary restarts so the same Action can reconcile and renew a reference; key or generation rotation must first settle any unresolved effect.

`commit_text_patch` and `run_project_command` are honestly modifying. Command
execution is limited to the pinned checksum, intentional-refusal, and deterministic source-fingerprint PNG canaries;
the preview-only `preview_project_command` is absent. The first native target
is C1 Personal because the user reports custom change/write support there.
There is no Business-only condition: actual tool scan and invocation decide
admission for each account/workspace route.

## Transport topology

```text
ChatGPT custom app
    |
OpenAI Secure MCP Tunnel
    |  outbound-only tunnel-client on Mac Studio
    v
stdio: scripts/mastermind_workbench_local_mcp.py
    |
bounded private MCP stdio boundary
    |
LocalWorkbenchGateway
    |
existing integrations.workbench_read_mcp.observer
    |
fixed owner-configured project descriptor
```

There is no Desktop Commander hosted relay, `broadcast_v1`, public inbound
listener, model-selected host, or generic remote shell in this path.

The stdio boundary validates closed JSON-RPC envelopes before MCP SDK dispatch,
caps inbound and outbound frames at 262,144 UTF-8 bytes, and returns a fixed
null-ID protocol refusal for malformed input. Rejected values are excluded from
SDK diagnostics. The server still validates each known tool against its frozen
schema and returns the adapter's bounded result envelope.

### Borrowed Read port for the Action runtime

The same four pure operations can be composed under an already-authorized
Action runtime without opening a second root or lifecycle:

```python
create_bound_read_port(
    project_ref,
    profile,
    allowed_paths,
    resolve_scope,
    clock_ms,
)
```

This factory returns a synchronous `call(name, arguments)` port. The host owns
all five inputs; none is a tool argument. `resolve_scope()` remains the sole
current authority and is called for every advertised tool, including manifest
and command preview. Manifest identity, generation, expiry and committed
baseline come from that current `ReadScope`. The port never opens, duplicates
or closes the borrowed root and creates no executor, audit sink, lease,
generation or cached live grant. Its `close()` only revokes the local port; the
Action runtime retains descriptor and drain ownership. File read and text
preview continue to use the protected descriptor-relative observer under the
Action runtime's existing physical executor.

## Owner configuration

The launcher accepts exactly one absolute owner-controlled JSON config. Example:

```json
{
  "schema": "mastermind.workbench_local_profile.v1",
  "profile": "pro_read_prepare",
  "project_ref": "mastermind-canary",
  "project_root": "/absolute/owner/selected/worktree",
  "allowed_paths": [
    "pyproject.toml",
    "docs/EXECUTIVE_MCP.md"
  ],
  "committed_head": "0123456789012345678901234567890123456789",
  "lease_expires_at_ms": 1789500000000
}
```

Config is bounded, duplicate-key refusing, same-euid, nofollow, regular-file,
and not group/world-writable. Acquisition requires the initial path, opened
descriptor, post-read descriptor and final path to retain the same identity,
mode, owner, link count, size, mtime and ctime, with an exact-size nonblocking
read. Project root must be same-euid, non-symlink,
non-group/world-writable directory. `.git` paths, traversal, absolute paths,
Windows-drive syntax and undeclared files refuse closed.

Server construction and initialization are inside the same cleanup boundary as
serving. Once an executor exists it drains before the owned project descriptor
closes. An ambiguous descriptor close reports
`PROJECT_CLEANUP_UNCERTAIN`, remains sticky on later close calls, and is never
retried against a possibly reused descriptor number.

The serving command is:

```sh
/Users/chriswong/.venvs/mastermind-executive-canary/bin/python \
  /absolute/checkout/scripts/mastermind_workbench_local_mcp.py \
  --config /Users/chriswong/.config/mastermind-workbench/pro-local-canary.json
```

`--describe` is dependency-light and does not start MCP or touch project state.

## Local proof completed 2026-09-13

Focused source and inherited read-boundary proof:

```text
43 passed  tests/workbench_local_mcp
47 passed  tests/workbench_read_mcp/test_observer.py
17 passed  tests/test_mcp_stdio_boundary.py
53 unittest subtests passed across the combined gate
```

A real MCP 1.28.1 stdio client then proved:

```text
initialize -> server Mastermind Workbench Local 0.1.0
list_tools -> four frozen tools
all four -> readOnly=true, destructive=false
workspace_manifest -> all effects false
read_project_file -> real source bytes
preview_text_replace -> PREVIEW_ONLY / applied=false / persisted=false
preview_project_command -> argv returned / started=false
post-preview source SHA-256 == pre-preview source SHA-256
```

This establishes a local stdio canary only. It is not proof of ChatGPT tunnel
transport, account enrollment, app scan, Personal-Pro policy acceptance, or
production longevity.

## Secure MCP Tunnel binding gate

Mac Studio already has the official tunnel client and a dedicated stopped C1
Workbench tunnel. Refresh its actual organization and single Personal workspace
association before use. Keep runtime credentials in the existing private
file/environment reference; never copy them into source, command history, chat,
or the MCP config.

Connect only that existing dedicated tunnel to the attended Action launcher
using its workspace-valid runtime key **by file/env reference**, never inline
secret text:

```sh
tunnel-client runtimes connect \
  --alias mastermind-workbench-chatgpt1 \
  --profile mastermind-workbench-chatgpt1 \
  --mcp-command "/absolute/hash-locked/python /absolute/protected/source/scripts/mastermind_workbench_action_stdio.py --config /Users/chriswong/.config/mastermind-workbench/action-c1.json" \
  --runtime-api-key file:/Users/chriswong/.config/tunnel-client/credentials/<workspace-runtime-key>

tunnel-client runtimes status mastermind-workbench-chatgpt1 --json
tunnel-client doctor --profile mastermind-workbench-chatgpt1 --explain
```

Do not report the tunnel ready unless health/ready are green and the exact
Workbench tunnel organization/workspace binding was read back.

The selected project is the existing assigned external-SSD helper project.
Attended Web source custody follows the installed `mmx-workspace acquire` and
`release` contract in `docs/DELIVERY_WORKFLOW.md`; its receipt, not a model path,
defines the workspace. This integration does not claim that it created a new
workspace through `mmx-workspace`, and it preserves the current assigned
checkout unless the custody owner explicitly supplies another receipt.

## ChatGPT app admission

After the tunnel is healthy, create or update one developer-mode Workbench app
in the intended C1 Personal workspace, choose **Tunnel** as the connection,
select the dedicated Workbench tunnel, and scan tools. The attended scan must
show exactly the ten tools above, with only `commit_text_patch` and
`run_project_command` marked modifying. Exercise manifest, bounded read/preview,
patch create/replace/reconcile, command exits 0/7, retained result paging, and
same-action reconciliation without replay. The pure local Read launcher remains
a separate four-tool profile and is never relabeled as the attended profile.

Do not call the result `PROVEN_LIVE` until the actual C1 Personal account has
successfully scanned and invoked it through ChatGPT and the revoke, physical
drain, disconnect, and rollback path has been exercised.

## Rollback

Stop only the Workbench alias:

```sh
tunnel-client runtimes stop mastermind-workbench-chatgpt1
```

Disconnect only the Workbench custom app. Do not stop or edit the existing
Mastermind Executive aliases/tunnels. Remove the Workbench profile/config only
after confirming no in-flight command and reconciling every ambiguous patch or
command effect.
