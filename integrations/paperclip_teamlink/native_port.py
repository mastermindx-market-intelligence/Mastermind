"""Bounded local transport for the existing T3 native client; no server or credentials.

The pinned CLI owns its native EnvironmentAuth session and revokes it on exit.
Only the send action can mutate T3. Observation never reads a child transcript.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from integrations.session_bridge.t3_native_client import (  # noqa: E402
    Conflict, Cursor, EffectUnknown, Rejected, ResultProgress,
    Run, Scope, T3NativeClient, Thread, Unavailable, TERMINAL,
)

MAX_OUTPUT = 2 * 1024 * 1024
SECRET = re.compile(r"(?i)\bBearer\s+\S{12,}|\bsk-(?:admin-|proj-)?[\w-]{20,}|\b(?:api[_-]?key|access[_-]?token|authorization|password)\s*[=:]\s*[^\s,;]{8,}")


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def sanitized(text):
    return SECRET.sub('[REDACTED]', text)


def run_dict(run):
    return {'threadId': run.thread.thread_id, 'projectId': run.thread.scope.project_id,
            'runId': run.run_id, 'requestId': run.request_id,
            'delivery': run.delivery, 'messageId': run.message_id}


def process_snapshot(port):
    """Only descendants of the exact native listener. Never argv or environment."""
    stamp = now()
    try:
        found = subprocess.run(['/usr/sbin/lsof', '-nP', f'-iTCP:{port}', '-sTCP:LISTEN', '-t'],
                               capture_output=True, text=True, timeout=3, check=True)
        roots = {int(x) for x in found.stdout.split()}
        if not roots:
            raise ValueError('listener missing')
        observed = subprocess.run(['/bin/ps', '-axo', 'pid=,ppid=,lstart=,etime=,%cpu=,%mem=,comm='],
                                  capture_output=True, text=True, timeout=3, check=True)
        processes = []
        for line in observed.stdout.splitlines():
            fields = line.split(None, 10)
            if len(fields) != 11:
                raise ValueError('unqualified process row')
            processes.append({'pid': int(fields[0]), 'parentPid': int(fields[1]),
                              'startedAtLocal': ' '.join(fields[2:7]), 'elapsed': fields[7],
                              'cpuPercent': float(fields[8]), 'memoryPercent': float(fields[9]),
                              'executable': Path(fields[10]).name})
        selected = set(roots)
        for _ in range(len(processes)):
            more = {p['pid'] for p in processes if p['parentPid'] in selected}
            if more <= selected:
                break
            selected |= more
        rows = [p for p in processes if p['pid'] in selected]
        if not roots <= {p['pid'] for p in rows}:
            raise ValueError('listener exited during census')
        return {'status': 'observed', 'observedAt': stamp, 'listenerPids': sorted(roots),
                'processes': rows[:128], 'totalObserved': len(rows), 'truncated': len(rows) > 128,
                'scope': 'native listener and OS descendants; not exact thread ownership'}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {'status': 'unavailable', 'observedAt': stamp, 'processes': None,
                'reason': 'PROCESS_OBSERVATION_UNAVAILABLE'}


class Port:
    def __init__(self, config):
        self.config = config
        for key in ('nativeCliPath', 'nodePath', 't3Home'):
            value = config.get(key)
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError('absolute installed path required')
        self.env = {'HOME': os.environ.get('HOME', ''),
                    'PATH': '/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin',
                    'TMPDIR': os.environ.get('TMPDIR', '/tmp'), 'T3CODE_HOME': config['t3Home']}
        self.schemas = None
        self.dispatched = False
        self.deadline = time.monotonic() + 20

    def cli(self, args, data=None, timeout=25):
        command = [self.config['nodePath'], self.config['nativeCliPath'], 'thread', *args,
                   '--json', '--log-level', 'error']
        # communicate() drains both pipes. Never emit native stderr or parse a JSON suffix.
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise Unavailable('observation budget exhausted')
        result = subprocess.run(command, input=None if data is None else json.dumps(data),
                                capture_output=True, text=True, timeout=min(timeout, remaining), env=self.env)
        if len(result.stdout.encode()) > MAX_OUTPUT or result.returncode:
            raise Unavailable('native CLI unavailable')
        value = json.loads(result.stdout)
        if not isinstance(value, dict):
            raise Unavailable('native JSON envelope unavailable')
        return value

    def tool(self, name, args):
        allowed = {'t3_environment_read', 't3_project_list', 'orchestrator_capabilities',
                   't3_thread_list', 't3_thread_read', 't3_thread_wait', 't3_thread_send', 't3_pending_request'}
        if name not in allowed:
            raise Unavailable('tool not allowed')
        if name == 't3_pending_request' and args.get('action') not in {'list', 'read'}:
            raise Rejected('unsupported_operation')
        if name == 't3_thread_send':
            self.dispatched = True
        return self.cli(['native', name], args, timeout=40 if name == 't3_thread_wait' else 25)

    def discover(self):
        environment = self.tool('t3_environment_read', {}).get('structuredContent')
        if not isinstance(environment, dict) or environment.get('environmentId') != self.config['environmentId']:
            raise Conflict('native environment changed')
        catalog = self.cli(['native-catalog'])
        self.schemas = {t['name']: t['inputSchema'] for t in catalog['tools']}
        for name in ('t3_thread_list', 't3_thread_read', 't3_thread_wait', 't3_thread_send'):
            if name not in self.schemas:
                raise Unavailable('native capability missing')
        return {k: environment.get(k) for k in ('environmentId', 'label', 'serverVersion', 'platform')}

    def client(self, project):
        if project not in self.config['projectIds']:
            raise Rejected('project_not_found')
        connection = 'paperclip-teamlink-' + digest(self.config['environmentId'] + '\n' + self.config['t3Home'])[:32]
        scope = Scope(connection, self.config['environmentId'], project)
        return T3NativeClient(scope, self.tool, self.schemas)

    async def root(self, client, thread_id):
        cursor = 0
        for _ in range(20):
            page = await client.list_threads(cursor=cursor, limit=100)
            for row in page['threads']:
                if row['threadId'] == thread_id:
                    if 'parentThreadId' not in row or row['parentThreadId'] is not None:
                        raise Rejected('unsupported_operation')
                    return Thread(client.scope, thread_id)
            cursor = page.get('nextCursor')
            if cursor is None:
                break
        raise Unavailable('root thread was not qualified')

    async def perform(self, action, request):
        environment = self.discover()
        if action == 'inventory':
            project_page = self.tool('t3_project_list', {}).get('structuredContent', {})
            projects = project_page.get('projects')
            if not isinstance(projects, list):
                raise Unavailable('project inventory unavailable')
            projects = [{'projectId': p['id'], 'title': p.get('title'), 'workspaceRoot': p.get('workspaceRoot'),
                         'archivedAt': p.get('archivedAt')}
                        for p in projects if p.get('id') in self.config['projectIds']]
            project = request.get('projectId') or self.config['projectIds'][0]
            page = await self.client(project).list_threads(cursor=request.get('cursor', 0), limit=50)
            keys = ('threadId', 'projectId', 'title', 'parentThreadId', 'status', 'activeRunId',
                    'providerInstanceId', 'model', 'archived', 'pendingRequestCount', 'updatedAt')
            return {'environment': environment, 'projects': projects, 'projectsNextCursor': project_page.get('nextCursor'), 'projectId': project,
                    'threads': [{k: t.get(k) for k in keys} for t in page['threads']],
                    'nextCursor': page.get('nextCursor'), 'observedAt': now(),
                    'processes': process_snapshot(self.config['t3Port']) if request.get('includeProcesses', True) else None}
        client = self.client(request['projectId'])
        thread = await self.root(client, request['threadId'])
        if action == 'bind':
            detail = (await client.read(thread, limit=1))['thread']
            if detail.get('archived') is not False:
                raise Rejected('thread_conflict')
            count = detail.get('itemCount')
            if type(count) is not int or count < 0:
                raise Unavailable('timeline boundary unavailable')
            return {'threadId': thread.thread_id, 'projectId': client.scope.project_id,
                    'environmentId': client.scope.environment_id,
                    # A running root may still update an existing item. Replay its
                    # native history through the new, unique binding filter rather
                    # than placing the initial cursor after mutable content.
                    'watchCursor': None if detail.get('activeRunId') else (count - 1 if count else None),
                    'initialActiveRunId': detail.get('activeRunId'), 'observedAt': now(),
                    'providerInstanceId': detail.get('providerInstanceId'), 'model': detail.get('model')}
        if action == 'send':
            # The existing client enforces model/provider admission and native queue mode.
            run = await client.send(thread, request_id=request['operationId'], message=request['wire'], mode='queue')
            return run_dict(run)
        if action == 'inspect':
            cursor = Cursor(thread, request['cursor']) if request.get('cursor') is not None else None
            page = await client.read(thread, cursor=cursor, view='activity', limit=20)
            keys = ('threadId', 'projectId', 'title', 'status', 'activeRunId', 'latestRunId',
                    'providerInstanceId', 'model', 'pendingRequestCount', 'itemCount', 'updatedAt')
            items = []
            for item in page['items']:
                if item.get('sourceThreadId') != thread.thread_id:
                    continue
                projected = {k: item.get(k) for k in ('position', 'itemId', 'runId', 'sourceThreadId', 'type', 'status', 'updatedAt')}
                if item.get('type') in {'user_message', 'assistant_message', 'error'}:
                    projected['text'] = sanitized(item.get('text') or '')
                    projected['textTruncated'] = item.get('textTruncated')
                items.append(projected)
            return {'thread': {k: page['thread'].get(k) for k in keys}, 'recentRuns': page['recentRuns'],
                    'items': items, 'nextCursor': page.get('nextPosition'), 'hasMore': page['hasMore'], 'observedAt': now()}
        if action == 'recover_send':
            cursor = Cursor(thread, request['cursor']) if request.get('cursor') is not None else None
            matches = request.get('matches', [])
            for _ in range(3):
                page = await client.read(thread, cursor=cursor, limit=100)
                for item in page['items']:
                    if (item.get('type') == 'user_message' and item.get('sourceThreadId') == thread.thread_id
                            and request['marker'] in (item.get('text') or '')):
                        text, complete = await client.read_full_item(thread, item)
                        if complete and digest(text) == request['wireHash']:
                            match = {'itemId': item['itemId'], 'messageId': item.get('messageId') or item['itemId'],
                                     'runId': item.get('runId')}
                            if match not in matches:
                                matches.append(match)
                cursor = Cursor(thread, page['nextPosition']) if page.get('nextPosition') is not None else cursor
                if not page['hasMore']:
                    return {'complete': True, 'matches': matches, 'cursor': None if cursor is None else cursor.position}
            return {'complete': False, 'matches': matches, 'cursor': None if cursor is None else cursor.position}
        if action == 'observe':
            receipt = request['run']
            run = Run(thread, receipt['runId'], receipt['requestId'], receipt['delivery'], receipt.get('messageId'))
            waited = await client.wait(run, timeout_ms=min(15000, max(1, request.get('waitMs', 1))), include_children=False)
            status = waited['status']
            progress = None
            if request.get('progress'):
                p = request['progress']
                progress = ResultProgress(run, p['resultRunId'], p['status'], Cursor(thread, p['cursor']), p.get('candidateItemId'))
            result = await client.original_result(run, max_pages=3, progress=progress)
            status = result.status
            continuation = None if result.progress is None else {
                'resultRunId': result.progress.result_run_id, 'status': result.progress.status,
                'cursor': result.progress.cursor.position, 'candidateItemId': result.progress.candidate_item_id}
            answer = None if result.answer is None else sanitized(result.answer)
            pending_ids = []
            pending_count = result.pending_requests
            if status not in TERMINAL:
                detail = (await client.read(thread, limit=1))['thread']
                if detail.get('activeRunId') == run.run_id:
                    pending_count = detail.get('pendingRequestCount')
                    if type(pending_count) is int and pending_count > 0:
                        pending_ids = list(await client.pending_questions(thread))[:20]
            return {'status': status, 'complete': result.complete, 'answer': answer,
                    'redacted': result.answer is not None and result.answer != answer,
                    'terminal': status in TERMINAL, 'pendingRequests': pending_count,
                    'pendingRequestIds': pending_ids,
                    'progress': continuation, 'observedAt': now()}
        if action == 'scan':
            cursor = Cursor(thread, request['cursor']) if request.get('cursor') is not None else None
            page = await client.read(thread, cursor=cursor, limit=50)
            rows = []
            advanced = request.get('cursor')
            known_runs = {r['runId']: r['status'] for r in page['recentRuns'] if isinstance(r, dict) and 'runId' in r and 'status' in r}
            for item in page['items']:
                if self.deadline - time.monotonic() < 4:
                    return {'messages': rows, 'cursor': advanced, 'hasMore': True, 'budgetLimited': True}
                if item.get('type') == 'assistant_message' and item.get('sourceThreadId') == thread.thread_id:
                    exact = [item]
                    # A terminal run in the same native page predates the item
                    # snapshot. Otherwise qualify completion and re-read the item.
                    if known_runs.get(item['runId']) not in TERMINAL:
                        run = Run(thread, item['runId'], 'observe-native-inbox', 'started')
                        state = await client.wait(run, timeout_ms=1, include_children=False)
                        if state['status'] not in TERMINAL:
                            return {'messages': rows, 'cursor': advanced, 'hasMore': True, 'waitingForRun': run.run_id}
                        final = await client._call('t3_thread_read', {
                            'threadId': thread.thread_id, 'itemId': item['itemId'], 'textOffset': 0,
                            'maxCharsPerItem': 8192, 'runLimit': 1})
                        client._qualify_read(thread, final, None, 1)
                        exact = final['items']
                        if (len(exact) != 1 or exact[0].get('itemId') != item['itemId']
                                or exact[0].get('runId') != item['runId']
                                or exact[0].get('sourceThreadId') != thread.thread_id):
                            raise Conflict('final native item changed')
                    # Protocol messages start with this marker. Decide only from
                    # the final exact item, never a mutable streaming snippet.
                    # Large ordinary messages can advance without reading bodies.
                    if not (exact[0].get('text') or '').lstrip().startswith('<teamlink-to-paperclip>'):
                        advanced = item['position']
                        continue
                    full, complete = await client.read_full_item(thread, exact[0])
                    if not complete:
                        return {'messages': rows, 'cursor': advanced, 'hasMore': True, 'incompleteItemId': item['itemId']}
                    blocks = re.findall(r'<teamlink-to-paperclip>\s*(\{.*?\})\s*</teamlink-to-paperclip>', full, re.S)
                    if len(blocks) == 1:
                        try:
                            message = json.loads(blocks[0])
                            if (set(message) <= {'bindingId', 'kind', 'message', 'replyTo'}
                                    and isinstance(message.get('bindingId'), str) and len(message['bindingId']) <= 256
                                    and message.get('kind') in {'update', 'question', 'blocker'}
                                    and isinstance(message.get('message'), str)
                                    and 0 < len(message['message'].encode()) <= 16000
                                    and (message.get('replyTo') is None or isinstance(message['replyTo'], str))):
                                rows.append({'bindingId': message['bindingId'], 'itemId': item['itemId'], 'runId': item['runId'], 'position': item['position'],
                                             'kind': message['kind'], 'message': sanitized(message['message']),
                                             'replyTo': message.get('replyTo'), 'sourceHash': digest(full)})
                        except (TypeError, ValueError):
                            pass  # Invalid protocol is ordinary native text, never an instruction.
                advanced = item['position']
            if not page['hasMore'] and page.get('nextPosition') is not None:
                advanced = page['nextPosition']
            return {'messages': rows, 'cursor': advanced, 'hasMore': page['hasMore'], 'observedAt': now()}
        raise ValueError('unknown port action')


def main():
    action = None
    port = None
    try:
        raw = sys.stdin.read(100001)
        if len(raw.encode()) > 100000:
            raise ValueError('input too large')
        request = json.loads(raw)
        action = request['action']
        port = Port(request['config'])
        data = asyncio.run(port.perform(action, request))
        print(json.dumps({'ok': True, 'data': data}, ensure_ascii=True, allow_nan=False))
    except Rejected as exc:
        print(json.dumps({'ok': False, 'error': 'NATIVE_REFUSED', 'code': exc.code}))
    except EffectUnknown:
        print(json.dumps({'ok': False, 'error': 'NATIVE_EFFECT_UNKNOWN'}))
    except (Conflict, Unavailable, ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError):
        # Before native send the client distinguishes refusal; all other send failures
        # conservatively preserve uncertainty. No raw diagnostic or token is emitted.
        error = 'NATIVE_EFFECT_UNKNOWN' if port and port.dispatched else ('NATIVE_PRECONDITION_UNAVAILABLE' if action == 'send' else 'NATIVE_UNAVAILABLE')
        print(json.dumps({'ok': False, 'error': error}))


if __name__ == '__main__':
    main()
