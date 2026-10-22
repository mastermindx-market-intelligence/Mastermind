"""Complete synthetic inventories only; never sample or mutate the host."""
from types import SimpleNamespace as S
from unittest.mock import Mock

import pytest

from tests.test_native_acquisition import MAIN, OTHER, _load_fixture_world


@pytest.fixture
def world(monkeypatch):
    peer, release, host, normalization = _load_fixture_world()
    own = normalization.Instance(10, 110, 1)
    state = S(peer=peer, release=release, host=host, own=own, now=10,
              inventories=[(1, 10, 20)] * 2, inventory_calls=[], images=[],
              row_maps={}, image_error=None, inventory_error=None,
              after_inventory=lambda count: None, instance=own,
              main=MAIN, budgets=[])

    def row(pid, identity=OTHER, path='/positive/image', unique=None):
        return host._ImageRow(normalization.Instance(pid, unique or pid + 100, 1),
                              path, identity)

    state.row = row

    def boundary(budget):
        state.budgets.append(budget)
        budget.check(force=True)

    def pids(budget):
        boundary(budget)
        count = len(state.inventory_calls)
        if state.inventory_error is not None:
            raise state.inventory_error
        assert count < len(state.inventories), 'unexpected additional inventory'
        value = state.inventories[count]
        state.inventory_calls.append(value)
        state.after_inventory(count + 1)
        return value

    def image(pid, budget):
        boundary(budget)
        acquisition = (len(state.inventory_calls) - 1) // 2
        state.images.append((acquisition, pid))
        if state.image_error is not None:
            raise state.image_error
        return state.row_maps.get(acquisition, {}).get(
            pid, row(pid, MAIN if pid == 10 else OTHER))

    def instance(pid, budget):
        boundary(budget)
        assert pid == 10
        return state.instance

    def physical(path, budget):
        boundary(budget)
        assert path == peer._PYTHON_MAIN_EXECUTABLE
        return state.main

    monkeypatch.setattr(host, 'os', S(getpid=lambda: 10, geteuid=lambda: 0))
    monkeypatch.setattr(host, 'sys', S(platform='darwin'))
    monkeypatch.setattr(release, 'time', S(monotonic_ns=lambda: state.now))
    monkeypatch.setattr(host, '_root_pids', pids)
    monkeypatch.setattr(host, '_image_row', image)
    monkeypatch.setattr(host, '_instance', instance)
    monkeypatch.setattr(host, '_physical_file', physical)
    state.budget = release._Budget(1000)
    return state


@pytest.mark.parametrize('first,settled', [
    ((1, 10, 20), (1, 10, 20, 30)),
    ((1, 10, 20), (1, 10)),
])
def test_complete_inventory_churn_discards_rows_and_acquires_new_proof(world, first, settled):
    world.inventories = [first, settled, settled, settled]
    # Even an unchanged PID is freshly read, never copied from the old pass.
    world.row_maps[1] = {1: world.row(1, path='/new/positive/image')}
    result = world.host._root_census(world.budget)
    assert tuple(row.instance.pid for row in result.rows) == settled
    assert result.rows[0].kernel_path == '/new/positive/image'
    assert result.matching_runtime_instances == (world.own,)
    assert world.images == ([(0, pid) for pid in first]
                            + [(1, pid) for pid in settled] * 2)
    assert all(budget is world.budget for budget in world.budgets)
    assert world.budget.endpoint == 1000


def test_third_complete_acquisition_can_settle_without_reusing_rows(world):
    a, b, c = (1, 10, 20), (1, 10, 20, 30), (1, 10, 20, 30, 40)
    world.inventories = [a, b, b, c, c, c]
    result = world.host._root_census(world.budget)
    assert tuple(row.instance.pid for row in result.rows) == c
    assert world.images == ([(0, pid) for pid in a] + [(1, pid) for pid in b]
                            + [(2, pid) for pid in c] * 2)
    world.peer._verify_python_runtime.assert_called_once_with(world.budget)


def test_churn_is_bounded_without_a_fourth_inventory_pair(world):
    world.inventories = [(1, 10, 20), (1, 10, 20, 30)] * 3
    with pytest.raises(world.host.HostObservationError, match='ROOT_CENSUS_DRIFT'):
        world.host._root_census(world.budget)
    assert len(world.inventory_calls) == 6


@pytest.mark.parametrize('code', [
    'SERVICE_PROCESS_OBSERVATION_SIZE_INVALID', 'RECOVERY_PROCESS_IMAGE_DRIFT',
    'RECOVERY_IMAGE_MAPPING_UNAVAILABLE', 'permission denied',
])
def test_unknown_or_unstable_image_is_never_reacquired(world, code):
    error = ValueError(code)
    world.image_error = error
    with pytest.raises(ValueError) as raised:
        world.host._root_census(world.budget)
    assert raised.value is error
    assert len(world.inventory_calls) == 1


def test_unknown_image_after_positive_churn_still_stops_immediately(world):
    world.inventories = [(1, 10, 20), (1, 10)] * 3
    error = OSError('unreadable')
    def after(count):
        if count == 3:
            world.image_error = error
    world.after_inventory = after
    with pytest.raises(OSError) as raised:
        world.host._root_census(world.budget)
    assert raised.value is error
    assert len(world.inventory_calls) == 3


def test_inventory_refusal_is_not_churn(world):
    world.inventory_error = world.host.HostObservationError('RECOVERY_ROOT_INVENTORY_UNAVAILABLE')
    with pytest.raises(world.host.HostObservationError) as raised:
        world.host._root_census(world.budget)
    assert raised.value is world.inventory_error
    assert not world.images


@pytest.mark.parametrize('missing_in', ['before', 'after'])
def test_observer_must_belong_to_both_inventories(world, missing_in):
    world.inventories[0 if missing_in == 'before' else 1] = (1, 20)
    with pytest.raises(world.host.HostObservationError, match='OBSERVER_NOT_ACCOUNTED'):
        world.host._root_census(world.budget)
    assert len(world.inventory_calls) == (1 if missing_in == 'before' else 2)


def test_changed_observer_image_between_candidates_cannot_be_reanchored(world):
    world.inventories = [(1, 10, 20), (1, 10)] + [(1, 10)] * 2
    world.row_maps[1] = {10: world.row(10, MAIN, '/changed/observer/path')}
    with pytest.raises(world.host.HostObservationError, match='ROOT_CENSUS_DRIFT'):
        world.host._root_census(world.budget)


def test_existing_budget_refusal_prevents_any_acquisition(world):
    refusal = world.release.ReleaseObservationError('ORIGINAL_REFUSAL')
    world.budget.primary_refusal = refusal
    with pytest.raises(world.release.ReleaseObservationError) as raised:
        world.host._root_census(world.budget)
    assert raised.value is refusal
    assert not world.inventory_calls and not world.images
    world.peer._verify_python_runtime.assert_not_called()


@pytest.mark.parametrize('change', ['observer', 'runtime', 'runtime_recheck'])
def test_anchors_cannot_be_replaced_during_inventory_churn(world, change):
    world.inventories = [(1, 10, 20), (1, 10)] * 3
    def after(count):
        if count == 2:
            if change == 'observer':
                world.instance = world.row(10, unique=999).instance
            elif change == 'runtime':
                world.main = OTHER
            else:
                world.peer._recheck_python_runtime.side_effect = ValueError('runtime invalid')
    world.after_inventory = after
    with pytest.raises(ValueError):
        world.host._root_census(world.budget)
    assert len(world.inventory_calls) == 2


@pytest.mark.parametrize('new_time,code', [(1000, 'DEADLINE_EXCEEDED'), (9, 'CLOCK_ROLLBACK')])
def test_one_absolute_budget_latches_failure_during_reacquisition(world, new_time, code):
    world.inventories = [(1, 10, 20), (1, 10)] * 3
    world.after_inventory = lambda count: setattr(world, 'now', new_time) if count == 2 else None
    with pytest.raises(world.release.ReleaseObservationError, match=code) as original:
        world.host._root_census(world.budget)
    world.now = 20
    with pytest.raises(world.release.ReleaseObservationError) as later:
        world.budget.check(force=True)
    assert later.value is original.value
    assert len(world.inventory_calls) == 2
    assert world.budget.endpoint == 1000


@pytest.mark.parametrize('earlier,later', [(True, False), (False, True)])
def test_reacquisition_cannot_discard_or_introduce_an_observed_runtime_owner(world, earlier, later):
    world.inventories = [(1, 10, 20), (1, 10, 20, 30)] + [(1, 10, 20, 30)] * 2
    world.row_maps = {0: {20: world.row(20, MAIN if earlier else OTHER)},
                      1: {20: world.row(20, MAIN if later else OTHER)}}
    with pytest.raises(world.host.HostObservationError, match='ROOT_CENSUS_DRIFT'):
        world.host._root_census(world.budget)


def test_stable_foreign_python_still_fails_old_owner_exclusion_after_churn(world, monkeypatch):
    world.inventories = [(1, 10, 20), (1, 10, 20, 30)] + [(1, 10, 20, 30)] * 2
    world.row_maps = {i: {20: world.row(20, MAIN, '/different/path/same/inode')} for i in (0, 1)}
    monkeypatch.setattr(world.release, '_boot', Mock(return_value='same-boot'))
    monkeypatch.setattr(world.host, '_strict_disabled_unloaded', Mock())
    with pytest.raises(world.host.HostObservationError, match='PINNED_ROOT_INTERPRETER_REMAINS'):
        world.host._observe_old_owner_exclusion(deadline_monotonic_ns=1000)


def test_positive_row_drift_inside_final_pair_is_not_inventory_churn(world, monkeypatch):
    original = world.host._image_row
    def image(pid, budget):
        value = original(pid, budget)
        return world.row(pid, unique=999) if len(world.inventory_calls) == 2 and pid == 20 else value
    monkeypatch.setattr(world.host, '_image_row', image)
    with pytest.raises(world.host.HostObservationError, match='ROOT_CENSUS_DRIFT'):
        world.host._root_census(world.budget)
    assert len(world.inventory_calls) == 2
