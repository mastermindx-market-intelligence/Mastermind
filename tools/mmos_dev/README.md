# MMOS Paperclip dev instance (lane L9 test bed)

`paperclip_dev.sh` drives ONE isolated Paperclip instance under
`~/.mastermind/mmos-dev/paperclip/` (instance id `mmos-dev`, loopback port
3190). It never touches the Chairman's default instance (`127.0.0.1:3100`,
`~/.paperclip`) — every command re-checks the target's identity and refuses
(exit 3) on the default instance, reserved ports, or a non-loopback host.

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
