# External provider verification — separate from Mastermind source and native proof

Checked against official Claude Code documentation on **2026-10-04**. These are provider-document
observations, not measurements of Mastermind's installed SDK, CLI, account, settings or enforcement.
No provider inference, login or installation was performed. The design implications below are
our engineering decisions beneath current Mastermind authority, not provider-granted permission.

## E1 — Tool visibility is not automatic approval

Source: [Agent SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions).

The documentation distinguishes allowed-tool approval rules from the tool inventory. Calls
approved earlier can skip `canUseTool`; applicable ask/interaction requirements are exceptions.

Design implication: never put the sole authorization control in a callback that the native
permission flow may skip. Qualify exact inventory and retain the existing server/host guard.
A plugin's convenient allowed-tools list is not a capability ceiling.

## E2 — Settings isolation must be tested on the actual version

Source: [Python SDK reference](https://code.claude.com/docs/en/agent-sdk/python),
`SettingSource` / `setting_sources` and `strict_mcp_config` sections.

The reference documents that Python SDK 0.1.59 and earlier did not make an empty settings-source
list disable filesystem settings. It also states that strict MCP configuration uses explicitly
provided servers and excludes plugin-provided MCP servers.

Design implication: qualify the installed native/SDK combination behaviorally, not from copied
options. The first proposed package composition uses instruction content plus explicit MCP
projection; bundled-server parity is separately qualified. A newer version alone is not admission.

## E3 — Managed and inherited settings are material inputs

Source: [Settings files and precedence](https://code.claude.com/docs/en/settings).

Managed settings have the highest general precedence, while some security keys retain stricter
lower-level values. List settings can merge rather than replace each other.

Design implication: native observation must account for effective settings and provenance. Do not
turn off managed policy or assume a short project config erases ambient rules. Changes relevant to
the admitted profile require the existing owner's requalification decision.

## Qualification record required before native claims

Record exact native binary and SDK versions/digests, selected package/profile source, effective
configuration observation, managed-policy provenance, expected/observed tool and schema generation,
and actual positive/refusal behavior through existing owner receipts. Documentation URLs can
change; they are research references, not immutable runtime attestation or protected source law.

The referenced public facts identify concrete hazards to test. They do not establish that the
current Mastermind host has any particular affected version, that a provider capability is fully
available there, or that any current denial may be bypassed.

## E4 — GitHub check eligibility and commit association

Source: [Troubleshooting required status checks](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks).

GitHub distinguishes latest-head and test-merge checks, can require an expected GitHub App, and
can count neutral/skipped conclusions toward required-check satisfaction. Some workflow events
do not produce checks eligible for a pull request's ruleset.

Design implication: the observer must consume the actual release/ruleset association, not infer
PASS from a green-looking collection. Record test execution separately from platform merge
eligibility; neither substitutes for product acceptance. No repository rules were changed here.
