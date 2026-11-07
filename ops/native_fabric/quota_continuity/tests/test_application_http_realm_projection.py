"""Sealed HTTP realm/driver projection: source-bound offline proof only.

These fixtures compile the exact hash-pinned ``1fc6ebfc`` source bytes, prove
real ``MiniMaxResponsesDriver``/``BailianResponsesDriver`` identity and
``prepare_request`` parity with the generated metadata through an in-process
transport spy that fails if it is ever invoked, and exercise the adversarial
refusals. No provider, credential, account, broker grant, installed
generation or application admission is touched; the compiler is metadata
only and proves neither an ordinary-handler connection nor pool coverage.
"""
import ast
from collections.abc import Mapping
import hashlib
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "candidate"), str(ROOT / "rollout"), str(ROOT / "source"),
                str(ROOT / "tests"), str(REPO)]

from _offline_boundary import acquire as offline_acquire, release as offline_release

import application_http_realm_projection as projection
from application_http_realm_projection import (
    INPUT_SOURCES, ProjectionRefused, SOURCE_COMMIT, compile_projection,
    compile_projection_bytes, validate_projection as _validate_projection,
)

import application_http_transports as transports
from application_http_transports import (
    BailianResponsesDriver, MiniMaxResponsesDriver, TransportRefused,
)
from control_plane.codex_provider_realm import (
    ALIBABA_TOKEN_PLAN, MINIMAX_TOKEN_PLAN, OPENCODE_GO_TOKEN_PLAN,
    REVIEWED_CODEX_PROVIDER_REALMS,
)


def setUpModule():
    offline_acquire()


def tearDownModule():
    offline_release()


def _pinned_inputs():
    # These inert exact1fc snapshots are compiler evidence, not runtime code.
    # Archive/shallow checkouts need no historical Git object acquisition.
    evidence = {
        projection.REALM_SOURCE_PATH: ROOT / "source/codex_provider_realm.py.preimage",
        projection.TRANSPORT_SOURCE_PATH: ROOT / "source/application_http_transports.py.preimage",
    }
    return {entry["path"]: evidence.get(entry["path"], REPO / entry["path"]).read_bytes()
            for entry in INPUT_SOURCES}


def _spy_transport(request):
    raise AssertionError("transport invoked during projection proof")


def _refused(case, function, code):
    with case.assertRaises(ProjectionRefused) as caught:
        function()
    case.assertEqual(caught.exception.code, code)


def _tampered(payload, mutate):
    document = json.loads(payload)
    mutate(document)
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def validate_projection(payload):
    """Structural cases commit their fixture; integrity cases use the real API."""
    digest = hashlib.sha256(payload).hexdigest() if isinstance(payload, (bytes, bytearray)) else "0" * 64
    return _validate_projection(payload, expected_sha256=digest)


MINIMAX_POLICY = {"requires_codex_auth_file": False,
                  "interactive_subscription_only": True,
                  "request_max_retries": 0, "stream_max_retries": 0}

EXPECTED_DRIVERS = [
    {
        "driver_id": "alibaba-token-plan-sg.responses",
        "realm_id": "alibaba-token-plan-sg",
        "provider": "alibaba",
        "pool": "bailian",
        "base_url": ALIBABA_TOKEN_PLAN.base_url,
        "endpoint": ALIBABA_TOKEN_PLAN.base_url + "/responses",
        "protocol": "responses",
        "env_key": "ALIBABA_TOKEN_PLAN_KEY",
        "allowed_models": ["qwen3.8-flash", "qwen3.8-max"],
        "default_model": "qwen3.8-flash",
        "declared_realm_policy": dict(MINIMAX_POLICY),
    },
    {
        "driver_id": "minimax-token-plan.responses",
        "realm_id": "minimax-token-plan",
        "provider": "minimax",
        "pool": "minimax",
        "base_url": MINIMAX_TOKEN_PLAN.base_url,
        "endpoint": MINIMAX_TOKEN_PLAN.base_url + "/responses",
        "protocol": "responses",
        "env_key": "MINIMAX_TOKEN_PLAN_KEY",
        "allowed_models": ["MiniMax-M3"],
        "default_model": None,
        "declared_realm_policy": dict(MINIMAX_POLICY),
    },
]

EXPECTED_DOCUMENT = {
    "schema": projection.SCHEMA,
    "source_commit": SOURCE_COMMIT,
    "sources": [{"path": entry["path"], "git_blob_sha1": entry["git_blob_sha1"],
                 "sha256": entry["sha256"]}
                for entry in sorted(INPUT_SOURCES, key=lambda item: item["path"])],
    "drivers": EXPECTED_DRIVERS,
}


class SourcePinTests(unittest.TestCase):
    """The admitted checkout must carry the exact pinned input bytes."""

    def test_exact_input_commitments(self):
        for path, data in _pinned_inputs().items():
            entry = next(e for e in INPUT_SOURCES if e["path"] == path)
            self.assertEqual(projection._git_blob_sha1(data),
                             entry["git_blob_sha1"], path)
            self.assertEqual(projection._sha256(data), entry["sha256"], path)

    def test_admitted_candidate_carries_exactly_the_two_new_paths(self):
        self.assertTrue(
            (ROOT / "rollout" / "application_http_realm_projection.py").is_file())
        self.assertTrue(
            (ROOT / "tests" / "test_application_http_realm_projection.py").is_file())

    def test_reviewed_realms_are_exactly_the_two_imported_owners(self):
        self.assertEqual(sorted(REVIEWED_CODEX_PROVIDER_REALMS),
                         ["alibaba-token-plan-sg", "minimax-token-plan"])
        self.assertNotIn(OPENCODE_GO_TOKEN_PLAN.realm_id,
                         REVIEWED_CODEX_PROVIDER_REALMS)


class CompilationTests(unittest.TestCase):
    """Deterministic canonical bytes derived from the closed declarations."""

    def setUp(self):
        self.inputs = _pinned_inputs()
        self.payload = compile_projection_bytes(self.inputs)

    def test_exact_expected_projection(self):
        self.assertEqual(json.loads(self.payload), EXPECTED_DOCUMENT)

    def test_deterministic_and_order_independent(self):
        self.assertEqual(self.payload, compile_projection_bytes(self.inputs))
        reordered = compile_projection_bytes(
            {key: self.inputs[key] for key in reversed(list(self.inputs))})
        self.assertEqual(self.payload, reordered)
        self.assertEqual(self.payload,
                         self.payload.decode("utf-8").encode("utf-8"))

    def test_spec_only_go_never_leaks_into_output(self):
        self.assertNotIn(b"opencode-go", self.payload)
        self.assertNotIn(b"OpenCode", self.payload)
        self.assertNotIn(b"OPENCODE_GO_KEY", self.payload)
        for record in json.loads(self.payload)["drivers"]:
            self.assertNotEqual(record["realm_id"], OPENCODE_GO_TOKEN_PLAN.realm_id)
            self.assertNotEqual(record["pool"], "go")

    def test_env_key_is_symbol_name_only(self):
        self.assertNotIn(b"sk-", self.payload)
        for record in json.loads(self.payload)["drivers"]:
            self.assertRegex(record["env_key"], r"^[A-Z][A-Z0-9_]{0,63}$")

    def test_no_ambient_access_during_compile_and_readback(self):
        with (mock.patch("builtins.open", side_effect=AssertionError("open")),
              mock.patch("socket.socket", side_effect=AssertionError("socket")),
              mock.patch("os.environ", {"__sealed__": "1"}),
              mock.patch("time.time", side_effect=AssertionError("clock"))):
            payload = compile_projection_bytes(self.inputs)
            validate_projection(payload)
        self.assertEqual(payload, self.payload)

    def test_frozen_result_is_mutation_isolated(self):
        frozen = compile_projection(self.inputs)
        with self.assertRaises(TypeError):
            frozen["drivers"][0]["pool"] = "go"
        with self.assertRaises(TypeError):
            frozen["drivers"][0]["declared_realm_policy"]["request_max_retries"] = 3
        self.assertEqual(projection._unfreeze(frozen), EXPECTED_DOCUMENT)
        self.assertEqual(json.loads(compile_projection_bytes(self.inputs)),
                         EXPECTED_DOCUMENT)


class DriverParityTests(unittest.TestCase):
    """Real accepted H identity/prepare_request must match the projection.

    The transport spy fails the test if the driver ever tries to send: this
    proof exercises identity compilation only and never a provider exchange.
    """

    def _records(self):
        document = json.loads(compile_projection_bytes(_pinned_inputs()))
        return {record["driver_id"]: record for record in document["drivers"]}

    def test_identity_matches_projection_exactly(self):
        records = self._records()
        for driver, driver_id in (
                (MiniMaxResponsesDriver(transport=_spy_transport),
                 "minimax-token-plan.responses"),
                (BailianResponsesDriver(transport=_spy_transport),
                 "alibaba-token-plan-sg.responses")):
            record = records[driver_id]
            identity = driver.identity
            for field in ("driver_id", "realm_id", "provider", "pool", "base_url",
                          "endpoint", "protocol", "env_key", "default_model"):
                self.assertEqual(getattr(identity, field), record[field])
            self.assertEqual(sorted(identity.allowed_models), record["allowed_models"])

    def test_prepare_request_consumes_the_same_transport_metadata(self):
        records = self._records()
        for driver, driver_id, model in (
                (MiniMaxResponsesDriver(transport=_spy_transport),
                 "minimax-token-plan.responses", "MiniMax-M3"),
                (BailianResponsesDriver(transport=_spy_transport),
                 "alibaba-token-plan-sg.responses", "qwen3.8-max"),
                (BailianResponsesDriver(transport=_spy_transport),
                 "alibaba-token-plan-sg.responses", "qwen3.8-flash")):
            record = records[driver_id]
            compiled = driver.prepare_request(
                {"model": model,
                 "messages": [{"role": "user", "content": "parity"}]})
            self.assertEqual(compiled.driver_id, record["driver_id"])
            self.assertEqual(compiled.realm_id, record["realm_id"])
            self.assertEqual(compiled.provider, record["provider"])
            self.assertEqual(compiled.pool, record["pool"])
            self.assertEqual(compiled.endpoint, record["endpoint"])
            self.assertEqual(compiled.protocol, record["protocol"])
            self.assertEqual(compiled.model, model)
            body = json.loads(compiled.wire_body)
            self.assertEqual(body["model"], model)
            self.assertIs(body["stream"], False)

    def test_default_model_resolution_matches_projection(self):
        bailian = BailianResponsesDriver(transport=_spy_transport)
        compiled = bailian.prepare_request(
            {"messages": [{"role": "user", "content": "default"}]})
        self.assertEqual(compiled.model, "qwen3.8-flash")
        minimax = MiniMaxResponsesDriver(transport=_spy_transport)
        with self.assertRaises(TransportRefused) as caught:
            minimax.prepare_request(
                {"messages": [{"role": "user", "content": "none"}]})
        self.assertEqual(caught.exception.code, "model_required")

    def test_prepare_request_refuses_unprojected_model(self):
        bailian = BailianResponsesDriver(transport=_spy_transport)
        with self.assertRaises(TransportRefused) as caught:
            bailian.prepare_request(
                {"model": "MiniMax-M3",
                 "messages": [{"role": "user", "content": "cross"}]})
        self.assertEqual(caught.exception.code, "model_not_qualified")


class AdversarialInputTests(unittest.TestCase):
    """Changed, missing, extra, relabelled or drifted inputs refuse."""

    def setUp(self):
        self.inputs = _pinned_inputs()

    def test_changed_source_bytes_refuse(self):
        for entry in INPUT_SOURCES:
            mutated = dict(self.inputs)
            data = bytearray(mutated[entry["path"]])
            data[len(data) // 2] ^= 0x20
            mutated[entry["path"]] = bytes(data)
            _refused(self, lambda m=mutated: compile_projection_bytes(m),
                     "source_blob_mismatch")

    def test_missing_and_extra_inputs_refuse(self):
        for entry in INPUT_SOURCES:
            missing = {key: value for key, value in self.inputs.items()
                       if key != entry["path"]}
            _refused(self, lambda m=missing: compile_projection_bytes(m),
                     "input_closure_mismatch")
        extra = dict(self.inputs)
        extra["ops/native_fabric/quota_continuity/rollout/extra.py"] = b"x = 1\n"
        _refused(self, lambda: compile_projection_bytes(extra),
                 "input_closure_mismatch")

    def test_relabelled_inputs_refuse(self):
        realm_path, protocol_path, transport_path = (
            entry["path"] for entry in INPUT_SOURCES)
        _refused(self, lambda: compile_projection_bytes(
            {realm_path: self.inputs[protocol_path],
             protocol_path: self.inputs[realm_path],
             transport_path: self.inputs[transport_path]}), "source_blob_mismatch")
        _refused(self, lambda: compile_projection_bytes(
            {realm_path: self.inputs[transport_path],
             protocol_path: self.inputs[protocol_path],
             transport_path: self.inputs[realm_path]}), "source_blob_mismatch")

    def test_non_bytes_input_refuses(self):
        relaxed = dict(self.inputs)
        relaxed[INPUT_SOURCES[0]["path"]] = "text is not bytes"
        _refused(self, lambda: compile_projection_bytes(relaxed),
                 "invalid_input_bytes")


class StructuralRefusalTests(unittest.TestCase):
    """Duplicate, shadowed or dynamic closed constructs refuse."""

    def _realms(self, source):
        return projection._extract_realms(ast.parse(source))

    def _transports(self, source):
        return projection._extract_transports(ast.parse(source))

    REALM_TEMPLATE = '''
import dataclasses

@dataclasses.dataclass(frozen=True)
class CodexProviderRealm:
    realm_id: str
    provider_alias: str
    display_name: str
    base_url: str
    env_key: str
    wire_api: str
    requires_codex_auth_file: bool = False
    interactive_subscription_only: bool = True
    request_max_retries: int = 0
    stream_max_retries: int = 0

REALM = CodexProviderRealm(
    realm_id="realm-a", provider_alias="a", display_name="A",
    base_url="https://a.example/v1", env_key="A_KEY", wire_api="responses")

REVIEWED_CODEX_PROVIDER_REALMS = {realm.realm_id: realm for realm in (%s,)}
'''

    def test_duplicate_realm_binding_refuses(self):
        source = (self.REALM_TEMPLATE % "REALM") + (
            '\nREVIEWED_CODEX_PROVIDER_REALMS = {"realm-a": REALM}\n')
        _refused(self, lambda: self._realms(source), "duplicate_binding")

    def test_dynamic_reviewed_realms_refuse(self):
        _refused(self, lambda: self._realms(self.REALM_TEMPLATE % "make_realms()"),
                 "dynamic_reviewed_realms")
        _refused(self, lambda: self._realms(self.REALM_TEMPLATE % "*REALM_SOURCES"),
                 "dynamic_reviewed_realms")
        _refused(self, lambda: self._realms(
            "REVIEWED_CODEX_PROVIDER_REALMS = dict()\n"),
            "unsupported_reviewed_realms")

    def test_dynamic_realm_construct_refuses(self):
        source = self.REALM_TEMPLATE % "REALM, OTHER"
        source += ('\nOTHER = CodexProviderRealm(\n'
                   '    **{"realm_id": "kwarg-realm", "provider_alias": "k",\n'
                   '        "display_name": "K", "base_url": "https://k.example/v1",\n'
                   '        "env_key": "K_KEY", "wire_api": "responses"})\n')
        _refused(self, lambda: self._realms(source),
                 "positional_or_dynamic_argument")

    def test_non_constant_realm_construct_refuses(self):
        source = self.REALM_TEMPLATE % "REALM, OTHER"
        source += ('\nOTHER = CodexProviderRealm(\n'
                   '    realm_id="kwarg-realm", provider_alias="k",\n'
                   '    display_name="K", base_url="https://k.example/v1",\n'
                   '    env_key="K_KEY", wire_api="responses",\n'
                   '    request_max_retries=int(0))\n')
        _refused(self, lambda: self._realms(source), "unsupported_realm_policy")

    def test_missing_realm_policy_defaults_refuse(self):
        source = self.REALM_TEMPLATE % "REALM"
        source = source.replace("    request_max_retries: int = 0\n", "")
        _refused(self, lambda: self._realms(source), "missing_realm_policy_defaults")

    def test_realm_policy_override_is_preserved_as_declared(self):
        source = self.REALM_TEMPLATE % "REALM"
        source = source.replace('env_key="A_KEY", wire_api="responses")',
                                'env_key="A_KEY", wire_api="responses",\n'
                                '    request_max_retries=0)')
        realms = self._realms(source)
        self.assertEqual(
            realms["realm-a"]["declared_realm_policy"]["request_max_retries"], 0)
        self.assertTrue(
            realms["realm-a"]["declared_realm_policy"]["interactive_subscription_only"])

    TRANSPORT_TEMPLATE = '''
RESPONSES_PROTOCOL = "responses"

class _FixedResponsesDriver:
    driver_id = ""
    realm_id = ""
    pool = ""
    allowed_models = frozenset()
    default_model = None

    def __init__(self):
        self._identity = DriverIdentity(
            driver_id=self.driver_id,
            realm_id=realm.realm_id,
            provider=realm.provider_alias,
            pool=self.pool,
            base_url=realm.base_url,
            endpoint=realm.base_url + "/responses",
            protocol=protocol,
            env_key=realm.env_key,
            default_model=self.default_model,
            allowed_models=frozenset(self.allowed_models),
        )

%s
'''

    DRIVER = '''
class %s(_FixedResponsesDriver):
    driver_id = "%s"
    realm_id = "%s"
    pool = "%s"
    allowed_models = frozenset({%s})
    default_model = %s
'''

    MINIMAX_DRIVER = ("MiniMaxResponsesDriver", "minimax-token-plan.responses",
                      "minimax-token-plan", "minimax", '"MiniMax-M3"', "None")
    BAILIAN_DRIVER = ("BailianResponsesDriver", "alibaba-token-plan-sg.responses",
                      "alibaba-token-plan-sg", "bailian",
                      '"qwen3.8-flash", "qwen3.8-max"', '"qwen3.8-flash"')
    GO_DRIVER = ("GoResponsesDriver", "opencode-go.responses", "opencode-go",
                 "go", '"go-model"', "None")

    def _both_drivers(self):
        return (self.DRIVER % self.MINIMAX_DRIVER) + (self.DRIVER % self.BAILIAN_DRIVER)

    def test_unexpected_third_driver_subclass_refuses(self):
        source = self.TRANSPORT_TEMPLATE % (
            self._both_drivers() + (self.DRIVER % self.GO_DRIVER))
        _refused(self, lambda: self._transports(source), "unexpected_driver_subclass")

    def test_missing_driver_class_refuses(self):
        source = self.TRANSPORT_TEMPLATE % (self.DRIVER % self.MINIMAX_DRIVER)
        _refused(self, lambda: self._transports(source), "missing_driver_class")

    def test_wrong_endpoint_derivation_refuses(self):
        source = (self.TRANSPORT_TEMPLATE % self._both_drivers()).replace(
            'endpoint=realm.base_url + "/responses"', 'endpoint=caller_endpoint')
        _refused(self, lambda: self._transports(source),
                 "unsupported_endpoint_derivation")

    def test_duplicate_class_attribute_refuses(self):
        source = (self.TRANSPORT_TEMPLATE % self._both_drivers()).replace(
            '    driver_id = "minimax-token-plan.responses"\n',
            '    driver_id = "minimax-token-plan.responses"\n    pool = "other"\n', 1)
        _refused(self, lambda: self._transports(source), "duplicate_class_attribute")

    def test_wrong_transport_protocol_constant_refuses(self):
        source = (self.TRANSPORT_TEMPLATE % self._both_drivers()).replace(
            'RESPONSES_PROTOCOL = "responses"', 'RESPONSES_PROTOCOL = "openai-chat"')
        _refused(self, lambda: self._transports(source),
                 "unsupported_transport_protocol")

    def test_ambiguous_identity_construction_refuses(self):
        source = (self.TRANSPORT_TEMPLATE % self._both_drivers()).replace(
            "            allowed_models=frozenset(self.allowed_models),\n        )\n",
            "            allowed_models=frozenset(self.allowed_models),\n        )\n"
            "        self._identity = DriverIdentity(\n"
            "            driver_id=self.driver_id,\n"
            "            realm_id=realm.realm_id,\n"
            "            provider=realm.provider_alias,\n"
            "            pool=self.pool,\n"
            "            base_url=realm.base_url,\n"
            '            endpoint=realm.base_url + "/responses",\n'
            "            protocol=protocol,\n"
            "            env_key=realm.env_key,\n"
            "            default_model=self.default_model,\n"
            "            allowed_models=frozenset(self.allowed_models),\n"
            "        )\n", 1)
        _refused(self, lambda: self._transports(source),
                 "ambiguous_identity_construction")


class ReadbackValidationTests(unittest.TestCase):
    """Strict readback: closed keys, exact commitments, bounded values."""

    def setUp(self):
        self.payload = compile_projection_bytes(_pinned_inputs())

    def test_valid_bytes_round_trip(self):
        document = projection._unfreeze(validate_projection(self.payload))
        self.assertEqual(document, EXPECTED_DOCUMENT)

    def test_altered_records_refuse(self):
        cases = (
            ("enabled_flag_injection",
             lambda d: d["drivers"][0].update(enabled=True),
             "unsupported_driver_record"),
            ("unsorted_allowed_models",
             lambda d: d["drivers"][0].update(
                 allowed_models=["qwen3.8-max", "qwen3.8-flash"]),
             "unsupported_allowed_models"),
            ("env_key_value_injection",
             lambda d: d["drivers"][0].update(env_key="sk-secret-value"),
             "unsupported_env_key_name"),
            ("retry_policy_rewrite",
             lambda d: d["drivers"][0]["declared_realm_policy"].update(
                 request_max_retries=3),
             "unsupported_realm_policy"),
            ("subscription_gate_weakening",
             lambda d: d["drivers"][1]["declared_realm_policy"].update(
                 interactive_subscription_only=False),
             "unsupported_realm_policy"),
            ("endpoint_injection",
             lambda d: d["drivers"][0].update(
                 endpoint="https://attacker.example/responses"),
             "unsupported_endpoint"),
            ("unqualified_default_model",
             lambda d: d["drivers"][1].update(default_model="other-model"),
             "default_model_unqualified"),
        )
        for label, mutate, expected_code in cases:
            _refused(self, lambda m=mutate: validate_projection(
                _tampered(self.payload, m)), expected_code)

    def test_altered_envelope_refuses(self):
        cases = (
            ("schema_drift",
             lambda d: d.update(schema="mastermind.application_http_realms.v2"),
             "schema_mismatch"),
            ("stale_source_commitment",
             lambda d: d.update(source_commit="0" * 40),
             "source_commit_mismatch"),
            ("unsorted_drivers", lambda d: d["drivers"].reverse(),
             "unsorted_driver_inventory"),
            ("dropped_driver", lambda d: d["drivers"].pop(),
             "unsupported_driver_inventory"),
            ("stale_sha256_commitment",
             lambda d: d["sources"][0].update(sha256="0" * 64),
             "source_commitment_mismatch"),
            ("stale_blob_commitment",
             lambda d: d["sources"][0].update(git_blob_sha1="0" * 40),
             "source_commitment_mismatch"),
            ("extra_envelope_field", lambda d: d.update(extra="field"),
             "unsupported_projection_shape"),
            ("dropped_envelope_field", lambda d: d.pop("sources"),
             "unsupported_projection_shape"),
        )
        for label, mutate, expected_code in cases:
            _refused(self, lambda m=mutate: validate_projection(
                _tampered(self.payload, m)), expected_code)

    def test_malformed_payload_refuses(self):
        _refused(self, lambda: validate_projection(self.payload + b"\x00"),
                 "unparsable_projection")
        duplicate_key = (b'{"schema":"mastermind.application_http_realms.v1",'
                         b'"schema":"other","source_commit":"' + SOURCE_COMMIT.encode()
                         + b'","sources":[],"drivers":[]}')
        _refused(self, lambda: validate_projection(duplicate_key),
                 "duplicate_output_key")
        _refused(self, lambda: validate_projection(b""), "projection_size")
        _refused(self, lambda: validate_projection(None), "invalid_projection_payload")

    def test_readback_is_frozen_and_stateless(self):
        frozen = validate_projection(self.payload)
        with self.assertRaises(TypeError):
            frozen["drivers"][0]["pool"] = "go"
        with self.assertRaises((TypeError, AttributeError)):
            frozen["drivers"][0]["declared_realm_policy"].update(request_max_retries=3)
        again = validate_projection(self.payload)
        self.assertEqual(projection._unfreeze(frozen), projection._unfreeze(again))


class OriginalArtifactIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.inputs = _pinned_inputs()
        self.payload = compile_projection_bytes(self.inputs)
        self.commitment = hashlib.sha256(self.payload).hexdigest()

    def test_coherent_identity_edits_cannot_retain_original_artifact_commitment(self):
        mutations = [
            lambda d: d["drivers"][0].update(base_url="https://other.invalid/v1",
                endpoint="https://other.invalid/v1/responses"),
            lambda d: d["drivers"][0].update(allowed_models=["other-model"], default_model="other-model"),
            lambda d: d["drivers"][0].update(env_key="OTHER_KEY"),
            lambda d: d["drivers"][0].update(provider="other"),
            lambda d: d["drivers"][0].update(driver_id="aaa.responses"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutations.index(mutate)):
                changed = _tampered(self.payload, mutate)
                _refused(self, lambda: _validate_projection(changed,
                    expected_sha256=self.commitment), "projection_commitment_mismatch")
        _refused(self, lambda: _validate_projection(self.payload + b"\n",
            expected_sha256=self.commitment), "projection_commitment_mismatch")

    def test_missing_or_malformed_trusted_commitment_is_not_derived_from_payload(self):
        with self.assertRaises(TypeError):
            _validate_projection(self.payload)
        for value in (None, "", "A" * 64, "0" * 63, 0, [], {}):
            _refused(self, lambda v=value: _validate_projection(self.payload,
                expected_sha256=v), "invalid_projection_commitment")
        _refused(self, lambda: _validate_projection(self.payload,
            expected_sha256="0" * 64), "projection_commitment_mismatch")
        self.assertEqual(projection._unfreeze(_validate_projection(self.payload,
            expected_sha256=self.commitment)), json.loads(self.payload))

    def test_changing_mapping_is_read_once_then_snapshot_is_used(self):
        originals = self.inputs

        class ChangingInputs(Mapping):
            def __init__(self):
                self.reads = {key: 0 for key in originals}
            def __iter__(self):
                return iter(originals)
            def __len__(self):
                return len(originals)
            def __getitem__(self, key):
                self.reads[key] += 1
                return originals[key] if self.reads[key] == 1 else originals[key] + b"\n# changed after verification\n"

        changing = ChangingInputs()
        self.assertEqual(compile_projection_bytes(changing), self.payload)
        self.assertTrue(all(count == 1 for count in changing.reads.values()))

    def test_mutable_input_buffers_cannot_change_verified_parsing_or_hashes(self):
        mutable = {key: bytearray(value) for key, value in self.inputs.items()}
        parse = projection._parse

        def mutate_after_snapshot(data, path):
            for value in mutable.values():
                value.clear()
            return parse(data, path)

        with mock.patch.object(projection, "_parse", mutate_after_snapshot):
            self.assertEqual(compile_projection_bytes(mutable), self.payload)
        self.assertTrue(all(not value for value in mutable.values()))

    def test_non_string_env_key_is_a_bounded_structural_refusal(self):
        for value in (None, [], {}, False, 123):
            changed = _tampered(self.payload, lambda d: d["drivers"][0].update(env_key=value))
            _refused(self, lambda: validate_projection(changed), "unsupported_env_key_name")


if __name__ == "__main__":
    unittest.main()
