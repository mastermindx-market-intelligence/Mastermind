"""Real sealed synthetic Tailnet two-seat fixtures on the actual supplied source.

Baseline classes execute against private_service as supplied: they prove the
exact argv-only refusal of the unchanged private verifier on fully sealed
Tailnet seats and that generic stage/upgrade stays refused. Selector classes
exercise the parent's future owner composition and fail RED with
FUTURE_API_MISSING until implemented. No skips. Only the launchctl subprocess
boundary and the native successor context are mocked; every seat byte,
descriptor hash and verifier is the real temp fixture.
"""

import hashlib, io, json, os, plistlib, sys, tempfile, unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import private_service as svc

TAILNET_ACCOUNTS = ("fabric-design", "fabric-read")
CONTROL_ACCOUNT = "admin-business"
TAILNET_GATEWAY = "tailnet-gateway.mjs"
FUTURE_API = ("_NATIVE_POOL_PIN_TAILNET_CANONICAL", "_native_pin_manifest_valid", "_verify_native_pin_install")
# Supplied public pin contract: exact canonical old/post selector pins.
TAILNET_PIN_SUPPLIED_CANONICAL = {
    "fabric-design": ("87de91f4fd0d51571c2350cf4fe53704ad035eba8f095c13b09352732307671c",
                      "b08c021b6c3c9cd9a1acdd57957fbf5e88b6d63daa11b963b7476d993b1a8b46"),
    "fabric-read": ("f39e118cb770d4f793dd92c31e9f17f7153e7daef4e9703be7408fde702d40bb",
                    "328c25399daf9ab16c994ea30bd4a628ef40483e5f9af89fe34f191ac4f48819"),
}
SEAT_PORT = {"fabric-design": 45118, "fabric-read": 45117, CONTROL_ACCOUNT: 45119}
SEAT_MODULE_NAMES = {a: tuple(sorted(svc.NATIVE_POOL_PIN_PREDECESSORS[a]))
                     for a in (CONTROL_ACCOUNT, *TAILNET_ACCOUNTS)}


def synthetic_seat(home, account):
    """Build one real fully sealed temp seat with synthetic Tailnet identity bytes."""
    roots = svc._build_runtime_roots(account)
    for path in (roots["base"], roots["state"], roots["logs"]):
        svc._ensure_secure_dir(path)
    files = {}
    for name in SEAT_MODULE_NAMES[account]:
        path = roots["base"] / name
        svc._atomic_write_bytes(path, b"// synthetic seat module %s %s\n" % (account.encode(), name.encode()))
        files[name] = svc._sha256_file(path)
    node = home / ("node-" + account)
    svc._atomic_write_bytes(node, b"#!/bin/sh\nexec true  # synthetic node\n"); node.chmod(0o700)
    backend = home / ("backend-%s.mjs" % account)
    svc._atomic_write_bytes(backend, b"// synthetic backend %s\n" % account.encode())
    deps = roots["node_modules"] / "fixture-dep"
    deps.mkdir(parents=True); (deps / "index.js").write_bytes(b"module.exports = {};  // synthetic\n")
    pool = home / "native-pool.bin"; pool.write_bytes(b"current-native-pool-bridge")
    label = "com.mastermind.studio-direct-private." + account
    gateway = TAILNET_GATEWAY if account in TAILNET_ACCOUNTS else svc.PRIVATE_GATEWAY_NAME
    config = {
        "accountLabel": account, "host": "127.0.0.1", "testMode": False,
        "port": SEAT_PORT[account], "command": str(node),
        "args": [str(backend), "--no-onboarding"], "cwd": str(home),
        "childEnv": {"NODE_OPTIONS": ""}, "stateDir": str(roots["state"]),
        "maxSessions": svc.MAX_SESSIONS,
        "tailnetGateway": {"enabled": True, "module": gateway},
        "opaque_existing_capability": {"args": ["PRIVATE-CANARY"], "enabled": True},
        "fleetStatus": {
            "enabled": True, "launcherPath": str(home / "studio-direct"),
            "launcherSha256": "a" * 64, "timeoutMs": 15000,
            "fabricLauncherPath": str(pool), "fabricLauncherSha256": "9" * 64,
            "fabricTimeoutMs": 8000,
        },
    }
    svc._atomic_write_bytes(roots["config"], svc._fabric_release_json(config))
    roots["plist"].parent.mkdir(parents=True, exist_ok=True)
    argv = [str(node), str(roots["base"] / gateway), str(roots["config"])]
    svc._write_plist(roots["plist"], {
        "Label": label, "ProgramArguments": argv,
        "EnvironmentVariables": {"NODE_OPTIONS": "", "HOME": str(home)},
        "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": str(roots["logs"] / "out.log"),
        "StandardErrorPath": str(roots["logs"] / "err.log")})
    manifest = {
        "version": svc.MANIFEST_VERSION, "account": account, "label": label,
        "files": files, "source": str(home / ("source-" + account)),
        "node": str(node), "backend": str(backend),
        "nodeHash": svc._stable_regular_file_hash(node, label="node"),
        "backendHash": svc._stable_regular_file_hash(backend, label="backend"),
        "dependencyTreeHash": svc._dependency_tree_hash(roots["node_modules"]),
        "host": "127.0.0.1", "port": SEAT_PORT[account],
        "configHash": svc._sha256_file(roots["config"]),
        "plistHash": svc._sha256_file(roots["plist"])}
    svc._atomic_write_text(roots["manifest"], json.dumps(manifest, indent=2, sort_keys=True))
    post_bridge = hashlib.sha256(b"future-native-pool-bridge").hexdigest()
    post_config = json.loads(json.dumps(config))
    post_config["fleetStatus"]["fabricLauncherSha256"] = post_bridge
    post_config_bytes = svc._fabric_release_json(post_config)
    post_manifest = dict(manifest, configHash=hashlib.sha256(post_config_bytes).hexdigest())
    return SimpleNamespace(
        account=account, label=label, roots=roots, manifest=manifest, argv=argv,
        gateway=gateway, pool=pool, post_bridge=post_bridge,
        post_config_bytes=post_config_bytes, post_manifest=post_manifest,
        canonical=svc._canonical_json_sha256(manifest),
        post_canonical=svc._canonical_json_sha256(post_manifest), node=node, backend=backend)


class TailnetFixtureBase(unittest.TestCase):
    """Two real sealed Tailnet seats plus one sealed generic control seat."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve() / "home"
        self.home.mkdir(mode=0o700)
        patch = mock.patch.object(svc, "_user_root", return_value=self.home)
        patch.start(); self.addCleanup(patch.stop)
        self.seats, self.predecessors = {}, {}
        for account in (CONTROL_ACCOUNT, *TAILNET_ACCOUNTS):
            seat = synthetic_seat(self.home, account)
            self.seats[account] = seat
            self.predecessors[account] = dict(seat.manifest["files"])
        patch = mock.patch.object(svc, "NATIVE_POOL_PIN_PREDECESSORS", self.predecessors)
        patch.start(); self.addCleanup(patch.stop)
        self.canonical_map = {
            a: frozenset((self.seats[a].canonical, self.seats[a].post_canonical))
            for a in TAILNET_ACCOUNTS}

    def seat_bytes(self, seat):
        observed = {p: p.read_bytes() for p in sorted(seat.roots["base"].rglob("*")) if p.is_file()}
        observed[seat.roots["plist"]] = seat.roots["plist"].read_bytes()
        observed[seat.node] = seat.node.read_bytes(); observed[seat.backend] = seat.backend.read_bytes()
        return observed

    def restore(self, seat, before):
        for path, data in before.items():
            if path.read_bytes() != data: path.write_bytes(data)
        self.assertEqual(self.seat_bytes(seat), before)


class TailnetBaselineDiscriminatorTests(TailnetFixtureBase):
    def test_sealed_tailnet_fixture_preserves_every_descriptor(self):
        for account in TAILNET_ACCOUNTS:
            with self.subTest(account=account):
                seat = self.seats[account]
                manifest = json.loads(seat.roots["manifest"].read_text())
                self.assertEqual(manifest, seat.manifest)
                for name, digest in manifest["files"].items():
                    self.assertEqual(svc._sha256_file(seat.roots["base"] / name), digest)
                self.assertEqual(svc._sha256_file(seat.roots["config"]), manifest["configHash"])
                self.assertEqual(svc._sha256_file(seat.roots["plist"]), manifest["plistHash"])
                self.assertEqual(svc._stable_regular_file_hash(seat.node, label="node"), manifest["nodeHash"])
                self.assertEqual(svc._stable_regular_file_hash(seat.backend, label="backend"), manifest["backendHash"])
                self.assertEqual(svc._dependency_tree_hash(seat.roots["node_modules"]), manifest["dependencyTreeHash"])
                plist = plistlib.loads(seat.roots["plist"].read_bytes())
                self.assertEqual(plist["Label"], seat.label)
                self.assertEqual(list(plist["ProgramArguments"]), seat.argv)
                config = json.loads(seat.roots["config"].read_bytes())
                self.assertEqual(config["opaque_existing_capability"], {"args": ["PRIVATE-CANARY"], "enabled": True})
                self.assertEqual(config["fleetStatus"]["fabricLauncherPath"], str(seat.pool))
                self.assertTrue(svc._valid_manifest(manifest, seat.account, seat.label))

    def test_baseline_private_verifier_refuses_exact_tailnet_argv_only(self):
        for account in TAILNET_ACCOUNTS:
            with self.subTest(account=account):
                seat = self.seats[account]
                expected = svc._expected_argv(seat.node, seat.roots["gateway"], seat.roots["config"])
                actual = plistlib.loads(seat.roots["plist"].read_bytes())["ProgramArguments"]
                self.assertEqual(actual[0], expected[0]); self.assertEqual(actual[2], expected[2])
                self.assertEqual(expected[1], str(seat.roots["gateway"]))
                self.assertEqual(Path(expected[1]).name, svc.PRIVATE_GATEWAY_NAME)
                self.assertNotEqual(actual[1], expected[1]); self.assertEqual(Path(actual[1]).name, TAILNET_GATEWAY)
                before = self.seat_bytes(seat)
                with self.assertRaises(SystemExit) as caught:
                    svc._verify_staged_install(seat.account, seat.label, seat.roots)
                self.assertEqual(str(caught.exception), "plist is not our exact install")
                self.assertEqual(self.seat_bytes(seat), before)

    def test_baseline_verifier_accepts_sealed_generic_control_seat(self):
        seat = self.seats[CONTROL_ACCOUNT]
        self.assertEqual(Path(seat.argv[1]).name, svc.PRIVATE_GATEWAY_NAME)
        self.assertEqual(svc._verify_staged_install(seat.account, seat.label, seat.roots), seat.manifest)

    def test_generic_stage_and_upgrade_stay_refused_for_tailnet_accounts(self):
        for account, with_marker in (("fabric-design", False), ("fabric-read", True)):
            with self.subTest(account=account, pin_marker=with_marker):
                if with_marker: (self.seats[account].roots["state"] / "native-pool-pin").mkdir()
                for operation in (svc.cmd_stage, svc.cmd_upgrade):
                    with self.assertRaises(SystemExit) as caught:
                        operation(SimpleNamespace(account=account))
                    self.assertEqual(str(caught.exception), "NATIVE_POOL_PIN_PROFILE_REQUIRES_PIN_OWNER")

    def test_predecessor_identity_has_no_account_or_digest_wildcard(self):
        for account in (CONTROL_ACCOUNT, *TAILNET_ACCOUNTS):
            with self.subTest(account=account):
                seat = self.seats[account]
                manifest = dict(seat.manifest)
                self.assertTrue(svc._valid_manifest(manifest, account, seat.label))
                name = sorted(manifest["files"])[0]
                tampered = dict(manifest, files={**manifest["files"], name: "0" * 64})
                self.assertFalse(svc._valid_manifest(tampered, account, seat.label))
                self.assertFalse(svc._valid_manifest(manifest, "unknown-seat", "com.mastermind.studio-direct-private.unknown-seat"))


class TailnetControlPinStartFenceTests(TailnetFixtureBase):
    """Existing pin-owner boundary: an unselected future pin refuses start."""

    def setUp(self):
        super().setUp()
        self.account = CONTROL_ACCOUNT; self.seat = self.seats[self.account]
        self.loaded = False; self.calls = []

        def run(argv, **kwargs):
            self.calls.append(list(argv))
            if argv[:2] == ["launchctl", "print"]:
                if self.loaded:
                    return svc.CmdResult(0, '%s = {\n\tpath = %s\n\tstate = running\n\tpid = 1234\n}\n' % (
                        svc._launchd_target(self.seat.label), self.seat.roots["plist"]), "")
                return svc.CmdResult(113, "", 'Bad request.\nCould not find service "%s" in domain '
                                     'for user gui: %s\n' % (self.seat.label, os.getuid()))
            if argv[:2] == ["launchctl", "bootstrap"]:
                self.loaded = True
                return svc.CmdResult(0, "", "")
            raise AssertionError("unexpected external launchctl effect")

        patch = mock.patch.object(svc, "_run", run)
        patch.start(); self.addCleanup(patch.stop)
        self.binding = {
            "successor_digest": "1" * 64, "target_generation": "2" * 64,
            "expected_selection": {"generation": "3" * 64, "sequence": 23},
            "pool_target": str(self.seat.pool),
            "pool_previous": svc._sha256_file(self.seat.pool),
            "pool_bridge": hashlib.sha256(b"future-native-pool-bridge").hexdigest(),
            "phase": "PREVIOUS"}

        @contextmanager
        def native(*args, **kwargs):
            yield self.binding
        self.native = native
        self.args = SimpleNamespace(
            account=self.account, expected_manifest_sha256=svc._sha256_file(self.seat.roots["manifest"]),
            successor_bundle=str(self.home / "successor"), successor_plan_sha256="1" * 64,
            expected_plan_sha256=None, operation="preview")

    def capture(self, fn):
        out = io.StringIO()
        with redirect_stdout(out):
            rc = fn()
        self.assertEqual(rc, 0)
        return json.loads(out.getvalue())

    def invoke(self):
        with mock.patch.object(svc, "_pin_native_context", self.native):
            return self.capture(lambda: svc.cmd_native_pool_pin(self.args))

    def test_future_pin_start_refuses_until_bridge_is_selected(self):
        plan = self.invoke()
        self.args.expected_plan_sha256 = plan["planSha256"]
        self.args.operation = "apply"
        self.assertEqual(self.invoke()["effect"], "APPLIED")
        self.assertEqual(json.loads(self.seat.roots["config"].read_bytes())["fleetStatus"]["fabricLauncherSha256"],
                         self.binding["pool_bridge"])
        with mock.patch.object(svc, "_pin_native_context", self.native):
            with self.assertRaises(SystemExit) as caught:
                self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))
            self.assertEqual(str(caught.exception), "NATIVE_POOL_PIN_FUTURE_PIN_NOT_READY")
            self.assertFalse(self.loaded); self.assertFalse(any(x[:2] == ["launchctl", "bootstrap"] for x in self.calls))
            self.seat.pool.write_bytes(b"future-native-pool-bridge"); self.binding["phase"] = "SELECTED"
            self.capture(lambda: svc.cmd_start(SimpleNamespace(account=self.account)))
        self.assertTrue(self.loaded)


class TailnetFutureSelectorTests(TailnetFixtureBase):
    """Expected RED until the parent implements the strict Tailnet owner."""

    def future_api(self, fixture_map=False):
        missing = [name for name in FUTURE_API if not hasattr(svc, name)]
        if missing:
            self.fail("FUTURE_API_MISSING: parent has not implemented " + ",".join(missing))
        if fixture_map:
            patch = mock.patch.object(svc, "_NATIVE_POOL_PIN_TAILNET_CANONICAL", self.canonical_map)
            patch.start(); self.addCleanup(patch.stop)

    def strict(self, account, **kwargs):
        seat = self.seats[account]
        return svc._verify_native_pin_install(seat.account, seat.label, seat.roots, **kwargs)

    def test_selector_pins_exactly_the_two_supplied_tailnet_accounts(self):
        self.future_api()
        supplied = {a: frozenset(pair) for a, pair in TAILNET_PIN_SUPPLIED_CANONICAL.items()}
        self.assertEqual({a: frozenset(v) for a, v in svc._NATIVE_POOL_PIN_TAILNET_CANONICAL.items()}, supplied)
        for account, (old, post) in TAILNET_PIN_SUPPLIED_CANONICAL.items():
            with self.subTest(account=account):
                self.assertNotEqual(old, post)
                self.assertTrue(all(map(svc._sha256_hex, (old, post))))
                self.assertIn(account, svc.NATIVE_POOL_PIN_ACCOUNTS)
        self.assertNotIn(CONTROL_ACCOUNT, svc._NATIVE_POOL_PIN_TAILNET_CANONICAL)

    def test_strict_owner_accepts_both_real_sealed_tailnet_argv_seats(self):
        self.future_api(fixture_map=True)
        for account in TAILNET_ACCOUNTS:
            with self.subTest(account=account):
                self.assertEqual(Path(self.seats[account].argv[1]).name, TAILNET_GATEWAY)
                self.assertEqual(self.strict(account), self.seats[account].manifest)
                self.assertEqual(self.strict(account, require_runtime_seal=False), self.seats[account].manifest)

    def test_private_control_keeps_unchanged_private_verifier(self):
        self.future_api(fixture_map=True)
        self.assertNotIn(CONTROL_ACCOUNT, svc._NATIVE_POOL_PIN_TAILNET_CANONICAL)
        seat = self.seats[CONTROL_ACCOUNT]
        self.assertEqual(svc._verify_native_pin_install(seat.account, seat.label, seat.roots), seat.manifest)
        before = self.seat_bytes(seat)
        payload = plistlib.loads(seat.roots["plist"].read_bytes())
        payload["ProgramArguments"][1] = str(seat.roots["base"] / "other-gateway.mjs")
        seat.roots["plist"].write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML))
        with self.assertRaises(SystemExit):
            self.strict(CONTROL_ACCOUNT)
        self.restore(seat, before)

    def test_tailnet_owner_requires_full_seal_even_when_not_requested(self):
        self.future_api(fixture_map=True)
        seat = self.seats["fabric-design"]
        (seat.roots["node_modules"] / "fixture-dep" / "drift.js").write_bytes(b"drift\n")
        before = self.seat_bytes(seat)
        with self.assertRaises(SystemExit):
            self.strict("fabric-design", require_runtime_seal=False)
        self.assertEqual(self.seat_bytes(seat), before)

    def test_selector_refuses_unselected_accounts_without_effects(self):
        self.future_api(fixture_map=True)
        seat = self.seats["fabric-read"]
        before = self.seat_bytes(seat)
        for account in ("fabric-operator", "chatgpt1", "unknown-seat"):
            with self.subTest(account=account):
                with self.assertRaises(SystemExit):
                    svc._verify_native_pin_install(account, "com.mastermind.studio-direct-private." + account, seat.roots)
        self.assertEqual(self.seat_bytes(seat), before)

    def test_pin_manifest_valid_requires_exact_map_and_canonical_membership(self):
        self.future_api(fixture_map=True)
        seat = self.seats["fabric-design"]
        manifest = seat.manifest
        self.assertTrue(svc._native_pin_manifest_valid(manifest, seat.account, seat.label))
        self.assertTrue(svc._native_pin_manifest_valid(seat.post_manifest, seat.account, seat.label))
        self.assertFalse(svc._native_pin_manifest_valid(manifest, "fabric-read", seat.label))
        name = sorted(manifest["files"])[0]
        cases = {
            "module_hash": dict(manifest, files={**manifest["files"], name: "0" * 64}),
            "extra_module": dict(manifest, files={**manifest["files"], "extra.mjs": "1" * 64}),
            "missing_module": dict(
                manifest, files={k: v for k, v in manifest["files"].items() if k != name}),
            "extra_field": dict(manifest, opaqueExtra=True),
            "unknown_canonical": dict(manifest, port=manifest["port"] + 1),
            "tampered_postimage": dict(manifest, configHash="0" * 64),
        }
        for case, value in cases.items():
            with self.subTest(case=case):
                self.assertFalse(svc._native_pin_manifest_valid(value, seat.account, seat.label))
        self.assertEqual(self.canonical_map["fabric-design"], frozenset((seat.canonical, seat.post_canonical)))

    def reseal_plist(self, seat, argv):
        payload = plistlib.loads(seat.roots["plist"].read_bytes())
        payload["ProgramArguments"] = argv
        seat.roots["plist"].write_bytes(plistlib.dumps(payload, fmt=plistlib.FMT_XML))
        manifest = dict(json.loads(seat.roots["manifest"].read_text()),
                        plistHash=svc._sha256_file(seat.roots["plist"]))
        seat.roots["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True))

    def reseal_config(self, seat, extra_field):
        config = json.loads(seat.roots["config"].read_bytes()); config[extra_field] = {"enabled": True}
        seat.roots["config"].write_bytes(svc._fabric_release_json(config))
        manifest = dict(json.loads(seat.roots["manifest"].read_text()),
                        configHash=svc._sha256_file(seat.roots["config"]))
        seat.roots["manifest"].write_text(json.dumps(manifest, indent=2, sort_keys=True))

    def test_tailnet_owner_refuses_each_single_component_drift(self):
        self.future_api(fixture_map=True)
        seat = self.seats["fabric-read"]
        module = sorted(seat.manifest["files"])[0]
        deps_index = seat.roots["node_modules"] / "fixture-dep" / "index.js"
        R = seat.roots
        cases = (
            ("module", (R["base"] / module,), lambda: (R["base"] / module).write_bytes(b"tampered\n")),
            ("config", (R["config"],), lambda: R["config"].write_bytes(b"{}\n")),
            ("plist", (R["plist"],), lambda: R["plist"].write_bytes(b"bogus")),
            ("argv_path", (R["plist"], R["manifest"]),
             lambda: self.reseal_plist(seat, [str(seat.node), str(R["base"] / "other.mjs"), str(R["config"])])),
            ("node", (seat.node,), lambda: seat.node.write_bytes(b"tampered-node\n")),
            ("backend", (seat.backend,), lambda: seat.backend.write_bytes(b"tampered-backend\n")),
            ("dependency", (deps_index,), lambda: deps_index.write_bytes(b"drift\n")),
            ("extra_config_field", (R["config"], R["manifest"]), lambda: self.reseal_config(seat, "opaqueExtra")),
        )
        for case, touched, mutate in cases:
            with self.subTest(case=case):
                before = self.seat_bytes(seat)
                mutate()
                with self.assertRaises(SystemExit):
                    self.strict("fabric-read")
                after = self.seat_bytes(seat)
                self.assertEqual({p for p in after if after[p] != before[p]}, set(touched))
                self.restore(seat, before)


if __name__ == "__main__":
    unittest.main()
