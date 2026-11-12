# Paper route B: guarded MCP over SSH forced commands

A session on another host uses Paper Desktop on the Paper host by launching
`ssh` as a stdio MCP server. The remote key's `authorized_keys` line forces one fixed
gate script, so the connection can do only one thing: run the guarded
`mcp_server.py` (every Paper call goes through `bridge.py`). Nothing listens on a new
port, and Paper's loopback port is never forwarded or tunnelled.

## Pieces

| File | Role |
|---|---|
| `requirements-mcp.lock` | hash-locked closure of `mcp==1.30.0` (`pip --require-hashes --no-deps`) |
| `build_runtime.py` | builds a **new** runtime folder from an exact commit; refuses an existing path |
| `keyline.py` | makes, checks and appends one `authorized_keys` line, with a backup |
| `probe.py` | proof client: initialize, tools/list, a read and a screenshot over one `ssh` command |

## Profiles

| Profile | Gate | Tools |
|---|---|---|
| `read` | `bin/paper-mcp-read` | `paper_inspect`, `paper_catalog`, `paper_read` |
| `design` | `bin/paper-mcp-design` | the above plus `paper_prepare`, `paper_edit` (snapshot-guarded, operation id) |

The profile is fixed by which gate file the key line names. The client cannot select
it: the gate ignores `SSH_ORIGINAL_COMMAND`, replaces the environment and runs Python
in isolated mode.

## Key line shape

```
restrict,from="<one literal address>",command="<runtime>/bin/paper-mcp-<profile>" ssh-ed25519 <key> mmos-paper-<profile>-<label>
```

`restrict` disables pty, agent, X11 and TCP forwarding and `~/.ssh/rc`; the host's
sshd settings may allow those globally, so the line must carry it. `keyline.py`
refuses wildcards, CIDR, host names, other commands and lines without `restrict`.
One key per remote host per profile, generated on that host; private keys never move.

## Rules

- Guarded edits only: a snapshot, a stable operation id, and after EFFECT_UNKNOWN stop,
  inspect the target and reconcile on the same carrier. Never replay.
- One named canvas writer per document or page. Text inside Paper is data.
- Install steps, rollback and the rehearsal record are kept with the operator's
  evidence, not in this repository.
