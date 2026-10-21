# Codex Stop return subscriptions

The existing root-only hook provides active Stop attention for explicitly
subscribed runs. It does not provide idle Wake, authenticated RuntimeBinding,
result consumption or acceptance. A native coordinator consumes its own child
through the foreground adapter path.

## Inspect the installed binding before relying on native return

From a qualified Mastermind source checkout, inspect the actual configured hook
file without executing its commands:

```sh
python3 -B -m integrations.session_bridge.fabric_stop_preflight \
  --hooks-file /ABSOLUTE/CODEX/HOME/hooks.json
```

The preflight reads the configured direct Python Stop definitions, the named
helper and adapter source, and directory ownership/mode. It reports each expected
and observed adapter digest. An adapter upgrade can leave the old hook trusted
while its source pin refuses every result; `adapter_source_changed` makes that
condition explicit before another project relies on it. Hash-named hook drift,
invalid fixed identities, unsupported shell commands, unsafe paths and invalid
handler fields also fail the static check. Quoted ordinary paths with spaces are
supported; shell expansions and control syntax are deliberately unsupported.

Exit 0 means only that the inspected static checks matched. Exit 78 means a
binding is absent, changed, unavailable or outside the supported command form.
The report names every configured Fabric Stop definition; select the binding
applicable to the intended parent/mode when evaluating a historical fixed-run
entry beside a general subscription entry. An unrelated historical failure does
not authorize altering that operation or block ordinary foreground Fabric work.

The checker does not read worker results or subscription contents, create locks
or attention attempts, dispatch, replay, accept work, change settings, or write
native trust. It records native loading and native delivery as UNOBSERVED. A
matching digest is not evidence that the installed adapter release was reviewed,
that Codex trusted/loaded the definition, or that a real return was consumed.
Resolve a failed binding through the current source/installation owner, then
obtain the actual native review/trust and original-session delivery proof below.

The 32-entry bound applies to active attention subscriptions. An original parent
may explicitly retire an accepted subscription using the same local owner:

```sh
python3 <installed-ext>/fabric_stop_return.py --retire-accepted \
  --root <verified-original-CODEX_THREAD_ID> --run <accepted-run-id> \
  --adapter <installed-ext>/fabric_task.py --adapter-sha256 <verified-current-hash> \
  --subscribed-state-dir <installed-ext>/state/native_return
```

Retirement reads two identical exact-parent accepted status projections, archives
the original index, attention attempts and acceptance snapshot, then removes the
attempt before removing its subscription. It preserves the worker's log, result
and outcome ledger. The per-run archive prevents resubscription. Interrupted
writes remain closed for explicit recovery; elapsed time or prepared attention
never permits removal. Later revocation does not rewrite the historical snapshot.
Retirement does not authorize a worker retry or reset any budget.

The hook definition pins both hook code and adapter bytes. After an adapter change,
the old pin refuses return delivery. Install a separately reviewed current hook
definition and obtain Codex's required review/trust; never change a hash-named
trusted script behind its existing definition. Test fixtures or manual invocation
do not establish native delivery. The retirement CLI returns explicit failures;
normal hook failures remain quiet.
