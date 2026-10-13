"""Native terminalization must not wait for slow subscribed HTTPS notification.

This is an isolated Executive source seam with fake Runtime and supervisor.
It does NOT run any native work, JWT issuance, Runtime write or network I/O.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from control_plane.executive_runtime import AttemptStatus
from control_plane.executive_service import ExecutiveControlService, _NativeOperatorDispatch


def test_verified_native_reply_can_terminalize_while_callback_remains_pending():
    async def scenario():
        callback_entered = asyncio.Event()
        release_callback = asyncio.Event()
        finished_native = asyncio.Event()
        terminal_projection = asyncio.Event()
        calls = []

        retained = SimpleNamespace(lease=SimpleNamespace(
            attempt=SimpleNamespace(attempt_id="attempt-001"),
            lease_token="lease-test-only",
        ), job=SimpleNamespace(root_job_id="root-001"))
        current_attempt = SimpleNamespace(attempt_id="attempt-001",status=AttemptStatus.RUNNING)
        runtime = SimpleNamespace(
            attempts=SimpleNamespace(get_attempt=lambda key: current_attempt),
            jobs=SimpleNamespace(get_job=lambda key: SimpleNamespace(job_id=key)),
        )

        class Supervisor:
            async def start_retained_native_job(self, job, *, command_id):
                calls.append("start")
                return retained

            def retain_native_wait_window(self, value):
                assert value is retained

            async def run_native_continuation(self, value, *, source, read_ref):
                assert value is retained and read_ref == "read-ref-001"
                calls.append("native-reply")

            async def finish_retained_native_job(self, value):
                assert value is retained
                calls.append("finish-native")
                finished_native.set()

            async def abort_retained_native_job(self,*args,**kwargs):
                calls.append("aborted")
                return False

        class OriginalSource:
            async def require_committed_native_reply(self, *, read_ref):
                assert read_ref == "read-ref-001"
                calls.append("canonical-committed")
                return {"reply_committed": True,
                        "message_key":"asd-native-reply-"+ "a"*40,
                        "fingerprint":"b"*64,"parent_consumed":False}

        class DummyService:
            _service_state = "READY"
            _closing = False
            _dispatch_errors = {}
            _physical_workers = set()

            def __init__(self):
                self._supervisor=Supervisor()
                self._runtime=runtime
                self._native_operator_dispatch=None
                self._dispatch_tasks={}

            def _require_operator_supervisor(self):
                return self._supervisor

            def _require_runtime(self):
                return self._runtime

            async def _run_owned_coroutine(self, coroutine):
                return await coroutine

            async def _signal_native_continuation(self):
                return None

            def _native_return_source(self, _root):
                return None

            async def _notify_native_reply_events(self, read_ref, committed):
                assert read_ref == "read-ref-001" and committed["reply_committed"] is True
                calls.append("callback-start")
                callback_entered.set()
                await release_callback.wait()
                calls.append("callback-finished")

            async def _project_terminal_return(self, job_id, *, expected_attempt_id):
                assert job_id == "job-001" and expected_attempt_id == "attempt-001"
                calls.append("terminal-projected")
                terminal_projection.set()

            def _schedule_native_reply_events(self, read_ref, committed):
                return ExecutiveControlService._schedule_native_reply_events(
                    self, read_ref, committed)

        owner=DummyService()
        from common.reply_subscription_private_contract import ReplyEventCommitConsumer
        owner._company_consultation_host=SimpleNamespace(
            reply_event_consumer=ReplyEventCommitConsumer(runtime,lambda **kw:None))
        owner._ceo_ingress_app_binding=SimpleNamespace(
            armed=True,reply_event_provider_factory=lambda _runtime:None)
        loop=asyncio.get_running_loop()
        start=loop.create_future()
        continuation=loop.create_future()
        continuation.set_result("read-ref-001")
        dispatch=_NativeOperatorDispatch(
            job_id="job-001",command_id="command-001",
            started=start,continuation=continuation,source=OriginalSource(),
        )
        owner._native_operator_dispatch=dispatch
        task=asyncio.create_task(
            ExecutiveControlService._run_native_operator_dispatch(owner,dispatch))
        owner._dispatch_tasks["job-001"]=task
        try:
            await asyncio.wait_for(terminal_projection.wait(),timeout=0.5)
            assert finished_native.is_set()
            assert start.done()
            assert owner._service_state=="READY" and not owner._dispatch_errors
            assert "aborted" not in calls
            assert "callback-finished" not in calls
            assert len(owner._physical_workers)==1
            release_callback.set()
            await asyncio.wait_for(task,timeout=1)
            await asyncio.wait_for(callback_entered.wait(),timeout=1)
            for pending in tuple(owner._physical_workers):
                await asyncio.wait_for(pending,timeout=1)
            assert "callback-finished" in calls
            assert "finish-native" in calls
        finally:
            release_callback.set()
            for pending in tuple(owner._physical_workers):
                pending.cancel()
            await asyncio.gather(task,*tuple(owner._physical_workers),return_exceptions=True)

    asyncio.run(scenario())


def test_callback_owner_failure_does_not_escape_after_native_commit():
    from common.reply_subscription_private_contract import ReplyEventCommitConsumer

    async def scenario():
        class FailingConfiguration:
            _closing=False
            _service_state="READY"
            _physical_workers=set()

            def __init__(self):
                self._company_consultation_host=SimpleNamespace(
                    reply_event_consumer=ReplyEventCommitConsumer(
                        runtime=object(),handler=lambda **kwargs:None))
                self._ceo_ingress_app_binding=SimpleNamespace(
                    armed=True,reply_event_provider_factory=lambda _:None)

            def _require_runtime(self):
                raise RuntimeError("Runtime unavailable during post-commit notification")

            async def _notify_native_reply_events(self,*args):
                raise AssertionError("no callback should have been scheduled")

        host=FailingConfiguration()
        ExecutiveControlService._schedule_native_reply_events(
            host,"read-ref-001",{"reply_committed":True})
        assert host._physical_workers==set()

    asyncio.run(scenario())


def test_disarmed_notification_has_no_new_service_tasks():
    from common.reply_subscription_private_contract import ReplyEventCommitConsumer

    async def scenario():
        owned_runtime=object()
        class DisarmedHost:
            _closing=False
            _service_state="READY"
            _physical_workers=set()
            _company_consultation_host=SimpleNamespace(
                reply_event_consumer=ReplyEventCommitConsumer(
                    runtime=owned_runtime,handler=lambda **kwargs:None))
            _ceo_ingress_app_binding=SimpleNamespace(
                armed=False,reply_event_provider_factory=lambda _:None)

            def _require_runtime(self):
                raise AssertionError("disarmed host must not read Runtime")

            async def _notify_native_reply_events(self,*args):
                raise AssertionError("disarmed host must not notify")

        host=DisarmedHost()
        ExecutiveControlService._schedule_native_reply_events(
            host,"read-ref-001",{"reply_committed":True})
        assert host._physical_workers==set()

    asyncio.run(scenario())


def test_existing_executive_service_shutdown_drain_retains_pending_callback():
    from common.reply_subscription_private_contract import ReplyEventCommitConsumer

    async def scenario():
        owned_runtime = object()
        entered = asyncio.Event()
        release = asyncio.Event()

        class ExistingOwner:
            _closing=False
            _service_state="READY"
            _physical_workers=set()
            config=SimpleNamespace(shutdown_grace_seconds=1.0)
            _ceo_ingress_app_binding=SimpleNamespace(
                armed=True,reply_event_provider_factory=lambda _:None)
            _company_consultation_host=SimpleNamespace(
                reply_event_consumer=ReplyEventCommitConsumer(
                    runtime=owned_runtime,handler=lambda **kw:None))

            def _require_runtime(self):
                return owned_runtime

            async def _notify_native_reply_events(self,*args):
                entered.set()
                await release.wait()

        host=ExistingOwner()
        ExecutiveControlService._schedule_native_reply_events(
            host,"read-ref-001",{"reply_committed":True})
        await asyncio.wait_for(entered.wait(),timeout=1)
        assert len(host._physical_workers)==1
        drain=asyncio.create_task(ExecutiveControlService._drain_service_tasks(
            host,host._physical_workers))
        await asyncio.sleep(0)
        assert not drain.done()  # Explicit existing service owner retains custody.
        release.set()
        await asyncio.wait_for(drain,timeout=1)
        await asyncio.sleep(0)
        assert all(task.done() for task in host._physical_workers)

    asyncio.run(scenario())
