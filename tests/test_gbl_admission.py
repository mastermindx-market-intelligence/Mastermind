"""GBL-3 admission table tests (lane GBL, BUILD_PLAN row GBL-3).

admission.py owns the edge's closed door in the fixed lane order —
principal → targets → kinds → rates → per-thread allowlist — over an
immutable table that SHIPS EMPTY (v1: every caller refused until the
principal's act adds a row).  Pure law, no I/O; harmless fixture words.
"""
from __future__ import annotations

import pytest

from common.gbl_contract import MAX_ASKS_PER_HOUR_PER_PRINCIPAL
from integrations.gbl.admission import (
    DEFAULT_ADMISSION_TABLE,
    GblAdmissionError,
    PrincipalAdmission,
    admit_ask,
    admit_kind,
    admit_message_thread,
    admit_principal,
    admit_rate,
    admit_target,
)

SUBJECT = "a" * 64          # sha256-shaped fixture digest
PRINCIPAL = "grok-account-main"
TARGET = "secretary"
ENV_ID = "team-dev-1"
THREAD_REF = "th_team_dev_1"


def row(**over) -> PrincipalAdmission:
    base = {
        "subject_digest": SUBJECT,
        "principal": PRINCIPAL,
        "targets": frozenset({"secretary", "assurance"}),
        "kinds": frozenset({"delegate"}),
        "max_asks_per_hour": 5,
        "message_allowlist": ({"environment_id": ENV_ID,
                               "thread_ref": THREAD_REF},),
    }
    base.update(over)
    return PrincipalAdmission(**base)


def typed(expect):
    return pytest.raises(GblAdmissionError) as err


# ── The table ships EMPTY ────────────────────────────────────────────────────


class TestShipsEmpty:
    def test_default_table_is_empty(self):
        assert DEFAULT_ADMISSION_TABLE == ()

    def test_empty_table_refuses_every_principal(self):
        with pytest.raises(GblAdmissionError) as err:
            admit_principal((), SUBJECT)
        assert err.value.code == "ADMISSION_EMPTY"


# ── The fixed order: principal → target → kind → rate ───────────────────────


class TestOrder:
    def test_principal_before_target(self):
        # Unknown principal AND unknown target: principal is named first.
        with pytest.raises(GblAdmissionError) as err:
            admit_ask((row(),), subject_digest="b" * 64, target="nobody",
                      kind="delegate", asks_in_last_hour=0)
        assert err.value.code == "PRINCIPAL_NOT_ADMITTED"

    def test_target_before_kind(self):
        with pytest.raises(GblAdmissionError) as err:
            admit_ask((row(),), subject_digest=SUBJECT, target="nobody",
                      kind="question", asks_in_last_hour=0)
        assert err.value.code == "TARGET_NOT_ALLOWED"

    def test_kind_before_rate(self):
        with pytest.raises(GblAdmissionError) as err:
            admit_ask((row(),), subject_digest=SUBJECT, target=TARGET,
                      kind="question", asks_in_last_hour=99)
        assert err.value.code == "KIND_NOT_ALLOWED"

    def test_rate_last(self):
        with pytest.raises(GblAdmissionError) as err:
            admit_ask((row(),), subject_digest=SUBJECT, target=TARGET,
                      kind="delegate", asks_in_last_hour=5)
        assert err.value.code == "RATE_LIMITED"

    def test_happy_path_returns_the_row(self):
        found = admit_ask((row(),), subject_digest=SUBJECT, target=TARGET,
                          kind="delegate", asks_in_last_hour=4)
        assert found.principal == PRINCIPAL


# ── The individual gates ─────────────────────────────────────────────────────


class TestGates:
    def test_admit_principal_finds_and_refuses(self):
        table = (row(), row(subject_digest="c" * 64, principal="second"))
        assert admit_principal(table, "c" * 64).principal == "second"
        with pytest.raises(GblAdmissionError) as err:
            admit_principal(table, "d" * 64)
        assert err.value.code == "PRINCIPAL_NOT_ADMITTED"

    def test_admit_target(self):
        table = (row(),)
        admit_target(admit_principal(table, SUBJECT), "assurance")
        with pytest.raises(GblAdmissionError) as err:
            admit_target(admit_principal(table, SUBJECT), "nobody")
        assert err.value.code == "TARGET_NOT_ALLOWED"

    def test_admit_kind_subset_of_contract_kinds(self):
        with pytest.raises(GblAdmissionError) as err:
            admit_kind(admit_principal((row(),), SUBJECT), "question")
        assert err.value.code == "KIND_NOT_ALLOWED"

    def test_admit_rate_ceiling_and_global_law(self):
        admitted = admit_principal((row(),), SUBJECT)
        admit_rate(admitted, 4)                    # 4 + 1 <= 5: passes
        with pytest.raises(GblAdmissionError) as err:
            admit_rate(admitted, 5)
        assert err.value.code == "RATE_LIMITED"
        # The contract-global ceiling refuses even below the row ceiling.
        with pytest.raises(GblAdmissionError) as err:
            admit_rate(admitted, MAX_ASKS_PER_HOUR_PER_PRINCIPAL)
        assert err.value.code == "RATE_LIMITED"

    def test_row_ceiling_cannot_exceed_contract_maximum(self):
        with pytest.raises(ValueError):
            row(max_asks_per_hour=MAX_ASKS_PER_HOUR_PER_PRINCIPAL + 1)

    def test_row_kinds_must_be_contract_kinds(self):
        with pytest.raises(ValueError):
            row(kinds=frozenset({"admin"}))

    def test_row_subject_digest_shape(self):
        with pytest.raises(ValueError):
            row(subject_digest="not-a-digest")

    def test_row_targets_kinds_nonempty(self):
        with pytest.raises(ValueError):
            row(targets=frozenset())
        with pytest.raises(ValueError):
            row(kinds=frozenset())


# ── The per-thread allowlist (team.message) ──────────────────────────────────


class TestMessageAllowlist:
    def test_empty_allowlist_refuses_every_thread(self):
        admitted = admit_principal((row(message_allowlist=()),), SUBJECT)
        with pytest.raises(GblAdmissionError) as err:
            admit_message_thread(admitted, ENV_ID, THREAD_REF)
        assert err.value.code == "ALLOWLIST_EMPTY"

    def test_unlisted_thread_refused(self):
        admitted = admit_principal((row(),), SUBJECT)
        with pytest.raises(GblAdmissionError) as err:
            admit_message_thread(admitted, ENV_ID, "th_other")
        assert err.value.code == "THREAD_NOT_ALLOWED"

    def test_unlisted_environment_refused(self):
        admitted = admit_principal((row(),), SUBJECT)
        with pytest.raises(GblAdmissionError) as err:
            admit_message_thread(admitted, "chairman-app", THREAD_REF)
        assert err.value.code == "THREAD_NOT_ALLOWED"

    def test_listed_row_passes(self):
        admitted = admit_principal((row(),), SUBJECT)
        matched = admit_message_thread(admitted, ENV_ID, THREAD_REF)
        assert matched == {"environment_id": ENV_ID, "thread_ref": THREAD_REF}

    def test_allowlist_rows_must_be_well_formed(self):
        with pytest.raises(ValueError):
            row(message_allowlist=({"environment_id": ENV_ID},))
        with pytest.raises(ValueError):
            row(message_allowlist=({"environment_id": ENV_ID,
                                    "thread_ref": "",},))
