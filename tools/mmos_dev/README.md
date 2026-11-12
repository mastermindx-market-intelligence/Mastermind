# MMOS Paperclip dev instance (lane L9 test bed)

`paperclip_dev.sh` drives ONE isolated Paperclip instance under
`~/.mastermind/mmos-dev/paperclip/` (instance id `mmos-dev`, loopback port
3190). It never touches the Chairman's default instance (`127.0.0.1:3100`,
`~/.paperclip`) — every command re-checks the target's identity and refuses
(exit 3) on the default instance, reserved ports, or a non-loopback host.

## Direct-start launcher (deputy ruling 14)

`up` never invokes the CLI's `run`/`test-drive` wrappers: their doctor step
resolves store paths against `~/.paperclip`, and one abandoned launch joined
the real database for 90 seconds. Instead `up` writes a
`launch-server.mjs` into the instance dir and runs it with node; it imports
`startServer()` from the managed CLI install
(`~/.paperclip/cli/current/node_modules/@paperclipai/server`) directly, with
`PAPERCLIP_HOME`, `PAPERCLIP_INSTANCE_ID` and `PAPERCLIP_CONFIG` pinned to
the dev instance (the server falls back to `~/.paperclip/instances/default`
when those are unset). The config the script writes pins
`server.port`, `database.embeddedPostgresPort` and
`database.embeddedPostgresDataDir` explicitly.

`up` reads the start banner (server log) BEFORE making any request, then
calls the instance ready only after three isolation checks pass:

- (a) no socket on TCP:54329 held by the launcher pid or any of its children
  (the dev embedded PostgreSQL runs as a direct child);
- (b) the database listener is the configured dev port, serving the dev data
  dir, and the banner names that same port;
- (c) the banner/log names neither port 54329 nor any path under
  `~/.paperclip/instances/default`.

The server log is truncated at each launch, so the banner proof is always
this run's bytes, never a previous run's. The launch environment also
scrubs `DATABASE_URL`/`DATABASE_MIGRATION_URL` (the server prefers an
ambient `DATABASE_URL` over the pinned embedded cluster and would migrate
it before printing any banner), scrubs `PAPERCLIP_SERVER_PORT`/`HOST` and
the bind overrides, and sets `PAPERCLIP_DISABLE_CWD_ENV_FILE=true` so no
`.env` from the caller's cwd leaks in. Company seeding passes
`--api-base <dev url>` explicitly, and `down` verifies the target pid's
argv names the dev launcher before signalling it. `up` refuses to start at
all when `lsof`/`pgrep`/`ps` are missing — the isolation checks never run
degraded. A log left by a previous run is reset per launch; use
`logs` before `down` if you need the old output.

Any failure kills the launched process tree, prints exactly one line
`PAPERCLIP-DEV: REAL STORE REFUSED` (reason on stderr) and exits 3.

```
tools/mmos_dev/paperclip_dev.sh up      # create config (first run), launch, seed company
tools/mmos_dev/paperclip_dev.sh status  # url, company id, pid, installed modules
tools/mmos_dev/paperclip_dev.sh down | logs [n] | url | reset
```

## For the next lane: create a TEST company and TEST agent (dev instance ONLY)

The first `up` seeds one test company automatically — `MMOS Dev`
(prefix `MMO`). `status` prints its id; use it as `$CID` below.

Create a TEST agent (minimal fields; `role` feeds roster truth, `adapterType`
is the dispatch surface):

```
CID=$(tools/mmos_dev/paperclip_dev.sh status | sed -n 's/.*id: \([0-9a-f-]*\)).*/\1/p')
curl -s -X POST "http://127.0.0.1:3190/api/companies/$CID/agents" \
  -H 'content-type: application/json' -H 'x-instance-role: local_trusted' \
  -d '{"name":"Atlas","role":"engineer","adapterType":"process"}'
```

Wake it once (creates a run row; `source` must be one of
`timer|assignment|on_demand|automation`):

```
curl -s -X POST "http://127.0.0.1:3190/api/agents/<agentId>/wakeup" \
  -H 'content-type: application/json' -H 'x-instance-role: local_trusted' \
  -d '{"source":"on_demand"}'
```

Adapter types this build lists — `GET /api/adapters` (dev instance), as of
build 2026.1106.0: `acpx_local`, `claude_local`, `codex_local`, `cursor`,
`cursor_cloud`, `gemini_local`, `grok_local`, `hermes_gateway`,
`hermes_local`, `http`, `kimi_local`, `openclaw_gateway`, `opencode_local`,
`paperclip_runner`, `pi_local`, `process`. Plan V4's dispatch-join question
names `process` or `http`.

Installed modules (`mastermind-core`): see
`integrations/paperclip_plugins/mastermind-core/README.md` and
`skills/mmos-module-dev/SKILL.md`.
