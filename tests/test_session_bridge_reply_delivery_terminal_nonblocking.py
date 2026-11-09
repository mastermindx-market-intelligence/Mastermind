"""Native terminalization must not wait for slow subscribed HTTPS notification.

This is an isolated Executive source seam with fake Runtime and supervisor.
It does NOT run any native work, JWT issuance, Runtime write or network I/O.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from control_plane.executive_runtime import AttemptStatus
from control_plane.executive_service import ExecutiveControlService, _NativeOperatorDispatch


def _canonical_reply():
    """Authentic closed V2 Dialogue shape; unlike the native writer's receipt."""
    from common.agent_dialogue_contract_v2 import MESSAGE_SCHEMA_V2, build_message_v2
    from tests.test_session_bridge_native_reply import ACTOR, APPLIES, COMMISSION, REQUEST
    return build_message_v2({
        "schema":MESSAGE_SCHEMA_V2,
        "message_key":"asd-native-reply-"+"a"*40,
        "message_type":"PROGRESS",
        "work_ref":"WS:DOT-BRIDGE",
        "commission_ref":COMMISSION,
        "session_ref":"asd-session-dotbridge01",
        "actor_ref":ACTOR,
        "reply_to_message_key":REQUEST,
        "applies_to":APPLIES,
        "summary":"Native session replied to the current executive message.",
        "body":{"stage":"message_reply","completed":"Source finding.","next":"Continue."},
        "evidence_refs":[],
        "requires_response":False,
        "created_at":"2026-10-01T20:00:00Z",
    })


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
                return _canonical_reply()

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

            async def _project_terminal_return(self, job_id, *, expected_attempt_id):
                assert job_id == "job-001" and expected_attempt_id == "attempt-001"
                calls.append("terminal-projected")
                terminal_projection.set()

            def _schedule_native_reply_events(self, read_ref, committed):
                return ExecutiveControlService._schedule_native_reply_events(
                    self, read_ref, committed)

        owner=DummyService()
        from common.reply_subscription_private_contract import ReplyEventCommitConsumer

        async def delayed_consumer(**kwargs):
            assert kwargs["read_ref"]=="read-ref-001"
            calls.append("callback-start")
            callback_entered.set()
            await release_callback.wait()
            calls.append("callback-finished")

        owner._company_consultation_host=SimpleNamespace(
            reply_event_consumer=ReplyEventCommitConsumer(runtime,delayed_consumer))
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

        async def slow_owned_consumer(**kwargs):
            entered.set()
            await release.wait()

        class ExistingOwner:
            _closing=False
            _service_state="READY"
            _physical_workers=set()
            config=SimpleNamespace(shutdown_grace_seconds=1.0)
            _ceo_ingress_app_binding=SimpleNamespace(
                armed=True,reply_event_provider_factory=lambda _:None)
            _company_consultation_host=SimpleNamespace(
                reply_event_consumer=ReplyEventCommitConsumer(
                    runtime=owned_runtime,handler=slow_owned_consumer))

            def _require_runtime(self):
                return owned_runtime

        host=ExistingOwner()
        ExecutiveControlService._schedule_native_reply_events(
            host,"read-ref-001",_canonical_reply())
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


def test_already_scheduled_notification_survives_shutdown_start_before_task_runs():
    from common.reply_subscription_private_contract import ReplyEventCommitConsumer

    async def scenario():
        called = asyncio.Event()
        owned_runtime=object()

        canonical = _canonical_reply()
        async def authorized_consumer(**kwargs):
            assert kwargs == {
                "read_ref":"read-ref-001","message_key":canonical["message_key"],
                "fingerprint":canonical["fingerprint"],
            }
            called.set()

        class Owned:
            _closing=False
            _service_state="READY"
            _physical_workers=set()
            _ceo_ingress_app_binding=SimpleNamespace(
                armed=True,reply_event_provider_factory=lambda _:None)
            _company_consultation_host=SimpleNamespace(
                reply_event_consumer=ReplyEventCommitConsumer(
                    runtime=owned_runtime,handler=authorized_consumer))

            def _require_runtime(self):
                return owned_runtime

            async def _notify_native_reply_events(self,ref,committed):
                return await ExecutiveControlService._notify_native_reply_events(
                    self,ref,committed)

        service=Owned()
        ExecutiveControlService._schedule_native_reply_events(
            service,"read-ref-001",canonical)
        # Service begins a normal owned drain *before* this task has a timeslice.
        service._closing=True
        for pending in tuple(service._physical_workers):
            await asyncio.wait_for(pending,timeout=1)
        assert called.is_set(), "admitted callback must not disappear at shutdown"

    asyncio.run(scenario())


def test_admitted_callback_error_is_not_relabelled_as_native_job_failure():
    from common.reply_subscription_private_contract import ReplyEventCommitConsumer

    async def scenario():
        runtime=object()
        calls=[]

        async def callback(**kwargs):
            calls.append(kwargs["read_ref"])
            raise RuntimeError("synthetic callback transport failed after native COMMIT")

        class Owner:
            _closing=False
            _service_state="READY"
            _physical_workers=set()
            _company_consultation_host=SimpleNamespace(
                reply_event_consumer=ReplyEventCommitConsumer(runtime,callback))
            _ceo_ingress_app_binding=SimpleNamespace(
                armed=True,reply_event_provider_factory=lambda _runtime:None)

            def _require_runtime(self):
                return runtime

        owner=Owner()
        ExecutiveControlService._schedule_native_reply_events(
            owner,"read-ref-001",_canonical_reply())
        assert len(owner._physical_workers)==1
        for pending in tuple(owner._physical_workers):
            await asyncio.wait_for(pending,timeout=1)
            assert pending.exception() is None
        assert calls==["read-ref-001"] and owner._service_state=="READY"

    asyncio.run(scenario())


def test_legacy_native_host_without_optional_reply_event_field_is_noop():
    """Pre-event enabled ceo ingress bindings have no reply_event_provider_factory."""
    from common.reply_subscription_private_contract import ReplyEventCommitConsumer

    class ExistingLegacyHost:
        _closing=False
        _service_state="READY"
        _physical_workers=set()
        _company_consultation_host=SimpleNamespace(reply_event_consumer=None)
        # The installed native-host fixture retains a legacy App binding.
        _ceo_ingress_app_binding=SimpleNamespace(
            armed=True,session_bridge_provider_factory=lambda runtime:None)

        def _require_runtime(self):
            raise AssertionError("disabled notifier must not query Runtime")

    host=ExistingLegacyHost()
    ExecutiveControlService._schedule_native_reply_events(
        host,"fixture-read",{"message_key":"canonical-fixture"})
    assert not host._physical_workers


def test_malformed_optional_notifier_cannot_quarantine_committed_legacy_job():
    class LegacyHost:
        _closing=False
        _service_state="READY"
        _physical_workers=set()
        _company_consultation_host=SimpleNamespace(reply_event_consumer=None)
        _ceo_ingress_app_binding=SimpleNamespace(armed=True)

        def _require_runtime(self):
            raise AssertionError("no optional consumer")

    ExecutiveControlService._schedule_native_reply_events(
        LegacyHost(),"fixture-read",{"message_key":"canonical-fixture"})


def test_legacy_direct_notifier_with_no_optional_provider_is_noop():
    """Direct internal helper must also tolerate the installed legacy App view."""
    class LegacyHost:
        _closing=False
        _service_state="READY"
        _company_consultation_host=SimpleNamespace(reply_event_consumer=None)
        _ceo_ingress_app_binding=SimpleNamespace(
            armed=True,session_bridge_provider_factory=lambda _:None)

        def _require_runtime(self):
            raise AssertionError("unarmed optional notifier may not read Runtime")

    asyncio.run(ExecutiveControlService._notify_native_reply_events(
        LegacyHost(),"fixture-read",
        {"reply_committed":True,"message_key":"canonical-fixture","fingerprint":"f"*64},
    ))


def test_writer_receipt_and_malformed_dialogue_are_not_commit_evidence():
    from common.reply_subscription_private_contract import ReplyEventCommitConsumer
    runtime=object()
    invoked=[]

    async def consumer(**kwargs):
        invoked.append(kwargs)

    class Host:
        _closing=False
        _service_state="READY"
        _physical_workers=set()
        _ceo_ingress_app_binding=SimpleNamespace(
            armed=True,reply_event_provider_factory=lambda _:None)
        _company_consultation_host=SimpleNamespace(
            reply_event_consumer=ReplyEventCommitConsumer(runtime,consumer))

        def _require_runtime(self):
            return runtime

    host=Host()
    canonical=_canonical_reply()
    receipt={"reply_committed":True,"message_key":canonical["message_key"],
             "fingerprint":canonical["fingerprint"],"parent_consumed":False}
    bad_message={**canonical,"fingerprint":"0"*64}
    wrong_stage={**canonical,"body":{**canonical["body"],"stage":"not-message-reply"}}
    for input_record in (receipt,bad_message,wrong_stage):
        ExecutiveControlService._schedule_native_reply_events(
            host,"read-ref-001",input_record)
        assert not host._physical_workers
    assert invoked==[]
