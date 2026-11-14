# Executive reader `backend_unavailable` — production diagnosis (Director C, C2)

**Status: PROVEN at the parser boundary (2026-11-09).** Read-only diagnosis.
No service, daemon, socket, or config was touched; no dev instance was needed
(the failure reproduces at the exact parser boundary, below). Nothing in this
document is a claim about the production reader beyond what the cited
observations prove, and this document creates no registry, queue, or watcher.

## Observation being diagnosed (from the 2026-11-08 Web-CEO recovery)

From a connected Executive V3 (OAuth) MCP session (see
`docs/hermes/CHATGPT_WEB_TEAM_BUS.md` "Live census"):

- `session_targets({})` → success, empty **legacy** projection.
- `executive_state` → `backend_unavailable`.

## Production composition (where an `executive_state` read actually goes)

```text
Executive V3 MCP client (OAuth, read scope)
  -> integrations/executive_mcp/server.py (tool dispatch; executive_state in the
     read-tool set, server.py:225)
  -> integrations/mastermind_executive_app/gateway.py (CeoIngress read path;
     canonical-result validator gateway.py:3452, upstream-failure classifier
     `_classified_upstream_failure` gateway.py:3528-3545: unavailable upstream
     codes -> "backend_unavailable")
  -> integrations/executive_mcp/installed.py — InstalledBootPacketCollector
     (`_run_read_attempt` request scope for executive_state/executive_inbox,
     installed.py:3653-3660; `_collect_packet` installed.py:3081-3096)
  -> _build_macro_materialization_plan (installed.py:1376-1407)
  -> _macro_read_selection over EVERY agentos/workstreams/* record
     (installed.py:1327-1373) -> _frontmatter_lists (installed.py:1010-…)
```

Fail-closed by design: `_build_macro_materialization_plan` wraps ANY
`OSError | TimeoutError | ValueError` from the selection walk as

```
GatewayError("backend_unavailable", "installed Macro path-list frontmatter is unsupported")
```

(installed.py:1402-1406), and `_collect_packet` additionally requires exactly
one verified Macro snapshot (installed.py:3077-3081). One bad record refuses
the whole `executive_state` read.

## Why `session_targets({})` succeeds on the same connection

`session_targets` is served by the Session Bridge
(`integrations/session_bridge/installed.py:179-192`): a target projection with
**no Macro materialization / boot-packet dependency**. An empty legacy
projection (`{}` → legacy inventory) returns `[]` successfully. The two tools
have disjoint dependency sets, so one succeeding while the other refuses is the
expected composition, not a contradiction.

## Root cause — PROVEN against the exact installed generation

The installed Control reader generation is `b4a5a8925c6c` (Worker still running
on it; `docs/hermes/CHATGPT_WEB_TEAM_BUS.md` "Control adoption"). Its
`_frontmatter_lists` tokenizes frontmatter with

```python
if line.strip() and not line.lstrip().startswith("#")   # b4a5a8925c6c installed.py:1007
```

i.e. **every `#`-prefixed line is dropped before parsing** — including lines
that are continuations of a folded block scalar, not comments. PR #2088
(`910b3eca8`, "preserve hash lines inside quoted Macro metadata") moved comment
skipping to structural boundaries only; the installed generation predates it.

Reproduction (read-only, LIVE Macro checkout at
`/Users/chriswong/Documents/Cluade/Macro Dashboard`; both generations extracted
from this repository with `git show <sha>:integrations/executive_mcp/installed.py`):

```console
$ env -u PYTHONPATH /opt/homebrew/bin/python3.12 /tmp/dirc_repro2.py
records=115 both_ok=114 installed_b4a5_refuses=1 staged_036e_refuses=0
INSTALLED-REFUSES WS-PROPHET-END-TO-END-R7.md
```

- The installed generation (`b4a5a8925c6c`) **refuses exactly 1 of 115** live
  workstream records: `WS-PROPHET-END-TO-END-R7.md`, whose frontmatter contains
  issue-reference continuation lines that begin (after indent) with `#` —
  line 39 `#9422 (engine/news_impact) …` and line 80 `#8444 → HK → China …`
  inside folded (`>`) block scalars. Stripping them breaks the structural walk
  → `ValueError("unsupported YAML structure in path-list frontmatter")`.
- The staged release `036e8d26cb2b…` (contains the #2088 fix; 8
  `skip_comments` call sites) **accepts all 115**.
- One refused record aborts the whole materialization plan → `backend_unavailable`
  for `executive_state`. That is the live failure.

PROVEN: the parser verdicts above (both exact generations, live records).
NOT claimed: end-to-end HTTP reproduction through the production ingress (not
attempted — unnecessary for the diagnosis and outside this lane's authority).

## Resolution path (existing owners; nothing here releases a hold)

1. The fix is **not deployable from an MCP update**: the failing parser lives
   in the Control-side installed reader, behind the original Control release
   path (`ops/executive_os/control_component_update.py`, plan-gated
   `plan-control-component --expected-sha`).
2. The 2026-11-08 plan against the staged `036e8d26…` release returned
   `REFUSED / control_component_worker_live` (Worker live on `b4a5a8925c6c`).
   **Do not stop or disarm the Worker to make the plan eligible.**
3. The 09b/call5913 protected-result disposition (programme issue #1893) is a
   prerequisite to dependent installation; neither a component-only path nor a
   different carrier releases that hold.
4. PR #2177's `executive_runtime.py` / `executive_worker_routes.json` hunks are
   protected (ranges saved in `integrations/mmos/_pr2177_protected_hunks.diff`);
   the release path must not depend on editing them.

Consumers reading this for the Hermes/T3 seam: `executive_state` becoming
healthy requires the Control generation to move to ≥ the #2088 fix through its
owner. Until then, treat `executive_state` as genuinely unavailable (honest
UNKNOWN), and do not infer backend health from `session_targets` succeeding.
