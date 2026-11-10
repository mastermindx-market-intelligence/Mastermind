# T3 native desktop and fleet browser use

T3 uses its existing provider configuration and skill loaders. Native macOS UI goes through the already-installed quiet Peekaboo adapter; authenticated fleet browser work goes through the already-installed Mastermind Browser MCP bridge. T3's development preview remains its own browser. This integration creates no additional daemon, credential store, profile registry or queue.

## Installation

Run the source-owned helper from the exact accepted source revision on the intended Mac:

```bash
python3 scripts/t3_computer_use_setup.py plan
python3 scripts/t3_computer_use_setup.py apply --expected-plan-sha256 <preview-digest>
python3 scripts/t3_computer_use_setup.py verify
```

The helper discovers **enabled** Claude Agent SDK provider instances from `~/.t3/userdata/settings.json`. It installs `mastermind-computer-use` and `mastermind-browser-use` into T3's skill directory and links them into each actual provider home. It adds the `peekaboo` MCP entry and reuses or restores the identical `mmx-browser` entry. It also corrects the exact incumbent browser adapter's response writer to include the mandatory `jsonrpc: "2.0"` envelope field. Unknown enabled driver types, conflicting MCP entries, external provider homes, unsafe files, changed preimages or unqualified artifacts refuse without silently changing the owner.

The browser repair accepts only the observed adapter SHA-256 `854c8397ea5b3547a1faa93e5af27eb071eefc64e9d4f2279695994414727faf` or its corrected successor `325366ad6a64c6e28204727ffa36344c34a3e5bc418047e55e87467dd950fdd9`. It changes one response statement. Browser permissions, runtime descriptor, source closure, session identity, routing and effect reconciliation retain their existing owners. A strict official MCP client failed against the original adapter and successfully initialized and discovered `mmx_browser` against an isolated corrected copy. That is transport qualification; production installation and fresh T3 consumption remain separate acceptance steps.

The qualified desktop artifact is the existing signed Peekaboo **4.9.8** CLI behind the existing Cursor quiet adapter; SHA-256 pins are in the helper. The default PATH CLI may still be **4.2.2**, and the GUI app may report another version. None is substituted for the pinned MCP route. The browser adapter validates its own installed source closure and runtime descriptor on dispatch.

The installer changes no credentials, provider models, enabled flags, OS grants, browser permissions, active threads or services. It is not a full filesystem security sandbox; real OS/provider permissions and target ownership remain controlling. MCP configuration changes use the existing Claude CLI's `mcp add-json --scope user`, with the exact provider `CLAUDE_CONFIG_DIR`; the installer never replaces `.claude.json`. This preserves unrelated provider cache/settings writes through the configuration owner's mutation API. It does not claim cross-owner compare-and-swap for concurrent edits to the same MCP entry. Skill files use preimage checks and immediate postimage readback. A partial installation retains prepared/verified entries at its original targets for reconciliation.

Configuration is loaded by **fresh agent sessions**. Use a new bounded T3 canary to prove consumption. Preserve running threads; T3's existing Restart agent session action is available for an idle thread that should reload its setup.

### Portable browser skill

On another T3 execution host, install only the browser skill without requiring a local Peekaboo binary, browser release, or MCP configuration:

```bash
python3 scripts/t3_computer_use_setup.py plan --browser-skills-only
python3 scripts/t3_computer_use_setup.py apply --browser-skills-only \
  --expected-plan-sha256 <preview-digest>
python3 scripts/t3_computer_use_setup.py verify --browser-skills-only
```

This mode installs no browser transport and makes no runtime availability claim. A T3 execution host can consume an already enrolled fleet browser through the existing M2 MCP owner; it does not need a duplicate browser registry. A remote stdio connection requires a separately proven, existing authenticated route to that owner. Do not copy credentials, invent SSH aliases, expose a new listener, or infer reverse access from M2's outward SSH access. Upload inputs and produced artifacts belong to the browser MCP execution host, which may differ from the agent's working machine.

## Capabilities and limits

| Route | Qualified interface | Important boundary |
| --- | --- | --- |
| Native macOS | Quiet Peekaboo MCP: app/window inventory, capture, AX inspection, semantic background click, field replacement, typing, selected keys, scrolling and state verification | Exact fresh snapshots; excludes global cursor, foreground control, drag, window manipulation and clipboard paste |
| Fleet Chrome | Existing `mmx_browser`: browser/host census, target tabs, snapshots, DOM/AX, frames, semantic interactions, events/network, capture/PDF, uploads/downloads and controlled CDP | Exact host/profile/connection; each browser's grants and connection must be verified |
| Development browser | T3 preview/browser toolkit | Separate browser lifecycle from the user's fleet profiles |

The native adapter advertises 14 tools. The inspected browser bridge advertises 44 actions. Catalog discovery is not proof that every action is permitted or operational on every host.

Browser page-local input and supported native background actions can avoid taking over the physical pointer. Neither is a universal independent macOS desktop. Foreground-only or cross-window work needs the existing dedicated desktop owner or an explicitly coordinated attended action. Concurrent mutation of the same tab, window or field remains unsafe.

## Qualification

The retained setup tests cover preservation of unrelated/private config, enabled provider homes, idempotence, artifact integrity, unsupported drivers, conflicting MCP owners, changed preview/dependencies, SDK writers at the mutation boundary, failed owner commands without fallback, path escape, interrupted rollback, partial-effect receipts, strict JSON-RPC responses and portable skill-only installation. Eighteen focused tests pass for this candidate.

Live acceptance must separately establish:

1. The intended T3 provider's fresh skill list and MCP tool catalog.
2. Permissions from the actual Peekaboo sender, including action-specific Event Synthesizing.
3. A harmless exact-window native change and readback, with frontmost-app/pointer observations for any noninterference claim.
4. A task-owned browser tab on the intended fleet profile, grounded interaction and DOM/screenshot proof.
5. Correct target-drift/unknown-effect handling and host/profile-specific unavailable states.

The read-only MCP qualification uses protocol `2025-03-26`; an older `2024-11-05` probe timed out against this Peekaboo build. Preserve successful current-protocol evidence rather than describing that older negotiation failure as a current permission failure.

## Rollback

Each applied change saves owner-only preimages and a receipt containing paths, hashes and the public server definitions under T3's existing backups directory. Rollback uses the existing Claude CLI to remove only the exact installed MCP entries, preserving unrelated later SDK configuration updates. Skill files and links must still match their installation postimages:

```bash
python3 scripts/t3_computer_use_setup.py rollback \
  --receipt <returned-receipt-path> \
  --expected-receipt-sha256 <returned-receipt-digest>
```

A changed MCP entry or skill blocks automatic rollback to protect its newer writer. Rollback journals `PREPARED` and `VERIFIED` for each entry; an interruption leaves `ROLLING_BACK` or `ROLLBACK_PARTIAL_RECONCILE`. Read those original targets and the current receipt, then resume with its freshly computed SHA-256. Already-restored preimages are verified without repeating the mutation. The installer never restores a whole provider configuration from an old backup. A partial install is never replayed as a new operation without reconciling its original targets.

## Upstream references

- [Peekaboo 4.9.8 canonical skill](https://github.com/openclaw/Peekaboo/blob/v4.9.8/skills/peekaboo/SKILL.md): exact-window snapshots, background input, sender-owned permissions and readback.
- [T3 Claude computer-use issue](https://github.com/pingdotgg/t3code/issues/31437): reported SDK/interactive-provider difference in T3 0.1.7, not proof of a local permission denial.
- [Claude Code computer use](https://code.claude.com/docs/en/computer-use): native interactive feature constraints.
- [MCP base protocol](https://modelcontextprotocol.io/specification/2025-06-18/basic): mandatory JSON-RPC 2.0 response envelope, matching IDs and notification behavior.

The two local skills deliberately describe the installed restricted route. The broader upstream command catalog does not grant foreground or other capabilities excluded by this adapter.
