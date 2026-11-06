"""Source-issued canonical fixture inputs; no hand-authored Control Room rows.

The already-published disposable Macro revision is explicitly the configured
baseline of a NEW fixture. It is never an overlay on the original fixture's C.
The sole physical-child seam evaluates captured AgentOS code in-process.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import types

from control_plane import ceo_boot_packet, chairman_control_room
from control_plane.workspace_read_service import ExistingControlRoomCache, WorkspaceReadService
from scripts import chairman_control_room as cache_owner


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def fixture_clock_sample():
    """Explicit portable test clock premise, never installed Darwin capability.

    Preserve the Mlo/Wlo/Mhi/Whi bracket and live wall/monotonic movement.
    Production _source_clock_sample remains Darwin-only and fail-closed.
    """
    return (time.monotonic_ns() // 1000000, time.time_ns() // 1000000,
            time.monotonic_ns() // 1000000, time.time_ns() // 1000000)


class CanonicalFixtureCache:
    def __init__(self, macro_root, cache_root, *, mastermind_revision):
        self.mastermind_revision = mastermind_revision
        assert len(mastermind_revision) == 40 and all(c in "0123456789abcdef" for c in mastermind_revision)
        self.root = Path(macro_root).resolve()
        self.commit = git(self.root, 'rev-parse', 'HEAD')
        assert git(self.root, 'status', '--porcelain') == ''
        self.code = subprocess.check_output(['git', '-C', str(self.root), 'show', self.commit + ':scripts/agentos.py'])
        assert self.code == (self.root / 'scripts/agentos.py').read_bytes()
        self.owner = cache_owner.ServerConfig(repo_root=Path.cwd(), macro_root=str(self.root),
            bindings_path=None, token='inert-private-fixture', origin='http://127.0.0.1:0', port=0,
            validity_sample_fn=fixture_clock_sample)
        self.cache = ExistingControlRoomCache(lambda: self.owner)
        self.publish()

    def compile(self, runtime=None):
        assert git(self.root, 'rev-parse', 'HEAD') == self.commit
        assert git(self.root, 'status', '--porcelain') == ''
        name = '_s34_canonical_fixture_' + self.commit
        module = types.ModuleType(name)
        module.__file__ = str(self.root / 'scripts/agentos.py')
        previous = sys.modules.get(name)
        sys.modules[name] = module
        try:
            exec(compile(self.code, module.__file__, 'exec'), module.__dict__)
            moment = datetime.now(timezone.utc)
            stamp = moment.isoformat().replace('+00:00', 'Z')
            store = module.load_store(self.root / 'agentos', None)
            assert not [p for p in store.problems if p.hard], [p.render(self.root) for p in store.problems if p.hard]
            state = module.build_state(store, now=moment, degraded=module.Degraded(),
                builds=None, p0_status=None, worktrees={})
            brief = module.build_brief(state, now=moment, since=moment-timedelta(days=1), since_label='1d')
        finally:
            if previous is None: sys.modules.pop(name, None)
            else: sys.modules[name] = previous
        def captured_child(argv, *, cwd, timeout, max_bytes):
            expected = [sys.executable, str(self.root / 'scripts/agentos.py'), 'brief', '--json', '--no-remember', '--now', stamp]
            if argv == expected and Path(cwd) == self.root:
                raw = json.dumps(brief, ensure_ascii=False)
                assert len(raw.encode()) <= max_bytes
                return dict(code=0, stdout=raw, stderr='', timed_out=False, limit_exceeded=False, invalid_utf8=False)
            assert argv == ['git', 'rev-parse', 'HEAD'] and Path(cwd) == self.root
            return dict(code=0, stdout=git(cwd, *argv[1:]), stderr='', timed_out=False, limit_exceeded=False, invalid_utf8=False)
        packet = ceo_boot_packet.build_packet(repo_root=Path.cwd(), macro_root_flag=str(self.root),
            environ={}, now=stamp, runner=captured_child,
            mastermind_identity=dict(sha=self.mastermind_revision, branch='source-qualified-fixture'))
        assert packet['brief'] == brief and packet['macro']['sha'] == self.commit
        jobs = None
        if runtime is not None:
            _, jobs, error = chairman_control_room._read_runtime_jobs_from_runtime(runtime)
            assert error is None
        document = chairman_control_room.compose_control_room(inbox=None, boot_packet=packet,
            active_builds=None, agent_os_state=state, runtime_jobs=jobs, bindings=None, generated_at=stamp)
        assert git(self.root, 'rev-parse', 'HEAD') == self.commit and git(self.root, 'status', '--porcelain') == ''
        self.state, self.brief, self.packet = state, brief, packet
        return document

    def publish(self, runtime=None):
        # Full canonical composition happens before publication. No owner/row
        # replacement during a Fresh effect; later refresh is a new publication.
        anchor = self.owner.validity_sample_fn()
        document = self.compile(runtime)
        sample = self.owner.validity_sample_fn()
        assert sample is not None
        with self.owner.state_lock:
            self.owner.state_published_seq += 1
            self.owner.state_cache.update(doc=document, composed_monotonic=time.monotonic())
            cache_owner._publish_source_validity(self.owner, document, anchor, sample)
        return document

    def reader(self, runtime, principal):
        from common.executive_workspace_contract import PRINCIPAL_KEYS
        expected = {key:list(principal.scopes) if key=='scopes' else getattr(principal,key) for key in PRINCIPAL_KEYS}
        def authorize(raw): return raw == expected
        authorize.binding_digest = lambda raw: 'e'*64 if authorize(raw) else None
        return WorkspaceReadService(cache=self.cache, runtime=runtime, authorize=authorize, armed={}, runtime_identity={})

    def provenance(self):
        return dict(configured_macro_revision=self.commit, agentos_compiler_sha256=hashlib.sha256(self.code).hexdigest(),
            raw_workstream_sources=[row['source'] for row in self.state['workstreams']],
            premises=['new configured fixture baseline is the retained previously-published Macro revision',
                'actual pinned Store/build_state/build_brief and canonical compose_control_room',
                'physical AgentOS brief child evaluated in-process over exact captured code',
                'absent Inbox/active builds/bindings remain explicitly unavailable',
                'portable fixture Mlo/Wlo/Mhi/Whi clock is synthetic; no Darwin clock capability claim',
                'fixture READ binding and private kernel/provider enrollment remain synthetic'])
