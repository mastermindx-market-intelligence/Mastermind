"""OMH advice is consumed without adding a provider or admission authority."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def api():
    try:
        return importlib.import_module('integrations.hermes_omh.recommendations')
    except ModuleNotFoundError:
        pytest.fail('OMH recommendation bridge is not implemented')


def backend():
    return SimpleNamespace(
        mixture_chain_overrides_path=lambda home: Path(home)/'routing/model-chains.json',
        parse_mixture_chain_overrides=lambda raw: ({k:tuple((r['model'],r['reasoning_effort']) for r in v) for k,v in raw['categories'].items()}, 'applied'),
        chains_with_overrides=lambda raw: {'quick': (('glm-5.3-flash','low'), ('glm-5.3','medium')), **raw},
        recommend_skills=lambda message,limit: [dict(skill='test-driven-development',category='engineering',phase='test',description='Write the failing test.',suggested_prompt=message,served=True)],
        version='4.0.6')


def test_proposals_use_existing_backend_without_inventing_capacity(tmp_path):
    m=api();b=backend();before=set(tmp_path.iterdir())
    out=m.recommend('Find and fix the failing Python test','quick',omh_home=tmp_path,backend=b)
    assert out['state']=='RECOMMENDED_NOT_ADMITTED'
    assert out['model_candidates']==[{'model_alias':'glm-5.3-flash','reasoning_effort':'low'},{'model_alias':'glm-5.3','reasoning_effort':'medium'}]
    assert out['availability']=='NOT_OBSERVED' and out['admitted'] is False
    assert out['dispatched'] is False and out['selected_model'] is None
    assert 'served' not in json.dumps(out) and 'suggested_prompt' not in json.dumps(out)
    assert 'Find and fix' not in json.dumps(out)
    assert out['skills'][0]['skill']=='test-driven-development'
    assert set(tmp_path.iterdir())==before


def test_configured_chain_is_reused_not_replaced(tmp_path):
    m=api();b=backend();p=tmp_path/'routing/model-chains.json';p.parent.mkdir()
    p.write_text(json.dumps({'schema_version':'model_category_chains/v1','categories':{'quick':[{'model':'glm-5.3','reasoning_effort':'high'}]}}))
    before=p.read_bytes()
    out=m.recommend('test','quick',omh_home=tmp_path,backend=b)
    assert out['origin']=='configured_override'
    assert out['model_candidates']==[{'model_alias':'glm-5.3','reasoning_effort':'high'}]
    assert p.read_bytes()==before


@pytest.mark.parametrize('raw',[b'{"categories":{},"categories":{}}',b'{"categories":NaN}',b'\xff',b'['*1000+b']'*1000,b'x'*131073])
def test_invalid_override_refuses_without_default_fallback(tmp_path,raw):
    m=api();p=tmp_path/'routing/model-chains.json';p.parent.mkdir();p.write_bytes(raw)
    with pytest.raises(m.RecommendationError): m.recommend('test','quick',omh_home=tmp_path,backend=backend())


def test_upstream_rejection_remains_refusal(tmp_path):
    m=api();b=backend();p=tmp_path/'routing/model-chains.json';p.parent.mkdir();p.write_text('{}')
    b.parse_mixture_chain_overrides=lambda raw: ({},'invalid: SECRET_SENTINEL')
    with pytest.raises(m.RecommendationError) as exc:m.recommend('test','quick',omh_home=tmp_path,backend=b)
    assert 'SECRET_SENTINEL' not in str(exc.value)


@pytest.mark.parametrize('message,category',[('', 'quick'),('x'*4001,'quick'),('x','unknown'),('x',[]),('x\x00y','quick'),('\ud800','quick')])
def test_bad_request_refuses(tmp_path,message,category):
    m=api()
    with pytest.raises(m.RecommendationError):m.recommend(message,category,omh_home=tmp_path,backend=backend())


def test_only_existing_chain_file_is_read(tmp_path,monkeypatch):
    m=api();seen=[];real=m.read_chain_file
    def read(path):
        seen.append(str(path));return real(path)
    monkeypatch.setattr(m,'read_chain_file',read)
    m.recommend('test','quick',omh_home=tmp_path,backend=backend())
    assert seen==[str(tmp_path/'routing/model-chains.json')]


def test_symlinked_override_refuses(tmp_path):
    m=api();p=tmp_path/'routing/model-chains.json';p.parent.mkdir();t=tmp_path/'target';t.write_text('{}');p.symlink_to(t)
    with pytest.raises(m.RecommendationError):m.recommend('test','quick',omh_home=tmp_path,backend=backend())


def test_backend_error_is_not_claimed_as_no_match(tmp_path):
    m=api();b=backend()
    def fail(*a,**k):raise RuntimeError('PRIVATE_SENTINEL')
    b.recommend_skills=fail
    with pytest.raises(m.RecommendationError) as exc:m.recommend('test','quick',omh_home=tmp_path,backend=b)
    assert 'PRIVATE_SENTINEL' not in str(exc.value)
