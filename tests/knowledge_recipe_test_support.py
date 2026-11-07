"""Actual protected f55 compiler fixture, independent of installed READ modules.

This fixture attests only its exact published source bytes. It is not a compiler
issuer, source owner, installed capability or authenticated publication proof.
The workstream is synthetic and was already accepted by the canonical parser in
its separate READ tests. No live Macro checkout/environment variable is needed.
"""
from __future__ import annotations
import base64
import hashlib
import json
from pathlib import Path
import types
import zlib

HAS_OWNER_RECIPES = True  # A committed source fixture, not an optional live path.


def _fixture():
    value=json.loads((Path(__file__).parent/'fixtures/project-knowledge-recipe-canonical-a8a5.json').read_bytes())
    assert value['schema']=='mastermind.test_project_knowledge_recipe_source.v1'
    assert value['repository']=='mastermindx-market-intelligence/macro'
    assert value['commit']=='a8a5d3523614777d88eb2579d6efab52cd862e33'
    return value


def canonical_workstream():
    return _fixture()['synthetic_workstream_utf8']


def load_recipes():
    fixture=_fixture();source=fixture['recipe']
    assert source['path']=='scripts/project_knowledge_recipes.py'
    raw=zlib.decompress(base64.b64decode(source['zlib_base64'],validate=True))
    assert len(raw)<=131072
    assert hashlib.sha256(raw).hexdigest()==source['content_sha256']
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==source['git_blob_sha']
    module=types.ModuleType('_actual_protected_knowledge_recipe_test_fixture')
    module.__file__='published-source:a8a5d3523614777d88eb2579d6efab52cd862e33/'+source['path']
    exec(compile(raw,module.__file__,'exec'),module.__dict__)
    return module
