"""The original Brain bridge must recheck source at actual model dispatch.

No actual model, provider API, portfolio writer or capital operation runs.
"""
from datetime import datetime, timezone
import pytest
from tests.test_overnight_source_admission import synthetic


@pytest.mark.parametrize("module", ["autonomous","china","hk"])
def test_revoked_during_expensive_prompt_build_never_enters_bridge(monkeypatch,module):
    from data_layer import overnight
    from brain import cli_bridge
    from bot import overnight as watch
    import importlib
    runner=importlib.import_module("bot."+module)
    granted={"valid":True}
    monkeypatch.setattr(overnight,"_host_live_source_admitted",lambda _:granted["valid"])
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    directive=watch.QualifiedOvernightDirective(
        "OVERNIGHT REVIEW — source-qualified LIVE, synthetic only",packet,
    )
    def slow_build(*_args,**_kwargs):
        granted["valid"]=False
        return "prompt constructed before source revocation"
    monkeypatch.setattr(runner,"_build_prompt",slow_build)
    monkeypatch.setattr(cli_bridge,"reason",
                        lambda *_args,**_kwargs:pytest.fail("revoked source entered model"))
    with pytest.raises(ValueError,match="unqualified overnight evidence"):
        runner._run_brain("2026-10-15",False,directive=directive)


@pytest.mark.parametrize("module", ["autonomous","china","hk"])
def test_unwrapped_live_claim_cannot_bypass_dispatch_guard(monkeypatch,module):
    from brain import cli_bridge
    import importlib
    runner=importlib.import_module("bot."+module)
    monkeypatch.setattr(runner,"_build_prompt",lambda *_a,**_k:"synthetic prompt")
    monkeypatch.setattr(cli_bridge,"reason",
                        lambda *_a,**_k:pytest.fail("unwrapped live directive entered model"))
    with pytest.raises(ValueError,match="unqualified overnight evidence"):
        runner._run_brain("2026-10-15",False,
                          directive="OVERNIGHT REVIEW — claimed live by caller")


@pytest.mark.parametrize("module", ["autonomous", "china", "hk"])
def test_whitespace_normalized_live_directive_requires_original_source(monkeypatch,module):
    from brain import cli_bridge
    import importlib
    runner=importlib.import_module("bot."+module)
    monkeypatch.setattr(runner,"_build_prompt",lambda *_a,**_k:"synthetic reserved directive rendered")
    monkeypatch.setattr(cli_bridge,"reason",
                        lambda *_a,**_k:pytest.fail("unqualified directive entered model"))
    with pytest.raises(ValueError, match="unqualified overnight evidence"):
        runner._run_brain("2026-10-15",False,
                          directive="  \n\t OVERNIGHT REVIEW — claimed LIVE by caller")


@pytest.mark.parametrize("module", ["autonomous", "china", "hk"])
def test_source_revoked_between_coroutine_creation_and_backend_dispatch(monkeypatch,module):
    import asyncio
    import importlib
    from brain import cli_bridge
    from data_layer import overnight
    from bot import overnight as watcher
    runner=importlib.import_module("bot."+module)
    grant={"valid":True}
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        lambda _t:grant["valid"])
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    qualified=watcher.QualifiedOvernightDirective(
        "OVERNIGHT REVIEW — source-qualified LIVE synthetic only",packet)
    monkeypatch.setattr(runner,"_build_prompt",
                        lambda *_a,**_k:"synthetic prompt while permitted")
    async def provider_must_not_start(*args,**kwargs):
        pytest.fail("source was revoked before coroutine dispatch")
    monkeypatch.setattr(cli_bridge,"reason",provider_must_not_start)
    def scheduled_after_revocation(coro):
        grant["valid"]=False
        return asyncio.run(coro)
    monkeypatch.setattr(runner,"_run_coro",scheduled_after_revocation)
    with pytest.raises(ValueError,match="unqualified overnight evidence"):
        runner._run_brain("2026-10-15",False,directive=qualified)


@pytest.mark.parametrize("module", ["autonomous", "china", "hk"])
def test_mcp_preparation_revocation_refused_before_async_provider_bridge(
    monkeypatch,module,
):
    import asyncio
    import importlib
    from brain import cli_bridge
    from bot import overnight as watcher
    from data_layer import overnight
    runner=importlib.import_module("bot."+module)
    server=importlib.import_module("brain."+module+"_mcp")
    grant={"valid":True}
    monkeypatch.setattr(overnight,"_host_live_source_admitted",
                        lambda _t:grant["valid"])
    packet=synthetic(datetime.now(timezone.utc),change=-2.0)
    directive=watcher.QualifiedOvernightDirective(
        "OVERNIGHT REVIEW — source-qualified test",packet)
    monkeypatch.setattr(runner,"_build_prompt",
                        lambda *_args,**_kwargs:"synthetic source-checked prompt")
    def revoke_during_mcp():
        grant["valid"]=False
        return {}
    monkeypatch.setattr(server,"build_servers",revoke_during_mcp)
    monkeypatch.setattr(server,"allowed_tools",lambda:[])
    async def no_provider(*_args,**_kwargs):
        pytest.fail("revoked in MCP setup but entered async provider bridge")
    monkeypatch.setattr(cli_bridge,"reason",no_provider)
    monkeypatch.setattr(runner,"_run_coro",asyncio.run)
    with pytest.raises(ValueError,match="unqualified overnight evidence"):
        runner._run_brain("2026-10-15",False,directive=directive)
