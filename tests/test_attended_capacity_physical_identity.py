"""Real SQLite attended-route row must retain its physical registered identity.

These are pure test-owned memory rows and the protected attended catalogue;
they do not admit an installed external provider or launch a worker.
"""
import json
import sqlite3
import pytest

from control_plane.executive_runtime import _capacity_matches_route
from control_plane.executive_runtime import _normalise_constraints
from control_plane.model_router import ModelRouter
from tests.test_fabric_attended_routing import router, member
from control_plane.executive_runtime import _project_work_placement


def row_with_physical_fields(metadata, *, provider, worker_type, model):
    conn=sqlite3.connect(":memory:")
    conn.row_factory=sqlite3.Row
    try:
        return conn.execute(
            "SELECT ? AS worker_id, ? AS metadata_json, ? AS provider,"
            " ? AS worker_provider, ? AS worker_type, ? AS model,"
            " ? AS effort, ? AS cost_class",
            ("fixture-attended",json.dumps(metadata),provider,provider,
             worker_type,model,"medium","small"),
        ).fetchone()
    finally:conn.close()


@pytest.mark.parametrize("provider,worker_type,model", [
    ("glm","openai-compatible","minimax-m3"),
    ("minimax","openai-compatible","minimax-m3"),
    ("minimax","attended-fabric","foreign-model"),
])
def test_real_attended_quota_row_must_match_its_catalogue_physical_identity(router,provider,worker_type,model):
    from control_plane.executive_runtime import _normalise_constraints
    selected=member(router)
    plan={"work_placement_union":[selected]}
    constraints=_project_work_placement({},plan,
        {"provider_realm":"minimax","quota_class":"minimax-read"},
        raw_root_constraints=plan)
    constraints=_normalise_constraints(constraints)
    metadata={k:v for k,v in constraints.items()
              if k not in ("provider","eligible_quota_classes")}
    metadata["model_alias"]="minimax.attended"
    row=row_with_physical_fields(metadata,provider=provider,worker_type=worker_type,model=model)
    assert not _capacity_matches_route(row,constraints)


def test_real_attended_quota_row_accepts_exact_catalogue_identity(router):
    selected=member(router)
    plan={"work_placement_union":[selected]}
    constraints=_project_work_placement({},plan,
        {"provider_realm":"minimax","quota_class":"minimax-read"},
        raw_root_constraints=plan)
    constraints=_normalise_constraints(constraints)
    metadata={k:v for k,v in constraints.items()
              if k not in ("provider","eligible_quota_classes")}
    metadata["model_alias"]="minimax.attended"
    exact=row_with_physical_fields(metadata,provider="minimax",
                                   worker_type="attended-fabric",model="minimax-m3")
    assert _capacity_matches_route(exact,constraints)


def test_real_attended_sqlite_row_missing_worker_type_refuses_even_if_metadata_correct(router):
    selected=member(router)
    plan={"work_placement_union":[selected]}
    constraints=_project_work_placement({},plan,
        {"provider_realm":"minimax","quota_class":"minimax-read"},
        raw_root_constraints=plan)
    constraints=_normalise_constraints(constraints)
    metadata={k:v for k,v in constraints.items()
              if k not in ("provider","eligible_quota_classes")}
    metadata["model_alias"]="minimax.attended"
    conn=sqlite3.connect(":memory:")
    conn.row_factory=sqlite3.Row
    try:
        incomplete=conn.execute(
            "SELECT 'fixture-worker' AS worker_id, ? AS metadata_json,"
            " 'minimax' AS provider, 'minimax' AS worker_provider,"
            " 'minimax-m3' AS model, 'medium' AS effort,'small' AS cost_class",
            (json.dumps(metadata),),
        ).fetchone()
    finally:conn.close()
    assert not _capacity_matches_route(incomplete,constraints)
