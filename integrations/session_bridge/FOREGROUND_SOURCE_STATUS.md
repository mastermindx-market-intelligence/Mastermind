# Finite foreground request source

The installed Session Bridge owns semantic validation and authentication. Its
private duplex framing uses one bounded request and response on the same socket.
The framing distinction supplies no grant: the handler checks the current App
binding, armed service, original kernel peer and exact connection, including EOF
and transport closure. Legacy queued framing and session send/read behavior retain
their existing semantics.

`control_plane.foreground_operation.current_foreground_operation()` exposes one
in-process handle inside the actual awaited duplex summon handler. It captures
the normalized request and operation key, original principal identity, actual
READ/SUBMIT scopes and live principal window. The private canonical sink observer
binds only the fresh committed root; duplicate receipts, losing submissions,
caller booleans and pre-existing roots cannot supply that observation. Root event
identity is checked again before canonical claim. Post-commit loss retains the
original root and maps to `effect_unknown`, with no replay or substitute Job.

`require_root(root_id)` is the source check before the existing canonical claim.
After claim, `start_receipt(binding, physical_digest, start_request_digest)` binds
the exact current LAUNCH claim and immutable commission to this same invocation.
The incumbent transport owner must independently derive both transport digests.
`require_start` rechecks the exact in-process receipt instance and live source;
`as_dict()` exports inert evidence. The source closes on return, error or cancel,
including for copied async contexts. Runtime launch pins and the original
controller reservation remain authority; this source does not fence all async
network or Runtime effects.

Current summon behavior still returns the canonical queued receipt without
launching work. A real finite attended producer must keep the same handler open
through actual ordinary sealed-plan admission and the original exact dispatch's
full START. Its claim/router and Backend must recheck this source. Queued ticks,
`PLANNER_CREATED`, early process handshakes, profiles and receipt data are not
attendance. The incumbent client read deadline is ten seconds; any following
finite deadline extension needs actual composition and transport evidence.

The bounded native-return profile retains its no-child rule. Paid work requires
the existing ordinary planner/plan admission and an explicitly qualified work
placement. The separate original Fabric owner supplies Backend, supported
harness, physical realm, isolation and assignment withdrawal. This component
adds no worker registry, scheduler, conversation store, listener or retry system.

Local tests exercise real Runtime admission and local Unix/kernel peer paths;
external provider and production host boundaries remain fixtures. This source
component does not establish installation, active profile selection, production
START, GUI conversation writer adoption, idle Wake or exact-parent native result
consumption. C1 remains frozen. The full native result mission remains open.
