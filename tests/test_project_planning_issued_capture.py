"""Immediate real issued CODE proof; mutations are adverse in-process fixtures.

The production owner never restores a consumed proof. The test restores the
same actual producer token between independent corruption cases solely to
exercise closed guards without reissuing authority or touching Runtime state.
"""
import asyncio
import dataclasses
import time
import pytest
from tests.test_project_journey_canonical_create import joined,owner,env,isolated_git_env,identity
from tests.test_project_planning_factory import invocation
from integrations.executive_mcp import installed


def test_actual_issued_proof_is_one_use_and_rejects_corruption_or_expiry(joined):
    j=joined;factory,args=j['factory'],j['args']
    def exercise():
        data=factory._canonical_data();workspace=j['workspace']
        view=data.view(workspace,work_ref=args['work_ref'])
        key=installed._CANONICAL_CODE_CAPTURE;proof=view._verified_facts[key]
        def accept(selected=view):
            return factory._accept_new_canonical_view(data,selected,workspace=workspace,work_ref=args['work_ref'])
        assert accept() is view and key not in view._verified_facts
        with pytest.raises(ValueError):accept()
        altered=[object(),
            dataclasses.replace(proof,owner=object()),
            dataclasses.replace(proof,binding=()),
            dataclasses.replace(proof,view=object()),
            dataclasses.replace(proof,view_identity=()),
            dataclasses.replace(proof,observations=()),
            dataclasses.replace(proof,observations=('0'*40,*proof.observations[1:])),
            dataclasses.replace(proof,observations=(proof.observations[0],'0'*40,*proof.observations[2:])),
            dataclasses.replace(proof,macro_snapshot=object())]
        for corrupted in altered:
            view._verified_facts[key]=corrupted
            with pytest.raises(ValueError):accept()
            assert key not in view._verified_facts
        # Coherently rebind the private token to an altered DATA view; the real
        # producer's observation witness still refuses the foreign N.
        foreign=dataclasses.replace(view,data_commit='f'*40,_verified_facts={})
        foreign._verified_facts[key]=dataclasses.replace(proof,view=foreign,
            view_identity=foreign._owner._view_identity(foreign))
        with pytest.raises(ValueError):accept(foreign)
        # Real monotonic expiry; no clock, deadline or principal is extended.
        time.sleep(max(0,view._operation.read_deadline-time.monotonic())+.01)
        view._verified_facts[key]=proof
        with pytest.raises(ValueError):accept()
    before=len(j['runtime'].store.list_events())
    asyncio.run(invocation(factory,args,exercise,operation='result'))
    assert len(j['runtime'].store.list_events())==before
    assert j['runtime'].jobs.list_jobs()==[] and j['runtime'].attempts.list_attempts()==[]
