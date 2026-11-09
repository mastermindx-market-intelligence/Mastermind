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
        self.assertEqual([n for n,_ in self.native.calls],['t3_thread_read','t3_thread_interrupt'])

    def test_stop_all_is_not_just_interrupt(self):
        run(self.client.stop(THREAD,request_id='stop',stop_all=True))
        args=self.native.calls[-1][1];self.assertTrue(args['stop']);self.assertNotIn('runId',args)
        with self.assertRaises(ValueError):run(self.client.stop(THREAD,request_id='stop',stop_all=True,run_id='run-1'))

    def test_interrupt_requires_original_run(self):
        with self.assertRaises(ValueError):run(self.client.stop(THREAD,request_id='stop'))
        self.assertFalse(self.native.calls)

    def test_exact_result_does_not_wait_for_later_unrelated_thread_work(self):
        def native_wait(args):
            if args["untilDelegatedWorkSettled"]:
                return {"structuredContent":dict(threadId="thread-1",runId="run-1",status="completed",timedOut=True)}
            return {"structuredContent":dict(threadId="thread-1",runId="run-1",status="completed",timedOut=False)}
        self.native.responses["t3_thread_wait"]=native_wait
        self.native.detail["thread"].update(status="running",latestRunId="run-9",activeRunId="run-9")
        result=run(self.client.original_result(RUN))
        self.assertTrue(result.complete);self.assertEqual(result.answer,"done")
        self.assertFalse(self.native.calls[0][1]["untilDelegatedWorkSettled"])

    def test_later_thread_final_run_never_substitutes_original(self):
        self.native.responses["t3_thread_wait"]={"structuredContent":dict(threadId="thread-1",runId="run-1",status="completed",timedOut=False,resultRun={"runId":"run-9","status":"completed"})}
        self.native.detail["items"]=[item("unrelated latest final",rid="run-9")]
        with self.assertRaises(Conflict):run(self.client.original_result(RUN))
        self.assertNotIn("t3_thread_read",[n for n,_ in self.native.calls])

    def test_explicit_child_settlement_wait_remains_available(self):
        value={"structuredContent":dict(threadId="thread-1",runId="run-1",status="completed",timedOut=False,resultRun={"runId":"run-9","status":"completed"})}
        self.native.responses["t3_thread_wait"]=value
        observed=run(self.client.wait(RUN,include_children=True))
        self.assertEqual(observed["resultRun"]["runId"],"run-9")
        self.assertTrue(self.native.calls[-1][1]["untilDelegatedWorkSettled"])

    def test_large_page_bounds_per_item_text_budget(self):
        run(self.client.read(THREAD,limit=100))
        self.assertLessEqual(self.native.calls[-1][1]["maxCharsPerItem"]*100,131072)
        run(self.client.read(THREAD,limit=1))
        self.assertEqual(self.native.calls[-1][1]["maxCharsPerItem"],8192)

    def test_duplicate_native_thread_list_identity_refused(self):
        self.native.responses["t3_thread_list"]={"structuredContent":{"threads":[{"threadId":"same","projectId":"project-1"}]*2,"nextCursor":None}}
        with self.assertRaises(Unavailable):run(self.client.list_threads())

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

    def test_stop_validates_project_before_native_mutation(self):
        self.native.detail['thread']['projectId']='foreign-project'
        with self.assertRaises(Conflict):run(self.client.stop(THREAD,request_id='s',stop_all=True))
        self.assertNotIn('t3_thread_interrupt',[n for n,_ in self.native.calls])

    def test_stop_refuses_when_original_identity_read_fails(self):
        self.native.responses['t3_thread_read']=ConnectionError('lost read')
        with self.assertRaises(Unavailable):run(self.client.stop(THREAD,request_id='s',stop_all=True))
        self.assertNotIn('t3_thread_interrupt',[n for n,_ in self.native.calls])

    def test_result_continuation_keeps_original_candidate_across_pages(self):
        def respond(args):
            if 'itemId' in args:
                self.assertEqual(args['itemId'],'item-1');self.assertEqual(args['textOffset'],0)
                return {'structuredContent':observation([item('original final')])}
            if 'afterPosition' in args:
                v=observation([item('later answer',rid='run-2',pos=2)])
                v['nextPosition']=2;return {'structuredContent':v}
            v=observation([item('original final')]);v['hasMore']=True
            return {'structuredContent':v}
        self.native.responses['t3_thread_read']=respond
        first=run(self.client.original_result(RUN,max_pages=1))
        self.assertFalse(first.complete);self.assertIsNotNone(first.progress)
        self.assertIsNone(first.answer)
        final=run(self.client.original_result(RUN,progress=first.progress,max_pages=1))
        self.assertTrue(final.complete);self.assertEqual(final.answer,'original final')
        self.assertEqual(len([a for n,a in self.native.calls if 'itemId' in a]),1)

    def test_result_continuation_rejects_other_run(self):
        from integrations.session_bridge.t3_native_client import ResultProgress
        progress=ResultProgress(RUN,'run-1','completed',Cursor(THREAD,1),'item-1')
        other=Run(THREAD,'run-2','request-2','queued')
        with self.assertRaises(Conflict):run(self.client.original_result(other,progress=progress))
        self.assertFalse(self.native.calls)

    def test_result_continuation_detects_changed_native_lineage(self):
        from integrations.session_bridge.t3_native_client import ResultProgress
        progress=ResultProgress(RUN,'run-1','completed',Cursor(THREAD,1),'item-1')
        self.native.responses['t3_thread_wait']={'structuredContent':dict(threadId='thread-1',runId='run-1',status='completed',timedOut=False,resultRun={'runId':'other','status':'completed'})}
        with self.assertRaises(Conflict):run(self.client.original_result(RUN,progress=progress))

    def test_result_continuation_does_not_trust_wrong_candidate(self):
        from integrations.session_bridge.t3_native_client import ResultProgress
        progress=ResultProgress(RUN,'run-1','completed',Cursor(THREAD,1),'forged-item')
        def respond(args):
            if 'itemId' in args:return {'structuredContent':observation([item('unrelated',rid='other')])}
            v=observation([]);v['nextPosition']=None
            return {'structuredContent':v}
        self.native.responses['t3_thread_read']=respond
        with self.assertRaises(Conflict):run(self.client.original_result(RUN,progress=progress))

    def test_later_complete_original_message_replaces_oversized_earlier_one(self):
        earlier=item('a'*32769,pos=1,truncated=True)
        final=item('final answer',pos=2);final['itemId']='item-2'
        self.native.detail['items']=[earlier,final];self.native.detail['nextPosition']=2
        result=run(self.client.original_result(RUN))
        self.assertTrue(result.complete);self.assertEqual(result.answer,'final answer')

    def test_credentials_never_sent(self):
        with self.assertRaises(ValueError):run(self.client.send(THREAD,request_id='x',message='sk-admin-'+'a'*50))
        self.assertFalse(self.native.calls)

    def test_bool_is_not_a_cursor_or_timeout(self):
        with self.assertRaises(ValueError):Cursor(THREAD,True)
        with self.assertRaises(ValueError):run(self.client.wait(RUN,timeout_ms=True))


class NativeThreadToolsTests(unittest.TestCase):
    def setUp(self):
        import hashlib
        self.native=Native(); self.schemas=copy.deepcopy(SCHEMAS)
        self.schemas.update({
            't3_thread_configure':schema('environmentId','threadId','modelSelection'),
            't3_thread_organize':schema('environmentId','threadId','action','snoozedUntil'),
            't3_queue':schema('environmentId','threadId','action','queuedRunId','text','beforeRunId','targetRunId','cursor','limit'),
            't3_pending_request':schema('environmentId','threadId','action','requestId','answers'),
        })
        self.client=T3NativeClient(SCOPE,self.native,self.schemas)
        self.updated=self.native.detail['thread']['updatedAt']
        self.config=dict(threadId='thread-1',modelSelection={'instanceId':'capacity_fabric','model':'glm-5.3'},runtimeMode='approval-required',interactionMode='default')
        self.queued={'run-q':dict(queuedRunId='run-q',text='original queued work',truncated=False)}
        self.questions={'question-1':dict(requestId='question-1',questions=[dict(id='answer-1',question='Which bounded implementation?')])}
        def configure(args):
            if 'modelSelection' in args:
                self.config['modelSelection']=copy.deepcopy(args['modelSelection'])
                self.native.detail['thread'].update(providerInstanceId=args['modelSelection']['instanceId'],model=args['modelSelection']['model'])
                return {'structuredContent':{'sequence':17}}
            return {'structuredContent':self.config}
        def organize(args):
            self.native.detail['thread']['archived']=args['action']=='archive'
            return {'structuredContent':{'sequence':18}}
        def queue(args):
            action=args['action'];rid=args.get('queuedRunId')
            if action=='list':return {'structuredContent':dict(items=list(self.queued.values()),nextCursor=None)}
            if rid not in self.queued:return {'isError':True,'structuredContent':{'code':'invalid_request'}}
            if action=='read':return {'structuredContent':self.queued[rid]}
            if action=='edit':self.queued[rid]['text']=args['text']
            if action=='cancel':self.queued.pop(rid)
            return {'structuredContent':{'sequence':19}}
        def question(args):
            if args['action']=='list':return {'structuredContent':{'requestIds':list(self.questions)}}
            if args['action']=='read':return {'structuredContent':self.questions[args['requestId']]}
            return {'structuredContent':{'sequence':20}}
        self.native.responses.update(t3_thread_configure=configure,t3_thread_organize=organize,t3_queue=queue,t3_pending_request=question)
        self.sha=hashlib.sha256(b'original queued work').hexdigest()

    def mutations(self,name):
        return [args for n,args in self.native.calls if n==name and (('modelSelection' in args) if name=='t3_thread_configure' else args.get('action') not in ('read','list'))]

    def test_native_second_toolkit_capabilities_are_discovered(self):
        c=self.client.capabilities()
        for key in ('archive','model_configuration','queue_management','pending_questions'):self.assertTrue(c[key])
        self.assertFalse(c['lifecycle_extension'])

    def test_configuration_is_read_without_native_mutation(self):
        self.assertEqual(run(self.client.configuration(THREAD)),self.config)
        self.assertFalse(self.mutations('t3_thread_configure'))

    def test_set_model_explicit_capacity_and_modes_retained(self):
        result=run(self.client.set_model(THREAD,request_id='model-change',model='fabric/fast',expected_updated_at=self.updated))
        self.assertEqual(result['receipt']['sequence'],17)
        self.assertEqual(result['observed']['modelSelection'],{'instanceId':'capacity_fabric','model':'fabric/fast'})
        self.assertEqual(result['observed']['runtimeMode'],'approval-required')
        self.assertFalse(result['native_atomic_precondition'])
        self.assertEqual(len(self.mutations('t3_thread_configure')),1)
        self.assertEqual(set(self.mutations('t3_thread_configure')[0]),{'environmentId','threadId','modelSelection'})

    def test_model_change_rejects_stale_snapshot(self):
        with self.assertRaises(Conflict):run(self.client.set_model(THREAD,request_id='x',model='fabric/fast',expected_updated_at='older'))
        self.assertFalse(self.mutations('t3_thread_configure'))

    def test_model_change_rejects_active_and_pending(self):
        for patch in ({'activeRunId':'run-1'},{'pendingRequestCount':1},{'status':'queued'}):
            with self.subTest(patch=patch):
                self.native.detail=observation(**patch)
                with self.assertRaises(Conflict):run(self.client.set_model(THREAD,request_id='x',model='fabric/fast',expected_updated_at=self.updated))
        self.assertFalse(self.mutations('t3_thread_configure'))

    def test_model_change_requires_delegated_work_settled(self):
        self.native.responses['t3_thread_wait']={'structuredContent':dict(threadId='thread-1',runId='run-1',status='running',timedOut=True)}
        with self.assertRaises(Conflict):run(self.client.set_model(THREAD,request_id='x',model='fabric/fast',expected_updated_at=self.updated))
        self.assertFalse(self.mutations('t3_thread_configure'))

    def test_model_change_unknown_model_cannot_fallback(self):
        with self.assertRaises(Rejected):run(self.client.set_model(THREAD,request_id='x',model='foreign-model',expected_updated_at=self.updated))
        self.assertFalse(self.mutations('t3_thread_configure'))

    def test_model_readback_failure_retains_committed_sequence(self):
        original=self.native.responses['t3_thread_configure'];changed=[False]
        def fail(args):
            if 'modelSelection' in args:changed[0]=True;return original(args)
            if changed[0]:raise ConnectionError('lost readback')
            return original(args)
        self.native.responses['t3_thread_configure']=fail
        with self.assertRaises(EffectUnknown) as c:run(self.client.set_model(THREAD,request_id='x',model='fabric/fast',expected_updated_at=self.updated))
        self.assertEqual(c.exception.receipt,{'sequence':17})
        self.assertEqual(len(self.mutations('t3_thread_configure')),1)

    def test_model_permission_drift_not_reported_success(self):
        original=self.native.responses['t3_thread_configure']
        def mutate(args):
            result=original(args)
            if 'modelSelection' in args:self.config['runtimeMode']='full-access'
            return result
        self.native.responses['t3_thread_configure']=mutate
        with self.assertRaises(EffectUnknown):run(self.client.set_model(THREAD,request_id='x',model='fabric/fast',expected_updated_at=self.updated))

    def test_archive_and_unarchive_reuse_existing_tool(self):
        result=run(self.client.archive(THREAD,request_id='arc',expected_updated_at=self.updated))
        self.assertTrue(result['observed']['archived']);self.assertFalse(result['native_atomic_precondition'])
        result=run(self.client.archive(THREAD,request_id='unarc',expected_updated_at=self.updated,archived=False))
        self.assertFalse(result['observed']['archived'])
        self.assertEqual([x['action'] for x in self.mutations('t3_thread_organize')],['archive','unarchive'])

    def test_archive_refuses_active_run(self):
        self.native.detail['thread']['activeRunId']='run-1'
        with self.assertRaises(Conflict):run(self.client.archive(THREAD,request_id='arc',expected_updated_at=self.updated))
        self.assertFalse(self.mutations('t3_thread_organize'))

    def test_unarchive_refuses_noncapacity_execution_route(self):
        self.native.detail['thread'].update(archived=True,providerInstanceId='direct-provider')
        with self.assertRaises(Rejected):run(self.client.archive(THREAD,request_id='unarc',expected_updated_at=self.updated,archived=False))
        self.assertFalse(self.mutations('t3_thread_organize'))

    def test_archive_same_state_is_not_a_second_mutation(self):
        self.native.detail['thread']['archived']=True
        with self.assertRaises(Conflict):run(self.client.archive(THREAD,request_id='arc',expected_updated_at=self.updated))
        self.assertFalse(self.mutations('t3_thread_organize'))

    def test_archive_bad_readback_retains_native_receipt(self):
        self.native.responses['t3_thread_organize']={'structuredContent':{'sequence':18}}
        with self.assertRaises(EffectUnknown) as c:run(self.client.archive(THREAD,request_id='arc',expected_updated_at=self.updated))
        self.assertEqual(c.exception.receipt,{'sequence':18})

    def test_queue_list_and_exact_read(self):
        self.assertEqual(run(self.client.queue_list(THREAD))['items'],list(self.queued.values()))
        self.assertEqual(run(self.client.queue_read(THREAD,'run-q'))['text'],'original queued work')
        self.assertFalse(self.mutations('t3_queue'))

    def test_queue_duplicate_and_stalled_cursor_refused(self):
        for body in [dict(items=[self.queued['run-q']]*2,nextCursor=None),dict(items=[],nextCursor=0)]:
            self.native.responses['t3_queue']={'structuredContent':body}
            with self.assertRaises(Unavailable):run(self.client.queue_list(THREAD))

    def test_queue_read_foreign_run_is_rejected(self):
        self.native.responses['t3_queue']={'structuredContent':dict(queuedRunId='other',text='x',truncated=False)}
        with self.assertRaises(Conflict):run(self.client.queue_read(THREAD,'run-q'))

    def test_queue_edit_preserves_target_and_explicit_original_text(self):
        r=run(self.client.queue_change(THREAD,request_id='edit',action='edit',queued_run_id='run-q',text='revised bounded work',expected_text_sha256=self.sha))
        self.assertEqual(r,{'sequence':19});self.assertEqual(self.queued['run-q']['text'],'revised bounded work')
        self.assertEqual(len(self.mutations('t3_queue')),1)

    def test_queue_stale_or_truncated_text_not_overwritten(self):
        with self.assertRaises(Conflict):run(self.client.queue_change(THREAD,request_id='edit',action='edit',queued_run_id='run-q',text='x',expected_text_sha256='a'*64))
        self.queued['run-q']['truncated']=True
        with self.assertRaises(Conflict):run(self.client.queue_change(THREAD,request_id='edit',action='edit',queued_run_id='run-q',text='x',expected_text_sha256=self.sha))
        self.assertFalse(self.mutations('t3_queue'))

    def test_queue_cancel_does_not_need_healthy_capacity(self):
        self.native.responses['orchestrator_capabilities']=ConnectionError('down')
        run(self.client.queue_change(THREAD,request_id='cancel',action='cancel',queued_run_id='run-q'))
        self.assertFalse(self.queued)
        self.assertNotIn('orchestrator_capabilities',[n for n,_ in self.native.calls])

    def test_queue_reorder_to_end_is_explicit_null(self):
        run(self.client.queue_change(THREAD,request_id='reorder',action='reorder',queued_run_id='run-q'))
        self.assertIsNone(self.mutations('t3_queue')[0]['beforeRunId'])

    def test_queue_promotion_requires_exact_active_capacity_run(self):
        self.native.detail['thread']['activeRunId']='run-active'
        run(self.client.queue_change(THREAD,request_id='promote',action='promote_to_steer',queued_run_id='run-q',target_run_id='run-active'))
        self.assertEqual(self.mutations('t3_queue')[0]['targetRunId'],'run-active')

    def test_queue_promotion_refuses_replaced_target(self):
        self.native.detail['thread']['activeRunId']='changed'
        with self.assertRaises(Conflict):run(self.client.queue_change(THREAD,request_id='p',action='promote_to_steer',queued_run_id='run-q',target_run_id='old'))
        self.assertFalse(self.mutations('t3_queue'))

    def test_queue_promotion_never_uses_direct_provider(self):
        self.native.detail['thread'].update(activeRunId='run-active',providerInstanceId='other')
        with self.assertRaises(Rejected):run(self.client.queue_change(THREAD,request_id='p',action='promote_to_steer',queued_run_id='run-q',target_run_id='run-active'))
        self.assertFalse(self.mutations('t3_queue'))

    def test_queue_unrelated_arguments_refuse_before_native_read(self):
        with self.assertRaises(ValueError):run(self.client.queue_change(THREAD,request_id='x',action='cancel',queued_run_id='run-q',text='unrelated'))
        self.assertFalse(self.native.calls)

    def test_pending_questions_are_native_user_questions_only(self):
        self.assertEqual(run(self.client.pending_questions(THREAD)),('question-1',))
        self.assertEqual(run(self.client.read_question(THREAD,'question-1')),self.questions['question-1'])
        self.assertFalse(self.mutations('t3_pending_request'))

    def test_answer_only_original_question_and_capacity(self):
        receipt=run(self.client.answer_question(THREAD,request_id='question-1',operation_id='answer',answers={'answer-1':'Preserve the existing interface'}))
        self.assertEqual(receipt,{'sequence':20})
        args=self.mutations('t3_pending_request')[0]
        self.assertEqual(args['requestId'],'question-1');self.assertEqual(args['action'],'respond')
        self.assertNotIn('permission',args)

    def test_answer_unknown_question_cannot_mutate(self):
        with self.assertRaises(Conflict):run(self.client.answer_question(THREAD,request_id='question-1',operation_id='answer',answers={'permission-approval':True}))
        self.assertFalse(self.mutations('t3_pending_request'))

    def test_answer_secret_refused_before_native_call(self):
        with self.assertRaises(ValueError):run(self.client.answer_question(THREAD,request_id='question-1',operation_id='a',answers={'answer-1':'sk-admin-'+'a'*50}))
        self.assertFalse(self.native.calls)

    def test_answer_unready_capacity_does_not_fallback(self):
        self.native.detail['thread']['providerInstanceId']='direct'
        with self.assertRaises(Rejected):run(self.client.answer_question(THREAD,request_id='question-1',operation_id='a',answers={'answer-1':'x'}))
        self.assertFalse(self.mutations('t3_pending_request'))

    def test_unsupported_second_toolkit_is_not_invented(self):
        client=T3NativeClient(SCOPE,self.native,SCHEMAS)
        with self.assertRaises(Unavailable):run(client.configuration(THREAD))
        self.assertNotIn('t3_thread_configure',[n for n,_ in self.native.calls])

    def test_native_invalid_request_is_not_transport_unknown(self):
        self.native.responses['t3_queue']={'isError':True,'structuredContent':{'code':'invalid_request'}}
        with self.assertRaises(Rejected) as c:run(self.client.queue_read(THREAD,'run-q'))
        self.assertEqual(c.exception.code,'invalid_request')


if __name__ == '__main__':unittest.main()
