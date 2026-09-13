# Mastermind Workbench Local MCP + Secure MCP Tunnel

**State: BUILT_NOT_PROVEN.** The Personal-Pro-safe local MCP source exists and a
real SDK stdio initialize/list/call sequence passed on Mac Studio on 2026-09-13.
A new OpenAI Secure MCP Tunnel has **not** been registered for this surface and
no ChatGPT app/plugin has been created from it. Remote canary completion remains
blocked on an approved OpenAI Admin API key for tunnel creation.

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

### Business / full action surface

Do not widen this Personal-Pro adapter. The full Business surface belongs in
the bounded **Workbench Action sibling** already specified by the Web CEO/native
operator architecture. That sibling must own honest modifying tools and effect
truth (`NOT_APPLIED | APPLIED | EFFECT_UNKNOWN`) with prepare/consume/reconcile
semantics. Keep it independently versioned and connected as a write-capable
Business app while reusing the same canonical project/process owners.

## Transport topology

```text
ChatGPT custom app
    |
OpenAI Secure MCP Tunnel
    |  outbound-only tunnel-client on Mac Studio
    v
stdio: scripts/mastermind_workbench_local_mcp.py
    |
LocalWorkbenchGateway
    |
existing integrations.workbench_read_mcp.observer
    |
fixed owner-configured project descriptor
```

There is no Desktop Commander hosted relay, `broadcast_v1`, public inbound
listener, model-selected host, or generic remote shell in this path.

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
and not group/world-writable. Project root must be same-euid, non-symlink,
non-group/world-writable directory. `.git` paths, traversal, absolute paths,
Windows-drive syntax and undeclared files refuse closed.

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
13 passed  tests/workbench_local_mcp/test_local_profile.py
14 passed  tests/workbench_local_mcp
47 passed  tests/workbench_read_mcp/test_observer.py
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

## Secure MCP Tunnel registration gate

Mac Studio already has official `tunnel-client` 0.0.14 and healthy existing
Mastermind Executive tunnel runtimes. Creating a **new** remote tunnel requires
an OpenAI Admin API key. The current Studio and MacBook admin profiles reference
`env:OPENAI_ADMIN_KEY`, but that environment variable was not present during
this canary. Do not copy an Admin key into source, command history, chat, or the
MCP config merely to clear this gate.

Once an approved Admin key is available to the local operator environment,
create a new tunnel scoped only to the intended workspace. Do not reuse or
retarget either live Executive tunnel:

```sh
tunnel-client runtimes create \
  --alias mastermind-workbench-chatgpt1 \
  --name "Mastermind Workbench - Personal" \
  --description "Bounded local project reads and pure previews; no mutation or process execution." \
  --workspace-id <INTENDED_CHATGPT_WORKSPACE_ID>
```

Then connect the new tunnel to the local stdio command using a workspace-valid
runtime API key **by file/env reference**, not inline secret text:

```sh
tunnel-client runtimes connect \
  --alias mastermind-workbench-chatgpt1 \
  --profile mastermind-workbench-chatgpt1 \
  --mcp-command "/Users/chriswong/.venvs/mastermind-executive-canary/bin/python /absolute/checkout/scripts/mastermind_workbench_local_mcp.py --config /Users/chriswong/.config/mastermind-workbench/pro-local-canary.json" \
  --runtime-api-key file:/Users/chriswong/.config/tunnel-client/credentials/<workspace-runtime-key>

tunnel-client runtimes status mastermind-workbench-chatgpt1 --json
tunnel-client doctor --profile mastermind-workbench-chatgpt1 --explain
```

Do not report the tunnel ready unless health/ready are green and the tunnel is a
new Workbench tunnel, not an Executive tunnel with its command replaced.

## ChatGPT app admission

After the tunnel is healthy, create a separate developer-mode custom app in the
intended ChatGPT workspace, choose **Tunnel** as the connection, select the new
Workbench tunnel, and scan tools. The scan must show exactly the four
Personal-Pro tools above with no effectful tool. Test `workspace_manifest`, one
bounded file read, one preview replacement, and one command preview. Re-read the
source preimage after each preview to prove no effect.

Do not call the result `PROVEN_LIVE` until the actual Personal-Pro account has
successfully scanned and invoked it through ChatGPT and the disconnect/rollback
path has been exercised.

## Rollback

Stop only the Workbench alias:

```sh
tunnel-client runtimes stop mastermind-workbench-chatgpt1
```

Disconnect only the Workbench custom app. Do not stop or edit the existing
Mastermind Executive aliases/tunnels. Remove the Workbench profile/config only
after confirming no in-flight command and no ambiguous effect; this Personal
profile has no modifying effect state to reconcile.
