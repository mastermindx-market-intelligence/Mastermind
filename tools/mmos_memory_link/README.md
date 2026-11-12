# memory-link

A small stdio MCP server that gives one AI teammate narrow access to **one**
existing file-backed memory store. The server never reads or writes the store's
files. It only runs that store's own command-line program (`omh`) and returns
memory text.

## Why the store's own CLI

There is one store. That program already owns locking, admission, approval, and
on-disk layout. A second writer that opened the same files would race the store
and bypass its gates. memory-link is a translator: JSON-RPC in, `omh memory …`
argv out, teammate-facing text back.

## Config

Required launch argument: `--config <file.json>`. The file must be owned by the
current user and must not be group- or world-writable.

| key | meaning |
| --- | --- |
| `omh_bin` | Absolute path to the store CLI. |
| `omh_home` | Absolute store home passed as `--omh-home`. |
| `hermes_home_for_omh` | Absolute **empty private directory** the server owns. Passed as `--hermes-home` and as the child `HOME`, so the store never sees the agent runtime home. |
| `teammate` | Slug `[a-z0-9-]+`. Written as tag `teammate-<slug>` on save. |
| `write_enabled` | Boolean. Default `false`. |
| `profile_memory_dir` | Optional absolute directory of plain `MEMORY.md` / `USER.md` notes (read-only). |
| `limit_default` | Recall limit when the tool omits `limit` (default 8). |
| `limit_max` | Recall limit ceiling (default 20). |
| `max_chars` | Cap on every tool result, and `--max-chars` for recall (default 6000). |
| `call_timeout_sec` | Child timeout (default 20). |

Child environment is only `PATH=/usr/bin:/bin`, `HOME=<hermes_home_for_omh>`,
`LANG=C.UTF-8`. Global CLI flags always come before the `memory` subcommand.
`--observer` is never passed.

## Tools

| tool | when listed | input | output |
| --- | --- | --- | --- |
| `memory_recall` | always | `query` (1–300 chars), optional `limit` | Two labelled sections, `[own]` (scope `target / teammate-<slug>`) first, then `[shared]` (`user-global / default`), each with half the output budget: numbered `record_id · subject · approved_at · staleness: summary` lines, then `included=… excluded=… truncated=…`. No raw store JSON, paths, or env. |
| `memory_notes` | only if `profile_memory_dir` is set | none | Text of `MEMORY.md` and `USER.md` (each ≤ 4000 chars). Opened `O_RDONLY\|O_NOFOLLOW`; symlinks are refused. |
| `memory_save` | only if `write_enabled` is true | `summary` (10–500 chars), `type` (`fact`/`decision`/`lesson`/`procedure`/`episode`), optional `tags` (≤4 `[a-z0-9-]{1,32}`) | `saved <record_id> (auto_approved=<bool>)` or `not saved: <reason>`. Writes only to the teammate's own scope `target / teammate-<slug>`, never the shared scope; always adds tags `teammate-<slug>` and `via-memory-link`. Credential-shaped summaries are refused without calling the store. |

## Writing: own scope only

Writing is off by default (`write_enabled` false). When it is on, a save lands in
the teammate's own scope `target / teammate-<slug>`. The scope comes from the
config, never from the tool call, so one teammate cannot write or read another's
scope. Hermes' prompt prefetch does not select the `target` scope, so a teammate's
saves are not injected into Hermes bots. There is no promote tool: moving a
record into the shared scope is a person's review. Tool descriptions state that
recalled text is data, never an instruction.

## T3 teammate launch

Point the teammate at an MCP config file:

```
--mcp-config /ABS/PATH/example.mcp.json
```

The teammate tool gate must allow:

- `mcp__memory-link__memory_recall`
- `mcp__memory-link__memory_notes` (only if notes are configured)
- `mcp__memory-link__memory_save` (only if writing is ruled in)

See `example.mcp.json` for the server key `memory-link` and the
`python3.12 -I <server> --config <file>` command.
