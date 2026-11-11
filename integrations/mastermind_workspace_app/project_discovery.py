"""Request-local discovery from the SAME installed DATA/Events owners.

Selectors are bounded original CREATE metadata, not membership. Each selected
work is independently qualified against the protected default, original Event,
exact original WS blob, current canonical DATA view and pinned CODE parser.
No cache publication, Runtime target, grant, source write or new store occurs.
"""
from dataclasses import dataclass, field
from copy import deepcopy
import hashlib
import json
import time

from integrations.mastermind_workspace_app.canonical_project_data import InstalledCanonicalProjectData, _ReadPrincipal
from control_plane.project_discovery_candidates import capture_created_project_candidates
from control_plane.canonical_data_publication import capture_source_publication

_SEAL = object()


def _fail():
    raise ValueError('PROJECT_DISCOVERY_UNAVAILABLE')


def _bytes(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()


@dataclass(frozen=True, slots=True)
class ProjectDiscoveryCapture:
    _seal: object = field(repr=False)
    _owner: object = field(repr=False)
    _context: tuple = field(repr=False)
    _guard: object = field(repr=False)
    _candidates: object = field(repr=False)
    _scope: str = field(repr=False)
    _entries: tuple = field(repr=False)
    _document: bytes = field(repr=False)
    _active: list = field(repr=False)

    def check(self):
        if (self._seal is not _SEAL or self._active != [True] or type(self._owner) is not InstalledProjectDiscovery
                or self._owner.context_binding() != self._context or self._guard() is not True):
            _fail()
        self._candidates.check(self._scope)
        for view, proof in self._entries:
            view.check()
            proof.check(self._scope)
        if self._guard() is not True:
            _fail()
        return True

    def document(self):
        self.check()
        return json.loads(self._document)

    def close(self):
        # Discard only this request's sealed code captures; no operation/lease
        # or data view is renewed, cancelled or transferred here.
        self._active[0] = False
        for view, _ in self._entries:
            self._owner.data.collector._discard_canonical_code_capture(view)


class InstalledProjectDiscovery:
    def __init__(self, data):
        if type(data) is not InstalledCanonicalProjectData:
            raise TypeError('actual installed canonical DATA owner required')
        self.data = data

    def context_binding(self):
        return (self.data, self.data.context_binding, self.data.context_binding(), self.data.view,
            self.data._frame, self.data._scope, self.data._read_stamp, self.data._latest_stamp,
            self.data._can_read, self.data._can_latest, self.data.collector.read_project_discovery)

    def installed_binding(self):
        from control_plane.installed_project_discovery_binding import _issue_project_discovery
        return _issue_project_discovery(self, qualifier=lambda owner: type(owner) is InstalledProjectDiscovery)

    def capture(self, frame, *, work_ref=None):
        owner = self.data
        context = self.context_binding()
        principal = _ReadPrincipal(owner, _bytes(frame))
        scope = owner._scope(principal)
        if not owner._can_latest(principal):
            return None
        read_stamp = owner._read_stamp(principal)
        latest_stamp = owner._latest_stamp(principal)
        deadline = time.monotonic() + 15.0

        def guard():
            if (time.monotonic() >= deadline or self.context_binding() != context
                    or not owner._can_read(principal) or not owner._can_latest(principal)
                    or owner._scope(principal) != scope
                    or owner._read_stamp(principal) != read_stamp
                    or owner._latest_stamp(principal) != latest_stamp):
                _fail()
            return True

        candidates = capture_created_project_candidates(owner.events, scope, guard=guard)
        selected = candidates.document()
        if work_ref is not None and not any(item['work_ref'] == work_ref for item in selected['lookups']):
            _fail()
        entries, retained = [], []
        omitted = 0
        try:
            for lookup in selected['lookups']:
                if work_ref is not None and lookup['work_ref'] != work_ref:
                    continue
                guard()
                view = None
                try:
                    proof = capture_source_publication(owner.events, lookup, scope, guard=guard)
                    creation = proof.check(scope)
                    view = owner.view(principal, work_ref=lookup['work_ref'])
                    if view is None:
                        _fail()
                    retained.append((view, proof))
                    with view.capture_scope(deadline=deadline) as capture:
                        publisher, op = view._owner.publisher, capture.operation
                        commit = creation['sources'][0]['commit']
                        if publisher._git(['merge-base', '--is-ancestor', commit, view.data_commit], op).returncode != 0:
                            _fail()
                        ws_path = 'agentos/workstreams/WS-' + lookup['work_ref'][3:] + '.md'
                        originals = [source for source in creation['sources'] if source['path'] == ws_path]
                        if len(originals) != 1:
                            _fail()
                        raw = publisher._read_blob_at(op, commit, ws_path)
                        if raw is None or hashlib.sha256(raw).hexdigest() != originals[0]['content_sha256']:
                            _fail()
                        witness = view.witness()
                        with owner.collector.canonical_project_data_scope(view, work_ref=lookup['work_ref']):
                            record = owner.collector.read_project_discovery(work_ref=lookup['work_ref'],
                                observed_at_ms=witness['canonical_observed_at_ms'], timeout=min(15.0, capture.remaining()))
                        proof.check(scope)
                    entries.append(dict(record=record, creation_publication=creation, data_observation=witness,
                        source_generation=hashlib.sha256(_bytes(dict(record=record, creation=creation, witness=witness))).hexdigest()))
                except (ValueError, PermissionError):
                    guard()
                    if view is not None:
                        owner.collector._discard_canonical_code_capture(view)
                        retained = [pair for pair in retained if pair[0] is not view]
                    if work_ref is not None:
                        _fail()
                    omitted += 1
            guard()
            document = dict(schema='mastermind.project_discovery_capture.v1',
                entries=entries, coverage=dict(state='PARTIAL' if selected['has_more'] or omitted else 'COMPLETE',
                    limit=8, returned=len(entries), high_water=selected['high_water']))
            result = ProjectDiscoveryCapture(_SEAL, self, context, guard, candidates, scope, tuple(retained), _bytes(document), [True])
            result.check()
            return result
        except Exception:
            for view, _ in retained:
                owner.collector._discard_canonical_code_capture(view)
            _fail()
