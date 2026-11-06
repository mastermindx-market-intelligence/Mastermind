"""Reproduce the pinned selector counterexample without network or canonical writes.

The fixture contains finite regression inputs and AST-extracted code fragments.
Only the date regex, citation helpers, association and ranking are executed.
This is neither a full Agent OS compiler test nor a production operation.
Run with Python 3.9+ from any directory. Output is JSON on stdout only.
"""
from __future__ import annotations
import ast
import json
from pathlib import Path
import re
from typing import Any


def reproduce() -> dict[str, Any]:
    fixture = json.loads(Path(__file__).with_name('handoff-selector-fixture.json').read_text())
    scope: dict[str, Any] = {'re': re, 'Any': Any}
    for fragment in fixture['source_fragments']:
        node = ast.parse(fragment['ast_unparsed_source'])
        exec(compile(node, fixture['source_path'], 'exec'), scope)
    records = {Path(i['filename']).stem: i['frontmatter'] for i in fixture['inputs']}
    paths = {Path(i['filename']).stem: Path(i['filename']) for i in fixture['inputs']}
    scope.update(key=fixture['key'], hnd_all=records, handoff_paths=paths)
    exec(compile(ast.parse(fixture['association']['ast_unparsed_source']), fixture['source_path'], 'exec'), scope)
    mine = scope['mine']
    latest = max(mine, key=scope['handoff_rank'])
    return {
        'source_pin': fixture['source_pin'],
        'source_sha256': fixture['source_sha256'],
        'inputs': [{'filename': i['filename'], 'association_selected': Path(i['filename']).stem in mine,
                    'rank': scope['handoff_rank'](Path(i['filename']).stem)} for i in fixture['inputs']],
        'selected_handoff': latest + '.md',
        'dropped_as_older_handoff': [s + '.md' for s in mine if s != latest],
        'chronologically_latest': fixture['chronologically_latest'],
        'correct': latest + '.md' == fixture['chronologically_latest'],
        'scope': fixture['scope']
    }


if __name__ == '__main__':
    print(json.dumps(reproduce(), indent=2))
