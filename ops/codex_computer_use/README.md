# Mastermind Codex Computer Use — host-local MCP adapter

**State:** Experimental, scoped, and not yet proven for live desktop screenshots or remote Web use.

A signed Codex Computer Use client is exposed as a local stdio MCP for
Claude Code and compatible local clients. Based on the MIT-licensed
songkeys/claude-codex-computer-use at pinned commit
61a2ad3a02a2baa5adf703673bb1cffa36adf4fb;
upstream LICENSE and NOTICE are retained.

This adapter replaces the upstream blanket app-approval with a local
**owner-only exact allowlist** and enforces the official signed OpenAI
launcher Team ID (2DC432GLL2). It advertises only read tools unless the
owner has expressly authorized writes. The default permits zero apps.
No network listener or separate organizational authentication plane exists.

## Requirements and limits

macOS, OpenAI's Codex Computer Use installation, bundled OpenAI-signed
Codex executable, Node.js 22+, active GUI session, and existing macOS
Accessibility, Screen Recording, Input Monitoring and Automation grants
for the responsible process. The upstream signed sandbox launcher needs
an unrestricted filesystem profile to reach native macOS sockets.
This does not grant any remote caller desktop authority.

The M2 Studio and Mac mini 4 enumerated MCP tools and listed apps in
October 2026. Their controlled Calculator state/screenshot calls timed
out, so screenshots/clicks and broader app control are NOT yet accepted.
Do not bypass TCC, code signing or macOS consent to resolve this.

## App policy

The user-owned policy lives at:

    ~/.config/mastermind/computer-use-policy.json

It must be owned by the current user and permission mode 0600.
Missing file means no apps. The example grants read-only Calculator
access only. It is a **sample**, not fleet installation consent.
Each grant binds an exact bundle ID, display name, native elicitation
prompt, read/write flags, and an explicit per-app preapproval boolean.
Unknown or mismatched elicitations are declined. Inventory returns only
the locally configured app names and explicitly does not claim that
those apps are running.

## Verification

From the repository root:

    node --test ops/codex_computer_use/policy.test.mjs
    node ops/codex_computer_use/smoke.mjs

With a consented Calculator policy, test the real GUI with:

    MMX_CUSE_SMOKE_APP=com.apple.calculator node ops/codex_computer_use/smoke.mjs

The latter must return an image block to pass. The smoke never prints
screen images or whole app accessibility contents.

For Claude Code, configure a **project-scoped** stdio MCP whose command is
node and whose argument is the absolute path to bridge.mjs. Do not register
globally or offer the adapter as remotely accessible before GUI acceptance.

## Intended next integration

Reuse the existing Mastermind Studio Direct / SCF authenticated MCP
carrier and Executive OS / Capacity / RuntimeBinding authority and
machine-placement/custody owners. Do NOT create another queue,
identity service, lease registry, retry system, or fleet orchestrator.
A later remote transport must independently enforce OAuth principal,
machine binding, explicit app scope, exclusive GUI custody, audit,
cancellation, screenshot disclosure rules and effect reconciliation.
ChatGPT Web and Claude Web connection/installation are separate proof
gates and have not been performed here.

## Failure and cleanup

No automatic replay after a timed-out desktop action. A click or typing
operation may be EFFECT_UNKNOWN until its original machine/session is
reconciled. Native Esc-stop, idle timeout and client process exit
release the upstream app hold; these are not Executive acceptance or
remote permission receipts. Treat the signed runtime as version-coupled
to ChatGPT/Codex releases and re-test after updates.
