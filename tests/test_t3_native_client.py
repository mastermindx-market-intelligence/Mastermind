import asyncio
import copy
import unittest
from integrations.session_bridge.t3_native_client import (
    Scope, Thread, Run, Cursor, T3NativeClient, Unavailable, Conflict, Rejected, EffectUnknown,
)


def run(awaitable):
    return asyncio.run(awaitable)


def schema(*props):
    return {"type": "object", "properties": {p: {} for p in props}}


SCHEMAS = {
    "orchestrator_capabilities": schema("environmentId", "search"),
    "t3_thread_list": schema("environmentId", "projectId", "cursor", "limit", "includeSubagents"),
    "t3_thread_read": schema("environmentId", "threadId", "view", "limit", "runLimit", "maxCharsPerItem", "afterPosition", "itemId", "textOffset"),
    "t3_thread_launch": schema("environmentId", "projectId", "title", "message", "modelSelection", "workspaceStrategy"),
    "t3_thread_send": schema("environmentId", "threadId", "message", "mode", "clientRequestId"),
    "t3_thread_wait": schema("environmentId", "threadId", "runId", "timeoutMs", "untilDelegatedWorkSettled"),
    "t3_thread_interrupt": schema("environmentId", "threadId", "runId", "reason", "stop", "clientRequestId"),
}
SCOPE = Scope("connected-client-a", "native-env-1", "project-1")
THREAD = Thread(SCOPE, "thread-1")
RUN = Run(THREAD, "run-1", "request-1", "launched")


def item(text="done", *, rid="run-1", pos=1, truncated=False):
    return dict(itemId="item-1", sourceThreadId="thread-1", runId=rid, position=pos,
                type="assistant_message", text=text, textTruncated=truncated,
                nextTextOffset=len(text) if truncated else None)


def observation(items=None, **detail):
    thread = dict(threadId="thread-1", projectId="project-1", status="completed",
                  providerInstanceId="capacity_fabric", model="glm-5.3",
                  activeRunId=None, latestRunId="run-1", pendingRequestCount=0,
                  archived=False, settled=True, updatedAt="2026-11-09T11:00:00Z")
    thread.update(detail)
    return dict(thread=thread, items=[item()] if items is None else items,
                recentRuns=[], nextPosition=1, hasMore=False)


class Native:
    def __init__(self):
        self.calls = []
        self.responses = {}
        self.detail = observation()

    async def __call__(self, name, args):
        self.calls.append((name, copy.deepcopy(args)))
        if name in self.responses:
            value = self.responses[name]
            if isinstance(value, BaseException):raise value
            if callable(value):value = value(args)
            if isinstance(value, BaseException):raise value
            return copy.deepcopy(value)
        if name == "orchestrator_capabilities":
            body = dict(providers=[dict(providerInstanceId="capacity_fabric", canRunChildTask=True,
                        constraints=[], models=[{"id": "glm-5.3"}, {"id": "fabric/fast"}])])
        elif name == "t3_thread_read":body = copy.deepcopy(self.detail)
        elif name == "t3_thread_list":body = dict(threads=[dict(threadId="thread-1", projectId="project-1")], nextCursor=None)
        elif name == "t3_thread_launch":body = dict(threadId="thread-1", projectId="project-1", runId="run-1")
        elif name == "t3_thread_send":
            body = dict(threadId="thread-1", runId="run-2", messageId="message-2",
                        delivery={"queue": "queued", "steer": "steered", "restart": "restarted"}[args["mode"]], status="running")
        elif name == "t3_thread_wait":body = dict(threadId="thread-1", runId="run-1", status="completed", timedOut=False)
        elif name == "t3_thread_interrupt":body = dict(threadId="thread-1", runId=args.get("runId"), status="interrupt_requested")
        else:raise AssertionError(name)
        return dict(structuredContent=body, isError=False)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.native = Native()
        self.client = T3NativeClient(SCOPE, self.native, SCHEMAS)

    def test_only_capacity_provider_can_be_selected(self):
        with self.assertRaises(ValueError):Scope("a", "b", "c", "codex")
        self.assertEqual(run(self.client.capacity_models()), ("glm-5.3", "fabric/fast"))

    def test_launch_uses_exact_capacity_model_and_no_default(self):
        receipt = run(self.client.launch(request_id="task-1", title="Task", prompt="Do bounded work", model="glm-5.3"))
        self.assertEqual(receipt.thread, THREAD)
        args = self.native.calls[-1][1]
        self.assertEqual(args["modelSelection"], {"instanceId": "capacity_fabric", "model": "glm-5.3"})
        self.assertNotIn("clientRequestId", args)  # This native launch has no retry key.
        self.assertEqual(args["environmentId"], SCOPE.environment_id)

    def test_writes_require_exact_worktree(self):
        with self.assertRaises(ValueError):run(self.client.launch(request_id="task", title="x", prompt="y", model="glm-5.3", writable=True))
        self.assertFalse(self.native.calls)
        run(self.client.launch(request_id="task", title="x", prompt="y", model="glm-5.3", writable=True, base_sha="a"*40))
        self.assertEqual(self.native.calls[-1][1]["workspaceStrategy"], {"type": "worktree", "baseRef": "a"*40})

    def test_unknown_model_never_launches(self):
        with self.assertRaises(Rejected):run(self.client.launch(request_id="task", title="x", prompt="y", model="missing"))
        self.assertEqual([x[0] for x in self.native.calls], ["orchestrator_capabilities"])

    def test_unready_capacity_never_falls_back(self):
        for field,value in [("constraints",["missing authentication"]),("canRunChildTask",False)]:
            with self.subTest(field=field):
                row=dict(providerInstanceId="capacity_fabric",canRunChildTask=True,constraints=[],models=[]);row[field]=value
                self.native.responses["orchestrator_capabilities"]={"structuredContent":{"providers":[row]}}
                with self.assertRaises(Rejected):run(self.client.capacity_models())

    def test_duplicate_capacity_rows_fail(self):
        self.native.responses["orchestrator_capabilities"]={"structuredContent":{"providers":[{"providerInstanceId":"capacity_fabric"}]*2}}
        with self.assertRaises(Unavailable):run(self.client.capacity_models())

    def test_schema_capability_is_not_invented(self):
        client=T3NativeClient(SCOPE,self.native,{})
        self.assertFalse(client.capabilities()["lifecycle_extension"])
        with self.assertRaises(Unavailable):run(client.read(THREAD))
        self.assertFalse(self.native.calls)

    def test_unsupported_schema_arguments_refuse_before_call(self):
        schemas=copy.deepcopy(SCHEMAS);schemas["t3_thread_launch"]["properties"].pop("modelSelection")
        client=T3NativeClient(SCOPE,self.native,schemas)
        with self.assertRaises(Unavailable):run(client.launch(request_id="task",title="x",prompt="y",model="glm-5.3"))
        self.assertNotIn("t3_thread_launch",[x[0] for x in self.native.calls])

    def test_scope_cross_connection_refused(self):
        foreign=Thread(Scope("other","native-env-1","project-1"),"thread-1")
        with self.assertRaises(Conflict):run(self.client.read(foreign))
        self.assertFalse(self.native.calls)

    def test_foreign_project_result_refused(self):
        self.native.detail["thread"]["projectId"]="other"
        with self.assertRaises(Conflict):run(self.client.read(THREAD))

    def test_cursor_is_thread_and_connection_bound(self):
        cursor=Cursor(Thread(SCOPE,"other"),4)
        with self.assertRaises(Conflict):run(self.client.read(THREAD,cursor=cursor))
        self.assertFalse(self.native.calls)

    def test_page_does_not_repeat_positions(self):
        with self.assertRaises(Conflict):run(self.client.read(THREAD,cursor=Cursor(THREAD,1)))

    def test_duplicate_timeline_positions_refuse(self):
        self.native.detail["items"]=[item(pos=1),item(pos=1)]
        with self.assertRaises(Unavailable):run(self.client.read(THREAD))

    def test_has_more_without_cursor_refuses(self):
        self.native.detail.update(hasMore=True,nextPosition=None)
        with self.assertRaises(Unavailable):run(self.client.read(THREAD))

    def test_list_project_escape_refuses(self):
        self.native.responses['t3_thread_list']={'structuredContent':{'threads':[{'threadId':'thread-x','projectId':'wrong'}],'nextCursor':None}}
        with self.assertRaises(Conflict):run(self.client.list_threads())

    def test_list_bad_pagination_refuses(self):
        self.native.responses['t3_thread_list']={'structuredContent':{'threads':[],'nextCursor':0}}
        with self.assertRaises(Unavailable):run(self.client.list_threads())

    def test_queued_send_pins_model_and_new_run(self):
        receipt=run(self.client.send(THREAD,request_id='next',message='Continue'))
        self.assertEqual(receipt.run_id,'run-2');self.assertEqual(receipt.delivery,'queued')
        self.assertEqual(self.native.calls[-1][1]['mode'],'queue')
        self.assertEqual(self.native.calls[-1][1]['clientRequestId'],'next')
        self.assertNotIn('freshContext',self.native.calls[-1][1])

    def test_steer_requires_live_run(self):
        with self.assertRaises(Conflict):run(self.client.send(THREAD,request_id='next',message='Clarify',mode='steer'))
        self.native.detail['thread']['activeRunId']='run-1'
        receipt=run(self.client.send(THREAD,request_id='next',message='Clarify',mode='steer'))
        self.assertEqual(receipt.delivery,'steered')

    def test_restart_is_explicit(self):
        self.native.detail['thread']['activeRunId']='run-1'
        receipt=run(self.client.send(THREAD,request_id='next',message='Restart',mode='restart'))
        self.assertEqual(receipt.delivery,'restarted')
        with self.assertRaises(ValueError):run(self.client.send(THREAD,request_id='next',message='x',mode='auto'))

    def test_send_cannot_use_non_capacity_thread(self):
        self.native.detail['thread']['providerInstanceId']='codex'
        with self.assertRaises(Rejected):run(self.client.send(THREAD,request_id='next',message='Continue'))
        self.assertNotIn('t3_thread_send',[x[0] for x in self.native.calls])

    def test_archived_thread_not_resumed_implicitly(self):
        self.native.detail['thread']['archived']=True
        with self.assertRaises(Conflict):run(self.client.send(THREAD,request_id='next',message='Continue'))

    def test_modifying_disconnect_is_unknown_no_replay(self):
        self.native.responses['t3_thread_send']=ConnectionError('secret bearer text')
        with self.assertRaises(EffectUnknown) as caught:run(self.client.send(THREAD,request_id='next',message='Continue'))
        self.assertEqual(caught.exception.thread_id,THREAD.thread_id)
        self.assertNotIn('secret',str(caught.exception))
        self.assertEqual(sum(x[0]=='t3_thread_send' for x in self.native.calls),1)

    def test_modifying_cancel_is_unknown(self):
        self.native.responses['t3_thread_launch']=asyncio.CancelledError()
        with self.assertRaises(EffectUnknown):run(self.client.launch(request_id='task',title='x',prompt='y',model='glm-5.3'))

    def test_read_cancel_propagates(self):
        self.native.responses['t3_thread_read']=asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):run(self.client.read(THREAD))

    def test_native_denial_preserved(self):
        self.native.responses['t3_thread_send']={'isError':True,'structuredContent':{'code':'capability_denied'}}
        with self.assertRaises(Rejected) as e:run(self.client.send(THREAD,request_id='next',message='x'))
        self.assertEqual(e.exception.code,'capability_denied')

    def test_unknown_native_error_is_unknown(self):
        self.native.responses['t3_thread_send']={'isError':True,'structuredContent':{'code':'upstream_timeout'}}
        with self.assertRaises(EffectUnknown):run(self.client.send(THREAD,request_id='next',message='x'))

    def test_malformed_launch_effect_is_unknown(self):
        self.native.responses['t3_thread_launch']={'structuredContent':{'projectId':'wrong','threadId':'thread-2','runId':'run-2'}}
        with self.assertRaises(EffectUnknown):run(self.client.launch(request_id='x',title='x',prompt='x',model='glm-5.3'))

    def test_send_mode_mismatch_is_unknown(self):
        self.native.responses['t3_thread_send']={'structuredContent':{'threadId':'thread-1','runId':'run-2','messageId':'m2','delivery':'restarted'}}
        with self.assertRaises(EffectUnknown):run(self.client.send(THREAD,request_id='x',message='x'))

    def test_stop_does_not_require_capacity_or_provider_ready(self):
        self.native.responses['orchestrator_capabilities']=AssertionError('must not be called')
        v=run(self.client.stop(THREAD,request_id='stop',run_id='run-1'))
        self.assertEqual(v['status'],'interrupt_requested')
        self.assertEqual([n for n,_ in self.native.calls],['t3_thread_interrupt'])

    def test_stop_all_is_not_just_interrupt(self):
        run(self.client.stop(THREAD,request_id='stop',stop_all=True))
        args=self.native.calls[-1][1];self.assertTrue(args['stop']);self.assertNotIn('runId',args)
        with self.assertRaises(ValueError):run(self.client.stop(THREAD,request_id='stop',stop_all=True,run_id='run-1'))

    def test_interrupt_requires_original_run(self):
        with self.assertRaises(ValueError):run(self.client.stop(THREAD,request_id='stop'))
        self.assertFalse(self.native.calls)

    def test_wait_is_bounded_and_original(self):
        run(self.client.wait(RUN,timeout_ms=123))
        args=self.native.calls[-1][1];self.assertEqual(args['runId'],'run-1');self.assertTrue(args['untilDelegatedWorkSettled'])
        with self.assertRaises(ValueError):run(self.client.wait(RUN,timeout_ms=30001))

    def test_wait_foreign_result_refused(self):
        self.native.responses['t3_thread_wait']={'structuredContent':dict(threadId='thread-1',runId='other',timedOut=False,status='completed')}
        with self.assertRaises(Conflict):run(self.client.wait(RUN))

    def test_historical_run_result_not_latest_thread(self):
        self.native.detail['thread'].update(status='running',latestRunId='run-9',activeRunId='run-9')
        result=run(self.client.original_result(RUN))
        self.assertTrue(result.complete);self.assertEqual(result.answer,'done')

    def test_other_runs_answer_is_not_original(self):
        self.native.detail['items']=[item(rid='other')]
        result=run(self.client.original_result(RUN));self.assertFalse(result.complete);self.assertIsNone(result.answer)

    def test_pending_wait_not_terminal(self):
        self.native.responses['t3_thread_wait']={'structuredContent':dict(threadId='thread-1',runId='run-1',status='running',timedOut=True)}
        result=run(self.client.original_result(RUN));self.assertFalse(result.complete)
        self.assertNotIn('t3_thread_read',[n for n,_ in self.native.calls])

    def test_failed_run_is_not_success(self):
        self.native.responses['t3_thread_wait']={'structuredContent':dict(threadId='thread-1',runId='run-1',status='failed',timedOut=False)}
        result=run(self.client.original_result(RUN));self.assertFalse(result.complete);self.assertEqual(result.status,'failed')

    def test_truncated_item_is_expanded_by_exact_native_identity(self):
        first=item('Hello ',truncated=True)
        self.native.detail['items']=[first]
        def respond(args):
            if 'itemId' in args:
                self.assertEqual(args['itemId'],'item-1');self.assertEqual(args['textOffset'],6)
                return {'structuredContent':observation([item('world')])}
            return {'structuredContent':copy.deepcopy(self.native.detail)}
        self.native.responses['t3_thread_read']=respond
        result=run(self.client.original_result(RUN));self.assertTrue(result.complete);self.assertEqual(result.answer,'Hello world')

    def test_truncated_offset_stall_refused(self):
        chunk=item('a',truncated=True)
        self.native.responses['t3_thread_read']={'structuredContent':observation([chunk])}
        with self.assertRaises(Unavailable):run(self.client.read_full_item(THREAD,chunk))

    def test_truncated_identity_change_refused(self):
        first=item('Hello ',truncated=True);other=item('foreign',rid='other')
        self.native.responses['t3_thread_read']={'structuredContent':observation([other])}
        with self.assertRaises(Conflict):run(self.client.read_full_item(THREAD,first))

    def test_unknown_pending_count_not_zero(self):
        self.native.detail['thread'].pop('pendingRequestCount')
        with self.assertRaises(Unavailable):run(self.client.original_result(RUN))

    def test_credentials_never_sent(self):
        with self.assertRaises(ValueError):run(self.client.send(THREAD,request_id='x',message='sk-admin-'+'a'*50))
        self.assertFalse(self.native.calls)

    def test_bool_is_not_a_cursor_or_timeout(self):
        with self.assertRaises(ValueError):Cursor(THREAD,True)
        with self.assertRaises(ValueError):run(self.client.wait(RUN,timeout_ms=True))


if __name__ == '__main__':unittest.main()
