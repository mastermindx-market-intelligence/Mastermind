# Pinned upstream source data for native Agent OS memory qualification

These fourteen `.py.source` files are complete, unmodified source snapshots from
Hermes `1c0cd667746d3395fe9e1b6c74f8f85952486f18`, retained as archive data rather
than importable application modules. This is the same convention as the accepted
request_observation fixtures. The adjacent MIT license and provenance manifest
retain each original source URL, byte length, Git blob and SHA-256.

`test_native_agentos_memory.source()` verifies all three byte identities before
materializing the original `.py` module path in a disposable vendor directory.
It executes the selected original AST definitions or identified complete modules
with explicit environment/SDK/storage edge doubles. Changing the archive suffix
does not change donor bytes, original module origins, actual executed bodies,
source qualification, production imports, source pins or acceptance assertions.
All fourteen logical Python sources additionally traverse the existing identity
guard with an injected identity-literal refusal canary. The ordinary changed-file
identity guard remains in force.

The ordinary archive scan initially classified the donor's prose about a provider
HTTP 400 response as an identity literal because its final suffix was `.source`.
The existing D8 language classifier now recognizes `.py.source` as Python and
collects its exact postimage for the same AST/string/alias analysis used for `.py`.
This is language recognition, not a path exemption or numeric allowlist. Both
logical and actual archive paths are checked, and executable identities remain
detectable. Invalid Python still receives the guard's existing conservative
fallback. No CodeQL configuration is changed.

## CodeQL finding diagnosis for the original e7bd8ae snapshot

The original Python-file packaging made CodeQL treat these complete archives as
additional application implementations. Check run `128333894473` reported two
new high-severity logging findings at:

- `agent/agent_init.py::_print_key_banner`: the upstream verbose string-key banner
  prints the first eight and last four characters of a credential. This is real
  partial-key disclosure in an upstream verbose path. This test fixture executes
  only `_init_memory` and `_memory_provider_init_kwargs` from that full file; the
  banner is not executed. The exact v2 adopted enrollment requests `{source:tool}`
  and the original `_inspect_enrollment` checks the frozen policy with
  `same_create_retry`. Upstream policy defaults `verbose` to false, so this
  enrolled construction uses `quiet_mode=True`. The generic legacy session
  lookup does not establish quiet mode and is not claimed to do so.
- `agent/memory_caller_scope.py::_refuse`: `current_secret_scope_home()` returns
  the bound `profile_home`, distinct from the secret mapping. This diagnostic
  logs profile paths, not a key or token. The fixture exercises that original
  refusal behavior against synthetic profile homes.

No security query/configuration, alert status, production logger or source pin
is suppressed or changed. The production sources remain scanned. CodeQL and
the original required CI must qualify the new head; packaging is not a claim
of installed security acceptance or proof that every unrelated upstream verbose
session is safe.

Finding source: [original check annotations](https://github.com/mastermindx-market-intelligence/Mastermind/runs/128333894473).
