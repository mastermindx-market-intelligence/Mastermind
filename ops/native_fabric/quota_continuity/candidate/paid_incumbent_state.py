"""Bind immutable paid controller code to its ONE existing mutable owner.

No new state, credentials, provider or admission is created here. The existing
broker/ledger CLI keeps its own decisions, locks, writes and return codes.
Manual and finite entrypoints do not invoke this private composition.
"""
from __future__ import annotations
import importlib
import os
from pathlib import Path
import sys

OWNER = Path('/Users/chriswong/.claude/projects/-Users-chriswong-Documents-Cluade-Macro-Dashboard/handoff_kits/meta-ceo-b-2026-09-08/ext')
HERE = Path(__file__).resolve().parent


def configure(name):
    if (name != 'lease_broker'
            or os.environ.get('FABRIC_CANONICAL_PAID_MODE') != 'sealed-model-only-v1'
            or os.environ.get('FABRIC_CANONICAL_PAID_STATE_EXT') != str(OWNER)):
        raise ValueError('canonical_paid_state_refused')
    expected = dict(POOL_BROKER_DB=str(OWNER/'broker/leases.sqlite'),
        POOL_BROKER_LOCK=str(OWNER/'broker/leases.lock'),
        POOL_ACCOUNTS_YAML=str(OWNER.parent/'orch/fabric/accounts.yaml'),
        POOL_STATUS_JSON=str(OWNER.parent/'orch/fabric/status.json'),
        POOL_LEDGER_PATH=str(OWNER.parent/'orch/fabric/ledger.jsonl'))
    if any(os.environ.get(k) != v for k,v in expected.items()):
        raise ValueError('canonical_paid_state_refused')
    # All executable modules remain the same root-qualified release source.
    # Only already-existing mutable DATA coordinates are bound below.
    def load(module_name):
        module=importlib.import_module(module_name)
        if Path(module.__file__).resolve()!=HERE/(module_name+'.py'):
            raise ValueError('canonical_paid_state_refused')
        return module
    quota=load('quota_remote')
    quota.CACHE_PATH=str(OWNER/'quota_cache.json')
    quota.BAILIAN_USAGE=str(OWNER/'bailian_usage.json')
    module=load(name)
    module.HOSTS_JSON=str(OWNER/'hosts.json')
    module.GROK_EXHAUSTED=str(OWNER/'GROK_EXHAUSTED')
    return module


def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    try:
        if not argv:raise ValueError
        if str(HERE) not in sys.path:sys.path.insert(0,str(HERE))
        module=configure(argv[0])
    except Exception:
        print('CANONICAL_PAID_STATE_REFUSED before_lease=1',file=sys.stderr)
        return 78
    return module.main(argv[1:])


if __name__=='__main__':
    raise SystemExit(main())
