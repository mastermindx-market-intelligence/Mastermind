# Codex Stop return subscriptions

The existing root-only hook provides active Stop attention for explicitly
subscribed runs. It does not provide idle Wake, authenticated RuntimeBinding,
result consumption or acceptance. A native coordinator consumes its own child
through the foreground adapter path.

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
