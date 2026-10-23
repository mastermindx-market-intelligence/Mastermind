"""Focused unit tests for the frozen cross-kind policy function
``control_plane.executive_runtime._paid_subject_codex_review_is_independent``.

Boundary and scope
------------------
These are unit boundary tests. They do NOT claim end-to-end producer proof of
any launch receipt: the two canonical validation boundaries are replaced with
known, already-qualified source fixtures and spied, while everything the
policy itself decides is exercised for real.

* ``control_plane.executive_paid_runtime.validated_paid_launch_material`` is
  the only paid-side seam that is replaced; both tests and policy agree that
  the real validator owns actual paid launch receipts.
* ``control_plane.executive_runtime._validated_sealed_worker_launch_material``
  is the only v1-side seam that is replaced.
* Both seams are spies: the tests assert the policy consulted each with the
  actual connection object and the exact attempt row, in order.
* The exact two-job lookup runs for real against a miniature in-memory SQLite
  database, so ``SELECT * FROM jobs WHERE job_id IN (?, ?)`` behaviour and the
  missing-row failure path are exercised.
* The real ``ExecutionCapabilityRegistry`` supplies the existing default
  ``sealed.worker.readonly.no-extensions.v1`` profile id and digest; no
  registry, profile, or digest is invented here.

Fixture discipline: every fixture below is clearly unit data. The paid GLM
subject fixtures deliberately carry no home anywhere (an absent paid home must
never participate in an independence comparison); the owned v1 sealed Codex
reviewer fixture carries its existing principal home. No secret, provider
call, network access, or account process is used: the only IO is the
in-memory SQLite database and the registry's own read-only input.
"""

import copy
import json
import sqlite3
import unittest
from unittest import mock

import control_plane.executive_runtime as er

# The existing default sealed worker profile this policy must stay pinned to.
SEALED_PROFILE_ID = "sealed.worker.readonly.no-extensions.v1"

_REVIEW_ATTESTATION_SCHEMA = "mastermind.executive_launch_attestation/v1"
_REVIEW_PRINCIPAL_SCHEMA = "mastermind.execution_principal_snapshot/v1"


def _canonical_json(value):
    """Exactly the canonical JSON form persisted rows must carry."""
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


def _non_sealed_execution_mode():
    """A real, non-sealed execution mode value for rejection cases."""
    for member in getattr(er.AttemptExecutionMode, "__members__", {}).values():
        value = getattr(member, "value", member)
        if value != er.AttemptExecutionMode.SEALED_WORKER.value:
            return value
    return "unsealed-direct"


def _base_fixtures(profile):
    """Fresh, already-qualified source fixtures. All values are unit data.

    Dict literals are kept in sorted key order so the stored JSON strings are
    canonical under the runtime's strict canonical JSON loader regardless of
    which canonicalizer compares them.
    """
    profile_id = profile.profile_id
    profile_digest = profile.profile_digest
    constraints = {
        "execution_profile_digest": profile_digest,
        "execution_profile_id": profile_id,
    }
    routing = {
        "adapter_id": "codex-cli",
        "execution_profile_digest": profile_digest,
        "execution_profile_id": profile_id,
    }
    subject_att = {
        "process_identity": {
            "boot_id": "unit-boot-a",
            "pgid": 3100,
            "pid": 3101,
            "start_identity": "unit-generation-subject",
        },
        "provider": "glm",
        "schema_version": _REVIEW_ATTESTATION_SCHEMA,
    }
    # Full honest paid principal: deliberately NO home anywhere.
    subject = {
        "account_label": "unit-glm-paid-account",
        "os_principal_name": "unit-paid-principal",
        "os_principal_uid": 2401,
        "provider": "glm",
        "schema_version": _REVIEW_PRINCIPAL_SCHEMA,
        "worker_id": "unit-glm-worker-subject",
    }
    subject_placement = {"kind": "paid-runtime"}  # unused by the policy
    subject_grant = {  # unused by the policy; paid work, not review
        "authorities": ["RESEARCH", "RUN_TESTS"],
        "write_paths": ["/unit/workspace"],
    }
    reviewer_att = {
        "process_identity": {
            "boot_id": "unit-boot-b",
            "pgid": 4100,
            "pid": 4102,
            "start_identity": "unit-generation-reviewer",
        },
        "provider": "codex",
        "schema_version": _REVIEW_ATTESTATION_SCHEMA,
    }
    # Owned v1 sealed Codex principal with its actual existing home.
    reviewer = {
        "account_label": "unit-codex-reviewer-account",
        "home": "/unit/codex/reviewer",
        "os_principal_name": "unit-codex-reviewer-principal",
        "os_principal_uid": 2410,
        "provider": "codex",
        "schema_version": _REVIEW_PRINCIPAL_SCHEMA,
        "worker_id": "unit-codex-worker-reviewer",
    }
    reviewer_placement = {"kind": "sealed-worker"}  # unused by the policy
    qualified_review_grant = {
        "authorities": ["READ"],
        "grant_id": "unit-grant-reviewer",
        "schema_version": "mastermind.execution_grant/v1",
        "validation_argv": [],
        "write_paths": [],
    }
    subject_job = {
        "constraints_json": _canonical_json(constraints),
        "current_attempt_id": "unit-attempt-subject",
        "job_id": "unit-job-subject",
        "orchestration_role": "work",
        "parent_job_id": "unit-job-parent",
        "reviews_job_id": None,
        "root_job_id": "unit-job-root",
    }
    review_job = {
        "constraints_json": _canonical_json(constraints),
        "current_attempt_id": "unit-attempt-review",
        "job_id": "unit-job-review",
        "orchestration_role": "review",
        "parent_job_id": "unit-job-parent",
        "reviews_job_id": "unit-job-subject",
        "root_job_id": "unit-job-root",
    }
    launch_metadata_json = _canonical_json({"routing": routing})
    reviewed_attempt = {
        "attempt_id": "unit-attempt-subject",
        "execution_mode": er.AttemptExecutionMode.SEALED_WORKER.value,
        "job_id": "unit-job-subject",
        "launch_metadata_json": launch_metadata_json,
    }
    review_attempt = {
        "attempt_id": "unit-attempt-review",
        "execution_mode": er.AttemptExecutionMode.SEALED_WORKER.value,
        "job_id": "unit-job-review",
        "launch_metadata_json": launch_metadata_json,
    }
    return {
        "constraints": constraints,
        "qualified_review_grant": qualified_review_grant,
        "review_attempt": review_attempt,
        "review_job": review_job,
        "review_grant": copy.deepcopy(qualified_review_grant),
        "reviewer": reviewer,
        "reviewer_att": reviewer_att,
        "reviewer_placement": reviewer_placement,
        "reviewed_attempt": reviewed_attempt,
        "routing": routing,
        "subject": subject,
        "subject_att": subject_att,
        "subject_grant": subject_grant,
        "subject_job": subject_job,
        "subject_placement": subject_placement,
    }


def _fresh_connection(fixtures):
    """Miniature in-memory database: the exact two-job lookup runs for real."""
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute(
        "CREATE TABLE jobs ("
        "job_id TEXT, orchestration_role TEXT, reviews_job_id TEXT,"
        " root_job_id TEXT, parent_job_id TEXT, current_attempt_id TEXT,"
        " constraints_json TEXT)"
    )
    connection.execute(
        "CREATE TABLE attempts ("
        "attempt_id TEXT, job_id TEXT, execution_mode TEXT,"
        " launch_metadata_json TEXT)"
    )
    for job in (fixtures["subject_job"], fixtures["review_job"]):
        connection.execute(
            "INSERT INTO jobs VALUES (?,?,?,?,?,?,?)",
            (
                job["job_id"],
                job["orchestration_role"],
                job["reviews_job_id"],
                job["root_job_id"],
                job["parent_job_id"],
                job["current_attempt_id"],
                job["constraints_json"],
            ),
        )
    for attempt in (fixtures["reviewed_attempt"], fixtures["review_attempt"]):
        connection.execute(
            "INSERT INTO attempts VALUES (?,?,?,?)",
            (
                attempt["attempt_id"],
                attempt["job_id"],
                attempt["execution_mode"],
                attempt["launch_metadata_json"],
            ),
        )
    connection.commit()
    return connection


class PaidSubjectCodexReviewIndependenceTest(unittest.TestCase):
    """Policy decisions for paid GLM SUBJECT -> sealed Codex REVIEWER."""

    maxDiff = None

    @classmethod
    def setUpClass(cls):
        # Real registry, real existing default profile, real digest.
        cls.profile = er.ExecutionCapabilityRegistry.load().resolve(
            SEALED_PROFILE_ID
        )

    # -- harness -------------------------------------------------------

    def _fixtures(self):
        return _base_fixtures(self.profile)

    def _run_policy(
        self, fixtures, *, db_mutate=None, paid_side=None, sealed_side=None
    ):
        connection = _fresh_connection(fixtures)
        if db_mutate is not None:
            db_mutate(connection)
        review_row = connection.execute(
            "SELECT * FROM attempts WHERE job_id = ?",
            (fixtures["review_job"]["job_id"],),
        ).fetchone()
        reviewed_row = connection.execute(
            "SELECT * FROM attempts WHERE job_id = ?",
            (fixtures["subject_job"]["job_id"],),
        ).fetchone()
        calls = []

        def paid_boundary(connection_arg, attempt_arg):
            calls.append(("paid", connection_arg, attempt_arg))
            if paid_side is not None:
                return paid_side(connection_arg, attempt_arg)
            return (
                fixtures["subject_att"],
                fixtures["subject"],
                fixtures["subject_placement"],
                fixtures["subject_grant"],
            )

        # The policy calls this seam as seam(review, connection=connection):
        # the keyword name is part of the canonical boundary contract.
        def sealed_boundary(attempt_arg, connection):
            calls.append(("v1", connection, attempt_arg))
            if sealed_side is not None:
                return sealed_side(attempt_arg, connection)
            return (
                fixtures["reviewer_att"],
                fixtures["reviewer"],
                fixtures["reviewer_placement"],
                fixtures["qualified_review_grant"],
            )

        with mock.patch.object(
            er, "_validated_sealed_worker_launch_material", sealed_boundary
        ), mock.patch(
            "control_plane.executive_paid_runtime.validated_paid_launch_material",
            paid_boundary,
        ):
            result = er._paid_subject_codex_review_is_independent(
                connection,
                review=review_row,
                reviewed=reviewed_row,
                review_grant=fixtures["review_grant"],
            )
        return result, calls, connection, review_row, reviewed_row

    def _assert_rejected(self, mutate=None, label="", **run_kwargs):
        fixtures = self._fixtures()
        if mutate is not None:
            mutate(fixtures)
        result, calls, connection, _review_row, _reviewed_row = self._run_policy(
            fixtures, **run_kwargs
        )
        self.assertFalse(result, f"policy must reject: {label}")
        self.assertTrue(
            calls, f"policy never consulted a validation boundary: {label}"
        )
        self.assertIs(
            calls[0][1],
            connection,
            "paid boundary must receive the actual connection",
        )
        return calls

    def _assert_qualified_fixtures_are_honest(self, fixtures):
        # The real default profile really is the qualified read-only v1 one;
        # these are exactly the attributes the policy itself requires.
        self.assertEqual(self.profile.profile_id, SEALED_PROFILE_ID)
        self.assertEqual(self.profile.execution_surface, "codex-exec")
        self.assertEqual(self.profile.auth_realm, "dedicated-worker-account")
        self.assertEqual(self.profile.sandbox_policy, "read-only")
        self.assertFalse(self.profile.write_capable)
        self.assertTrue(self.profile.enabled)
        # The paid subject carries no home anywhere; the owned v1 Codex
        # reviewer principal does.
        self.assertNotIn("home", fixtures["subject"])
        self.assertNotIn("home", fixtures["subject_placement"])
        self.assertNotIn("home", fixtures["subject_att"])
        self.assertIn("home", fixtures["reviewer"])

    # -- approved shapes ----------------------------------------------

    def test_qualified_paid_subject_and_owned_v1_codex_reviewer_are_independent(
        self,
    ):
        fixtures = self._fixtures()
        self._assert_qualified_fixtures_are_honest(fixtures)
        result, calls, connection, review_row, reviewed_row = self._run_policy(
            fixtures
        )
        self.assertTrue(result)
        # Exact boundary discipline: paid subject first, then the v1 sealed
        # reviewer, each with the actual connection and the exact attempt row.
        self.assertEqual([kind for kind, _c, _a in calls], ["paid", "v1"])
        self.assertIs(calls[0][1], connection)
        self.assertIs(calls[0][2], reviewed_row)
        self.assertIs(calls[1][1], connection)
        self.assertIs(calls[1][2], review_row)

    def test_repair_subject_is_independent_too(self):
        fixtures = self._fixtures()
        fixtures["subject_job"]["orchestration_role"] = "repair"
        result, calls, _connection, _review, _reviewed = self._run_policy(fixtures)
        self.assertTrue(result)
        self.assertEqual([kind for kind, _c, _a in calls], ["paid", "v1"])

    def test_same_uid_numbers_on_different_boots_are_independent(self):
        # Independence is anchored to the (boot_id, uid) identity derived from
        # each complete owned launch, not to uid numbers or a host label:
        # two genuinely different qualified OS instances may share uid 2401.
        fixtures = self._fixtures()
        fixtures["reviewer"]["os_principal_uid"] = (
            fixtures["subject"]["os_principal_uid"]
        )
        self.assertEqual(
            fixtures["reviewer"]["os_principal_uid"],
            fixtures["subject"]["os_principal_uid"],
        )
        self.assertNotEqual(
            fixtures["reviewer_att"]["process_identity"]["boot_id"],
            fixtures["subject_att"]["process_identity"]["boot_id"],
        )
        result, _calls, _connection, _review, _reviewed = self._run_policy(fixtures)
        self.assertTrue(result)

    def test_same_pid_numbers_on_different_boots_are_independent(self):
        # Process generations are only identical when the whole
        # (boot_id, pid, pgid, start_identity) tuple matches; recycled pid
        # numbers across different boots stay independent.
        fixtures = self._fixtures()
        subject_process = fixtures["subject_att"]["process_identity"]
        reviewer_process = fixtures["reviewer_att"]["process_identity"]
        reviewer_process["pid"] = subject_process["pid"]
        reviewer_process["pgid"] = subject_process["pgid"]
        self.assertNotEqual(
            reviewer_process["boot_id"], subject_process["boot_id"]
        )
        result, _calls, _connection, _review, _reviewed = self._run_policy(fixtures)
        self.assertTrue(result)

    # -- canonical validator refusals ---------------------------------

    def test_canonical_validator_refusals_return_false(self):
        def paid_owner_refusal(connection, attempt):
            raise er.RuntimeProofError("unit paid owner refusal")

        calls = self._assert_rejected(
            label="paid owner refusal", paid_side=paid_owner_refusal
        )
        # A refused paid subject ends the comparison before the v1 side.
        self.assertEqual([kind for kind, _c, _a in calls], ["paid"])

        def v1_owner_refusal(attempt, connection):
            raise er.CapabilityPolicyError("unit v1 owner refusal")

        calls = self._assert_rejected(
            label="v1 owner refusal", sealed_side=v1_owner_refusal
        )
        self.assertEqual([kind for kind, _c, _a in calls], ["paid", "v1"])

    # -- missing or mistyped source fields ----------------------------

    def test_missing_or_mistyped_required_source_fields_return_false(self):
        def without(fixtures, mapping, key):
            del mapping(fixtures)[key]

        def without_constraints_profile_id(fixtures):
            constraints = copy.deepcopy(fixtures["constraints"])
            del constraints["execution_profile_id"]
            fixtures["review_job"]["constraints_json"] = _canonical_json(constraints)

        def without_routing(fixtures):
            fixtures["review_attempt"]["launch_metadata_json"] = _canonical_json({})

        def with_review_constraints(fixtures, constraints_json):
            fixtures["review_job"]["constraints_json"] = constraints_json

        cases = [
            (
                "missing subject worker_id",
                lambda fx: without(fx, lambda f: f["subject"], "worker_id"),
            ),
            (
                "missing reviewer account_label",
                lambda fx: without(fx, lambda f: f["reviewer"], "account_label"),
            ),
            (
                "missing subject process_identity",
                lambda fx: without(fx, lambda f: f["subject_att"], "process_identity"),
            ),
            (
                "missing reviewer boot_id",
                lambda fx: without(
                    fx,
                    lambda f: f["reviewer_att"]["process_identity"],
                    "boot_id",
                ),
            ),
            (
                "missing reviewer os_principal_uid",
                lambda fx: without(
                    fx, lambda f: f["reviewer"], "os_principal_uid"
                ),
            ),
            (
                "constraints without execution_profile_id",
                without_constraints_profile_id,
            ),
            ("review launch metadata without routing", without_routing),
            (
                "string reviewer uid",
                lambda fx: fx["reviewer"].update(os_principal_uid="2410"),
            ),
            (
                "bool reviewer uid",
                lambda fx: fx["reviewer"].update(os_principal_uid=True),
            ),
            (
                "string subject uid",
                lambda fx: fx["subject"].update(os_principal_uid="2401"),
            ),
            (
                "unparsable constraints_json",
                lambda fx: with_review_constraints(fx, "{not-json"),
            ),
            (
                "non-canonical constraints_json",
                lambda fx: with_review_constraints(
                    fx, json.dumps(fx["constraints"])
                ),
            ),
            (
                "unparsable review launch metadata",
                lambda fx: fx["review_attempt"].update(
                    launch_metadata_json="{not-json"
                ),
            ),
        ]
        for label, mutate in cases:
            with self.subTest(case=label):
                self._assert_rejected(mutate, label)

    # -- shared identities ---------------------------------------------

    def test_shared_worker_attempt_or_account_identity_rejects(self):
        def same_attempt_id(fixtures):
            shared = fixtures["reviewed_attempt"]["attempt_id"]
            fixtures["review_attempt"]["attempt_id"] = shared
            fixtures["review_job"]["current_attempt_id"] = shared

        def same_worker_id(fixtures):
            fixtures["reviewer"]["worker_id"] = fixtures["subject"]["worker_id"]

        def same_account_label(fixtures):
            fixtures["reviewer"]["account_label"] = (
                fixtures["subject"]["account_label"]
            )

        def empty_reviewer_account_label(fixtures):
            fixtures["reviewer"]["account_label"] = ""

        def empty_subject_account_label(fixtures):
            fixtures["subject"]["account_label"] = ""

        cases = [
            ("shared attempt id", same_attempt_id),
            ("shared worker id", same_worker_id),
            ("shared account label", same_account_label),
            ("empty reviewer account label", empty_reviewer_account_label),
            ("empty subject account label", empty_subject_account_label),
        ]
        for label, mutate in cases:
            with self.subTest(case=label):
                self._assert_rejected(mutate, label)

    def test_same_os_instance_identity_rejects(self):
        def same_os_instance(fixtures):
            fixtures["reviewer_att"]["process_identity"]["boot_id"] = (
                fixtures["subject_att"]["process_identity"]["boot_id"]
            )
            fixtures["reviewer"]["os_principal_name"] = (
                fixtures["subject"]["os_principal_name"]
            )
            fixtures["reviewer"]["os_principal_uid"] = (
                fixtures["subject"]["os_principal_uid"]
            )

        self._assert_rejected(same_os_instance, "identical OS instance identity")

    def test_shared_uid_on_same_boot_rejects_despite_different_display_name(
        self,
    ):
        # The (boot_id, uid) pair is the root-defined actual identity tuple:
        # renaming the principal on the same boot with the same uid number
        # does not create an independent reviewer.
        def shared_boot_and_uid(fixtures):
            fixtures["reviewer_att"]["process_identity"]["boot_id"] = (
                fixtures["subject_att"]["process_identity"]["boot_id"]
            )
            fixtures["reviewer"]["os_principal_uid"] = (
                fixtures["subject"]["os_principal_uid"]
            )

        fixtures_probe = self._fixtures()
        self.assertNotEqual(
            fixtures_probe["reviewer"]["os_principal_name"],
            fixtures_probe["subject"]["os_principal_name"],
        )
        self._assert_rejected(
            shared_boot_and_uid, "shared boot and uid with different names"
        )

    def test_same_owned_process_generation_rejects(self):
        def same_generation(fixtures):
            fixtures["reviewer_att"]["process_identity"] = dict(
                fixtures["subject_att"]["process_identity"]
            )
            # Keep the OS instance tuple distinct so only the process
            # generation clause can reject this pair.
            fixtures["reviewer"]["os_principal_uid"] = (
                fixtures["subject"]["os_principal_uid"] + 1
            )

        self._assert_rejected(same_generation, "identical process generation")

    # -- cross-kind provider and schema --------------------------------

    def test_paid_reviewer_wrong_provider_or_stale_v1_schema_rejects(self):
        cases = [
            (
                "glm paid reviewer",
                lambda fx: fx["reviewer"].update(provider="glm"),
            ),
            (
                "codex paid subject",
                lambda fx: fx["subject"].update(provider="codex"),
            ),
            (
                "stale reviewer attestation schema",
                lambda fx: fx["reviewer_att"].update(
                    schema_version="mastermind.executive_launch_attestation/v2"
                ),
            ),
            (
                "stale reviewer principal schema",
                lambda fx: fx["reviewer"].update(
                    schema_version="mastermind.execution_principal_snapshot/v2"
                ),
            ),
        ]
        for label, mutate in cases:
            with self.subTest(case=label):
                self._assert_rejected(mutate, label)

    # -- reviewer grant -------------------------------------------------

    def test_reviewer_grant_must_be_the_exact_read_only_grant(self):
        def read_and_research(fixtures):
            fixtures["review_grant"]["authorities"] = ["READ", "RESEARCH"]

        def read_and_run_tests(fixtures):
            fixtures["review_grant"]["authorities"] = ["READ", "RUN_TESTS"]

        def with_write_path(fixtures):
            fixtures["review_grant"]["write_paths"] = ["/unit/report"]

        def with_validation_argv(fixtures):
            fixtures["review_grant"]["validation_argv"] = ["--unit-flag"]

        def drifted_grant_identity(fixtures):
            # Same READ-only shape, different grant identity: the caller-side
            # grant must equal the re-derived qualified grant exactly.
            fixtures["review_grant"]["grant_id"] = "unit-grant-other"

        cases = [
            ("READ+RESEARCH authorities", read_and_research),
            ("READ+RUN_TESTS authorities", read_and_run_tests),
            ("non-empty write_paths", with_write_path),
            ("non-empty validation_argv", with_validation_argv),
            ("drifted grant identity", drifted_grant_identity),
        ]
        for label, mutate in cases:
            with self.subTest(case=label):
                self._assert_rejected(mutate, label)

    # -- job graph and roles --------------------------------------------

    def test_foreign_job_graph_or_roles_reject(self):
        cases = [
            (
                "review job not a review",
                lambda fx: fx["review_job"].update(orchestration_role="work"),
            ),
            (
                "subject job is itself a review",
                lambda fx: fx["subject_job"].update(orchestration_role="review"),
            ),
            (
                "review points at a different subject",
                lambda fx: fx["review_job"].update(
                    reviews_job_id="unit-job-other"
                ),
            ),
            (
                "foreign root",
                lambda fx: fx["review_job"].update(root_job_id="unit-job-root-other"),
            ),
            (
                "foreign parent",
                lambda fx: fx["review_job"].update(
                    parent_job_id="unit-job-parent-other"
                ),
            ),
            (
                "review job current attempt mismatch",
                lambda fx: fx["review_job"].update(
                    current_attempt_id="unit-attempt-review-2"
                ),
            ),
            (
                "subject job current attempt mismatch",
                lambda fx: fx["subject_job"].update(
                    current_attempt_id="unit-attempt-subject-2"
                ),
            ),
            (
                "review attempt not sealed",
                lambda fx: fx["review_attempt"].update(
                    execution_mode=_non_sealed_execution_mode()
                ),
            ),
            (
                "subject attempt not sealed",
                lambda fx: fx["reviewed_attempt"].update(
                    execution_mode=_non_sealed_execution_mode()
                ),
            ),
        ]
        for label, mutate in cases:
            with self.subTest(case=label):
                self._assert_rejected(mutate, label)

    def test_missing_job_row_breaks_the_exact_two_job_lookup(self):
        def drop_review_job(connection):
            connection.execute("DELETE FROM jobs WHERE job_id = 'unit-job-review'")

        def drop_subject_job(connection):
            connection.execute(
                "DELETE FROM jobs WHERE job_id = 'unit-job-subject'"
            )

        for label, db_mutate in (
            ("review job row missing", drop_review_job),
            ("subject job row missing", drop_subject_job),
        ):
            with self.subTest(case=label):
                self._assert_rejected(label=label, db_mutate=db_mutate)

    # -- profile and routing qualification ------------------------------

    def test_profile_or_routing_mismatch_rejects(self):
        stale_digest = "unit-stale-profile-digest"

        def with_review_routing(fixtures, **changes):
            routing = copy.deepcopy(fixtures["routing"])
            routing.update(changes)
            fixtures["review_attempt"]["launch_metadata_json"] = _canonical_json(
                {"routing": routing}
            )

        def with_review_constraints(fixtures, **changes):
            constraints = copy.deepcopy(fixtures["constraints"])
            constraints.update(changes)
            fixtures["review_job"]["constraints_json"] = _canonical_json(constraints)

        cases = [
            (
                "unknown routing adapter",
                lambda fx: with_review_routing(fx, adapter_id="unknown-cli"),
            ),
            (
                "routing profile id mismatch",
                lambda fx: with_review_routing(
                    fx, execution_profile_id="unit.other.profile/v9"
                ),
            ),
            (
                "stale routing profile digest",
                lambda fx: with_review_routing(
                    fx, execution_profile_digest=stale_digest
                ),
            ),
            (
                "stale constraints profile digest",
                lambda fx: with_review_constraints(
                    fx, execution_profile_digest=stale_digest
                ),
            ),
            (
                "unknown constraints profile id",
                lambda fx: with_review_constraints(
                    fx, execution_profile_id="unit.absent.profile/v9"
                ),
            ),
        ]
        for label, mutate in cases:
            with self.subTest(case=label):
                self._assert_rejected(mutate, label)

    def test_real_but_unqualified_profile_surface_rejects(self):
        other = self._find_enabled_profile_with_surface_other_than("codex-exec")
        self.assertIsNotNone(other, "current real registry must expose a non-Codex profile")
        self.assertNotEqual(other.execution_surface, "codex-exec")

        def point_at_real_other_profile(fixtures):
            constraints = copy.deepcopy(fixtures["constraints"])
            constraints["execution_profile_id"] = other.profile_id
            constraints["execution_profile_digest"] = other.profile_digest
            fixtures["review_job"]["constraints_json"] = _canonical_json(constraints)
            routing = copy.deepcopy(fixtures["routing"])
            routing["execution_profile_id"] = other.profile_id
            routing["execution_profile_digest"] = other.profile_digest
            fixtures["review_attempt"]["launch_metadata_json"] = _canonical_json(
                {"routing": routing}
            )

        self._assert_rejected(
            point_at_real_other_profile,
            f"real profile {other.profile_id!r} without a codex-exec surface",
        )

    def _find_enabled_profile_with_surface_other_than(self, surface):
        registry = er.ExecutionCapabilityRegistry.load()
        candidates = []
        for attribute in (
            "profiles",
            "all_profiles",
            "list_profiles",
            "iter_profiles",
            "catalog",
            "_profiles",
        ):
            value = getattr(registry, attribute, None)
            if callable(value):
                try:
                    found = list(value())
                except Exception:  # probing only; the policy path is below
                    continue
                if found:
                    candidates = found
                    break
            elif isinstance(value, dict):
                candidates = list(value.values())
                if candidates:
                    break
            elif isinstance(value, (list, tuple)):
                candidates = list(value)
                if candidates:
                    break
        for profile in candidates:
            if (
                getattr(profile, "profile_id", None)
                and getattr(profile, "execution_surface", None) != surface
                and getattr(profile, "enabled", True)
            ):
                return profile
        return None


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
