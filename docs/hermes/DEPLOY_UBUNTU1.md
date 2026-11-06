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

**Native BYOK credential enrollment:** the supervisor reads provider-key names and
`*_FILE` pointers from each role's private `mmsecretary.secrets.env` or
`mmmeta.secrets.env` through the existing `load_secrets` owner. It does **not**
read the operator's interactive shell environment for primary model keys. Never
place real model keys directly in a systemd unit, on argv or in GitHub.

In the Secretary's existing mode-0600 secrets file, alongside its distinct
gateway/dashboard and own Slack bot credentials, add only:

```text
BYTEPLUS_MODELARK_API_KEY_FILE=/home/YOUR_OS_USERNAME/.config/hermes-runtime/credentials/modelark.key
```

In the Meta-CEO's separate mode-0600 secrets file, add only:

```text
ZAI_API_KEY_FILE=/home/YOUR_OS_USERNAME/.config/hermes-runtime/credentials/zai.key
```

Replace `YOUR_OS_USERNAME` with the actual runtime user. These are **literal,
absolute paths**, not shell expressions. Do not write `$HOME`, `~` or a
relative path in a secrets-file value: the native secret reader does not expand
them. The referenced key file must be regular, owned by the runtime user, mode
0600, and not a symlink or hard link. A set `*_FILE` pointer is authoritative;
empty, inaccessible or unsafe pointers fail closed rather than falling back
to an inline key. Only the role's selected primary credential reaches its
native model child; its sibling's provider credential is not forwarded.

## Native HTTPS egress — mandatory, not automatically provisioned

Native BYOK requires a role-private, canonical HTTPS CONNECT proxy.
Only the **PID1-managed** root-owned system units are eligible to serve
on Ubuntu1. They keep `IPAddressDeny=any` and
`RestrictAddressFamilies=AF_UNIX AF_INET` and allow **only** the assigned
role IP: 127.0.0.2/32 (Secretary) or 127.0.0.3/32 (Meta-CEO).
The runtime gateway and pinned Hermes backend also bind that role IP.
Never add shared 127.0.0.1/32, blanket localhost, public egress,
arbitrary proxy hosts, inherited shell proxy or cross-role credentials.
Legacy generated systemd --user units are inert staging artifacts and
their startup is rejected by the production supervisor on Ubuntu1.

The **existing private 0600 Secretary** file additionally needs these
operator-provisioned settings (port shown as an example only):

```text
HERMES_NATIVE_EGRESS_ROLE=mmsecretary
HERMES_NATIVE_HTTPS_PROXY=http://127.0.0.2:18651
```

The **separate private 0600 Meta-CEO** file needs its own intended role and
a different proxy endpoint (example port only):

```text
HERMES_NATIVE_EGRESS_ROLE=mmmeta
HERMES_NATIVE_HTTPS_PROXY=http://127.0.0.3:18652
```

`integrations.hermes_runtime.egress.native_egress_child_env` validates these
two fields from that role's private secrets, never the interactive shell, and
passes only `HTTPS_PROXY` plus a fixed localhost `NO_PROXY` to the native
model child. Empty, external, noncanonical, URL-credentialed, privileged-port,
wrong-role and unqualified settings refuse before the child starts. ModelArk
and Z.AI keys remain independently loaded from the previously reviewed
credential pointers; neither key is forwarded to the proxy by this module.

**Pinned donor source-level proxy contract:** at
`NousResearch/hermes-agent@1c0cd667746d3395fe9e1b6c74f8f85952486f18`,
`agent/process_bootstrap.py::_get_proxy_from_env` selects `HTTPS_PROXY`
ahead of `HTTP_PROXY` and `ALL_PROXY`. `build_keepalive_http_client`
passes the selected value to the OpenAI-wire `httpx.Client(proxy=...,
verify=...)`, and `agent/agent_runtime_helpers.py` creates primary
OpenAI-compatible model clients through that helper. This confirms the
**intended source transport** honors the injected proxy, rather than relying
on ambient shell proxy discovery; it still does not prove the installed
binary, proxy listener, hostname allowlist, TLS peer or remote inference.

**Critical cross-role isolation:** `IPAddressAllow=localhost` was
originally broad (`127.0.0.0/8` and `::1/128`) and allowed either role
to connect to a sibling proxy on a different localhost port. The updated
root-managed unit now permits only **its own** 127.0.0.2/32 or
127.0.0.3/32 IP for all local role services (gateway, backend, proxy).
A 127.0.0.1/32 grant allows **every port** on that address, including
unrelated host listeners, so it is forbidden for either root unit.
The proxy must actually bind the selected role IP (not 0.0.0.0 or 127.0.0.1),
and the host must prove that effective parent/system/user slice rules do
not add a broader localhost allowance.

systemd notes that cgroup eBPF-based `IPAddressAllow/Deny` can be silently
ineffective on unsupported kernels, delegation layouts or container
managers. `systemd --user` unit text, local `/api/health` 200 and
`systemctl show` values are **not enforcement proof**. Before using either
provider credential, separately test **from each actual running unit cgroup**:
own proxy permitted, sibling proxy forbidden, unauthorized 127/8
destination forbidden, direct public 443 forbidden, and only the intended
host:443 CONNECT allowed by the operator-owned proxy. Test both
directions, including negative results, and retain the host-bound receipts.
Without proven enforcement, STOP production qualification; do not assume
that different IP aliases by themselves provide isolation.

**The proxy process is not created, installed or certified by this repository.**
A currently authorized host network owner must separately provide and
validate an existing compatible role-specific loopback HTTP CONNECT proxy
that enforces the Secretary's exact commercial ModelArk destination
`ark.ap-southeast.bytepluses.com:443` and the Meta-CEO's exact Z.AI
destination `api.z.ai:443`, with TLS validation by the native model
client. Deny all other destinations, including unrestricted tunneling; never
use the proxy as a backdoor for Slack, general browsing, Fabric, or a second
authority plane. It must not be accessible across role boundaries without
the required host-side policy. Verify the installed Linux systemd cgroup
actually enforces the network rules and the pinned native HTTP client honors
the explicit HTTPS proxy. These are real-host canaries, not source-test claims.

`hermesctl doctor` reports missing per-role proxy setup under
`network_proxy:mmsecretary` / `network_proxy:mmmeta`, refuses shared
bot/gateway/proxy identity and incumbent Grok Secretary bot-ID reuse as core
readiness, and returns `core_text_status=CONFIG_READY_NOT_LIVE_PROVEN`
only when its core configuration prerequisites are satisfied. It continues
reporting optional Mac computer-use, future Fabric/Steward and Dot-account gaps
independently; its overall status/exit behavior remains fail-closed.

To qualify **only the two core text-bot configuration prerequisites** without
requiring unrelated Mac/Fabric/vision features, use:

```sh
python3 integrations/hermes_harness/hermesctl doctor --core-text-config-only --json
```

This explicitly scoped command exits zero only for `CONFIG_READY_NOT_LIVE_PROVEN`.
The JSON still says `status: MISSING` when future/optional capabilities are
missing; it does not permit Slack send, model inference, Executive admission,
host deployment, arbitrary traffic or proxy installation. Unscoped
`hermesctl doctor` keeps the previous conservative full-readiness exit status.
No doctor, local HTTP 200, proxy URL or selected model constitutes a live
authenticated inference receipt.

For actual acceptance, obtain authenticated pinned Hermes structured
one-shot output through `chat -Q --query-file - --format stream-json` inside
the approved service/network confinement, validate it using
`integrations.hermes_harness.native_turn_evidence` from the companion
stacked PR, prove remote TLS/provider usage and blocked destinations,
then observe an authorized exact-parent thread reply from each distinct
role bot through the existing Agent Dialogue owner. Keep the incumbent Grok
Secretary operating until independent review, protected release and rollback
proof are complete.

MiniMax, Cursor pool and Steward MCP credentials and endpoints remain separate
future qualification routes. Their optional pointer names include
`MINIMAX_TOKEN_PLAN_KEY_FILE`, `CURSOR_API_KEY_FILE` and
`MASTERMIND_STEWARD_ACCESS_TOKEN_FILE`; none grants an active auxiliary,
automatic fallback, enabled Steward MCP or computer-use tool. The disabled
Cursor endpoint defaults to `https://cursor-pool.invalid/v1`. Personal
Coding Plan `/api/coding` provider URLs are refused.

Each role has a separate **root-managed system unit running as a
distinct non-root account/group**, named mmsecretary or mmmeta, with
unequal numeric UIDs/GIDs, private 0700 state/secret directories, and its
own mode-0600 secrets file. Shared longr/operator ownership is refused. The old user
units are generated only into an inert staging directory; do not
enable/start them. Slack bot identities are role-private and not
shared with Grok Secretary.

| Agent | Root-managed system unit | Secrets file |
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
Production root units have no `EnvironmentFile=`. After cgroup, OS-identity,
private-path and Landlock checks, the CLI alone loads the existing private
secret file. The native child receives its own Slack user id, never the
Slack bot token or gateway token. Inert legacy user units are not launchable
production services and must never be activated.

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

## Explicit native BYOK model selection

List the choices already present in the reviewed role catalog without opening
any credential or calling a provider:

```sh
python3 integrations/hermes_harness/hermesctl models --role mmsecretary
python3 integrations/hermes_harness/hermesctl models --role mmmeta
```

Secretary can select `byteplus-modelark.glm-5.3-flash` (the existing default)
or `byteplus-modelark.deepseek-v4.1-flash`. Meta-CEO currently selects
`zai.glm-5.3`. This is a source-qualified configuration list, not proof of
live provider availability or permission to spend. Adding another provider
requires its existing role/catalog qualification; an arbitrary model name,
custom URL, cross-role model or disabled Cursor route is refused.

Pass one explicit `--model-provider <provider-id>` to the existing `install`
command below. The choice is persisted in the role's existing `profile.yaml`
and consumed by its native config, matching provider overlay, scoped key
loader and install/status receipts. No separate preference database, provider
router, fallback chain or secret store is introduced. `status` distinguishes
`requested_model` from `served_model_verified: false`.

An upgrade with no `--model-provider` preserves the installed selection. A
corrupt, missing or wrong-role previous profile fails closed rather than
resetting the model. This is an installation-time setting, **not hot
switching**: do not change an occupied role or unresolved turn. A model or
account change never replays an earlier denied, rate-limited or uncertain
operation. Existing source review, credential enrollment and runtime gates
still control first launch. The installed systemd network policy remains
loopback-only and is not relaxed by selecting a model.

The doctor now checks the selected provider and actual private credential
file referenced by an installed role profile, rather than treating an
operator shell key or a different role's config as native readiness.

## Role configuration metadata read

Read one role's installed configuration without opening a credential, calling
a provider, observing a running service or attesting the host:

```sh
python3 integrations/hermes_harness/hermesctl role-metadata \
  --state "$HOME/.local/state/hermes-runtime-mmsecretary" --role mmsecretary
python3 integrations/hermes_harness/hermesctl role-metadata \
  --state "$HOME/.local/state/hermes-runtime-mmmeta" --role mmmeta
```

The projection is `mastermind.hermes.role_metadata.v1`. `state` is
`CONFIGURATION_OBSERVED` when the installed manifest, current release
receipt and role profile agree, `ABSENT` when the selected role root is
readable and qualified, the incumbent install manifest is genuinely absent
and no surviving install evidence is left in the root, and `UNAVAILABLE` with
one fixed `reason` code otherwise. A root that still has a current-release
link or a written release but no manifest is a damaged installation, not an
absent role, and reports `MANIFEST_MISSING`. `ABSENT`
never means the credential is absent, and it never says anything about a
role on another host: a reader without a trusted binding to this host has no
observation at all, and the `source_binding` field stays `NOT_ATTESTED`.

`requested` carries the provider and model identifiers derived from the
existing role catalog; `provenance` carries the upstream SHA, the release id
and the manifest/profile/config digests. No credential name, credential
digest, credential value, private path or raw error text is ever returned.
The `proof` block always reports `credentials_read: false`,
`provider_called: false`, `service_observed: false`,
`served_model_verified: false` and `credential_enrollment: "UNVERIFIED"`.
Run each command under the role's own login and point `--state` at that
role's own state directory.

`hermesctl status` is the incumbent operator summary and is deliberately
lenient about a damaged installation: it keeps reporting `INSTALLED` for a
root whose profile drifted or whose manifest was replaced by a symlink. A
consumer that must not report a damaged install as healthy reads
`role-metadata` instead, which returns `UNAVAILABLE` for those states. The
two commands answer the same question differently on purpose; the difference
is pinned by a test so neither can drift into the other unnoticed.

## Install

From the approved readable repo root on ubuntu1, run the Secretary block
under the separately provisioned mmsecretary login and the Meta-CEO block
under mmmeta. Each has its OWN HOME, private files and pinned executable.
Never execute both blocks under one operator/shared account. Account
provisioning is a separate authorized host-owner action, not this installer.
See ROLE_ISOLATION_REPAIR.md; unsupported Landlock or failed numeric-ID
isolation blocks service startup before keys are loaded.

Secretary (mmsecretary account):

```sh
umask 077
mkdir -p "$HOME/.config/hermes-runtime/credentials" \
  "$HOME/.local/state" \
  "$HOME/.local/share/hermes-stage/systemd/user"
# This directory must be inert, unsymlinked, and outside active systemd user search.
# Never use $HOME/.config/systemd/user for this staging-only installer.
# Create the 0600 files above out of band. Do not echo tokens into the shell history.

# Global doctor is not cross-UID credential proof. Inspect each installed
# role with status --state under its own login; the actual CLI gates qualify it.

# HERMES_BIN is the already-built hermes executable from the ubuntu1
# pinned checkout. This procedure does not choose that path for you.
python3 integrations/hermes_harness/hermesctl install \
  --role mmsecretary \
  --state "$HOME/.local/state/hermes-runtime-mmsecretary" \
  --systemd-user-dir "$HOME/.local/share/hermes-stage/systemd/user" \
  --secrets-file "$HOME/.config/hermes-runtime/mmsecretary.secrets.env" \
  --hermes-bin "$HERMES_BIN" \
  --fetch
```

Meta-CEO (mmmeta account, a DIFFERENT HOME and credential owner):

```sh
umask 077
mkdir -p "$HOME/.config/hermes-runtime/credentials" \
  "$HOME/.local/state" \
  "$HOME/.local/share/hermes-stage/systemd/user"
# Provision this account's separate 0600 files and HERMES_BIN out of band.
python3 integrations/hermes_harness/hermesctl install \
  --role mmmeta \
  --state "$HOME/.local/state/hermes-runtime-mmmeta" \
  --systemd-user-dir "$HOME/.local/share/hermes-stage/systemd/user" \
  --secrets-file "$HOME/.config/hermes-runtime/mmmeta.secrets.env" \
  --hermes-bin "$HERMES_BIN" \
  --fetch
```

`--fetch` is the only network step. It refuses every revision except the pin.
Each role independently fetches the exact pinned upstream source and must
have its **own** `upstream_attested: true` install receipt before the operator
canary is eligible. Reusing the first role's checkout through
`--upstream-source` produces `upstream_attested: false` and therefore
blocks the second role's canary; never paper over that attestation gate.
All installs are operator-authorized postrelease actions, not CI steps.

`install` writes:

- legacy **user** unit artifacts only in the inert, isolated staging directory
- legacy `default.target.wants` symlinks **inside that inert directory**,
  never in an active user-manager search path; do not enable/start those units
- the root operator separately renders/reviews/installs the PID1-managed
  system units from `ROOT_CONFINED_SYSTEM_UNIT.md` after acceptance gates
- role-local gateway ports `127.0.0.2:8765` (Secretary) and `127.0.0.3:8865` (Meta-CEO); never activate staged user units
- `RestrictAddressFamilies=AF_UNIX AF_INET`, `IPAddressDeny=any`, only\n  role-specific host-prefix `IPAddressAllow` rules (no blanket `localhost` 127/8)
- legacy staged units may name an EnvironmentFile, but production root units
  do NOT preload it; the CLI reads private credentials only after isolation
- mandatory inherited Linux Landlock TCP bind/connect policy in production,
  using fixed role gateway/backend ports and exact proxy port 18651 or 18652
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
gateway token. The agent's own `HERMES_SLACK_BOT_TOKEN` must also differ
from the gateway token, dashboard password and primary model key: reusing a
Slack bearer here could expose it to the model child under a different
credential name. The BYOK child refuses each alias before process spawn;
it never selects a replacement secret automatically. Never copy or reuse
the incumbent Grok Secretary bot token. Actual values must be provisioned and
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

**Only after** the normal protected release, independent review, root
operator approval, installed one-Squid proxy and a proven fail-closed
PID1 cgroup firewall, enable each **system** unit separately. Never
enable a user-manager Hermes unit; this still does not post to Slack:

```sh
sudo systemctl daemon-reload
# Requires independently approved root-owned unit files and host network tests.
sudo systemctl enable --now hermes-runtime-mmsecretary.service
# Only after Secretary isolation passes; a separate controlled cutover.
sudo systemctl enable --now hermes-runtime-mmmeta.service
sudo systemctl status hermes-runtime-mmsecretary.service hermes-runtime-mmmeta.service
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
request = urllib.request.Request("http://127.0.0.2:8765/api/health")
request.add_header("Authorization", f"Bearer {token}")
with urllib.request.urlopen(request, timeout=5) as response:
    print(response.status)
PY
```

Expect `200` from health **only after** the pinned child process is
running and its separate `127.0.0.2` backend responds to `GET /api/health`
with HTTP `200`, a JSON object containing `"ok": true`, and a `commit`
exactly equal to the protected Hermes donor pin
`1c0cd667746d3395fe9e1b6c74f8f85952486f18`. This is the pinned
donor's published lightweight health identity contract in
`hermes_cli/web_routers/status.py` (the public route is listed in
`hermes_cli/dashboard_auth/public_paths.py`). A live PID with an absent,
nonresponsive, wrong-version, unstamped, malformed, oversized, or non-200
backend reports `503` / `starting` (`backend_ready: false`), not a healthy
agent; a crash-loop is `503` / `failed`. If this stays at 503, check that
the **actual executable** invoked by the systemd unit carries the pinned
donor provenance; copying a pinned source tree alongside a different binary
does not make that binary trusted. Do not relax the check to accept any HTTP 200.
The probe is loopback-only, credential-free, capped at 4 KiB and configured
with a 250ms socket timeout. Matching a public SHA is a provenance
cross-check, **not cryptographic attestation of the port owner**, nor proof
of a model completion, company tools, Executive admission, Slack delivery
or long-running acceptance.
The gateway token stays in the Python process and is not printed. Unauthenticated
health is `401`.

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

Stop approved root-owned **system** services first. Uninstall affects
legacy staged user-unit artifacts and installed runtime state, not the
root-owned service files: the root operator must separately remove those
after verifying their original identities. Keep 0600 secrets private.

```sh
sudo systemctl disable --now hermes-runtime-mmsecretary.service || true
sudo systemctl disable --now hermes-runtime-mmmeta.service || true
# Legacy user-manager units, only if installed; never restart them.
systemctl --user disable --now hermes-runtime-mmsecretary.service || true
systemctl --user disable --now hermes-runtime-mmmeta.service || true
systemctl --user daemon-reload

python3 integrations/hermes_harness/hermesctl uninstall \
  --state "$HOME/.local/state/hermes-runtime-mmsecretary" \
  --systemd-user-dir "$HOME/.local/share/hermes-stage/systemd/user"

python3 integrations/hermes_harness/hermesctl uninstall \
  --state "$HOME/.local/state/hermes-runtime-mmmeta" \
  --systemd-user-dir "$HOME/.local/share/hermes-stage/systemd/user"
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

## Own-alias TCP and numeric-identity release checks

ROLE_ISOLATION_REPAIR.md supersedes all prior shared-UID examples. Require
distinct actual mmsecretary/mmmeta UIDs/GIDs, private directories, no extra
shared supplementary group, no preloaded EnvironmentFile, and actual
Landlock ABI >= 4 attachment before runtime secret loading. Network guards
reject ephemeral/colliding ports or a proxy port other than 18651/18652.
From each final service prove an unrelated wildcard TCP listener is denied
through the role's OWN alias, and synthetic sibling-file reads are denied.
A skipped Linux test or source-only mock is not host proof. TCP restrictions
do not claim UDP/Unix IPC containment, TLS, billing, or Slack acceptance.


## Isolated runtime source entry

The root-managed unit selects
`/opt/mastermind-executive/releases/<40-character-commit>/ops/executive_os/release_manifest.py`
with CPython 3.12 and `-I -S -B`. The fixed `hermes-runtime` entry admits the
existing `supervise` and separately authorized `canary` commands. The renderer
refuses other release-root shapes and a supplied implementation label that
differs from the selected release directory.

Before importing Hermes, the existing release owner holds the physical source
ancestry, manifest and imported files. It refuses writable or non-root-owned
objects, links, ACLs, changed descriptors, unlisted imports and changed source
bytes. It compiles manifest-matched source snapshots and uses the existing
pinned pure PyYAML closure. It adds no repository or site-package import path.
The held context stays with the existing CLI process; there is no second
supervisor, lifecycle owner or retry service.

Linux enrollment includes exactly `paid_yaml_runtime.py`,
`paid_pyyaml_6_0_3.zip` and `paid_pyyaml_provenance.json` from the current native
Fabric source owner. It does not install packages or enable a role.

This closes the source-loading recipe. Interpreter/stdlib/native-library
qualification, effective-unit and current-process binding, credentials and
kernel isolation still belong to their existing host owners. The BYOK observer
continues to report its installed source as unbound until those facts are
qualified. A rendered unit or implementation label does not establish them.

### Credential-free qualification entry

The fixed isolated release entry also accepts `hermes-runtime isolation-probe`.
Use the same CPython 3.12 `-I -S -B` recipe, protected release path and held
source/YAML context as the role service. This is a closed entry to the existing
finite probe, not an arbitrary module launcher. `--list-cases` is inert.
Follow [FINAL_ROLE_QUALIFICATION.md](FINAL_ROLE_QUALIFICATION.md) for the
qualification-only unit override, source identity, external witnesses and
restoration. This source capability does not clear the serving/deployment hold.

### Mastermind OS role observations through the existing host gateway

The authenticated Office role cards read the fixed pair through the existing
Workspace HTTP route, Control socket and MH1 mTLS host-observation family.
Control does not run Linux PID1 queries on the Mac. The Linux gateway owns its
local Hermes metadata observer.

Control's existing root-pinned Fabric v2 binding document may include one
optional `hermes_role_metadata_read` object with exactly these fields:

- `host_ref` and `worker_id`: one exact pair already present in
  `remote_transports` and its physical binding.
- `expected_host_binding_sha256`: the Linux owner's
  `remote_worker_gateway_config_digest(config)`, including its Hermes
  capability. This is not the physical Fabric binding digest.
- `expected_implementation_sha`: the protected Linux release commit expected
  by that gateway's Hermes observer.

The binding document remains selected through the existing
`fabric_bindings_path` and `fabric_bindings_sha256` Control inputs. There is
no second configuration file, endpoint or credential owner. An absent selection
preserves SOURCE_UNBOUND and performs no remote read. A malformed selection or
missing exact transport refuses configuration. The reader rechecks the original
source and TLS-file identities before and after one bounded request; changed
custody discards the observation as SOURCE_CHANGED. It neither retries nor falls
back to the Mac, another host or an Attempt client. Existing paid/attended
composition exclusions remain unchanged.

The selection enables only the authenticated metadata read; it does not arm
worker execution, install a role or enroll a key. The Linux installed-source
qualifier must still establish the actual release/runtime binding. Until then
the UI remains honestly unavailable even when the transport is connected.
Office refresh updates this observation without changing the direction draft,
frozen preview or existing launch owner. Configuration observed is not proof of
credential enrollment, service health, served model, useful turn or usage.
