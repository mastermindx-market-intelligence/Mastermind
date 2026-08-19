# OHF-P1A — Codex 0.147.0 minimal-surface evidence

**Date:** 2026-08-16
**Status:** production-inert live spike. Does not modify P0 probe semantics.
**Codex:** `codex-cli 0.147.0`
**Dedicated home:** `/Users/chriswong/.codex-ohf-p0` (independently authenticated; not `~/.codex`)
**Raw artifact SHA-256:** `d63c5938c63f31909aef6a593b6e327e79db236f6a65e7fa5c0b8f853c21c4f9`
**Repo copy:** `research/evidence/ohf_p1a/minimal_surface.json`

P0 canary (`ohf-p0-5cbe5e32673d`) is unchanged and remains the continuity/recovery
baseline. This spike only asks whether apps and bundled skills can be reduced.

## 1. Keys verified on 0.147.0

Throwaway `CODEX_HOME` (no `auth.json`) plus live App Server:

| Setting | Parse result |
|---|---|
| `[features] apps = false` | accepted |
| `[skills.bundled] enabled = false` | accepted (`BundledSkillsConfig`) |
| `[skills] bundled = false` | **rejected** (`expected struct BundledSkillsConfig`) |
| CLI `-c features.apps=false` | used |
| CLI `-c skills.bundled.enabled=false` | used |

`--strict-config` is not supported on `codex features`. Do not document that path.

## 2. Auth / config hygiene

- `auth.json` not copied, not symlinked, not printed.
- Implicit `~/.codex` not used.
- Default `~/.codex/auth.json` inode `909483118` / mtime `1786886116` unchanged.
- Dedicated `auth.json` inode `1146460587` unchanged.
- Dedicated `config.toml` hashed, backed up, restored: SHA-256
  `cdc4bbefcd048e0ab3ff5c696fa4e18de1c3dd65b253bc07a6d6b7f703650c9d` matched
  after the spike.

## 3. Observations

| Question | Result |
|---|---|
| Does `codex_apps` disappear? | **YES** (`mcp.servers = ["ohf_probe"]`) |
| Do the 31 P0 bundled/ambient skills disappear? | **PARTIAL** |
| Does `ohf-probe` remain discoverable? | **YES** |
| Does `ohf-probe` remain invokable? | **YES** |
| Does fixture MCP remain discoverable/callable? | **YES** (`ohf_probe_echo` → `echo:ping`) |
| Does thread start/resume still work? | **YES** (same id `01a00bc1-020b-7182-b44b-6693df054763`) |
| Does normal turn execution still work? | **YES** |
| Does `config/read` expose the reduction? | **YES**: `features.apps=false`, `skills.bundled.enabled=false`, sandbox `read-only`, approval `never`, model `gpt-5.6-sol` |

Removed versus P0 ambient baseline (examples): `imagegen`, `openai-docs`,
`plugin-creator`, `skill-creator`, `skill-installer`, `review-agent`, and the
entire `codex_apps` tool dict (P0: 134 unexpected tools → P1A: 0).

Still present after reduction (25 names): `github:*` (4),
`openai-templates:artifact-template-*` (20), `plugin-management:plugin-management`.

Do **not** fake a fully reduced profile. `config/read` tells the truth (`bundled
enabled=false`) while `skills/list` still returns plugin/template skills. Those
are a different surface from bundled system skills.

## 4. Version-specific 0.147.0 ambient baseline (provisional)

For ChatGPT Pro App Server 0.147.0 with apps disabled and bundled skills
disabled:

- Apps MCP can be removed.
- Bundled system skills can be mostly removed.
- Plugin/GitHub/template skills remain unless plugins are also disabled
  (not proven in this spike; `features.plugins` was left at default true).
- Write-capable production profiles must treat leftovers as **UNCLASSIFIED**
  until an explicit allowlist is reviewed. This spike's classifier returned
  `LAUNCH_REFUSED_UNCLASSIFIED`.

Unknown: whether `--disable plugins` would remove `github:*` /
`openai-templates:*` without breaking fixture MCP. Not claimed.

## 5. Implications for ExecutionProfile

Requested-set == observed-set remains false even after reduction.
Attestation must stay three-layer: REQUIRED / ALLOWED_AMBIENT / FORBIDDEN,
with UNCLASSIFIED fail-closed on write profiles.

## 6. R3 gate classification (unchanged residue)

Independent review classified this residue:

- architecture: **NONBLOCKING**
- write-capable Codex OHF canary: **BLOCKED**
- production arming: **BLOCKED**

R3 does **not** add `github:*`, `openai-templates:*`, or `plugin-management` to
ALLOWED_AMBIENT. The optional `features.plugins=false` spike was not run.
Residual names stay UNCLASSIFIED until a later explicit experiment or
versioned allowlist. Observed capability identities can carry digests when a
future probe exposes them; they still classify as UNCLASSIFIED today.
