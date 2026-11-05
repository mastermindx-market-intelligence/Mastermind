# Business Sol installation and enrollment ceremony

**Wave:** BSC-U1  
**Capability ceiling:** `BUILT_NOT_PROVEN / U1_BINDING_AND_ENROLLMENT_TOOLING / PRODUCTION_INERT`  
**Artifact:** native `.app.json` references plus a redacted Mastermind receipt.
The documented reference has one `apps` map, keyed by logical name, whose values
contain an actual app `id` and `required: true`. It is not a complete plugin
archive or an app-creation request. Never commit workspace-specific identifiers
into the protected source package. Validated input and metadata remain
Mastermind-private; public evidence exposes only digests.

## Purpose

This ceremony removes hand-edited plugin/app IDs and stale tool snapshots from the Business rollout. It does not create an app, connect OAuth, start a tunnel, install a plugin, call Executive OS, or grant production acceptance. The compiler consumes independently approved observations and either returns `READY_TO_COMPILE`, or a deterministic `PREFLIGHT_HELD` issue set with no output artifact.

Current OpenAI platform behavior was rechecked against the official documents **Developer mode and MCP apps in ChatGPT** and **Apps in ChatGPT** on September 4, 2026. The relevant operating facts are: Business admins or owners manage custom MCP apps; users authenticate to each app separately; published Business app tool snapshots are reviewed/frozen and material tool changes require a new publication generation; local MCP servers require Secure MCP Tunnel. Plugin package availability, app publication, app connection, and successful tool use are separate facts.

## Frozen generation-one topology

`mastermind-sol` generation 1 binds exactly:

1. **Mastermind Steward** — outer MCP app `mastermind-steward` version `2.0.0`, six read-only grounding tools, contract digest pinned in source. The protected `mastermind-secretary-grounding` contract owns result schemas; its name is not the app server identity.
2. **Mastermind Executive** — `mastermind-executive` version `1.0.0`, the existing five-tool Executive surface, contract digest pinned in source.

The future Surface app is absent from generation 1. No required binding may be omitted or converted to optional. Current real-workspace evidence is expected to produce `PREFLIGHT_HELD` until the Steward app has a published, enabled, available, approved app identity.

## Inputs

Supply one closed `mastermind.business_sol_installation_request.v1` document containing only:

- exact protected source commit and observed source commit;
- approved and observed plugin package digests;
- opaque workspace digest and current `ADMIN` or `OWNER` role classification;
- plugin package identity, registry identity plus approved digest, scanned generation, and observed installed Boolean;
- one row for each required app: opaque app ID plus approved digest, workspace/scope, publication and availability state, app generation, server name/version, resource and OAuth policy digests, exact tool names and contract digest, and observed installed/connected Booleans.

Raw resource URLs, redirects, tokens, secrets, cookies, passwords, private keys, emails, browser/profile data, local paths, OAuth codes, and model-authored authority claims are refused. The caller owns collection and approval of the input facts; this pure compiler performs no network, browser, MCP, OAuth, workspace, registry, Executive OS, or Agent OS discovery.

## Raw JSON admission boundary

The CLI reads each template/request as UTF-8, up to 1,048,576 bytes inclusive.
Duplicate object members (including equivalent escaped names) are refused before
normalization; neither equal duplicates nor a later valid value can hide an
invalid or secret-shaped earlier value. NaN and Infinity constants are refused.
Integer literals have at most 64 digits; container nesting has at most 64 levels.
These bounds do not depend on global interpreter settings. Normal whitespace and
pretty-printed JSON remain valid. File/encoding/decoder/depth failures produce the
existing fixed `INVALID_INPUT` envelope with exit 2 and no input, path, or traceback
echo. These checks finish before preflight, compilation, or staging can occur.

## Verify-only sequence

1. Pin protected Mastermind and validate the plugin package with `scripts/validate_mastermind_plugins.py`.
2. Export the protected symbolic template from `plugins/mastermind-sol/references/app-bindings.template.json`.
3. Collect the current workspace observations through the approved admin/browser path. Record raw IDs only in the private ceremony request; durable/public receipts contain digests.
4. Run:

```bash
python3 -m scripts.mastermind_business_installation \
  --template /private/ceremony/template.json \
  --request /private/ceremony/request.json \
  --mode preflight
```

5. Interpret the result:
   - `READY_TO_COMPILE`: every generation-one binding and source contract is complete and internally consistent. This is still no installation or OAuth proof.
   - `PREFLIGHT_HELD`: repair only the named missing/unavailable/stale app or source observation. No `.app.json` is emitted.
   - `REFUSED`: the request or template violated the closed contract. Do not repair values heuristically.

## Private staging sequence

Only after `READY_TO_COMPILE`:

1. Choose an explicit staging root outside the protected repository and outside any symlinked directory.
2. Record whether `.app.json` is absent or record its exact preimage digest and mode.
3. Run stage mode once with the expected preimage:

```bash
python3 -m scripts.mastermind_business_installation \
  --template /private/ceremony/template.json \
  --request /private/ceremony/request.json \
  --mode stage \
  --source-root /absolute/protected/repository \
  --output-root /absolute/private/staging \
  --expected-preimage-digest ABSENT
```

4. Preserve the redacted public receipt and rollback manifest. The private file contains IDs; never post it to Slack, commit it, or attach it to a public issue.
5. Run `--mode verify` against the same request and roots. Any mismatch is `READBACK_MISMATCH`; do not overwrite or silently regenerate.

Source/output overlap is checked before any staging-directory creation, so an
in-source path refusal cannot create directories inside the protected source tree.

The stage operation uses a fixed exclusive temporary file, exact byte/mode verification, one atomic rename, directory fsync, and post-effect readback. A lost rename response is reconciled against the exact postimage. Unreconciled stage or rollback outcomes remain `STAGE_EFFECT_UNKNOWN` or `ROLLBACK_EFFECT_UNKNOWN`; never repeat on another path.

## Live admin ceremony after source protection

The source wave does not perform these actions. The later privileged U1/C1 operation must execute them in order and preserve separate receipts:

1. **source proof** — exact protected package, compiler and contract digests;
2. **app publication** — exact Steward and Executive app generations and frozen tool snapshots;
3. **endpoint reachability** — loopback service plus approved Secure MCP Tunnel, raw-path-safe forwarding, and expected resource identity;
4. **OAuth** — per-user authentication to each app with exact resource/scope policy; no secret enters Mastermind receipts;
5. **user installation** — the exact Mastermind Sol package becomes available/installed for the selected Business user;
6. **successful read** — one real `executive_state` and one Steward read traverse the authenticated app path;
7. **write admission** — separately confirmed later; never inferred from read success and never executed by this ceremony;
8. **production acceptance** — explicit Sol/Chairman gate after the complete canary and rollback/readback evidence.

Do not claim later steps from success at an earlier step.

## Failure matrix

| Condition | Result | Effect law |
|---|---|---|
| Steward absent | `PREFLIGHT_HELD / REQUIRED_BINDING_MISSING` | no artifact |
| app ID absent | `PREFLIGHT_HELD / APP_ID_MISSING` | no artifact |
| app draft/disabled/unavailable | `PREFLIGHT_HELD` with complete sorted issues | no artifact |
| source/package observation drift | `PLUGIN_SOURCE_MISMATCH` | refuse |
| workspace, plugin, app or schema identity drift | fixed refusal | no repair/inference |
| stale tool names/digest | `APP_CONTRACT_MISMATCH` | create/review a new app generation, not an in-place lie |
| duplicate/extra binding, including Surface in generation 1 | fixed refusal | no output |
| secret, URL, email, or private path in request | `SECRET_SHAPED_INPUT` | no output/log echo |
| output inside/containing source or through symlink | fixed path refusal | no write |
| preimage mismatch or foreign temp | fixed conflict | no overwrite |
| ambiguous rename/rollback | effect-unknown | reconcile exact target; no retry/failover |
| readback mismatch | `READBACK_MISMATCH` | stop before install |

## Rollback

The stage receipt binds the private document digest, target-path digest, preimage state/digest, expected postimage, and mode without emitting the path or IDs. Rollback is legal only while the exact expected postimage remains present. It restores the exact prior bytes and mode or exact absence, fsyncs the directory, and verifies the result. A changed postimage is a conflict, not permission to overwrite.

Live plugin uninstall, app disconnect, OAuth revocation, tunnel shutdown, or workspace rollback are separate privileged actions and require their own preimages and readbacks. This source tool grants none of those authorities.


## Documented native reference boundary (rechecked September 5, 2026)

OpenAI now explicitly documents the existing-app `.app.json` format:
https://learn.chatgpt.com/docs/enterprise/plugin-management
https://help.openai.com/en/articles/20001504-importing-and-syncing-plugin-marketplaces-from-github

This supersedes the earlier claim that no native reference format is documented.
U1's generation-one policy accepts only the commissioned custom `asdk_app_` IDs;
`plugin_asdk_app_` is a directory plugin identity and is refused. Obtain the actual
app ID and its approved digest from the admin observation rather than silently
rewriting an approved plugin ID. The platform also supports other app families,
which are not commissioned in this generation.

The native file contains no Mastermind schema, registry ID, workspace hash,
OAuth data, or source/version metadata. The v2 public receipt binds the native
bytes with `binding_document_digest`, and independently binds the complete
validated private metadata with `installation_plan_digest`. A changed approved
app generation can keep the same native references while changing the metadata
evidence digest; reuse must compare both, not the native file hash alone.

**Assembly gate remains separate.** The approved staged plugin must contain
`.app.json` at its root and `"apps": "./.app.json"` in its
`.codex-plugin/plugin.json`. The protected P1 package is skills-only; this compiler
does not edit that manifest or claim an installable archive was assembled.
Record exact staged-manifest preimage, postimage and package digests in the later
privileged ceremony. Do not change a source-owned manifest without its approved
scope. The same package must not declare `mcp.json`, `.mcp.json` or inline MCP
servers for a web-only rollout; the official importer can mark them Desktop only.

Before choosing the delivery route, inspect whether the existing plugin is
GitHub-managed or archive-managed. GitHub-managed plugins cannot be replaced by
archive upload. Do not delete/recreate the plugin or marketplace to bypass that
state. A native reference, marketplace sync, plugin installation, app availability,
user authentication and a successful Steward read remain distinct facts.
