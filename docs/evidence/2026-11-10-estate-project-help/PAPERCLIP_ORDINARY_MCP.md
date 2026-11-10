# Paperclip finite sessions: ordinary MCP API avenue

## Decision

Use the ordinary, model-visible authenticated Hermes MCP route as the smaller
API-principal avenue. A new native prefetch hook or Secretary ConsumerSlot is
not a prerequisite for that route. It still needs a separately enrolled
Paperclip API principal and exact source profile; a Paperclip run JWT does not
become an Executive OAuth credential, and ordinary tool calls do not attest a
native Paperclip issue, Hermes session, T3 thread or parent.

The already accepted native-context census remains correct about its narrower
reach: its retained publication/ConsumerSlot constructor does not automatically
cover the thirteen ordinary `hermes_local` finite chat profiles. This addendum
identifies a separate existing consumer path, rather than expanding that claim.

## Actual existing owner evidence

The previously captured installed adapter executes ordinary `hermes chat -q`
through the real launcher. Fresh source-only reads of that installation show:

| Owner under `/Users/chriswong/.hermes/hermes-agent` | Observed source fact |
| --- | --- |
| `hermes_cli/main.py`, `cmd_chat`, SHA256 `e1321a2b30d92716b88c72fed3104b79195bc59067fad9f6b0740c3cc54f2f8c` | Ordinary `-q/-Q` uses the current classic HermesCLI with its gateway-backed agent. Stream-JSON/safe-mode branches have their own existing transport startup. Finite CLI does not imply the separately enrolled Mastermind native consumer. |
| `tools/mcp_tool_config.py`, `_load_mcp_config`, SHA256 `02d05318c60b5f203610185e9ca152ec15276420d3d11060cbbef206cd651797` | The normal loader reads the served profile's `mcp_servers`, honors native safe-worker/safe-mode restrictions and applies its existing filtering. |
| `tools/mcp_tool.py`, SHA256 `19059b5aadcaee0ac1ec8fbbfbaf30d090397dfdc92cf729e755e2221363d60e` | Live connections are keyed by owner scope plus server name under multiplexing. Two profiles using the same alias with different credentials remain separate connections. |
| `tools/mcp_tool_transport.py`, `_build_oauth_auth`, SHA256 `4d2fc8bb580e9a292ee9314da9cc13a7b929b583f83f751dfd97e543688426cb` | Streamable HTTP uses the central manager's existing OAuth provider, including reconnect reuse. |
| `tools/mcp_oauth_manager.py`, `_key`, SHA256 `5574bca545ba6507e3b30ead7c89a37962a1e87adaf04040d141eeb592ec1bea` | Credential/provider entries are keyed by resolved Hermes profile home and server name. The process-wide manager is not a cross-profile identity assertion. |
| `tools/mcp_oauth.py`, SHA256 `b25655d6a2ca717b3697f2fe98b5f817da5605c203ebdce8823da55398a8b99f` | Existing `HermesTokenStorage` uses the selected home’s `mcp-tokens` directory. Only source code was read; no token files were opened. |
| `tools/mcp_tool_handlers.py`, SHA256 `f29475bde493fb93f55ca16ca53a845b703f87b851ba85770a90f3b5369c58b7` | Calls use the captured server and its RPC lock/in-flight owner. Trust and cost policy remain the calling profile's own. |

The source search also reaches existing `register_mcp_servers` consumers in
`gateway/session_local_mcp.py` and the normal discovery owner
`tools/mcp_tool_discovery.py`. These are genuine ordinary tool lifecycle seams,
not evidence that a particular Paperclip profile currently has an enrolled
Executive connection. No model, worker, gateway or service was launched.

## Two independent API contracts

**Requester return:** the existing `coo.requester_return.v1` catalogue needs
only the Executive OAuth resource. Its host-frozen selected child, actual
Runtime claim, canonical result and explicit original-requester ACK can be
reused by a separately reviewed Paperclip API profile. A Paperclip profile
must not borrow the Hermes native or T3 API profile/grant. The new T3 API source
phase qualifies this same wire family without native-origin claims; it does
not enroll Paperclip or grant it admission.

**Project help:** `coo.project_help.v1` requires independently authenticated
Executive and Workspace bearers on the same request. The actual API proof
supplies both disposable signed tokens. It does not prove that ordinary
installed Hermes profiles can acquire and refresh the companion automatically.

The existing source qualification at Mastermind
`95762fc3700598a7be1a12b8c6c1995753071eed`, under
`integrations/hermes_qualification/workspace_oauth_privacy/`, extends the
incumbent OAuth manager/storage/refresh/HTTP owners for a fixed Workspace
companion. It targets Hermes `1c0cd667746d3395fe9e1b6c74f8f85952486f18` with
nine-file patch digest
`1d1df9a1fde6654d1690715e52ed10524c6b1b4d9af24b406243324d212146ce`.
The current installed source search found neither
`mastermind.hermes_workspace_oauth.v1` nor
`x-mastermind-workspace-authorization` in the ordinary tools/CLI code. That
extension therefore needs exact-current-source composition and qualification
through the incumbent Hermes cutover owner before installed help coverage can
be claimed. A static token header, token extraction, generic HTTP helper or
Paperclip JWT substitution would not close the credential-owner boundary.

## Smallest next safe source work

Add a distinct disabled Paperclip API profile and exact catalogue mapping
through the existing capability/installed-mission owners. Preserve the finite
run credential plugin, OMH runtime, managed-role instructions and project
bindings. Instructions may provide a work selector; they cannot grant a root,
source scope or execution permission. The existing Workspace/Executive owners
must independently prove the selected work/root/source relationship.

Qualify the exact ordinary Hermes loader and tool dispatch with two disposable
profile homes, their own OAuth managers, the existing signed App and actual
Control/Runtime. Check profile separation, current grant revocation and original
command reconciliation. The help branch additionally needs the paired OAuth
owner's acquire/refresh/no-leak proof. Keep native prefetch and native issue
origin as separate optional contracts.

PR #2403 at `b2b74c2cde0e68fa6af14e0e6bf28d77dc255bda` retains its finite
credential/cutover and original MAS-2 canary ownership. This census neither
modifies that carrier nor activates or repeats its effects.
