"""Tests for the closed-value workspace source-operation STATUS contract.

Pure stdlib unittest; no network, no install, no Runtime/SQL/Git evidence.
Every fixture below is a grammar-shaped closed value used to exercise the
validator only: no digest, URL or receipt here is treated as proof of
authenticity, no test authorizes a write, and no original ID is minted.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common.workspace_source_operation_contract import (  # noqa: E402
    unavailable,
    validate_advance,
    validate_lookup,
    validate_status,
)

CODE = "invalid_source_operation"

STATUS_SCHEMA = "mastermind.workspace_source_operation_status.v1"
LOOKUP_SCHEMA = "mastermind.workspace_source_operation_lookup.v1"
ADVANCE_SCHEMA = "mastermind.workspace_source_operation_advance.v1"

HEX40_A = "a" * 40
HEX40_B = "b" * 40
HEX64_A = "c" * 64
HEX64_B = "d" * 64
HEX64_C = "e" * 64
SCOPE = "f" * 64
SCOPE_FOREIGN = "0" * 64

REQUESTS = {
    "publish_project_proposal": "mmos-project-create-" + HEX40_A,
    "ADOPT_PLAN": "mmos-project-adopt-" + HEX40_B,
    "ACCEPT_DIRECTION": "mmos-direction-accept-" + HEX40_A,
    "add_project_file": "mmos-project-file-add-" + HEX40_B,
    "set_project_communication_preference": "mmos-project-preference-set-" + HEX40_A,
}

WORK_REF = "WS:PROPHET-US-V4"
PATH_OK = "src/app/prophet.ts"
PATH_UNICODE = "src/услуги/报告.md"
BRANCH_OK = "release-1.2"
PR_URL_PREFIX = (
    "https://github.com/mastermindx-market-intelligence/macro/pull/"
)
PR_URL_OK = PR_URL_PREFIX + "7"


def source(**over):
    body = {
        "repository": "macro",
        "commit": HEX40_A,
        "path": PATH_OK,
        "content_sha256": HEX64_B,
    }
    body.update(over)
    return body


def proposal(**over):
    body = {
        "number": 7,
        "url": PR_URL_OK,
        "head_commit": HEX40_B,
        "head_branch": BRANCH_OK,
    }
    body.update(over)
    return body


def receipt(**over):
    body = {
        "kind": "SOURCE_OBSERVED",
        "event_id": 42,
        "recorded_at_ms": 1730000000000,
        "receipt_sha256": HEX64_C,
        "sources": [source()],
        "proposal": None,
    }
    body.update(over)
    return body


def status_body(**over):
    body = {
        "schema": STATUS_SCHEMA,
        "selection": {
            "action": "publish_project_proposal",
            "request_id": REQUESTS["publish_project_proposal"],
            "work_ref": WORK_REF,
        },
        "owner_context": {"principal_scope": SCOPE},
        "disposition": "unknown",
        "reason": "SOURCE_UNAVAILABLE",
        "request_sha256": None,
        "recipe_fingerprint_sha256": None,
        "phase": None,
        "receipt": None,
        "advance": None,
    }
    body.update(over)
    return body


def accepted_body(**over):
    body = status_body(
        disposition="accepted",
        reason=None,
        request_sha256=HEX64_A,
        recipe_fingerprint_sha256=HEX64_B,
        phase="PUBLICATION",
        receipt=receipt(),
        advance=None,
    )
    body.update(over)
    return body


def adopted_body(**over):
    body = accepted_body(
        selection={
            "action": "ADOPT_PLAN",
            "request_id": REQUESTS["ADOPT_PLAN"],
            "work_ref": WORK_REF,
        },
        phase="ADOPTION",
    )
    body.update(over)
    return body


def proposal_observed_body(**proposal_over):
    return status_body(
        disposition="unknown",
        reason="IN_PROGRESS",
        request_sha256=HEX64_A,
        recipe_fingerprint_sha256=HEX64_B,
        phase="PUBLICATION",
        receipt=receipt(
            kind="PROPOSAL_OBSERVED", sources=[], proposal=proposal(**proposal_over)
        ),
    )


def ready_body(**over):
    body = status_body(
        selection={
            "action": "ADOPT_PLAN",
            "request_id": REQUESTS["ADOPT_PLAN"],
            "work_ref": WORK_REF,
        },
        disposition="unknown",
        reason="READY_FOR_ADVANCE",
        request_sha256=HEX64_A,
        recipe_fingerprint_sha256=HEX64_B,
        phase="CANDIDATE",
        receipt=receipt(receipt_sha256=HEX64_C),
        advance={"phase_receipt_digest": HEX64_C},
    )
    body.update(over)
    return body


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    )


class ContractCase(unittest.TestCase):
    def expect_invalid(self, fn, *args, **kwargs):
        with self.assertRaises(ValueError) as caught:
            fn(*args, **kwargs)
        self.assertEqual(str(caught.exception), CODE)
        return caught.exception

    def assert_invalid_status(self, value, marker=None):
        exception = self.expect_invalid(validate_status, value)
        if marker is not None:
            self.assertNotIn(marker, str(exception))
        return exception

    def assert_exact_builtin_tree(self, value):
        if value is None:
            return
        if type(value) is dict:
            for key, item in value.items():
                self.assertIs(type(key), str)
                self.assert_exact_builtin_tree(item)
        elif type(value) is list:
            for item in value:
                self.assert_exact_builtin_tree(item)
        else:
            self.assertIn(type(value), (str, int))


class LookupTests(ContractCase):
    def test_valid_lookup_per_action(self):
        for action, request_id in REQUESTS.items():
            result = validate_lookup({
                "schema": LOOKUP_SCHEMA,
                "action": action,
                "request_id": request_id,
                "work_ref": WORK_REF,
            })
            self.assertEqual(result, {
                "schema": LOOKUP_SCHEMA,
                "action": action,
                "request_id": request_id,
                "work_ref": WORK_REF,
            })
            self.assert_exact_builtin_tree(result)

    def test_input_not_mutated_and_output_detached(self):
        body = {
            "schema": LOOKUP_SCHEMA,
            "action": "ADOPT_PLAN",
            "request_id": REQUESTS["ADOPT_PLAN"],
            "work_ref": WORK_REF,
        }
        first = validate_lookup(body)
        body["action"] = "add_project_file"
        body["work_ref"] = "WS:OTHER"
        self.assertEqual(first["action"], "ADOPT_PLAN")
        self.assertEqual(first["work_ref"], WORK_REF)

    def test_rejects_closed_shape_violations(self):
        good = {
            "schema": LOOKUP_SCHEMA,
            "action": "publish_project_proposal",
            "request_id": REQUESTS["publish_project_proposal"],
            "work_ref": WORK_REF,
        }
        self.expect_invalid(validate_lookup, None)
        self.expect_invalid(validate_lookup, [])
        self.expect_invalid(validate_lookup, "lookup")
        missing = dict(good)
        del missing["work_ref"]
        self.expect_invalid(validate_lookup, missing)
        extra = dict(good)
        extra["actor"] = "someone"
        self.expect_invalid(validate_lookup, extra)
        wrong_schema = dict(good)
        wrong_schema["schema"] = STATUS_SCHEMA
        self.expect_invalid(validate_lookup, wrong_schema)
        int_key = dict(good)
        int_key[5] = 5
        del int_key["work_ref"]
        self.expect_invalid(validate_lookup, int_key)

    def test_rejects_action_request_id_mismatch(self):
        self.assert_invalid_marker(
            validate_lookup, {
                "schema": LOOKUP_SCHEMA,
                "action": "publish_project_proposal",
                "request_id": REQUESTS["ADOPT_PLAN"],
                "work_ref": WORK_REF,
            })
        self.assert_invalid_marker(
            validate_lookup, {
                "schema": LOOKUP_SCHEMA,
                "action": "add_project_file",
                "request_id": REQUESTS["publish_project_proposal"],
                "work_ref": WORK_REF,
            })

    def assert_invalid_marker(self, fn, value):
        with self.assertRaises(ValueError) as caught:
            fn(value)
        self.assertEqual(str(caught.exception), CODE)

    def test_rejects_bad_request_id_grammars(self):
        def lookup_with(request_id):
            return {
                "schema": LOOKUP_SCHEMA,
                "action": "publish_project_proposal",
                "request_id": request_id,
                "work_ref": WORK_REF,
            }

        for bad in (
            None,
            17,
            True,
            "",
            "mmos-project-create-",
            "mmos-project-create-" + "A" * 40,
            "mmos-project-create-" + "a" * 39,
            "mmos-project-create-" + "a" * 41,
            "mmos-project-create-" + "g" * 40,
            "mmos-project-create" + HEX40_A,
            REQUESTS["ADOPT_PLAN"],
        ):
            self.expect_invalid(validate_lookup, lookup_with(bad))

    def test_rejects_bad_work_ref_grammars(self):
        def lookup_with(work_ref):
            return {
                "schema": LOOKUP_SCHEMA,
                "action": "publish_project_proposal",
                "request_id": REQUESTS["publish_project_proposal"],
                "work_ref": work_ref,
            }

        for bad in (
            None, 3, True, "", "WS:", "WS:A", "prophet-us-v4",
            "WS:prophet-us-v4", "WS:PROPHET--US", "WS:-PROPHET",
            "WS:PROPHET-", "WS:PROPHET US", "WS:PROPHET_US",
            "PROPHET-US", "WS:PROPHET-US\n", "WS:" + "A" * 65,
            "WS:PROPHET-US-V4-",
        ):
            self.expect_invalid(validate_lookup, lookup_with(bad))
        self.assertEqual(
            validate_lookup(lookup_with("WS:AB"))["work_ref"], "WS:AB")
        self.assertEqual(
            validate_lookup(lookup_with("WS:" + "A" * 64))["work_ref"],
            "WS:" + "A" * 64)
        self.assertEqual(
            validate_lookup(lookup_with(
                "WS:" + "-".join(["A" * 5] * 10)))["work_ref"],
            "WS:" + "-".join(["A" * 5] * 10))


class AdvanceTests(ContractCase):
    def body(self, **over):
        body = {
            "schema": ADVANCE_SCHEMA,
            "action": "ADOPT_PLAN",
            "request_id": REQUESTS["ADOPT_PLAN"],
            "work_ref": WORK_REF,
            "phase_receipt_digest": HEX64_C,
        }
        body.update(over)
        return body

    def test_valid_advance(self):
        result = validate_advance(self.body())
        self.assertEqual(result, self.body())
        self.assert_exact_builtin_tree(result)
        self.assertEqual(validate_advance(self.body())["action"], "ADOPT_PLAN")

    def test_rejects_non_adopt_actions(self):
        for action, request_id in REQUESTS.items():
            if action == "ADOPT_PLAN":
                continue
            self.expect_invalid(validate_advance, self.body(
                action=action, request_id=request_id))

    def test_rejects_bad_digest(self):
        for bad in (
            None, 5, True, "", "c" * 63, "c" * 65, "C" * 64, "g" * 64,
            HEX40_A, " " + "c" * 63,
        ):
            self.expect_invalid(validate_advance, self.body(phase_receipt_digest=bad))

    def test_rejects_shape_and_pairing_violations(self):
        self.expect_invalid(validate_advance, None)
        missing = self.body()
        del missing["work_ref"]
        self.expect_invalid(validate_advance, missing)
        extra = self.body()
        extra["receipt"] = receipt()
        self.expect_invalid(validate_advance, extra)
        self.expect_invalid(validate_advance, self.body(schema=STATUS_SCHEMA))
        self.expect_invalid(validate_advance, self.body(
            request_id=REQUESTS["publish_project_proposal"]))
        self.expect_invalid(validate_advance, self.body(work_ref="WS:nope"))


class StatusShapeTests(ContractCase):
    def test_unknown_no_evidence_body_valid(self):
        result = validate_status(status_body())
        self.assertEqual(result, status_body())
        self.assert_exact_builtin_tree(result)
        self.assertEqual(validate_status(result), result)  # fixpoint, safe duplicate

    def test_accepted_final_publication_valid(self):
        result = validate_status(accepted_body())
        self.assertEqual(result, accepted_body())
        self.assert_exact_builtin_tree(result)
        validate_status(accepted_body(receipt=receipt(sources=[source(), source(), source()])))

    def test_adopted_final_adoption_valid(self):
        validate_status(adopted_body())

    def test_detached_output(self):
        body = accepted_body()
        result = validate_status(body)
        self.assertIsNot(result, body)
        self.assertIsNot(result["selection"], body["selection"])
        self.assertIsNot(result["receipt"], body["receipt"])
        self.assertIsNot(result["receipt"]["sources"], body["receipt"]["sources"])
        result["disposition"] = "refused"
        result["receipt"]["sources"][0]["path"] = "mutated"
        result["owner_context"]["principal_scope"] = "9" * 64
        self.assertEqual(body["disposition"], "accepted")
        self.assertEqual(body["receipt"]["sources"][0]["path"], PATH_OK)
        self.assertEqual(body["owner_context"]["principal_scope"], SCOPE)
        body["receipt"] = None
        self.assertIsNotNone(result["receipt"])

    def test_extra_private_keys_rejected_everywhere(self):
        def with_top(key, value):
            body = accepted_body()
            body[key] = value
            return body

        self.assert_invalid_status(with_top("actor", "someone"), "someone")
        self.assert_invalid_status(with_top("token", "T0K3NMARKER"), "T0K3NMARKER")
        self.assert_invalid_status(with_top("rationale", "WHYMARKER"), "WHYMARKER")
        self.assert_invalid_status(with_top("basis", "BASISMARKER"), "BASISMARKER")
        self.assert_invalid_status(with_top("upload", "UPLOADMARKER"), "UPLOADMARKER")

        selection = dict(accepted_body()["selection"])
        selection["note"] = "n"
        self.assert_invalid_status(accepted_body(selection=selection))

        owner = {"principal_scope": SCOPE, "account": "a"}
        self.assert_invalid_status(accepted_body(owner_context=owner))

        rich_receipt = receipt(token="t")
        self.assert_invalid_status(accepted_body(receipt=rich_receipt))

        rich_source = source(upload_url="https://example.invalid/x")
        self.assert_invalid_status(
            accepted_body(receipt=receipt(sources=[rich_source])))

        rich_proposal = proposal(rationale="WHYMARKER")
        self.assert_invalid_status(status_body(
            disposition="unknown", reason="IN_PROGRESS",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION", receipt=receipt(
                kind="PROPOSAL_OBSERVED", sources=[], proposal=rich_proposal)))

    def test_custom_containers_rejected_without_invocation(self):
        touches = {"count": 0}

        class SpyDict(dict):
            def keys(self):
                touches["count"] += 1
                return dict.keys(self)

            def get(self, key, default=None):
                touches["count"] += 1
                return dict.get(self, key, default)

            def __getitem__(self, key):
                touches["count"] += 1
                return dict.__getitem__(self, key)

        class SpyList(list):
            def __len__(self):
                touches["count"] += 1
                return list.__len__(self)

            def __iter__(self):
                touches["count"] += 1
                return list.__iter__(self)

        class SpyStr(str):
            pass

        class DuckMap:
            def keys(self):
                raise AssertionError("validator must not call keys()")

            def __getitem__(self, key):
                raise AssertionError("validator must not subscript duck map")

        self.assert_invalid_status(SpyDict(status_body()))
        self.assertEqual(touches["count"], 0)
        body = accepted_body(receipt=receipt(sources=SpyList([source()])))
        self.assert_invalid_status(body)
        self.assertEqual(touches["count"], 0)
        self.assert_invalid_status(status_body(selection=SpyDict({
            "action": "publish_project_proposal",
            "request_id": REQUESTS["publish_project_proposal"],
            "work_ref": WORK_REF,
        })))
        self.assertEqual(touches["count"], 0)
        self.assert_invalid_status(status_body(receipt=SpyStr("nope")))
        self.assert_invalid_status(DuckMap())
        self.assert_invalid_status(status_body(request_id=SpyStr(
            REQUESTS["publish_project_proposal"])))

    def test_scalar_type_strictness(self):
        for bad_scalar in (True, False, 3.0, float("nan"), None):
            self.assert_invalid_status(accepted_body(
                receipt=receipt(event_id=bad_scalar)))
        self.assert_invalid_status(accepted_body(
            receipt=receipt(recorded_at_ms=True)))
        self.assert_invalid_status(status_body(disposition=True))
        self.assert_invalid_status(status_body(reason=17))
        self.assert_invalid_status(accepted_body(receipt=receipt(sources=(
            (source(),)))))  # tuple, not list
        self.assert_invalid_status(accepted_body(receipt=receipt(
            proposal=proposal(number=True))))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            sources=[source(content_sha256=b"bytes")])))

    def test_safeint_bounds(self):
        self.assert_invalid_status(accepted_body(receipt=receipt(event_id=0)))
        self.assert_invalid_status(accepted_body(receipt=receipt(event_id=-1)))
        self.assert_invalid_status(accepted_body(
            receipt=receipt(event_id=2 ** 53)))
        validate_status(accepted_body(receipt=receipt(event_id=2 ** 53 - 1)))
        self.assert_invalid_status(accepted_body(
            receipt=receipt(recorded_at_ms=-1)))
        validate_status(accepted_body(
            receipt=receipt(recorded_at_ms=2 ** 53 - 1)))
        self.assert_invalid_status(proposal_observed_body(number=0))
        self.assert_invalid_status(proposal_observed_body(number=2 ** 53))
        validate_status(proposal_observed_body(
            number=2 ** 53 - 1,
            url=PR_URL_PREFIX + str(2 ** 53 - 1),
            head_branch="ok-max-number",
        ))

    def test_closed_enums(self):
        self.assert_invalid_status(status_body(disposition="pending"))
        self.assert_invalid_status(status_body(disposition="UNKNOWN"))
        self.assert_invalid_status(status_body(reason="BECAUSE"))
        self.assert_invalid_status(status_body(reason="refused"))
        self.assert_invalid_status(status_body(phase="DONE"))
        self.assert_invalid_status(accepted_body(receipt=receipt(kind="OBSERVED")))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            sources=[source(repository="other")])))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            sources=[source(commit="Z" * 40)])))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            sources=[source(content_sha256="d" * 63)])))
        self.assert_invalid_status(status_body(
            owner_context={"principal_scope": "F" * 64}))
        self.assert_invalid_status(status_body(
            owner_context={"principal_scope": SCOPE_FOREIGN + "0"}))

    def test_foreign_scope_grammar_is_scope_agnostic(self):
        body = status_body(owner_context={"principal_scope": SCOPE_FOREIGN})
        self.assertEqual(
            validate_status(body)["owner_context"]["principal_scope"],
            SCOPE_FOREIGN)

    def test_non_string_key_rejected(self):
        body = status_body()
        body[7] = 7
        self.assert_invalid_status(body)

    def test_receipt_sources_bounds(self):
        self.assert_invalid_status(accepted_body(
            receipt=receipt(sources=[])))  # SOURCE_OBSERVED needs >= 1
        self.assert_invalid_status(accepted_body(receipt=receipt(
            sources=[source(), source(), source(), source()])))


class StatusSemanticsTests(ContractCase):
    def test_accepted_candidate_rejected(self):
        self.assert_invalid_status(adopted_body(phase="CANDIDATE"))
        self.assert_invalid_status(accepted_body(phase=None))
        self.assert_invalid_status(accepted_body(phase="ADOPTION"))

    def test_accepted_requires_source_observed_kind(self):
        self.assert_invalid_status(accepted_body(receipt=receipt(
            kind="INTENT", sources=[], proposal=None)))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            kind="PHASE_ATTEMPTED", sources=[], proposal=None)))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            kind="PROPOSAL_OBSERVED", sources=[],
            proposal=proposal())))

    def test_accepted_requires_null_reason_and_advance(self):
        self.assert_invalid_status(accepted_body(reason="SOURCE_UNAVAILABLE"))
        self.assert_invalid_status(accepted_body(
            advance={"phase_receipt_digest": HEX64_C}))

    def test_accepted_hashes_are_pair_and_never_substituted(self):
        self.assert_invalid_status(accepted_body(recipe_fingerprint_sha256=HEX64_A))
        self.assert_invalid_status(accepted_body(request_sha256=HEX64_B))
        self.assert_invalid_status(accepted_body(
            request_sha256=None, recipe_fingerprint_sha256=HEX64_B))

    def test_intent_and_phase_attempted_shapes(self):
        intent = receipt(kind="INTENT", sources=[], proposal=None)
        validate_status(status_body(
            disposition="unknown", reason="IN_PROGRESS",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION", receipt=intent))
        self.assert_invalid_status(status_body(
            disposition="unknown", reason="IN_PROGRESS",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION",
            receipt=receipt(kind="INTENT", sources=[source()], proposal=None)))
        self.assert_invalid_status(status_body(
            disposition="unknown", reason="IN_PROGRESS",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION", receipt=receipt(
                kind="INTENT", sources=[], proposal=proposal())))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            kind="INTENT", sources=[], proposal=None)))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="CONFLICT",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION", receipt=receipt(
                kind="PHASE_ATTEMPTED", sources=[], proposal=None)))
        validate_status(status_body(
            selection={
                "action": "ADOPT_PLAN",
                "request_id": REQUESTS["ADOPT_PLAN"],
                "work_ref": WORK_REF,
            },
            disposition="unknown", reason="PHASE_ATTEMPT_UNRESOLVED",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="CANDIDATE",
            receipt=receipt(kind="PHASE_ATTEMPTED", sources=[], proposal=None)))

    def test_proposal_observed_shape(self):
        observed = receipt(
            kind="PROPOSAL_OBSERVED", sources=[], proposal=proposal())
        validate_status(status_body(
            disposition="unknown", reason="IN_PROGRESS",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION", receipt=observed))
        self.assert_invalid_status(status_body(
            disposition="unknown", reason="IN_PROGRESS",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION", receipt=receipt(
                kind="PROPOSAL_OBSERVED", sources=[], proposal=None)))
        self.assert_invalid_status(status_body(
            disposition="unknown", reason="IN_PROGRESS",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION", receipt=receipt(
                kind="PROPOSAL_OBSERVED", sources=[source()],
                proposal=proposal())))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            kind="PROPOSAL_OBSERVED", sources=[], proposal=proposal())))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="REFUSED", receipt=receipt(
                kind="PROPOSAL_OBSERVED", sources=[], proposal=proposal())))

    def test_source_observed_requires_sources_and_no_proposal(self):
        self.assert_invalid_status(accepted_body(receipt=receipt(sources=[])))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            sources=[source()], proposal=proposal())))

    def test_source_observed_candidate_is_unknown_only(self):
        self.assert_invalid_status(adopted_body(phase="CANDIDATE"))
        self.assert_invalid_status(status_body(
            selection={
                "action": "ADOPT_PLAN",
                "request_id": REQUESTS["ADOPT_PLAN"],
                "work_ref": WORK_REF,
            },
            disposition="refused", reason="CONFLICT",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="CANDIDATE", receipt=receipt(receipt_sha256=HEX64_C)))
        validate_status(status_body(
            selection={
                "action": "ADOPT_PLAN",
                "request_id": REQUESTS["ADOPT_PLAN"],
                "work_ref": WORK_REF,
            },
            disposition="unknown", reason="CONFLICT",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="CANDIDATE", receipt=receipt(receipt_sha256=HEX64_C)))

    def test_no_receipt_requires_null_evidence(self):
        self.assert_invalid_status(status_body(phase="PUBLICATION"))
        self.assert_invalid_status(status_body(request_sha256=HEX64_A))
        self.assert_invalid_status(status_body(recipe_fingerprint_sha256=HEX64_B))
        self.assert_invalid_status(status_body(
            advance={"phase_receipt_digest": HEX64_C}))
        validate_status(status_body())  # unknown != proof of no effect

    def test_receipt_requires_hashes_and_phase(self):
        evidenced = {
            "disposition": "unknown",
            "reason": "IN_PROGRESS",
            "request_sha256": HEX64_A,
            "recipe_fingerprint_sha256": HEX64_B,
            "phase": "PUBLICATION",
            "receipt": receipt(),
        }
        validate_status(status_body(**evidenced))
        self.assert_invalid_status(status_body(
            **dict(evidenced, phase=None)))
        self.assert_invalid_status(status_body(
            **dict(evidenced, request_sha256=None)))
        self.assert_invalid_status(status_body(
            **dict(evidenced, recipe_fingerprint_sha256=None)))

    def test_refused_shapes(self):
        for reason in ("NOT_DISPATCHED", "REFUSED", "CONFLICT"):
            validate_status(status_body(disposition="refused", reason=reason))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="IN_PROGRESS"))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="READY_FOR_ADVANCE"))
        self.assert_invalid_status(status_body(disposition="refused", reason=None))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="CONFLICT", receipt=receipt()))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="CONFLICT", request_sha256=HEX64_A))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="CONFLICT",
            recipe_fingerprint_sha256=HEX64_B))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="CONFLICT", phase="PUBLICATION"))
        self.assert_invalid_status(status_body(
            disposition="refused", reason="CONFLICT",
            advance={"phase_receipt_digest": HEX64_C}))

    def test_partial_publication_never_refused(self):
        self.assert_invalid_status(status_body(
            disposition="refused", reason="NOT_DISPATCHED",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="PUBLICATION", receipt=receipt()))
        self.assert_invalid_status(status_body(
            selection={
                "action": "ADOPT_PLAN",
                "request_id": REQUESTS["ADOPT_PLAN"],
                "work_ref": WORK_REF,
            },
            disposition="refused", reason="REFUSED",
            request_sha256=HEX64_A, recipe_fingerprint_sha256=HEX64_B,
            phase="CANDIDATE", receipt=receipt(receipt_sha256=HEX64_C)))

    def test_unknown_reason_matrix(self):
        for reason in (
            "ORIGINAL_OPERATION_NOT_OBSERVED",
            "IN_PROGRESS",
            "PHASE_ATTEMPT_UNRESOLVED",
            "PRECONDITION_UNAVAILABLE",
            "PRIVATE_INPUT_UNAVAILABLE",
            "SOURCE_UNAVAILABLE",
            "CONFLICT",
            "NOT_DISPATCHED",
        ):
            validate_status(status_body(reason=reason))
        self.assert_invalid_status(status_body(reason="REFUSED"))
        self.assert_invalid_status(status_body(reason=None))
        self.assert_invalid_status(status_body(reason="READY_FOR_ADVANCE"))

    def test_original_operation_not_observed_carries_no_evidence(self):
        self.assert_invalid_status(status_body(
            reason="ORIGINAL_OPERATION_NOT_OBSERVED", receipt=receipt()))
        self.assert_invalid_status(status_body(
            reason="ORIGINAL_OPERATION_NOT_OBSERVED",
            advance={"phase_receipt_digest": HEX64_C}))

    def test_ready_for_advance_pairing(self):
        validate_status(ready_body())
        self.assert_invalid_status(ready_body(
            advance={"phase_receipt_digest": HEX64_B}))
        self.assert_invalid_status(ready_body(advance=None))
        self.assert_invalid_status(ready_body(phase="ADOPTION"))
        self.assert_invalid_status(ready_body(receipt=receipt(
            kind="INTENT", sources=[], proposal=None)))
        self.assert_invalid_status(ready_body(
            selection={
                "action": "publish_project_proposal",
                "request_id": REQUESTS["publish_project_proposal"],
                "work_ref": WORK_REF,
            },
            phase="PUBLICATION"))
        self.assert_invalid_status(ready_body(disposition="accepted", reason=None))
        self.assert_invalid_status(ready_body(
            receipt=receipt(kind="SOURCE_OBSERVED", receipt_sha256=HEX64_A),
            advance={"phase_receipt_digest": HEX64_A},
            reason="READY_FOR_ADVANCE", phase="CANDIDATE",
            disposition="refused"))

    def test_advance_only_in_ready_state(self):
        in_progress = {
            "disposition": "unknown",
            "reason": "IN_PROGRESS",
            "request_sha256": HEX64_A,
            "recipe_fingerprint_sha256": HEX64_B,
            "phase": "PUBLICATION",
            "receipt": receipt(),
        }
        self.assert_invalid_status(status_body(
            **dict(in_progress, advance={"phase_receipt_digest": HEX64_C})))
        self.assert_invalid_status(accepted_body(
            advance={"phase_receipt_digest": HEX64_C}))

    def test_phase_grammar_per_action(self):
        self.assert_invalid_status(accepted_body(phase="CANDIDATE"))
        self.assert_invalid_status(accepted_body(phase="ADOPTION"))
        self.assert_invalid_status(adopted_body(phase="PUBLICATION"))
        self.assert_invalid_status(status_body(phase="CANDIDATE"))

    def test_error_never_echoes_input(self):
        marker = "SECRETMARKER"
        self.assert_invalid_status(
            status_body(work_ref="WS:" + marker + "-"), marker)
        self.assert_invalid_status(
            status_body(schema="leak" + marker), marker)


class PathAndBranchTests(ContractCase):
    def with_source_path(self, path):
        return accepted_body(receipt=receipt(sources=[source(path=path)]))

    def with_proposal(self, **over):
        return proposal_observed_body(**over)

    def test_valid_paths(self):
        validate_status(self.with_source_path(PATH_OK))
        validate_status(self.with_source_path(PATH_UNICODE))
        validate_status(self.with_source_path("single.ts"))
        validate_status(self.with_source_path("a/b/c/d/e/f/g.module.css"))

    def test_path_traversal_and_injection_rejected(self):
        for bad in (
            "", "../escape.ts", "a/../b.ts", ".", "./x", "a/./b",
            "a//b", "/absolute.ts", "trailing/", "a\\b", "a\nb", "a\tb",
            "a\x00b", "a\x7fb", "a\x85b", "..", "./", "/",
        ):
            self.assert_invalid_status(self.with_source_path(bad))

    def test_path_utf8_byte_budget(self):
        validate_status(self.with_source_path("src/" + "я" * 254))  # 512 bytes
        self.assert_invalid_status(self.with_source_path("src/" + "я" * 255))
        self.assert_invalid_status(self.with_source_path("a" * 513))
        validate_status(self.with_source_path("a" * 512))
        self.assert_invalid_status(self.with_source_path("\ud800"))  # lone surrogate

    def test_valid_branches(self):
        validate_status(self.with_proposal(head_branch="main"))
        validate_status(self.with_proposal(head_branch="feature/prophet-r7"))
        validate_status(self.with_proposal(head_branch="A" * 200))
        validate_status(self.with_proposal(head_branch="v1.0"))

    def test_branch_injection_rejected(self):
        for bad in (
            "", "-lead", "trail/", ".", "..", "a..b", "a@{b", "@{",
            "has space", "tab\tx", "new\nline", "a\\b", "double//slash",
            "lead/", ".lead", "trail.", "x.lock", "\x01ctrl", "\x85ctrl",
            "ünicode", "a:b", "a?b", "a*b", "a[b", "a^b", "a~b",
            "B" * 201,
        ):
            self.assert_invalid_status(self.with_proposal(head_branch=bad))

    def test_proposal_url_binding(self):
        validate_status(self.with_proposal())
        validate_status(self.with_proposal(
            number=8,
            url="https://github.com/mastermindx-market-intelligence/macro/pull/8",
            head_branch="ok-8"))
        self.assert_invalid_status(self.with_proposal(
            url="https://github.com/mastermindx-market-intelligence/macro/pull/8"))
        self.assert_invalid_status(self.with_proposal(
            url="http://github.com/mastermindx-market-intelligence/macro/pull/7"))
        self.assert_invalid_status(self.with_proposal(
            url="https://github.com/mastermindx-market-intelligence/macro/pull/7/files"))
        self.assert_invalid_status(self.with_proposal(
            url="https://github.com/other-org/macro/pull/7"))
        self.assert_invalid_status(self.with_proposal(
            url="https://github.com/mastermindx-market-intelligence/macro/pull/07"))
        self.assert_invalid_status(self.with_proposal(url=None))
        self.assert_invalid_status(self.with_proposal(url=7))


class UnavailableTests(ContractCase):
    def expected(self, action="publish_project_proposal", scope=SCOPE):
        return {
            "schema": STATUS_SCHEMA,
            "selection": {
                "action": action,
                "request_id": REQUESTS[action],
                "work_ref": WORK_REF,
            },
            "owner_context": {"principal_scope": scope},
            "disposition": "unknown",
            "reason": "ORIGINAL_OPERATION_NOT_OBSERVED",
            "request_sha256": None,
            "recipe_fingerprint_sha256": None,
            "phase": None,
            "receipt": None,
            "advance": None,
        }

    def test_exact_null_evidence_body(self):
        result = unavailable(
            "publish_project_proposal",
            REQUESTS["publish_project_proposal"],
            WORK_REF,
            SCOPE,
        )
        self.assertEqual(result, self.expected())
        self.assert_exact_builtin_tree(result)
        self.assertEqual(validate_status(result), result)

    def test_works_for_every_action(self):
        for action, request_id in REQUESTS.items():
            result = unavailable(action, request_id, WORK_REF, SCOPE)
            self.assertEqual(result, self.expected(action=action))
            self.assertEqual(result["selection"]["request_id"], request_id)

    def test_fresh_instance_per_call(self):
        first = unavailable(
            "publish_project_proposal",
            REQUESTS["publish_project_proposal"],
            WORK_REF,
            SCOPE,
        )
        second = unavailable(
            "publish_project_proposal",
            REQUESTS["publish_project_proposal"],
            WORK_REF,
            SCOPE,
        )
        self.assertIsNot(first, second)
        self.assertIsNot(first["selection"], second["selection"])
        first["disposition"] = "accepted"
        first["selection"]["work_ref"] = "WS:MUTATED"
        self.assertEqual(second["disposition"], "unknown")
        self.assertEqual(second["selection"]["work_ref"], WORK_REF)

    def test_argument_validation(self):
        good = (
            "publish_project_proposal",
            REQUESTS["publish_project_proposal"],
            WORK_REF,
            SCOPE,
        )
        self.expect_invalid(unavailable, "unknown_action", good[1], WORK_REF, SCOPE)
        self.expect_invalid(
            unavailable, good[0], "mmos-project-create-" + "A" * 40, WORK_REF, SCOPE)
        self.expect_invalid(unavailable, good[0], good[1], "bad-ref", SCOPE)
        self.expect_invalid(unavailable, good[0], good[1], WORK_REF, "F" * 64)
        self.expect_invalid(unavailable, good[0], good[1], WORK_REF, "f" * 63)
        self.expect_invalid(unavailable, good[0], good[1], WORK_REF, None)
        self.expect_invalid(unavailable, good[0], good[1], WORK_REF, True)


class BoundTests(ContractCase):
    def test_deep_malformed_is_bounded_without_recursion_leak(self):
        def nested(depth):
            box = []
            cursor = box
            for _ in range(depth):
                nxt = []
                cursor.append(nxt)
                cursor = nxt
            return box

        deep = nested(4000)
        self.assert_invalid_status(deep)
        self.assert_invalid_status(status_body(schema=deep))
        self.assert_invalid_status(status_body(selection=deep))
        self.assert_invalid_status(status_body(receipt=deep))
        self.assert_invalid_status(status_body(advance=deep))
        deep_dict = {"a": {"a": deep}}
        self.assert_invalid_status(status_body(owner_context=deep_dict))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            sources=[deep_dict])))

    def test_oversized_fields_rejected_quickly(self):
        self.assert_invalid_status(status_body(schema="x" * 200000))
        self.assert_invalid_status(status_body(work_ref="WS:" + "A" * 200000))
        self.assert_invalid_status(accepted_body(receipt=receipt(
            sources=[source(path="a" * 200000)])))

    def test_whole_status_budget_headroom(self):
        near_max = accepted_body(receipt=receipt(sources=[
            source(path="src/" + "я" * 254),
            source(path="src/" + "г" * 254, commit=HEX40_B),
            source(path="src/" + "e" * 508, commit=HEX40_A),
        ]))
        result = validate_status(near_max)
        payload = canonical(result)
        self.assertLessEqual(
            len(payload.encode("utf-8")) + 1, 32768)
        self.assertEqual(canonical(validate_status(result)), payload)

    def test_canonical_serializable_ascii_off(self):
        result = validate_status(self.with_unicode_source())
        payload = canonical(result)
        self.assertIn("услуги", payload)
        self.assertNotIn("\\u0443", payload)
        self.assertEqual(payload, canonical(json.loads(payload)))

    def with_unicode_source(self):
        return accepted_body(receipt=receipt(sources=[source(path=PATH_UNICODE)]))

    def test_output_shape_is_closed(self):
        result = validate_status(accepted_body())
        self.assertEqual(
            frozenset(result.keys()),
            frozenset((
                "schema", "selection", "owner_context", "disposition", "reason",
                "request_sha256", "recipe_fingerprint_sha256", "phase",
                "receipt", "advance",
            )),
        )
        self.assertEqual(
            frozenset(result["receipt"].keys()),
            frozenset((
                "kind", "event_id", "recorded_at_ms", "receipt_sha256",
                "sources", "proposal",
            )),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
