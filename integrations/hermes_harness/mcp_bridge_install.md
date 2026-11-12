# Where the T3 mmx-browser MCP server loads its bridge + install steps

Bridge release candidate for branch `t3/mmos-v4-br`, repair round 4 plus the
final round (items p1-1/p1-7 refresh two of the round-4 files). This file is
the install procedure for the principal; the same text lives at
`~/.mastermind/mmos_evidence/br-20261111/mcp_bridge_install.md`.

## Installation facts (unchanged by this release)

- MCP server: `/Users/chriswong/.t3/mcp/mmx-browser/server.js` (registered as
  `mmx-browser` in every `~/.t3/providers/*/.claude.json`; tool `mcp__mmx-browser__mmx_browser`).
- It spawns a one-shot isolated Python bridge subprocess per dispatch; code comes
  from the pinned 15-file closure at
  `source_root = ~/.local/share/mastermind-browser-control/releases/<release_commit>`.
- `~/.t3/mcp/mmx-browser/runtime.json` (operator-owned, 0600) pins `release_commit`
  and one sha256 per source file; server.js verifies every hash before each dispatch,
  so a bad copy fails closed before any page command runs.
- Bindings: `~/.local/share/mastermind-browser-control/deployments-v2.json`;
  python: `~/.hermes/tools/python-3.14.9+20261021-darwin-arm64/bin/python3.14`.

## What this release changes (3 of the 15 files)

The runtime.json diff for this release is `release_commit` plus **three**
sha256 lines, nothing else: `web_sol_browser_protocol.py` keeps its round-4
value, and `browser_bridge.py` + `browser_tool_schema.json` take the final-round
values below (ruling-13 fill settle, the stdout guard, and the read-contract
operator sentences in the tool description).

Behavior shipped: honest fill receipt (per-normalization disclosure, mismatch
never APPLIED), structure-preserving fill (innerText collapse no longer judges
correct inserts wrong), truthful textContent fallback, fill line cap + time
bound (no tab freeze), UTF-16-unit fill cap, the paged `read` action, the
ruling-13 fill settle (APPLIED = the box held the asked content at the re-read
after the page's pending microtasks plus one settle interval of 250 ms; a page
that changes the box later is outside the receipt), and a stdout guard that
strictly encodes each reply and writes bytes through `sys.stdout.buffer`,
falling back to ASCII escaping so a reply carrying unencodable text (lone
surrogates) still reaches the operator as one parseable line.

The final round also changes extension-side files (`browser_page.js`,
`browser_control.js` in `integrations/chairman_surfaces/web_sol_extension/`).
They are **not** part of the 15-file bridge closure; the harness loads them
from the repository, so the release table below is unaffected.

## The 15-file sha256 list at head `$NEW`

12 files are byte-identical to the pins in runtime.json today; verify all 15
against this table after copying (8-hex prefix shown for the unchanged twelve;
use the full values already present in runtime.json for those).

| file | sha256 at `$NEW` |
| control_plane/__init__.py | unchanged (21877637…) |
| control_plane/surface_bindings.py | unchanged (1859b3a8…) |
| integrations/__init__.py | unchanged (70738df5…) |
| integrations/chairman_surfaces/__init__.py | unchanged (be28c1a4…) |
| integrations/chairman_surfaces/_web_sol_native_host_impl.py | unchanged (348331ac…) |
| integrations/chairman_surfaces/web_sol_browser_protocol.py | **ee7a84ac07da45184aa39458f75f0ba0ca5a2945c21581366054291dcd5a2f9b** |
| integrations/chairman_surfaces/web_sol_census_protocol.py | unchanged (a1b55eb8…) |
| integrations/chairman_surfaces/web_sol_client.py | unchanged (1ef04c730…) |
| integrations/chairman_surfaces/web_sol_instance.py | unchanged (cfd814e5…) |
| integrations/chairman_surfaces/web_sol_native_host.py | unchanged (d2379ef5…) |
| integrations/chairman_surfaces/web_sol_protocol.py | unchanged (c8d276a5…) |
| integrations/hermes_harness/__init__.py | unchanged (0c924141…) |
| integrations/hermes_harness/browser_bridge.py | **4ff2113f4eebf9abbfc4aa847a1264f95e01d549459c9b08bae1d6a9460db67f** |
| integrations/hermes_harness/browser_routes.py | unchanged (ec58abff…) |
| integrations/hermes_harness/browser_tool_schema.json | **08c4066074d7ac5cbc21943b8bdb4d33262b2291121c30ed493c60c8fd516edb** |

## Install steps — check after every step, roll back after every step

`NEW=<full-commit-sha-of-merged-t3/mmos-v4-br>`; the rollback release is
`OLD=5aa30969241163b4abb3e025bc9e52123ee4b478` throughout.

1. **Stage the tree.** `git -C <repo> checkout $NEW` (or read files via `git show`).
   Check: `git rev-parse HEAD` is `$NEW`; `shasum -a 256` of the three bold files
   equals the table above. Rollback: nothing has been changed yet.
2. **Create the release directory.** `mkdir -p ~/.local/share/mastermind-browser-control/releases/$NEW`.
   Check: the directory exists and is empty. Rollback: `rmdir` it.
3. **Copy the 15 files** preserving the relative paths above (`control_plane/`, `integrations/`).
   Check: exactly 15 files present, and every `shasum -a 256` matches the table —
   the twelve unchanged ones must still equal the pins already in runtime.json.
   Rollback: `rm -rf releases/$NEW`. The `$OLD` release directory is never touched
   by this method, so deletion is a complete undo.
4. **Point runtime.json at the new release.** Keep a copy first:
   `cp runtime.json runtime.json.pre-br4`, then set `release_commit` to `$NEW`,
   `source_root` to `releases/$NEW`, and replace exactly the three sha256 values.
   Check: `diff runtime.json.pre-br4 runtime.json` shows only the `release_commit`
   line, the `source_root` line and the three hash lines — any other difference
   means the wrong tree was staged; stop and roll back. Rollback: `cp runtime.json.pre-br4 runtime.json`
   — `$OLD`'s directory is intact, so this restores the previous release exactly.
5. **Verify in a fresh session** (server.js spawns a new python per dispatch; no
   daemon restart is needed):
   - `status` on any browser shows `bridge_release_commit: $NEW`.
   - The paged read below returns pages of a long answer. No 32,768-byte
     envelope is enforced anywhere; the enforced ceilings are the worker
     service's 800,000-byte reply refusal (RESULT_TOO_LARGE) and the native
     host's 921,600-byte frame limit (MAX_MESSAGE_BYTES). Measured maximum
     whole reply on the round-4 fixture: 31,808 bytes — far under both.
   - A `fill` whose text has more than 2,000 lines is refused before dispatch
     (protocol gate; the tab never receives it).
   Rollback: step 4's runtime.json restore, taken after closing the fresh session.

## Rollback target

`5aa30969241163b4abb3e025bc9e52123ee4b478` — restoring the pre-br4 runtime.json
returns every dispatch to it because that release directory is left untouched.
Lane BR wrote nothing under `~/.local/share/mastermind-browser-control` or
`~/.t3/mcp`; every step above is the principal's.

## Operator call: paged whole-answer read

Tool name: `mmx_browser` (T3 surface: `mcp__mmx-browser__mmx_browser`).

First call (after `snapshot` gives `snapshot_id` and the element `ref` of the
answer container):

```json
{"action":"read","browser_id":"<browsers>","connection_id":"<status>",
 "tab_id":0,"url_fingerprint":"<tabs>","snapshot_id":"<snapshot>","ref":"<element ref>","offset":0}
```

Loop: while the reply's `next_offset` is not null, repeat the same call with
`offset` set to that `next_offset`; keep every other argument identical. The
reply carries `content` (always untrusted text), `total_characters`,
`next_offset` (null at the end) and `content_is_untrusted: true`. Reads never
consume the snapshot, mutate, scroll or focus — the same observation still
authorizes a later mutation. Offsets that are negative, non-integer, past the
end, or inside a surrogate pair return `READ_OFFSET_INVALID`; a wrong argument
shape returns `INPUT_REFUSED`.

Read-contract limits, in plain sentences:

- There is no drift guard across pages: a page that changes during a paged
  read can skip or repeat text.
- Repeated blank lines can hide a dropped empty line.
- For fills, read the box before sending: a fill's `APPLIED` means the box
  held the asked content at the re-read after the page's pending microtasks
  plus one settle interval (250 ms in this build) — a page that changes the
  box later is outside the receipt.
- `settle_interval_ms` is a floor, not a ceiling: hidden tabs throttle
  timers, so a fill in a hidden tab settles later than 250 ms — do not
  timeout-and-retry a fill that may have applied.
