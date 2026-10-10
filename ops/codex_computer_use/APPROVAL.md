# Native Claude MCP approval — attended one-time setup

## What is already installed

M2 Studio:
\`/Users/chriswong/Documents/GitHub/mmx-cuse-m2-pilot-20261009\`

mini1/mini2:
\`/Users/<macOS-username>/Projects/MastermindX/repos/mmx-cuse-pilot-20261009\`

mini4:
\`/Users/mini4/Projects/MastermindX/repos/codex-cuse-candidate-20261009\`

Every pilot has a project-scoped \`.mcp.json\` entry named
\`mastermind-computer-use\` running the existing OpenAI-signed computer-use
client through \`node ops/codex_computer_use/bridge.mjs\`. This is deliberately
not a global or remotely exposed server.

## Approve without bypassing Claude's trust boundary

1. On the **machine that will run the desktop control**, open Terminal as its
   logged-in macOS owner. Change into that machine's pilot directory above.
2. Start the installed interactive Claude Code CLI with \`~/.local/bin/claude\`.
   Do **not** use \`-p\`, a headless Agent SDK run, an allow-all permission mode,
   direct edits to \`~/.claude.json\`, or a bypass flag to approve.
3. If Claude asks "Is this a project you created or one you trust?", review the
   exact directory and explicitly choose "Yes, I trust this folder" *only if
   the human operator accepts its contents*. This is one real human ceremony.
4. From Claude's interactive prompt, enter \`/mcp\`. Find
   \`mastermind-computer-use\`; review the command and the absolute path,
   and select **Approve**. If the server appears as pending, do not rely on
   \`claude mcp list\` or \`claude mcp get\` to approve it: they only show state.
5. In a second Terminal tab in the same project, verify with:
   \`~/.local/bin/claude mcp get mastermind-computer-use\`.
   "Connected" proves discovery, not GUI/screenshot permissions.
6. Ask Claude in that trusted project to use only
   \`mastermind-computer-use.get_app_state\` on Calculator.
   Confirm native accessibility text **and an image** are returned. Only
   after the operator expressly authorizes writes should a separate test
   permission be granted. Keep the permanent policy \`write:false\`.

## Browser / phone access to that local Claude session

After the human trust and MCP approvals above, Claude Code supports its own
**Remote Control**: from the same interactive session, run \`/remote-control\`.
Accept the separate Remote Control enablement prompt, then open that session
at https://claude.ai/code or in the Claude mobile app. This continues the
*local* Claude process (and its approved local MCPs) without needing an inbound
VNC port or exposing the raw Computer Use server. It is **not** a remote MCP
server exposed to generic Claude Web sessions or ChatGPT Web.

Claude Remote Control itself is gated by an eligible signed-in Claude account
and organization settings; do not assume every seat is enabled. Remote Control
does not implicitly grant app/screenshot access.

## State and scope limits

- A pending approval is normal until the actual human confirms the project
  and MCP tool. Never auto-write Claude trust files or install a user-global
  server as a shortcut.
- A project can be MCP-approved while macOS Screen Recording, Accessibility
  or app-use consent is not. Those are distinct consent dialogs on each Mac.
- "Connected" in Claude, local MCP smoke, and production ChatGPT/Claude
  browser acceptance are separate evidence gates.
- The signed Codex Computer Use service may not stay open after an idle period.
  If \`get_app_state\` reports bootstrap timeout, start the existing Computer
  Use app through the logged-in GUI owner and inspect its legitimate macOS
  privacy prompts. Do not tamper with TCC or signing.
- On macOS, interacting with a graphical application requires an active
  graphical session. SSH processes and other headless agent runners can have
  different privacy attribution from an attended Terminal.
- For generic remote ChatGPT/Claude integration, reuse Mastermind's governed
  Studio Direct/SCF gateway and Executive/RuntimeBinding. See PR #1217.
  The local adapter in PR #1302 is intentionally not a shared HTTP endpoint.

## Quick diagnostics

From each pilot directory:

\`\`\`sh
~/.local/bin/claude mcp get mastermind-computer-use
node --test ops/codex_computer_use/policy.test.mjs \
  ops/codex_computer_use/remote-facet.test.mjs \
  ops/codex_computer_use/remote-output.test.mjs
\`\`\`

Only an intentionally attended client using the exact approved local app may
perform the live GUI canary. Screenshot bytes and private accessibility trees
must not be published to CI logs or GitHub issues.
