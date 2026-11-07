"""Real MM warmer -> Macro factory/client -> pinned native A/B -> loopback.

Only business stores, credentials, qualification and upstream answers are
synthetic. The cache lock, durable replacement, operation, broker, accounting
and close paths remain real. Required CI enables the paired class explicitly.
"""
from contextlib import redirect_stdout
from dataclasses import asdict, replace
import copy
import hashlib
import importlib.util
import io
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from brain import translate

# Forward fixture epoch: selected application admission composed over
# native HTTP f7d72b740103bdf7a817ae0b00474f65cc2d828d. Exact candidate blobs follow.
# Keep exact source validation; the prior 8af gate cannot describe the reviewed
# A/B/codec and HTTP realm composition now exercised by this repository's CI.
PINS = {
    "candidate/commission_deadline.py": "fade630ed75c1b93334a5711a6df7a554fbd24ee",
    "candidate/go_shim.py": "97deba9fc1f68458670b16a21cb410575a7466f8",
    "candidate/lease_broker.py": "9b22048111a2bb3112c65b0abfb57f0870126ed6",
    "candidate/go_lease_gateway.py": "7eb74e2a9a18d3c6a1ad1f51ed198bd0e32bcdeb",
    "candidate/go_lease_capability.py": "13e6b2d43cbb2933512e6e46d27a431e7813af88",
    "candidate/application_http_transports.py": "b0b8404b45dd0a3e73a34430c2ef3a28b1edbf6d",
    "candidate/provider_outcome.py": "981f35a01183e83fdb9f0b8a4175b290cdeb85f8",
    "candidate/quota_circuit.py": "1583a6ba773e56dbc3f295b65ffc08dea2d31d48",
    "source/model_tier.py": "96093c2747d2dda69b3f2255cb84e656355c87ea",
    "source/pool_status.py": "02922043357d63b4bcfa3791899df27a5c42be12",
    "source/application_http_transports.py.preimage": "a116d8c671594552dd5c14f46f91981cd7c15f43",
    # Historical metadata input selected by application_http_sources(); the
    # current realm module is not a fallback for this exact retained evidence.
    "source/codex_provider_realm.py.preimage": "eeea4c0fafc7e6df5c534c731cb6046bbe4d3f37",
    "rollout/application_http_realm_projection.py": "684c54d5c9d8dbdd5bc046d123af31d20fc99dd1",
    "tests/_offline_boundary.py": "e511ab65fe1cd30bf4d2addac6700ca43c3468da",
    "tests/test_go_application_handler_composition.py": "13ebd6bcee5167926807d7ccdc63bcabed0cf1b1",
    "tests/test_application_turn_admission.py": "efe876eec40dc8885dbc0059915f2401146be969",
}
REALM_PINS = {
    "control_plane/provider_protocols.py": "92452237ac3956e8104e45ab9ee386c2fa016b76",
    "control_plane/fs_security.py": "16617789dc115b5748a3e72cc0d9a53fbc368918",
}
MODEL = "fixture-model"


def _translation_race_process(root, expected_macro, transport, queue):
    """Fresh interpreter: same real owner and files, no inherited thread locks."""
    from brain import fabric_inference
    owner, _, actual_macro = fabric_inference._owner()
    if (actual_macro != Path(expected_macro)
            or not (actual_macro / ".fabric-composition-fixture").is_file()):
        raise AssertionError("race child requires the same isolated actual owner")
    owner._APPLICATION_FABRIC_TRANSPORTS["translation_fixture_v1"] = owner._ApplicationFabricTransport(**transport)
    translate._ROOT = Path(root)
    translate._CACHE_PATH = Path(root) / "data/brain/translations.json"
    translate._cache_mem, translate._cache_mtime = None, None
    queue.put(translate.translate_and_cache([" same input "]))


class CacheProjectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for name, value in (("_ROOT", self.root), ("_CACHE_PATH", self.root / "translations.json"),
                            ("_cache_mem", None), ("_cache_mtime", None)):
            guard = patch.object(translate, name, value)
            guard.start()
            self.addCleanup(guard.stop)

    def test_legacy_keys_named_like_metadata_are_historical_strings(self):
        legacy = {"schema": "模式", "operations": "操作", "English": "中文"}
        translate._CACHE_PATH.write_text(json.dumps(legacy))
        with patch.object(translate, "_fabric_selected", side_effect=AssertionError("selection")):
            self.assertEqual(translate._load_cache(), legacy)
            self.assertEqual(translate.translate_and_cache([" English "]), {"English": "中文"})
            self.assertEqual(translate.cached_zh("English"), "中文")
        self.assertEqual(json.loads(translate._CACHE_PATH.read_text()), legacy)

    def test_corrupt_or_duplicate_state_is_not_an_empty_mutation_store(self):
        for raw in (b"broken", b'{"same":"a","same":"b"}', b'{"schema":2}', b'[]'):
            with self.subTest(raw=raw):
                translate._CACHE_PATH.write_bytes(raw)
                with patch.object(translate, "_fabric_selected", side_effect=AssertionError("selection")):
                    self.assertEqual(translate.translate_and_cache(["new"]), {"new": "new"})
                    translate._save_cache({"unrelated": "其他"})
                self.assertEqual(translate._CACHE_PATH.read_bytes(), raw)

    def test_native_stale_merge_keeps_newer_entries(self):
        translate._CACHE_PATH.write_text(json.dumps({"old": "新值", "other": "其他"}))
        translate._save_cache({"old": "旧值", "added": "增加"})
        self.assertEqual(translate._load_cache(), {"old": "新值", "other": "其他", "added": "增加"})


class FabricTranslationCompositionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.environ.get("MM_REQUIRE_FABRIC_COMPOSITION") != "1":
            raise unittest.SkipTest("Required paired Fabric composition step")
        from brain import fabric_inference, cli_bridge, thinking_log
        cls.bridge, cls.thinking = cli_bridge, thinking_log
        cls.owner, cls.shared, cls.macro_root = fabric_inference._owner()
        expected = Path(os.environ["MM_FABRIC_FIXTURE_ROOT"]).resolve()
        import bot
        if (cls.macro_root != expected or bot._VENDOR.resolve() != expected
                or not (expected / ".fabric-composition-fixture").is_file()):
            raise AssertionError("Disposable actual Macro owner required")
        cls.config_paths = [expected / "config" / name for name in (
            "provider_production_modes.v1.json", "provider_workloads.v1.json", "capability_manifest.yml")]
        cls.originals = {p: p.read_bytes() if p.exists() else None for p in cls.config_paths}
        repository = Path(__file__).resolve().parents[2]
        root = repository / "ops/native_fabric/quota_continuity"
        for source_root, pins in ((root, PINS), (repository, REALM_PINS)):
            for relative, expected_blob in pins.items():
                raw = (source_root / relative).read_bytes()
                actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                if actual != expected_blob:
                    raise AssertionError("Native source mismatch: " + relative)
        cls.old_path = list(sys.path)
        sys.path[:0] = [str(root / "tests"), str(root / "candidate"), str(root / "source")]
        spec = importlib.util.spec_from_file_location("_translation_native_fixture",
            root / "tests/test_go_application_handler_composition.py")
        cls.native_module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.native_module
        spec.loader.exec_module(cls.native_module)

    @classmethod
    def tearDownClass(cls):
        for path, original in cls.originals.items():
            path.unlink(missing_ok=True) if original is None else path.write_bytes(original)
        sys.path[:] = cls.old_path
        sys.modules.pop("_translation_native_fixture", None)

    def start(self, guard):
        self.addCleanup(guard.stop)
        return guard.start()

    def setUp(self):
        from engine import fabric_inference_client
        self.transport = fabric_inference_client
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.native = self.native_module.NativeApplicationHTTPFixture()
        self.native.setUp()
        self.addCleanup(self.native.doCleanups)
        self.native.grant.update(workloads=["site_batch"], max_steps=8)
        self.native.save()
        service = replace(self.native.service, workload="site_batch")
        self.server = self.native.go.make_server(self.native.router,
            lease_gateway=self.native.gateway, application_services=(service,))
        self.native._serve(self.server)
        self.synthetic = self.owner._ApplicationFabricTransport(
            f"http://127.0.0.1:{self.server.server_port}/v1", service.credential_ref,
            "go", MODEL, "subscription", "fabric:translation-fixture", "translation_fixture",
            qualified=True, application_allowed=True, protocol=fabric_inference_client.NATIVE_PROTOCOL)
        self.start(patch.dict(self.owner._APPLICATION_FABRIC_TRANSPORTS, {"translation_fixture_v1": self.synthetic}))
        self.document = json.loads(self.originals[self.config_paths[0]])
        self.mode = {key: getattr(self.synthetic, key) for key in self.owner._APPLICATION_IDENTITY_FIELDS}
        self.mode.update(transport_id="translation_fixture_v1", enabled=True, application_allowed=True,
                         qualification=self.owner.PROFILE_QUALIFIED_CANARY,
                         qualification_ref="fixture:source-only", qualified_until=time.time() + 3600)
        self.document["application_fabric_modes"] = {"shared_fabric": self.mode}
        self.manifest = {"capabilities": [{"capability_id": "translation_fixture",
            "secret_ref": service.credential_ref, "kill_state": "active", "allowed_lanes": ["mastermind-text"]}]}
        self.save()
        self.config_paths[1].write_bytes(self.originals[self.config_paths[1]])
        self.start(patch.dict(os.environ, {
            "BOT_LLM_BACKEND": "fabric", "MM_PROVIDER_APPLICATION_MODE": "shared_fabric",
            service.credential_ref: service.credential,
            "PROVIDER_HEALTH_PATH": str(self.root / "health.jsonl"),
            "AI_COSTS_STATE_ROOT": str(self.root / "costs"),
        }, clear=True))
        for name, value in (("_ROOT", self.root), ("_CACHE_PATH", self.root / "data/brain/translations.json"),
                            ("_cache_mem", None), ("_cache_mtime", None)):
            self.start(patch.object(translate, name, value))
        self.forbidden = []
        for target, name in ((self.bridge, "available"), (self.bridge, "reason_sync"),
                             (self.bridge, "_subscription_env"), (self.shared, "_oauth_pool_candidates"),
                             (self.thinking, "log_turn_async")):
            self.forbidden.append(self.start(patch.object(target, name,
                side_effect=AssertionError("legacy/activity effect"))))
        self.addCleanup(lambda: [self.assertFalse(spy.called, "legacy/activity boundary was attempted")
                                 for spy in self.forbidden])
        self.events, self.operations, self.closes = [], [], []
        secret, client = self.owner._resolve_credential, fabric_inference_client.FabricInferenceClient
        original_close, original_begin = client.close, self.shared.begin_operation

        def read_secret(*args, **kwargs):
            self.events.append("credential")
            return secret(*args, **kwargs)

        def new_client(**kwargs):
            self.events.append("client")
            return client(**kwargs)

        def close(bound):
            self.closes.append(bound.operation_id)
            return original_close(bound)

        def begin(*args, **kwargs):
            operation = original_begin(*args, **kwargs)
            self.operations.append((operation, tuple(operation.providers)))
            return operation

        self.start(patch.object(self.owner, "_resolve_credential", read_secret))
        self.start(patch.object(fabric_inference_client, "FabricInferenceClient", new_client))
        self.start(patch.object(client, "close", close))
        self.start(patch.object(self.shared, "begin_operation", begin))
        self.native.on_upstream = self.answer

    def save(self):
        import yaml
        self.config_paths[0].write_text(json.dumps(self.document))
        self.config_paths[2].write_text(yaml.safe_dump(self.manifest))

    def answer(self):
        prompt = json.loads(self.native.posts[-1][1])["messages"][-1]["content"]
        text = (json.dumps({key: "译：" + value for key, value in json.loads(prompt.split("Input:\n", 1)[1]).items()},
                           ensure_ascii=False) if "Input:\n" in prompt else "译文")
        self.native.response = {"model": MODEL, "choices": [{"index": 0,
            "message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7}}

    def state(self):
        return json.loads(translate._CACHE_PATH.read_text())

    def costs(self):
        return [json.loads(line) for path in (self.root / "costs").rglob("*.jsonl")
                for line in path.read_text().splitlines()]

    def assert_closed(self, count):
        self.assertEqual(len(self.operations), count)
        self.assertEqual(len(self.closes), count)
        self.assertTrue(all(operation.providers == [] for operation, _ in self.operations))
        self.assertTrue(all(provider[0]["_fabric_closed"] for _, provider in self.operations))

    def test_actual_public_batch_and_warm_reuse(self):
        self.assertTrue(translate.translation_ready())
        self.assertEqual(self.events, [])
        result = translate.translate_and_cache([" first ", "second", "first"])
        self.assertEqual(result, {"first": "译：first", "second": "译：second"})
        self.assertEqual(len(self.native.posts), 1)
        self.assert_closed(1)
        self.assertEqual(self.events, ["credential", "client"])
        receipt = next(iter(self.state()["operations"].values()))
        self.assertEqual(receipt["state"], "completed")
        self.assertEqual(receipt["steps"][0]["observation"]["serving_model"], MODEL)
        self.assertEqual(receipt["usage"]["input_tokens"], 11)
        self.assertTrue(receipt["close"]["closed"])
        costs = self.costs()
        self.assertEqual(len(costs), 1)
        self.assertEqual((costs[0]["lane"], costs[0]["stage"], costs[0]["model"]),
                         ("mastermind-text", "translation", MODEL))
        self.assertEqual(self.native.rows("application_turns")[0]["workload"], "site_batch")
        with patch.object(translate, "_fabric_selected", side_effect=AssertionError("cache selection")):
            self.assertEqual(translate._call_haiku(["first"]), {"first": "译：first"})
            self.assertEqual(translate._call_haiku_direct("first"), "译：first")
            self.assertEqual(translate._translate_long("first"), "译：first")
            self.assertEqual(len(translate._load_cache()), 2)
        self.assertEqual(len(self.native.posts), len(self.costs()))
        self.assertEqual(len(self.costs()), 1)

    def test_six_item_chunks_are_separate_original_operations(self):
        result = translate.translate_and_cache(["text" + str(i) for i in range(7)])
        self.assertEqual(len(result), 7)
        self.assertEqual(len(self.native.posts), 2)
        self.assert_closed(2)
        self.assertEqual(len(set(self.closes)), 2)
        self.assertEqual(sorted(len(row["inputs"]) for row in self.state()["operations"].values()), [1, 6])

    def test_malformed_provenance_steps_usage_close_or_blank_success_refuses_mutation(self):
        self.assertEqual(translate._call_haiku(["original"]), {"original": "译：original"})
        original = self.state()
        op_id = next(iter(original["operations"]))
        changes = [
            lambda state: state["operations"][op_id]["identity"].update(model=[]),
            lambda state: state["operations"][op_id].update(steps=[None]),
            lambda state: state["operations"][op_id]["usage"].update(input_tokens=False),
            lambda state: state["operations"][op_id]["close"].update(closed="yes"),
            lambda state: state["translations"].update(original="   "),
        ]
        for change in changes:
            state = copy.deepcopy(original)
            change(state)
            raw = json.dumps(state).encode()
            with self.assertRaises((ValueError, TypeError)):
                translate._decode_state(raw)
            translate._CACHE_PATH.write_bytes(raw)
            self.assertEqual(translate._call_haiku(["another"]), {})
            self.assertEqual(translate._CACHE_PATH.read_bytes(), raw)
        self.assertEqual(len(self.native.posts), 1)

    def test_native_readiness_selection_change_prevents_native_dispatch(self):
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE", None)
        os.environ["BOT_LLM_BACKEND"] = "cli"
        def changed():
            os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
            return True
        with patch.object(self.bridge, "available", changed):
            self.assertEqual(translate._call_haiku(["new"]), {})
        self.assertEqual(self.events, [])
        self.assertEqual(self.native.posts, [])

    def test_native_before_start_guard_and_next_segment_recheck(self):
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE", None)
        os.environ["BOT_LLM_BACKEND"] = "cli"
        attempted = []
        def changed(prompt, **kwargs):
            attempted.append(prompt)
            os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
            kwargs["before_provider_start"]()
            raise AssertionError("provider must not start")
        with patch.object(self.bridge, "available", return_value=True), \
                patch.object(self.bridge, "reason_sync", changed):
            self.assertEqual(translate._call_haiku(["start-boundary"]), {})
        self.assertEqual(len(attempted), 1)
        os.environ.pop("MM_PROVIDER_APPLICATION_MODE", None)
        def first_only(prompt, **kwargs):
            kwargs["before_provider_start"]()
            attempted.append(prompt)
            os.environ["MM_PROVIDER_APPLICATION_MODE"] = "shared_fabric"
            return {"text": "第一段"}
        text = "A" * 700 + "\n\n" + "B" * 700
        with patch.object(self.bridge, "available", return_value=True), \
                patch.object(self.bridge, "reason_sync", first_only):
            self.assertIsNone(translate._translate_long(text))
        self.assertEqual(len(attempted), 2)
        self.assertEqual(self.native.posts, [])
        self.assertFalse(translate._CACHE_PATH.exists())

    def test_long_document_uses_one_operation_and_deliberate_steps(self):
        text = "\n\n".join(letter * 700 for letter in "ABC")
        self.assertEqual(translate.translate_and_cache([text]), {text: "译文\n\n译文\n\n译文"})
        self.assertEqual(len(self.native.posts), 3)
        self.assert_closed(1)
        rows = self.native.rows("application_requests")
        self.assertEqual(len({row["turn_id"] for row in rows}), 1)
        self.assertEqual([row["request_id"] for row in rows],
                         [self.closes[0] + ":brain:" + str(i) for i in range(3)])
        self.assertEqual(len(self.costs()), 3)
        receipt = next(iter(self.state()["operations"].values()))
        self.assertEqual(receipt["inputs"], [text])
        self.assertEqual(receipt["usage"]["input_tokens"], 33)
        self.assertEqual([row["state"] for row in receipt["steps"]], ["complete"] * 3)

    def test_long_second_segment_failure_does_not_send_third_or_publish_partial(self):
        def answer():
            self.answer()
            if len(self.native.posts) == 2:
                self.native.response["choices"][0]["finish_reason"] = "length"
        self.native.on_upstream = answer
        text = "\n\n".join(letter * 700 for letter in "ABC")
        self.assertEqual(translate.translate_and_cache([text]), {text: text})
        self.assertEqual(len(self.native.posts), 2)
        self.assertNotIn(text, self.state()["translations"])
        self.assert_closed(1)
        receipt = next(iter(self.state()["operations"].values()))
        self.assertEqual(len(receipt["steps"]), 2)
        self.assertEqual(receipt["usage"]["input_tokens"], 22)
        self.assertEqual(len(self.costs()), 2)
        self.assertIsNone(translate._translate_long(text))
        self.assertEqual(len(self.native.posts), 2)

    def test_actual_runner_uses_selected_fabric_and_completed_projection_count(self):
        path = Path(__file__).resolve().parents[2] / "scripts/translate_all.py"
        spec = importlib.util.spec_from_file_location("_translation_runner", path)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        portfolio = self.root / "data/portfolio/latest.json"
        portfolio.parent.mkdir(parents=True)
        portfolio.write_text(json.dumps({"disclaimer": "Existing portfolio context"}))
        with patch.object(runner, "_ROOT", self.root), redirect_stdout(io.StringIO()) as output:
            runner.main()
        self.assertIn("Cache: 0 -> 1 entries (+1 new)", output.getvalue())
        self.assertEqual(len(self.native.posts), 1)
        self.assert_closed(1)

    def test_all_direct_entries_obey_invalid_selected_mode_before_native_readiness(self):
        for mode in ("", "missing", "SHARED_FABRIC"):
            with self.subTest(mode=mode), patch.dict(os.environ, {"MM_PROVIDER_APPLICATION_MODE": mode}):
                self.assertFalse(translate.translation_ready())
                self.assertEqual(translate._call_haiku(["short"]), {})
                self.assertIsNone(translate._call_haiku_direct("direct"))
                self.assertIsNone(translate._translate_long("long"))
        self.assertEqual(self.events, [])
        self.assertEqual(self.native.posts, [])
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "fabric"}):
            os.environ.pop("MM_PROVIDER_APPLICATION_MODE", None)
            self.assertFalse(translate.translation_ready())
            self.assertEqual(translate._call_haiku(["short"]), {})
        self.assertEqual(self.events, [])

    def test_unknown_or_metered_basis_and_invalid_policy_refuse_before_credentials(self):
        for basis in ("unknown", "metered", "local"):
            with self.subTest(basis=basis):
                changed = replace(self.synthetic, cost_basis=basis)
                self.owner._APPLICATION_FABRIC_TRANSPORTS["translation_fixture_v1"] = changed
                self.mode["cost_basis"] = basis
                self.save()
                self.assertFalse(translate.translation_ready())
                self.assertEqual(translate._call_haiku(["short"]), {})
        self.owner._APPLICATION_FABRIC_TRANSPORTS["translation_fixture_v1"] = self.synthetic
        self.mode["cost_basis"] = "subscription"
        self.save()
        with patch.dict(os.environ, {"MM_PROVIDER_WORKLOAD_PROFILE": "development_agent"}):
            self.assertFalse(translate.translation_ready())
            self.assertEqual(translate._call_haiku(["short"]), {})
        self.assertEqual(self.events, [])
        self.assertFalse(translate._CACHE_PATH.exists())

    def test_valid_identity_change_between_inspection_and_binding_refuses_before_credentials(self):
        persist = translate._persist_state
        def changed(state):
            persist(state)
            replacement = replace(self.synthetic, model="other-model")
            self.owner._APPLICATION_FABRIC_TRANSPORTS["translation_fixture_v1"] = replacement
            self.mode["model"] = "other-model"
            self.save()
        with patch.object(translate, "_persist_state", changed):
            self.assertEqual(translate._call_haiku(["original"]), {})
        self.assertEqual(self.events, [])
        self.assertEqual(self.native.posts, [])
        self.assertEqual(next(iter(self.state()["operations"].values()))["identity"]["model"], MODEL)

    def test_bad_complete_outputs_are_held_without_repair_or_fallback(self):
        for kind in ("bad_json", "number", "empty", "tools", "refusal", "truncated", "http", "mismatch"):
            with self.subTest(kind=kind):
                def answer():
                    self.answer()
                    response = self.native.response
                    choice = response["choices"][0]
                    if kind == "bad_json": choice["message"]["content"] = "broken"
                    if kind == "number": choice["message"]["content"] = '{"0":3}'
                    if kind == "empty": choice["message"]["content"] = ""
                    if kind == "tools":
                        choice["message"] = {"role": "assistant", "content": "ignore", "tool_calls": [
                            {"id": "read-1", "type": "function", "function": {"name": "read", "arguments": "{}"}}]}
                        choice["finish_reason"] = "tool_calls"
                    if kind == "refusal": choice["finish_reason"] = "content_filter"
                    if kind == "truncated": choice["finish_reason"] = "length"
                    if kind == "mismatch": response["model"] = "other-model"
                    self.native.response_status = 503 if kind == "http" else 200
                self.native.on_upstream = answer
                before = len(self.native.posts)
                self.assertEqual(translate._call_haiku([kind]), {})
                self.assertEqual(translate._call_haiku([kind]), {})
                self.assertEqual(len(self.native.posts), before + 1)
                self.assertNotIn(kind, self.state()["translations"])
        self.assert_closed(8)
        self.assertEqual(len(self.costs()), 8)
        mismatch = next(row for row in self.state()["operations"].values() if row["inputs"] == ["mismatch"])
        self.assertEqual(mismatch["identity"]["model"], MODEL)
        self.assertEqual(mismatch["steps"][0]["observation"]["serving_model"], "other-model")

    def test_unknown_native_settlement_keeps_usage_subtotal_and_original_input_hold(self):
        with patch.object(self.native.gateway, "complete_application", side_effect=OSError("fixture commit loss")):
            self.assertEqual(translate._call_haiku([" original "]), {})
        row = next(iter(self.state()["operations"].values()))
        self.assertEqual(row["state"], "unknown")
        self.assertIsNone(row["usage"]["input_tokens"])
        self.assertEqual(row["usage"]["completed_input_tokens"], 11)
        self.assertFalse(row["close"]["closed"])
        self.assertEqual(len(self.costs()), 1)
        self.assertIn(self.native.rows("leases")[0]["state"], {"held", "rented"})
        with patch.dict(os.environ, {"BOT_LLM_BACKEND": "cli"}):
            os.environ.pop("MM_PROVIDER_APPLICATION_MODE", None)
            self.assertEqual(translate._call_haiku(["original"]), {})
            self.assertIsNone(translate._call_haiku_direct(" original "))
            self.assertIsNone(translate._translate_long("original"))
            translate._save_cache({"original": "must not overwrite hold", "other": "其他"})
        self.assertNotIn("original", self.state()["translations"])
        self.assertEqual(self.state()["translations"]["other"], "其他")
        self.assertEqual(len(self.native.posts), 1)

    def test_incomplete_usage_is_not_fabricated_zero(self):
        def answer():
            self.answer()
            self.native.response["usage"]["prompt_tokens"] = None
        self.native.on_upstream = answer
        self.assertEqual(translate._call_haiku(["usage"]), {"usage": "译：usage"})
        self.assertEqual(self.costs(), [])
        usage = next(iter(self.state()["operations"].values()))["usage"]
        self.assertIsNone(usage["input_tokens"])
        self.assertEqual(usage["usage_state"], "unknown")

    def test_pre_send_file_fsync_and_replace_failures_send_nothing(self):
        for owner, attribute in ((translate.os, "fsync"), (translate.os, "replace")):
            with self.subTest(attribute=attribute), patch.object(owner, attribute, side_effect=OSError("fixture persistence")):
                self.assertEqual(translate._call_haiku([attribute]), {})
        self.assertEqual(self.events, [])
        self.assertEqual(self.native.posts, [])
        self.assertEqual(self.costs(), [])

    def test_first_use_syncs_every_new_directory_link_before_provider_bytes(self):
        original_open, original_sync = os.open, os.fsync
        descriptors, synced = {}, set()
        def opening(path, flags, *args, **kwargs):
            fd = original_open(path, flags, *args, **kwargs)
            descriptors[fd] = Path(path).resolve()
            return fd
        def syncing(fd):
            original_sync(fd)
            if fd in descriptors:
                synced.add(descriptors[fd])
        expected = {path.resolve() for path in (self.root, self.root / "data", self.root / "data/brain")}
        def answer():
            self.assertTrue(expected <= synced, "new directory links unconfirmed before dispatch")
            self.answer()
        self.native.on_upstream = answer
        with patch.object(os, "open", opening), patch.object(os, "fsync", syncing):
            self.assertEqual(translate._call_haiku(["first-use"]), {"first-use": "译：first-use"})
        self.assertEqual(len(self.native.posts), 1)

    def test_directory_sync_failure_after_replace_still_precedes_binding(self):
        import stat
        original = os.fsync
        def syncing(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):
                raise OSError("fixture directory persistence")
            return original(fd)
        with patch.object(os, "fsync", syncing):
            self.assertEqual(translate._call_haiku(["directory"]), {})
        self.assertEqual(self.events, [])
        self.assertEqual(self.native.posts, [])
        self.assertEqual(next(iter(self.state()["operations"].values()))["state"], "pending")

    def test_unreadable_state_and_unconfirmed_claim_readback_send_nothing(self):
        translate._CACHE_PATH.parent.mkdir(parents=True)
        translate._CACHE_PATH.write_text("{}")
        original = Path.open
        def unreadable(path, *args, **kwargs):
            if path == translate._CACHE_PATH:
                raise OSError("fixture unreadable")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", unreadable):
            self.assertEqual(translate._call_haiku(["read"]), {})
        calls = [0]
        def bad_readback(path, *args, **kwargs):
            if path == translate._CACHE_PATH and args and args[0] == "rb":
                calls[0] += 1
                if calls[0] == 2:
                    return io.BytesIO(b"unconfirmed")
            return original(path, *args, **kwargs)
        with patch.object(Path, "open", bad_readback):
            self.assertEqual(translate._call_haiku(["readback"]), {})
        self.assertEqual(self.events, [])
        self.assertEqual(self.native.posts, [])
        self.assertEqual(next(iter(self.state()["operations"].values()))["state"], "pending")
        self.assertEqual(translate._call_haiku(["readback"]), {})

    def test_post_send_store_failure_survives_restarted_process_and_regrouping(self):
        persist = translate._persist_state
        writes = [0]
        def fail_final(state):
            writes[0] += 1
            if writes[0] == 2:
                raise OSError("fixture final commit failure")
            persist(state)
        with patch.object(translate, "_persist_state", fail_final):
            self.assertEqual(translate._call_haiku(["first", "second"]), {})
        self.assertEqual(next(iter(self.state()["operations"].values()))["state"], "pending")
        self.assertEqual(len(self.native.posts), 1)
        # A fresh interpreter uses the actual file/lock with Fabric removed.
        import subprocess
        code = (
            "from pathlib import Path\nfrom brain import translate, cli_bridge\n"
            f"translate._ROOT=Path({str(self.root)!r})\ntranslate._CACHE_PATH=Path({str(translate._CACHE_PATH)!r})\n"
            "def forbidden(*a,**k): raise AssertionError('native dispatch')\n"
            "cli_bridge.available=forbidden\ncli_bridge.reason_sync=forbidden\n"
            "assert translate._call_haiku([' second ', 'first']) == {}\n"
            "translate._save_cache({'other':'其他'})\n"
            "assert len(translate._read_state()['operations']) == 1\n")
        environment = dict(os.environ, BOT_LLM_BACKEND="cli",
                           PYTHONPATH=str(Path(__file__).resolve().parents[2]))
        environment.pop("MM_PROVIDER_APPLICATION_MODE", None)
        result = subprocess.run([sys.executable, "-c", code], env=environment,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.state()["operations"]), 1)
        self.assertEqual(self.state()["translations"], {"other": "其他"})

    def test_two_real_os_processes_racing_missing_input_send_once(self):
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        self.addCleanup(queue.close)
        release = threading.Event()
        def blocked_answer():
            self.answer()
            if not release.wait(10):
                raise AssertionError("race fixture provider was not released")
        self.native.on_upstream = blocked_answer
        args = (str(self.root), str(self.macro_root), asdict(self.synthetic), queue)
        first = context.Process(target=_translation_race_process, args=args)
        second = context.Process(target=_translation_race_process, args=args)
        children = [first, second]
        def cleanup():
            release.set()
            for process in children:
                if process.pid is not None:
                    process.join(5)
                    if process.is_alive():
                        process.terminate()
                        process.join(2)
        self.addCleanup(cleanup)
        first.start()
        self.assertTrue(self.native.arrived.wait(5), "first original never reached loopback provider")
        second.start()
        second.join(5)
        self.assertFalse(second.is_alive(), "contender must not wait on the cache owner")
        release.set()
        first.join(5)
        self.assertEqual((first.exitcode, second.exitcode), (0, 0))
        answers = [queue.get(timeout=2), queue.get(timeout=2)]
        self.assertIn({"same input": "译：same input"}, answers)
        self.assertEqual(len(self.native.posts), 1)
        self.assertEqual(len(self.native.rows("application_turns")), 1)
        self.assertEqual(len(self.costs()), 1)
        self.assertEqual(translate.cached_zh("same input"), "译：same input")
