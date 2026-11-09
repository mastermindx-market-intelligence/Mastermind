"""Canonical authored dependency records -> actual signed Programs owner, no DTO edits."""
import json
import os
from pathlib import Path
from tests import test_office_source_journey_export as original
from tests.test_workspace_project_direction_http import rsa_key, short_socket_root


def test_canonical_dependencies_reach_same_programs_observation(tmp_path, monkeypatch, rsa_key, short_socket_root):
    bound = original.bound
    def graph_source(*args, **kwargs):
        collector, seen = bound(*args, **kwargs)
        root = seen['macro'] / 'agentos/workstreams'
        record = root / 'WS-DIRECTION-TEST.md'
        record.write_text(record.read_text().replace('status: active', 'status: proposed\ndepends_on: ["WS:RESEARCH-INPUT"]'))
        (root / 'WS-RESEARCH-INPUT.md').write_text('''---
key: RESEARCH-INPUT
title: Research input
objective: Supply the authored input.
status: proposed
program: executive-os
repos: [macro]
owner: astra-meta-ceo
class: build
blast_radius: user_facing
ambiguity: scoped
waves:
  - id: INPUT
    title: Gather input
    status: todo
next_action: Gather the input.
---
Private input body must not be projected.
''')
        return collector, seen
    monkeypatch.setattr(original, 'bound', graph_source)
    target = tmp_path / 'whole.json'
    monkeypatch.setenv('MMOS_OFFICE_FIXTURE', str(target))
    original.test_whole_office_canonical_owner(tmp_path, monkeypatch, rsa_key, short_socket_root)
    value = json.loads(target.read_text())
    cards = value['responses']['programs']['body']['control_room']['work']
    by_ref = {row['work_ref']: row['agent_os'] for row in cards}
    actual = by_ref['WS:DIRECTION-TEST']
    assert actual['depends_on'] == ['WS:RESEARCH-INPUT']
    assert actual['unmet_dependencies'] == ['WS:RESEARCH-INPUT']
    assert actual['state'] == 'blocked'
    assert by_ref['WS:RESEARCH-INPUT']['depends_on'] == []
    assert 'Private input body' not in json.dumps(value)
    # Export this ONE whole owner result unchanged; no merge with earlier runs.
    destination = os.environ.get('MMOS_DEPENDENCIES_FIXTURE')
    if destination:
        Path(destination).write_bytes(target.read_bytes())
