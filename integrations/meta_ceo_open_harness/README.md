# Private Meta-CEO and Secretary interaction seats — DSH developer preview

**Status: local launch-layer source only. NOT a production Meta-CEO, autonomous Secretary, installed model, real-provider canary, or authorized Executive/Fabric client.** This additive launcher does not modify incumbent DSH PR #1717, ACP/MCP PR #1790, or Steward/Grok Secretary source.

This small seat wrapper starts the **existing** MIT-licensed DeepSeek Harness full application, pin `deepseek-ai/deepseek-harness@687f282e8625c6b8d11ff58211a90524be2e4317`, with independently private on-disk DSH homes for two *developer interaction profiles* with native DSH persona presets: `meta-ceo` and `secretary`. The profiles are not two company control planes, CEOs or Jobs. No Grok Bot retained proprietary code is used. Each seat selects its own DSH `agent-preset-registry` default and mounts only `dsh-persona`; neither preview agent is granted terminal, filesystem, web, calendar, email, delegation or scheduler tools.

The donor already implements **Settings → Models**, with a `zai` provider, custom OpenAI-compatible APIs, credential references, read-once key storage in `$DSH_HOME/.credentials.yaml`, and normal DSH native streaming chat. This wrapper neither stores API keys nor creates an alternate provider router. You enter your own authorized model key directly in **each seat's** DSH Models settings after launch. Never add secrets to this repository, CLI arguments, shell history, screenshots, GitHub issues, or test fixtures.

## Prerequisites

- Node available locally and a separately acquired, **exact pinned and built** donor checkout (follow existing `integrations/deepseek_harness/README.md`; use locked pnpm 11.28.5 as documented). This launcher intentionally does not install, download, update or clone dependencies.
- A local operator with read/write access to their own seat directory, and a browser on the same trusted machine. Ports 3080/3081 are loopback-only; no public service or account login is provisioned.
- Native DSH can run file, terminal and other tools according to its own permission profile. A private DSH home is **not** an OS sandbox, remote authentication boundary or Mastermind authorization grant. Until the governed profile is accepted, use only a disposable workspace with non-sensitive content.

```sh
# Read-only, secret-free preflight; validates pinned clean donor source and build.
python3 integrations/meta_ceo_open_harness/launch_seat.py \
  --seat meta-ceo --source /absolute/path/to/built/deepseek-harness --check

# Two separate foreground sessions/terminals, after independent permission review:
python3 integrations/meta_ceo_open_harness/launch_seat.py \
  --seat meta-ceo --source /absolute/path/to/built/deepseek-harness
python3 integrations/meta_ceo_open_harness/launch_seat.py \
  --seat secretary --source /absolute/path/to/built/deepseek-harness
```

The Meta-CEO development chat is at `http://127.0.0.1:3080`, Secretary at `http://127.0.0.1:3081`. Each profile writes only beneath `~/.mastermind/dsh-open-harness/<seat>/`; all existing seat directories must be real, owned by the invoking user, and mode 0700. Both seats load the matching reviewed `meta-ceo.patch.yml` / `secretary.patch.yml` via native `--patch` when they start; normal DSH UI can display the selected role. The launcher refuses a dirty or non-pinned donor checkout, symlinked target seat roots and permissive existing directories. `--port` and `--data-root` override development defaults; `--check` makes no seat state.

The child inherits only a narrow allowlist of non-secret environment variables plus its dedicated `DSH_HOME`. It **never** inherits existing `OPENAI_API_KEY`, `ZAI_API_KEY`, Company tokens, `DSH_HOME`, or arbitrary proxy settings. Provider and model selection is still DSH's own native per-seat configuration. Environment isolation is not an OS user or process sandbox; the original host's user permissions remain available to DSH and the browser itself has no Mastermind authentication.

## Test

```sh
python3 -m pip install 'PyYAML==6.0.2'  # test-only dependency
python3 -m unittest discover -s tests/meta_ceo_open_harness -v
```

These are hermetic contract tests; they replace `git` probes and the `execve` call, start **no real donor process**, contact no model endpoint, and prove no live provider billing, credentials, session streaming or Mastermind tool authorization.

## Required next integration owners and acceptance

- **DSH native interactive proof:** on an authorized host, run the original donor Web smoke (#1845) and a real browser chat/send/stream/cancel/resume check. This script's `--check` cannot satisfy that proof.
- **BYOK provider proof:** configure each DSH seat through native Models UI; validate the served model identity, usage, safe error handling and credential rotation with an authorized synthetic then live model route. Z.AI pool/account use for company work remains under existing Model Router/Capacity and may not be duplicated by this developer UI.
- **Governed company integration:** native DSH MCP/ACP consumes existing authenticated Executive/Steward/Agent OS contracts. A DSH chat response is **not** an Executive WorkerResult or original-parent accepted outcome. Never install a raw bearer token in committed YAML. The Steward six-tool read surface is partial and production-inert until separately authorized source and OAuth read proof.
- **Secretary workflows:** existing event-driven Wake/Dialogue/RuntimeBinding must wake the exact authorized responsibility, and Fabric only through admitted Executive child Jobs. No second schedule queue or credential subsystem.
- **Release:** independent nonauthor review, protected CI, host install permission, real signed-in Chairman user-path proof and 24-hour/7-day reliability, before any production/always-on claims.

Canonical work: Mastermind [#1841](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1841), [#1717](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1717), [#1790](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1790), [#1845](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1845). Protected Mastermind procedure pin at source creation: `bb85b429f2ffffd38408080ce4df7d6378c34100`, Skillpack 1.0.1/bootstrap 1.
