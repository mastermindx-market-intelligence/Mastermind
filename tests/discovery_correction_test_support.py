"""Exact Macro source fixture; source evidence only, no owner or installed grant."""
import base64
import hashlib
import json
from pathlib import Path
import zlib


def source_bytes(path):
    fixture=json.loads((Path(__file__).parent/'fixtures/discovery-correction-source.json').read_bytes())
    assert fixture['schema']=='mastermind.test_discovery_correction_source.v1'
    assert fixture['repository']=='mastermindx-market-intelligence/macro'
    assert fixture['base_commit']=='5c8d02f78ca2fe317e861d69169733e56237cbcc'
    assert fixture['source_commit']=='a9906c9d5aaf816048d6467fa39d895034180c87'
    assert fixture['source_status']=='PUBLISHED_SOURCE_CANDIDATE'
    assert fixture['pull_request']=='https://github.com/mastermindx-market-intelligence/macro/pull/10831'
    item=fixture['files'][path]
    raw=zlib.decompress(base64.b64decode(item['zlib_base64'],validate=True))
    assert len(raw)<=1048576
    assert hashlib.sha256(raw).hexdigest()==item['content_sha256']
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==item['git_blob_sha']
    return raw.decode('utf-8')
