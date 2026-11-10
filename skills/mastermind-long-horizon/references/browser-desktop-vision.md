# Browser, desktop and auxiliary vision

Contents: Installed owners; native Chrome; Peekaboo desktop; auxiliary vision.

## Use the installed owner, not an alternate control path

The T3 stdio package in `integrations/t3_harness` adapts the already-installed
Mastermind Native Messaging browser bridge and the native Peekaboo MCP process.
It does not create another browser driver, daemon, credential store or provider
router. The maintained MCP SDK handles protocol framing and typed image results.

Require actual native tool discovery. A manifest/configuration file is not a
loaded tool, a successful CLI probe is not a T3 model consuming it, and a native
permission receipt is not permission to perform an unrelated action.

The launcher receives `T3CODE_THREAD_ID` from the provider process and uses it for
reference separation. This environment variable is attribution, not authentication.
The host user, native T3 permission ceiling, original Bridge and extension's site
permissions remain controlling. Never supply another thread ID to a tool or copy
refs between threads. Unbound project context returns UNBOUND instead of guessing.

## Native Chrome workflow

Use `mmx_browser`, not Peekaboo's separate browser attachment or a raw debugging
port, for Mastermind's already-enrolled Chrome profiles.

1. List enrolled profiles; select the exact intended host/profile. A listed closed
   profile is not connected. Do not default to the user's personal profile.
2. Read status and retain the actual connection ID. List tabs only in that selected
   profile. Select the exact tab and URL fingerprint before inspecting content.
3. Read a fresh snapshot/accessibility tree. Use its element refs and document
   identity for the next action. After navigation or relevant page mutation,
   refresh the snapshot rather than reusing a stale selector.
4. Take the narrowest supported action and read back its receipt and visible
   postcondition. Receipt success, DOM change and task acceptance are distinct.
5. On a lost action response inspect the original request/operation through the
   incumbent bridge. Do not repeat a click/upload/submit, switch profile or launch
   another browser to evade an unknown effect or permission refusal.

Use DOM/accessibility evidence for structure and selectors; real screenshots for
visual layout. Preserve both where each is material. Images returned by the bridge
are actual MCP image attachments, not base64 text for the model to interpret.
Use Chrome-native capture/PDF/download only within the installed tool's scope and
already-approved artifact/upload roots. Keep secrets, passwords and unrelated
private tabs out of briefs, logs and shared source.

Control, screenshots, downloads, upload roots, site access and advanced CDP have
separate native constraints. Do not enable one merely because another works.
Advanced evaluation/network/CDP actions are not universally read-only. Validate the
specific action and outcome. No arbitrary endpoint attachment or automatic global
permission self-grant is introduced by this integration.

## Peekaboo desktop workflow

Use the native `mastermind-peekaboo` tool set for macOS application/window controls.
Discover the installed version and schemas. The qualified 4.2.2 MCP server is
background-only; do not invent newer foreground flags or use an alternate control
path after that native boundary refuses an action.

Read `permissions` first when permission state matters. List the intended app's
windows and select an exact window ID with matching application ownership. Prefer
an exact accessibility element from `see`/`inspect_ui`, then a supported `action`,
`set_value`, `click`, `type` or key operation. Scope visual captures to that window,
not every screen or whichever app happens to be frontmost.

Refresh after resize, navigation, dialogs or materially changed UI. Keep snapshot,
window, application and coordinate space together. Image pixels, logical points,
normalized coordinates and ROI-local coordinates are different. Never turn a
vision-estimated location into a global click without rechecking that mapping.
Use native `verify_state` or a fresh capture/read to verify the postcondition.

Do not invoke Peekaboo's autonomous `agent` capability as a replacement for T3
children, admitted paid Fabric labor or a refused handoff. Do not call its browser
connect tool to bypass the Mastermind extension's selected profile or grants.
Do not request Screen Recording/Accessibility grants programmatically or expose
clipboard contents without a task-specific reason. OCR is off by default and is
not a substitute for available accessibility data or the model's native vision.

The existing on-demand Peekaboo daemon owns desktop lifecycle. A stopped host is a
specific technical dependency, not a reason to build another daemon or switch
accounts. Recovery uses that original owner, with exact liveness/readback and no
blind replay of a prior UI action. Native daemon liveness does not mean an agent
mission is running in the background.

## Auxiliary vision without changing the primary model

Use the actual screenshot in the principal model when supported. For a separate
visual second opinion, use the already-installed native `analyze` tool and its
existing credential/provider owner. Keep the question bounded to the selected
image, e.g. overlap, clipped controls, state changes or a proposed element match.
A visual answer is an observation, not a click instruction or authorization.

Before remote vision, check the allowed destination and sensitive content. Do not
send an entire desktop, personal chat, credential panel or unrelated tabs merely
to review one component. Prefer a selected window/ROI. Retain image/source identity
and request/result references; reject conclusions based on a stale or different
capture. Do not forward the T3 principal's API key or base URL into Peekaboo. The
fixed launcher strips inference credentials and interpreter injection variables;
Peekaboo uses its own existing configuration and credential store.

MiniMax's official API documents `MiniMax-M3.1-Flash` with image/video input and
always-on, adjustable reasoning. That is vendor capability, not proof that the
installed Peekaboo route is enrolled or compatible. At qualification, Peekaboo's
existing native defaults still named M2.7. Its MCP `provider_config.type` allowed
auto/ollama/openai/anthropic/grok, not a newly invented minimax enum. Never replace
that exact schema with a guessed provider name or silently modify global defaults.

An M3.1 pilot must preserve the native credential owner, qualify the exact model
route, test one approved non-sensitive image, inspect actual usage and result,
check failure/no-replay behavior, and retain a rollback. Keep it unproven until
that real call succeeds. Do not claim the vendor's speed/cost figures as measured
fleet performance. A vision response must not silently authorize actions, spawn
workers or reset the mission's spending budget.

Primary vendor reference: https://platform.minimax.io/docs/api-reference/text-openai-api
Native behavior takes precedence over examples written for a newer release.
