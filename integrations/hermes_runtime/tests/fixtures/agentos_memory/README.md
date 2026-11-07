# Pinned source data for native Agent OS memory qualification

These fourteen `.py.source` files retain complete MIT-licensed source snapshots
based on Hermes `1c0cd667746d3395fe9e1b6c74f8f85952486f18`. Twelve remain
upstream-identical. `agent__agent_init.py.source` and
`agent__memory_caller_scope.py.source` are the exact `diagnostic_privacy`
postimages required by the v2 runtime. Their provenance keeps original source
URL, byte length, Git blob and SHA-256 under `upstream`, separately from the
derived identities and patch digest. The adjacent original MIT notice remains.

The archive convention matches the accepted request-observation fixtures.
`test_native_agentos_memory.source()` verifies all three byte identities before
materializing the qualified `.py` module path in a disposable vendor directory.
It executes selected pinned AST definitions or complete modules with explicit
environment/SDK/storage edge doubles. Archive packaging does not qualify a
runtime artifact or an installed host.

All fourteen logical Python sources and their actual archive paths traverse the
existing D8 identity guard with injected identity-literal refusal canaries. The
ordinary changed-source guard remains in force. Its `.py.source` language
recognition preserves Python AST/string/alias analysis, including conservative
fallback for invalid Python; this is not a path exemption or numeric allowlist.
No CodeQL configuration or alert disposition is changed.

## Fixed diagnostic privacy derivation

Original e7bd8ae check `128333894473` identified partial-credential output in
`agent/agent_init.py::_print_key_banner` and raw profile-home output in
`agent/memory_caller_scope.py::_refuse`. The latter receives profile-home metadata,
not the secret mapping. Both diagnostic flows are removed in these exact
postimages; shared-instance diagnostics also omit raw profile-home arguments.
The scope and instance refusal decisions remain unchanged.

The existing Executive vendor-derivation owner admits the fixed patch
`ded504ad2d660f14c89527ec74593fcc459485666fbb0994bb92f7b02c878bce`, verifies the
complete upstream-to-derived tree and frozen inventory, and records the same
six-field receipt used by its original computer-only variant. V2 context
consumers require this privacy selection and receipt before factory publication;
the actual runtime pins match these complete fixture postimages. Archive suffix
changes alone are not this source repair.

`tests/test_hermes_diagnostic_privacy.py` reverses the exact patch only in a
disposable test tree to reconstruct independently pinned upstream preimages for
behavior comparisons, then tests the production forward qualifier. No vulnerable
original is substituted at runtime, and no artifact is reverse-patched by the
release owner. Complete fixtures remain visible to the source identity audit.

The ordinary required CI and CodeQL must qualify the resulting exact head.
Source qualification establishes neither an installed derivation receipt nor
host/grant/transport admission, live model execution or original-parent
consumption.

Finding source: [original check annotations](https://github.com/mastermindx-market-intelligence/Mastermind/runs/128333894473).
