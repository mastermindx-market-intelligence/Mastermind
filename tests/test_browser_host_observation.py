from dataclasses import asdict, replace
import pytest

from control_plane.executive_steward import Freshness, SourceOwner, SourceRef
from control_plane.browser_host_observation import (
    BrowserHostObservation,
    BrowserHostObservationError,
    BrowserHostQualification,
    BrowserHostState,
    qualify_browser_host,
)

NOW=1_791_192_000_000
DIGEST='a'*64


def observation(**changes):
    row=BrowserHostObservation(
        host_ref='m2',
        boot_ref='boot-20261005',
        profile_ref='chrome-profile-a',
        browser_instance_ref='chrome-instance-a',
        connector_generation='devtools-generation-a',
        browser_version='154.0.8037.95',
        backend_version='1.10.1',
        backend_schema_digest=DIGEST,
        remote_debugging_enabled=True,
        user_consent_observed=True,
        connected=True,
        observed_at_ms=NOW-1000,
        expires_at_ms=NOW+14000,
        source=SourceRef(
            SourceOwner.SURFACE_BINDINGS,
            'browser-surface-a',
            '2026-10-05T09:30:00Z',
            Freshness.CURRENT,
        ),
    )
    return replace(row,**changes) if changes else row


def qualify(row=None, *, digest=DIGEST, now=NOW):
    result=qualify_browser_host(
        row or observation(),
        expected_backend_schema_digest=digest,
        trusted_now_ms=now,
    )
    assert result.is_placement is False
    assert result.is_admission is False
    return result


def test_current_consented_autoconnect_host_is_ready_but_not_placement():
    result=qualify()
    assert result.state is BrowserHostState.READY
    assert result.reason=='ready'
    assert result.host_ref=='m2'
    assert result.boot_ref=='boot-20261005'
    assert result.profile_ref=='chrome-profile-a'
    assert result.backend_schema_digest==DIGEST
    assert set(result.to_dict())=={
        'schema','host_ref','boot_ref','profile_ref','browser_instance_ref',
        'connector_generation','backend_schema_digest','state','reason',
        'is_placement','is_admission',
    }


@pytest.mark.parametrize('version',['143.9.9.9','120.0.1.2'])
def test_chrome_before_autoconnect_floor_is_unavailable(version):
    result=qualify(observation(browser_version=version))
    assert (result.state.value,result.reason)==('unavailable','browser_version_unsupported')


def test_backend_version_and_schema_generation_are_exact():
    result=qualify(observation(backend_version='1.10.2'))
    assert (result.state.value,result.reason)==('unavailable','backend_version_mismatch')
    result=qualify(observation(backend_schema_digest='b'*64))
    assert (result.state.value,result.reason)==('unavailable','backend_schema_mismatch')


@pytest.mark.parametrize('field,reason',[
    ('remote_debugging_enabled','remote_debugging_disabled'),
    ('user_consent_observed','browser_consent_missing'),
    ('connected','backend_disconnected'),
])
def test_required_live_surface_conditions_fail_closed(field,reason):
    result=qualify(observation(**{field:False}))
    assert (result.state.value,result.reason)==('unavailable',reason)


@pytest.mark.parametrize('field',[
    'remote_debugging_enabled','user_consent_observed','connected'
])
def test_unknown_live_surface_condition_is_unknown_not_false_green(field):
    result=qualify(observation(**{field:None}))
    assert (result.state.value,result.reason)==('unknown','surface_state_unknown')


@pytest.mark.parametrize('change',[
    {'observed_at_ms':NOW+1},
    {'expires_at_ms':NOW},
    {'expires_at_ms':NOW-1},
])
def test_future_or_expired_observation_is_unknown(change):
    result=qualify(observation(**change))
    assert (result.state.value,result.reason)==('unknown','observation_not_current')


@pytest.mark.parametrize('freshness',[Freshness.STALE,Freshness.UNKNOWN])
def test_source_freshness_is_required_even_when_numeric_window_looks_current(freshness):
    row=observation()
    row=replace(row,source=replace(row.source,freshness=freshness))
    result=qualify(row)
    assert (result.state.value,result.reason)==('unknown','observation_not_current')


def test_expected_schema_digest_must_be_valid_and_exact():
    for value in ['', 'A'*64, 'a'*63, '/tmp/schema']:
        with pytest.raises(BrowserHostObservationError):
            qualify(observation(),digest=value)
    result=qualify(observation(),digest='b'*64)
    assert (result.state.value,result.reason)==('unavailable','backend_schema_mismatch')


@pytest.mark.parametrize('field,value',[
    ('host_ref','/Users/private'),
    ('profile_ref','alice@example.com'),
    ('browser_instance_ref',''),
    ('connector_generation','x\n'),
    ('boot_ref','x'*129),
    ('browser_version','154'),
    ('browser_version','154.x.1.1'),
    ('backend_version','1.10'),
    ('backend_schema_digest','g'*64),
    ('remote_debugging_enabled',1),
    ('user_consent_observed','yes'),
    ('connected',0),
    ('observed_at_ms',True),
    ('expires_at_ms',-1),
])
def test_observation_shape_is_secret_safe_and_strict(field,value):
    with pytest.raises(BrowserHostObservationError):
        observation(**{field:value})


def test_surface_binding_source_owner_is_required():
    row=observation()
    with pytest.raises(BrowserHostObservationError):
        replace(row,source=SourceRef(
            SourceOwner.CAPACITY,'capacity-a','2026-10-05T09:30:00Z',Freshness.CURRENT))


@pytest.mark.parametrize('now',[True,-1,1.5,'1'])
def test_trusted_clock_is_strict(now):
    with pytest.raises(BrowserHostObservationError):
        qualify(observation(),now=now)


def test_result_is_deterministic_and_input_is_not_mutated():
    row=observation(); before=asdict(row)
    first=qualify(row); second=qualify(row)
    assert first==second
    assert before==asdict(row)


def test_contract_does_not_duplicate_capacity_or_placement_metrics():
    names=set(BrowserHostObservation.__dataclass_fields__)
    for forbidden in {'cpu','memory','load','active_lanes','lane_ceiling','quota','rank','score','worker_id','attempt_id'}:
        assert forbidden not in names

def test_ready_qualification_cannot_be_forged_outside_the_qualifier():
    with pytest.raises(BrowserHostObservationError, match='qualification seal'):
        BrowserHostQualification(
            host_ref='m2',
            boot_ref='boot-20261005',
            profile_ref='chrome-profile-a',
            browser_instance_ref='chrome-instance-a',
            connector_generation='devtools-generation-a',
            backend_schema_digest=DIGEST,
            state=BrowserHostState.READY,
            reason='ready',
        )
