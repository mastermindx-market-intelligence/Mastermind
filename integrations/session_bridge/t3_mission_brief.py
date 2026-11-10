"""Complete long-horizon task context, not a workflow engine or admission grant."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlparse


def _text(value, label, bound=8192):
    if (type(value) is not str or not value.strip() or len(value.encode()) > bound
            or any(ord(x) < 32 and x not in '\n\r\t' or ord(x) == 127 for x in value)
            or re.search(r'\bsk-(?:admin-|proj-)?[A-Za-z0-9_-]{20,}|\bBearer\s+\S{16,}',value)):
        raise ValueError('Invalid or secret-like '+label)
    return value


def _items(values,label,limit=32):
    if type(values) is not tuple or not values or len(values)>limit:raise ValueError('Bounded immutable '+label+' required')
    for value in values:_text(value,label,2048)


@dataclass(frozen=True, slots=True)
class Phase:
    phase_id: str
    objective: str
    checks: tuple[str,...]

    def __post_init__(self):
        if type(self.phase_id) is not str or not re.fullmatch(r'[a-z][a-z0-9_-]{0,47}',self.phase_id):raise ValueError('Exact phase id required')
        _text(self.objective,'phase objective',4096);_items(self.checks,'phase checks',16)


@dataclass(frozen=True, slots=True)
class MissionBrief:
    mission_id: str
    objective: str
    source_ref: str
    base_sha: str
    phases: tuple[Phase,...]
    done_when: tuple[str,...]
    allowed_write_paths: tuple[str,...]
    non_goals: tuple[str,...]
    stop_conditions: tuple[str,...]
    notes_ref: str
    execution_envelope_ref: str

    def __post_init__(self):
        if type(self.mission_id) is not str or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',self.mission_id):raise ValueError('Exact mission id required')
        _text(self.objective,'objective')
        _text(self.source_ref,'source ref',2048)
        url=urlparse(self.source_ref);parts=url.path.split('/')
        if (url.scheme!='https' or url.netloc!='github.com' or len(parts)<6 or parts[3]!='blob'
                or not re.fullmatch(r'[0-9a-f]{40}',parts[4]) or url.query or url.fragment
                or '%' in url.path or any(x in ('','.','..') for x in parts[1:])):
            raise ValueError('Immutable source-linked mission required')
        if type(self.base_sha) is not str or not re.fullmatch(r'[0-9a-f]{40}',self.base_sha):raise ValueError('Exact accepted base required')
        if (type(self.phases) is not tuple or not 1<=len(self.phases)<=16
                or any(type(x) is not Phase for x in self.phases)
                or len({x.phase_id for x in self.phases})!=len(self.phases)):
            raise ValueError('Unique bounded phases required')
        for key in ('done_when','allowed_write_paths','non_goals','stop_conditions'):_items(getattr(self,key),key)
        for value in self.allowed_write_paths:
            p=PurePosixPath(value)
            if (p.is_absolute() or str(p)!=value or '\\' in value or any(x in ('.','..','.git') for x in p.parts)
                    or value=='.' or any(x in value for x in '*?[]:%') or any(ord(x)<=32 for x in value)):
                raise ValueError('Exact relative write scope required')
        for key in ('notes_ref','execution_envelope_ref'):_text(getattr(self,key),key,2048)
        if len(self.render().encode())>32768:raise ValueError('Mission exceeds prompt budget')

    def document(self):
        return dict(schema='mastermind.t3_mission_brief.v1',mission_id=self.mission_id,
                    objective=self.objective,source_ref=self.source_ref,base_sha=self.base_sha,
                    phases=[dict(phase_id=x.phase_id,objective=x.objective,checks=list(x.checks)) for x in self.phases],
                    done_when=list(self.done_when),allowed_write_paths=list(self.allowed_write_paths),
                    non_goals=list(self.non_goals),stop_conditions=list(self.stop_conditions),
                    notes_ref=self.notes_ref,execution_envelope_ref=self.execution_envelope_ref)

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.document(),sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def render(self):
        return ('BOUNDED NATIVE IMPLEMENTATION MISSION. This document describes work; it does not grant permissions, budget, provider accounts or child admission.\n'
                +json.dumps(self.document(),ensure_ascii=True,indent=2)
                +'\nExecute through the existing T3 thread and native tools. Keep Capacity Fabric as the provider; do not silently fall back. '
                 'Preserve the full original DONE_WHEN when steering, switching an allowed model, or compacting context. '
                 'After each material phase: run its checks, write a CAS-protected checkpoint to the linked shared notes, then reassess and continue the next safe in-scope phase. '
                 'Do not stop merely because a phase/commit/test is complete. Do not invent tests or accept your own completion. '
                 'Use native child delegation only under the existing scope and budget; return to the original thread. '
                 'At genuine permission, spend, unsafe effect, user-input or scope boundary, preserve exact original effects and report the gate rather than retrying or escalating privileges. '
                 'A final return must include mission_id, brief fingerprint, completed phases, original thread/run, changed files/artifact refs, actual checks with outcomes, remaining DONE_WHEN, blockers, and exact next action. '
                 'Native execution and notes are durable; the Web conversation is not a background daemon.\n')

    def checkpoint(self, *, completed_phases: tuple[str,...], next_action: str,
                   evidence: tuple[str,...], remaining: tuple[str,...], unknown_effects: tuple[str,...]=()):
        if (type(completed_phases) is not tuple or len(set(completed_phases))!=len(completed_phases)
                or not set(completed_phases)<={p.phase_id for p in self.phases}):raise ValueError('Checkpoint phase identity differs')
        _text(next_action,'next action',4096);_items(evidence,'evidence');_items(remaining,'remaining acceptance')
        if type(unknown_effects) is not tuple or len(unknown_effects)>16:raise ValueError('Bounded original-effect list required')
        for x in unknown_effects:_text(x,'unknown effect',2048)
        return dict(schema='mastermind.t3_mission_checkpoint.v1',mission_id=self.mission_id,
                    brief_sha256=self.fingerprint,completed_phases=list(completed_phases),
                    evidence=list(evidence),remaining_done_when=list(remaining),next_action=next_action,
                    unresolved_original_effects=list(unknown_effects),accepted=False)
