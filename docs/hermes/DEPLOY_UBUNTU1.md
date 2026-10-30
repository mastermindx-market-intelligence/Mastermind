# Hermes harness on ubuntu1

ubuntu1 is the preferred host for the headless Secretary and Meta-CEO harness.
This document is the install procedure. It does not start a live Slack seat,
admit a child, or replace Grok Secretary. DeepSeek Harness stays the donor
and fallback.

Pin: `NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`.
Entry point: `integrations/hermes_harness/hermesctl`.

Run `hermesctl doctor` before install. Exit 2 means something in the list
below is still missing. The command prints names only.

## Layout

All of these files are mode `0600`, owned by the operator user, regular files,
not symlinks, and not hard links. None of them are committed.

| Pointer | Path |
| --- | --- |
| Secretary gateway and dashboard | `~/.config/hermes-runtime/mmsecretary.secrets.env` |
| Meta-CEO gateway and dashboard | `~/.config/hermes-runtime/mmmeta.secrets.env` |
| Z.AI GLM-5.3 | `~/.config/hermes-runtime/credentials/zai.key` |
| ModelArk GLM-5.3-Flash and DeepSeek Flash | `~/.config/hermes-runtime/credentials/modelark.key` |
| MiniMax-M3 | `~/.config/hermes-runtime/credentials/minimax.key` |
| Cursor pool | `~/.config/hermes-runtime/credentials/cursor.key` |
| Secretary state | `~/.local/state/hermes-runtime-mmsecretary` |
| Meta-CEO state | `~/.local/state/hermes-runtime-mmmeta` |
| User unit directory | `~/.config/systemd/user` |

A credential file is one line, the token, or one JSON object `{"api_key":"..."}`.
The gateway file is `KEY=value` lines and must include `HERMES_GATEWAY_TOKEN`
(at least 16 characters, not a placeholder). Optional lines
`HERMES_DASHBOARD_BASIC_AUTH_USERNAME` and
`HERMES_DASHBOARD_BASIC_AUTH_PASSWORD`. When the password line is omitted,
the runtime uses the gateway token as that password and still keeps it off
argv.

Provider env pointers, set in the operator environment, not in the unit file:

```
ZAI_API_KEY_FILE=$HOME/.config/hermes-runtime/credentials/zai.key
BYTEPLUS_MODELARK_API_KEY_FILE=$HOME/.config/hermes-runtime/credentials/modelark.key
MINIMAX_TOKEN_PLAN_KEY_FILE=$HOME/.config/hermes-runtime/credentials/minimax.key
CURSOR_API_KEY_FILE=$HOME/.config/hermes-runtime/credentials/cursor.key
HERMES_CURSOR_POOL_BASE_URL=https://<operator-supplied-cursor-pool>
MASTERMIND_STEWARD_MCP_URL=https://<operator-supplied-steward>
MASTERMIND_STEWARD_ACCESS_TOKEN_FILE=$HOME/.config/hermes-runtime/credentials/steward.token
```

`HERMES_CURSOR_POOL_BASE_URL` is not a secret. Until it is set, the Cursor
pool stays on the disabled placeholder `https://cursor-pool.invalid/v1` and
is last in every chain. Personal Coding Plan `/api/coding` URLs are refused.

A set `*_FILE` pointer is the only source for that provider. A missing or
mode-wrong file does not fall back to the matching env var.

Each always-on Hermes agent has its own systemd user unit and its own 0600
secrets file. The Slack bot identity is per unit, not shared with Grok Secretary.

| Agent | User unit | Secrets file |
| --- | --- | --- |
| `hermes-secretary` | `hermes-runtime-mmsecretary.service` | `~/.config/hermes-runtime/mmsecretary.secrets.env` |
| `hermes-metaceo` | `hermes-runtime-mmmeta.service` | `~/.config/hermes-runtime/mmmeta.secrets.env` |

Add these lines to each secrets file, with that agent's own values. Do not
copy one agent's bot onto the other unit, and do not use Grok Secretary's id
`U0BTCHX8HMF` as either self:

```
HERMES_SLACK_BOT_USER_ID=U<this-agents-bot-user-id>
HERMES_SLACK_BOT_TOKEN=<this-agents-bot-token>
```

`self` is only that unit's `HERMES_SLACK_BOT_USER_ID`. Sibling Hermes ids live
in `roster.json` under `sibling_hermes_agent_ids` and are not a self loop.
Each user unit has `EnvironmentFile=` set to that unit's 0600 secrets file, so
systemd loads `HERMES_SLACK_BOT_USER_ID` into the unit process. The unit text
contains the path, not the secret bytes. The Hermes child receives that user
id and does not receive `HERMES_SLACK_BOT_TOKEN` or `HERMES_GATEWAY_TOKEN`.

The harness refuses to leave shadow mode when `HERMES_SLACK_BOT_USER_ID` is
unset or malformed (`SHADOW_ID_REQUIRED`). Shadow mode remains the default
and still posts nothing.

Chairman Chris is `U0BRET6191C` (`chris@mastermind-x.com`). Grok Secretary
`U0BTCHX8HMF` (`groksecretary@mastermind-x.com`) is a permanent peer. Hermes
reads Grok's posts, can take assignments and receipts from Grok, and may
address Grok in a pre-authorized thread.

Ids and credentials doctor still reports until they are provided:

- `id:hermes-secretary:HERMES_SLACK_BOT_USER_ID` and `credential:hermes-secretary:HERMES_SLACK_BOT_TOKEN`
- `id:hermes-metaceo:HERMES_SLACK_BOT_USER_ID` and `credential:hermes-metaceo:HERMES_SLACK_BOT_TOKEN`
- Dot bot user ids are unknown.
- m2studio computer-use machine `61f4e9d7-b202-4cda-85ed-36904689931e` has no Mac TCC grant.
- Executive admission is not bound. `mmx_delegate` returns `EXECUTIVE_ADMISSION_NOT_BOUND`.
- Fabric live submit stays off.
- A pinned upstream checkout is attested only after `install --fetch` writes `upstream_attested: true`.

## Install

From the repo root, as the operator user on ubuntu1:

```sh
umask 077
mkdir -p "$HOME/.config/hermes-runtime/credentials" \
  "$HOME/.local/state" \
  "$HOME/.config/systemd/user"
# Create the 0600 files above out of band. Do not echo tokens into the shell history.

python3 integrations/hermes_harness/hermesctl doctor

# HERMES_BIN is the already-built hermes executable from the ubuntu1
# pinned checkout. This procedure does not choose that path for you.
python3 integrations/hermes_harness/hermesctl install \
  --role mmsecretary \
  --state "$HOME/.local/state/hermes-runtime-mmsecretary" \
  --systemd-user-dir "$HOME/.config/systemd/user" \
  --secrets-file "$HOME/.config/hermes-runtime/mmsecretary.secrets.env" \
  --hermes-bin "$HERMES_BIN" \
  --fetch

python3 integrations/hermes_harness/hermesctl install \
  --role mmmeta \
  --state "$HOME/.local/state/hermes-runtime-mmmeta" \
  --systemd-user-dir "$HOME/.config/systemd/user" \
  --secrets-file "$HOME/.config/hermes-runtime/mmmeta.secrets.env" \
  --hermes-bin "$HERMES_BIN" \
  --upstream-source "$HOME/.local/state/hermes-runtime-mmsecretary/current/upstream"
```

`--fetch` is the only network step. It refuses every revision except the pin.
The second install copies that attested tree and does not fetch again.
`--upstream-source` records `upstream_attested: false` unless the bytes came
from `--fetch`.

`install` writes:

- `hermes-runtime-mmsecretary.service` and `hermes-runtime-mmmeta.service` in the user unit directory
- a `default.target.wants` symlink for each
- loopback ports `127.0.0.1:8765` (Secretary) and `127.0.0.1:8865` (Meta-CEO)
- `RestrictAddressFamilies=AF_UNIX AF_INET`, `IPAddressDeny=any`, `IPAddressAllow=localhost`
- `EnvironmentFile=` pointing at that unit's 0600 secrets file, and no secret bytes in the unit
- provider overlay `provider-overlay.yaml` and `vision-overlay.yaml` under the role's `hermes-home`

Model order in those overlays:

- `mmsecretary`: ModelArk GLM-5.3-Flash, then ModelArk DeepSeek Flash, then Cursor
- `mmmeta`: Z.AI GLM-5.3, then Cursor
- vision: MiniMax-M3, then Cursor

**Native BYOK configuration (source stage; not an active provider):**
`hermesctl install` now materializes the reviewed WP2 **primary text-model**
into the actual native `profiles/<role>/config.yaml`, rather than only writing
a disconnected `provider-overlay.yaml` for inspection. Secretary selects the
commercial ModelArk `byteplus-modelark` GLM-5.3-Flash model; Meta-CEO selects
the named `zai-glm` GLM-5.3 model. The exact approved provider registry uses
`key_env` references without embedding credentials. The pinned donor supports
the `providers:` named-custom shape
(`website/docs/integrations/providers.md` at
`NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`).

The fresh Hermes supervisor now has a **source-implemented**, role-scoped
credential path: the existing WP2 credential reader accepts only the reviewed
primary role's key from the existing 0600 secret file (or the existing
mode-0600 file-pointer contract) and exposes that key **only** to the native
model-serving child, not the CLI tool-registry preflight. Missing/unsafe
credentials fail closed. It does not copy another role's provider key,
gateway credential, Slack bot token, or ambient parent environment.
**Additional credential separation is mandatory before model-child launch:**
the host operator must provision a *distinct*
`HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` rather than accepting the older
`load_secrets` default that aliases it to `HERMES_GATEWAY_TOKEN`. The
model provider key must also differ from both the dashboard password and
gateway token. The BYOK child will refuse either alias; it never selects a
replacement secret automatically. Actual values must be provisioned and
rotated by the pre-existing credential owner, never recorded in GitHub or
tool logs.

This has passed offline tests with synthetic fixture values only. No real
provider credential was read, no model request executed, and no receiving
owner has accepted authenticated inference or metering. The model's source
configuration and restricted child-env transport are **BUILT_NOT_PROVEN**,
not a ready service or automatic right to spend tokens. Executive admission
and app computer-use rights are unaffected. No Hermes automatic
fallback is installed: Cursor remains disabled and provider/model retries
remain with the existing provider/capacity owner. The `auxiliary.vision`
stanza is intentionally excluded from this native output until mini1
computer-use authority is accepted. The existing separate vision-overlay
file is not a running vision route.

Hermes built-in toolsets `delegation` and `skills` stay disabled.
**The installed runnable profile now admits only the native `clarify` toolset.**
Six Steward reads remain declared in a **disabled** MCP server. `mmx_delegate`
and the three Secretary skill names exist only in non-authoritative Python
shadow-mode declarations: they are **not** Hermes-native, executable tools and
do not appear in the installed profile's allowlist. This is intentional until
actual native plugin registration and receiving-owner admission are proven.

**Native registration gate (unarmed):** The Hermes role's installed
`hermes-home/profiles/<role>/config.yaml` now contains the exact upstream
`mcp_servers.mastermind_steward` definition from the reviewed read-only WP3
source. It has `enabled: false` in **every default install**, including when
credential pointers exist. Its six `tools.include` names are exact; MCP
resources and prompts remain disabled. This is only native configuration
presence, not an authenticated connection or an actual callable tool.

The Python `boot_harness()` registration table names intended extensions
but is **not** a Hermes-native plugin or actual model-callable tool registry.
The installed systemd supervisor is a fresh process and does not carry that
table from the installer. Actual native Steward enablement, plugin
installation for `mmx_delegate`, live tool discovery, Executive admission
and original-parent result consumption all remain blocked until their
receiving-owner evidence and independent review exist. Do not remove the
`enabled: false` fence to make a model start or call a tool. No
`hermesctl install` receipt or local health response can prove those grants.

Enable each user unit on its own. One unit does not start the other.
This still does not post to Slack:

```sh
systemctl --user daemon-reload
systemctl --user enable --now hermes-runtime-mmsecretary.service
systemctl --user enable --now hermes-runtime-mmmeta.service
systemctl --user status hermes-runtime-mmsecretary.service hermes-runtime-mmmeta.service
python3 integrations/hermes_harness/hermesctl status \
  --state "$HOME/.local/state/hermes-runtime-mmsecretary"
python3 - <<'PY'
from pathlib import Path
import urllib.request
text = Path.home().joinpath(".config/hermes-runtime/mmsecretary.secrets.env").read_text()
token = next(
    line.split("=", 1)[1].strip()
    for line in text.splitlines()
    if line.startswith("HERMES_GATEWAY_TOKEN=")
)
request = urllib.request.Request("http://127.0.0.1:8765/api/health")
request.add_header("Authorization", f"Bearer {token}")
with urllib.request.urlopen(request, timeout=5) as response:
    print(response.status)
PY
```

Expect `200` from health. The token stays in the Python process and is not
printed. Unauthenticated health is `401`.

## 24 hour shadow

**Canonical Wake/continuity boundary:** The Hermes Secretary's
`wake_bridge` now accepts only a typed `AgentDialogueAttention` object
projected through the **existing**
`integrations.slack_agent_dialogue.turn_wake_adapter`. A Slack message field
named `canonical_source_ref`, a plausible 64-hex digest, a bot assertion,
a timer tick, or a chat text instruction cannot originate a Wake obligation.
The typed adapter preserves original root-job, source-workstream and target
seat, refusing target-seat mismatch. Even a `MINTED` result is **only an
in-memory shadow annotation**: current-source verification, canonical Wake
ledger persistence, transport dispatch, ACK, original-parent worker result
consumption and clearing a task remain with their existing Executive,
Agent Dialogue, Wake and Agent OS owners. No Hermes-owned task queue,
memory database, scheduler or new watcher has been created.

Do not install the Hermes cron catalog. `install_into_hermes_home()` refuses,
and every job in `integrations/hermes_secretary/routines/jobs.json` stays
`enabled: false`. The merged catalog sets `m2studio-browser-tab-sweep` to
`40 2-23/3 * * *` on `America/Cancun`, which is Vancouver `40 */3` under
tzdata 2026e (UTC-7, no later fallback). Shadow-run does not install that cron.

For 24 hours, replay recorded Slack history. `shadow-run` reads a JSON
fixture and writes local JSONL. It does not call Slack.

```sh
OUT="$HOME/.local/state/hermes-runtime-mmsecretary/shadow/would-decisions.jsonl"
mkdir -p "$(dirname "$OUT")"
python3 integrations/hermes_harness/hermesctl shadow-run \
  --mode ping_scan \
  --fixture /path/to/recorded-slack-history.json \
  --output "$OUT"
```

Repeat on the Secretary ping cadence (minute 12 and minute 42, America/Cancun)
for 24 hours, using a new output file per pass or accepting that a second
pass over the same fixture dedups to an empty tick. Placement rows call
`mmx_delegate` and must come back `REFUSED` / `EXECUTIVE_ADMISSION_NOT_BOUND`
with `live_submit` false and `admitted` false. `would_post` is false on
every row.

At the end of the window, compare with Grok Secretary's posts. Posts are a
JSON list of `{channel, ts, thread_ts, text}` already read by an operator.
This command does not fetch them:

```sh
python3 integrations/hermes_harness/hermesctl parity-check \
  --decisions "$OUT" \
  --posts /path/to/secretary-posts.json \
  --start '1761410000.000000' \
  --end '1761496400.000000'
```

Parity is acceptable for a shadow only when all of these hold:

- every decision has `would_post: false`
- `admitted` is 0 and no row has `live_submit: true`
- secret-shaped inbound text is withheld or redacted, not copied
- `matched` covers the secretary posts that share a thread and a kind marker
- `shadow_only`, `secretary_only`, and `mismatched_kind` are empty or written down as known residuals
- the Slack client methods observed by the harness are only `conversations_history` and `conversations_replies`
- doctor still reports `grant:executive_admission` and `grant:fabric_live_submit`

A passing shadow is not a cutover. Grok Secretary keeps the live seat.

## Rollback

Stop the user services first. Uninstall removes the state directory and the
user unit. It leaves the 0600 secrets files in place.

```sh
systemctl --user disable --now hermes-runtime-mmsecretary.service || true
systemctl --user disable --now hermes-runtime-mmmeta.service || true
systemctl --user daemon-reload

python3 integrations/hermes_harness/hermesctl uninstall \
  --state "$HOME/.local/state/hermes-runtime-mmsecretary" \
  --systemd-user-dir "$HOME/.config/systemd/user"

python3 integrations/hermes_harness/hermesctl uninstall \
  --state "$HOME/.local/state/hermes-runtime-mmmeta" \
  --systemd-user-dir "$HOME/.config/systemd/user"
```

A second uninstall prints `ABSENT`. To keep the tree and undo one bad
release instead, use the runtime rollback on that state directory:

```sh
python3 -m integrations.hermes_runtime rollback \
  --state "$HOME/.local/state/hermes-runtime-mmsecretary"
```

Rollback only exists after a second install. It points `current` at the
previous release and does not delete secrets. Grok Secretary is not stopped
by any of these commands.
