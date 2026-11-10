# Native gateway composition and release boundary

Assignment: `hermes-capacity-m2-20261106-c3`. Parent consumer #2155; attended follow-on #2166.
Pinned Hermes source: `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`.

## Generic framework prerequisite

`hermes_core/hermes-2bd378ed-host-bound.patch` is a reviewable, generic framework
extension against that exact upstream source. It is not an installed patch and
the plugin never edits core. It requires inclusion in the legitimate protected
Hermes release before the general plugin can register.

The registered `ProviderProfile.host_bound_runtime` flag lets the CLI resolve a
route without an API key, endpoint, credential pool or dummy secret. Only an
explicitly registered provider can use the flag. Ordinary providers retain their
credential checks. Nonempty credential/endpoint overrides refuse.

The existing `TurnRunner.run_sync` ExitStack enters
`provide_gateway_turn_context` after the final model route is resolved, before
native agent reuse or construction. Exactly one context manager must answer.
A missing, failing or ambiguous plugin refuses the turn. Cleanup runs when the
physical synchronous executor unwinds, not when an async observer disconnects.

The existing `SessionAuthority.bind_provider_turn` validates the current native
admission in its SQLite store and consumes one process-local marker on its own
`LiveSession`, under the incumbent event-stream lock. The marker is keyed by
original epoch, generation and admission ID; changing provider, model, plugin
instance or runner does not create a new claim. It is retained on failure and
close. Native restart/unknown recovery remains the only recovery owner. No
second admission, lease, retry, history or settlement registry is added.

## Consumer composition

Install the complete buildable adapter root and its companion `model_provider`
entry through the existing native PM after source release. The root general-plugin
entry and early provider import the same canonical
`integrations.hermes_application_fabric` package. Installing only the old
`gateway_plugin_entry` wrapper is insufficient. The existing PluginManager owns
hook/middleware registrations and unload; see [installation](ATTENDED_INSTALLATION.md).

`gateway_plugin.py` consumes the original admitted local turn, supplies its
admission ID as the original APPLICATION operation ID, and resolves the
dedicated attended factory using the original `make_application_fabric_factory`.
The factory comes from the exact Macro projection inside the selected sealed
Executive release. The verified source context holds its complete config/engine/lib
closure through catalog inspection and each admitted turn, without ambient
checkout imports. There is no config string that can import an alternate factory
or supply a provider key/URL.

Native primary model calls, tool calls/results, history and interruption remain
inside Hermes. Reused agents resolve the current turn through the same
middleware; they do not retain an earlier turn's APPLICATION owner.

The explicit AUTO label uses the original attended automatic descriptor. A concrete
model under an AUTO enrollment narrows that same owner before inspection freezes;
a fixed enrollment refuses AUTO. Selection may change between admitted turns,
while a turn and its tools retain the original binding. Unsupported reasoning or
streaming options continue to refuse rather than being silently dropped.

## Qualified and unqualified surfaces

The new qualification suite runs against an immutable archive of the pinned
upstream source plus this patch, using the installed native runtime dependencies,
an isolated HERMES_HOME and the original checksum-verified APPLICATION client.
The installed launcher holds its native dependency lease while a clean child
uses the current in-memory dependency search paths and the patched fixture.
This avoids retaining pre-imported installed core modules; no selected dependency
generation path is written into a launcher or persisted for later reuse.
It exercises real CLI resolution, native SQLite admission, atomic duplicate
entry, generation/Stop/restart fencing, native gateway hook entry and primary
model execution over a loopback fixture. It is not a live provider canary.

The ordinary local in-process gateway is the target. Managed worker processes,
API-server direct construction, background/auxiliary calls and non-local chat
identities do not inherit this admission and remain unqualified. The keyless
facade refuses when unbound; they must not be enabled by adding placeholder
credentials or borrowing the attended identity.

Production acceptance still needs the original owner enrollment and release,
the complete qualified serving endpoint, a real account/model/tool/usage
conversation, verified settlement, and original C1/C3/C4 hold disposition.
Neither this artifact nor passing tests authorizes activation or resolves those
holds.
