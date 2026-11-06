"""Compiler, owner-transaction and lineage regressions for the C1 fleet-gateway
Git-failure correction.

The exact historical predecessor is resolved from the qualified repository Git
object, never from a network fetch. A missing input fails the qualification; it
never skips a test and never triggers a runtime download. Every installed
fixture is synthetic and lives in a temporary directory: no credential, host,
repository, publisher or live service is touched.
"""
import copy
import fcntl
import hashlib
import io
import json
import os
import plistlib
import subprocess
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import fleet_git_failure_compat as compat
import private_service as svc
import private_service_pin as pin

PREIMAGE_GIT_BLOB = "f87ac012339e82fe46bce5ddc70d1d04183d1b6e"
PREIMAGE_SHA256 = "17157fa5f8739dbe17aae767a335e97dd713a978dde9b192feb1b41a7b036b30"
PREIMAGE_SIZE = 101068
SUCCESSOR_SHA256 = "336de8ed10e7da483d46e93bd98439fd00c3e277111b39b5baa9cf0e68074674"
SUCCESSOR_SIZE = 102141
SUCCESSOR_GIT_BLOB = "c02bcdada5217bbc987099e90ebdce236f023b86"
ACCOUNT = "chatgpt1"
PORT = 45018
RETAINED_SUCCESSOR_DIGEST = "77c2c136852a783a1e2572c145af7536ee6cd0d7f443daa4c09795c333fd3dc7"
RETAINED_TARGET_GENERATION = "28faaf101463bcabef578ab1acabdcd270e301c7ed9cedf294e82fd459ccfcce"
CURRENT_GENERATION = "9eec6f73903fabfdd6d15bfe6f815f652f0946b5838cef6d40e96ca5b7e7f185"
CURRENT_PREVIOUS = "b" * 64


def sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def git_blob_sha1(blob: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(blob)).encode("ascii") + b"\0" + blob).hexdigest()


def offline_blob(blob: str) -> bytes:
    """Read a retained object without inheriting any promisor remote.

    The canonical object directory is only an alternate of a temporary bare
    repository. Missing historical input is a qualification failure, never a
    lazy network fetch from a partial clone.
    """
    repo = Path(__file__).resolve().parents[2]
    common = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True, timeout=120, check=True).stdout.decode().strip()
    with tempfile.TemporaryDirectory(prefix="c1-offline-objects-") as temporary:
        store = Path(temporary) / "store.git"
        subprocess.run(["git", "init", "--bare", "-q", str(store)],
                       capture_output=True, timeout=120, check=True)
        env = dict(os.environ, GIT_DIR=str(store),
                   GIT_ALTERNATE_OBJECT_DIRECTORIES=str(Path(common) / "objects"),
                   GIT_TERMINAL_PROMPT="0")
        proc = subprocess.run(["git", "cat-file", "blob", blob], cwd=store,
                              env=env, capture_output=True, timeout=120, check=False)
    if proc.returncode != 0 or not proc.stdout:
        raise AssertionError(
            "the qualified fleet gateway Git object is unavailable; missing input "
            "fails qualification and is never skipped")
    return proc.stdout


def resolve_preimage() -> bytes:
    """The exact historical predecessor from the qualified offline Git store."""
    return offline_blob(PREIMAGE_GIT_BLOB)


@contextmanager
def isolated_home(account: str = ACCOUNT):
    with tempfile.TemporaryDirectory() as raw:
        home = Path(raw) / "home"
        home.mkdir(mode=0o700)
        (home / "Library" / "LaunchAgents").mkdir(parents=True, mode=0o700)
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            yield home, svc._build_runtime_roots(account)


def _launchd_run(state: str, plist: Path):
    """A launchctl print result that proves a stopped or a loaded service."""
    def run(cmd, check: bool = True, timeout: float = 30.0):
        if list(cmd[:2]) != ["launchctl", "print"]:
            raise AssertionError(f"unexpected command: {cmd!r}")
        target = cmd[2]
        label = target.rsplit("/", 1)[-1]
        if state == "stopped":
            absent = (f'Bad request.\nCould not find service "{label}" '
                      f'in domain for user gui: {os.getuid()}\n')
            return svc.CmdResult(113, "", absent)
        stdout = "\n".join([
            f"{target} = {{", f"\tpath = {plist}",
            "\tstate = running", "\tpid = 4242", "}",
        ]) + "\n"
        return svc.CmdResult(0, stdout, "")
    return run


def _write_pin_transaction(roots: dict, *, account: str = ACCOUNT,
                            config_before: bytes, config_after: bytes,
                            manifest_before: bytes, manifest_after: bytes,
                            result: dict | None = None) -> Path:
    """Write one synthetic retained native-pool pin transaction."""
    path = roots["state"] / "native-pool-pin"
    path.mkdir(parents=True, exist_ok=True)
    path.chmod(0o700)
    plan = {
        "schema": pin.SCHEMA, "account": account, "uid": os.getuid(),
        "config_before": sha(config_before), "config_after": sha(config_after),
        "manifest_before": sha(manifest_before),
        "manifest_after": sha(manifest_after),
        "config_mode": 0o600, "manifest_mode": 0o600,
    }
    plan_bytes = json.dumps(plan, indent=2, sort_keys=True).encode("utf-8")
    (path / "plan.json").write_bytes(plan_bytes)
    (path / "plan.json").chmod(0o600)
    for name, payload in (
        ("config.before.json", config_before),
        ("config.after.json", config_after),
        ("manifest.before.json", manifest_before),
        ("manifest.after.json", manifest_after),
    ):
        (path / name).write_bytes(payload)
        (path / name).chmod(0o600)
    if result is not None:
        (path / "result.json").write_bytes(
            json.dumps(result, indent=2, sort_keys=True).encode("utf-8"))
        (path / "result.json").chmod(0o600)
    return path


class Install:
    """One synthetic sealed chatgpt1 fleet install in a temporary directory."""

    def __init__(self, home: Path, roots: dict, tmp: Path, *,
                 account: str = ACCOUNT, gateway: bytes | None = None):
        self.home = home
        self.roots = roots
        self.account = account
        self.label = f"com.mastermind.studio-direct-private.{account}"
        roots["base"].mkdir(parents=True, exist_ok=True)
        roots["base"].chmod(0o700)
        roots["state"].mkdir(parents=True, exist_ok=True)
        roots["state"].chmod(0o700)
        node = tmp / "node"
        node.write_text("#!/bin/sh\necho node\n", encoding="utf-8")
        node.chmod(0o755)
        backend = tmp / "backend.mjs"
        backend.write_text("// desktop-commander index\n", encoding="utf-8")
        backend.chmod(0o600)
        self.node = node
        self.backend = backend
        modules = {name: f"// synthetic {name}\n".encode("utf-8")
                   for name in sorted(svc.V2_CHATGPT1_FLEET_TAILNET_PREDECESSOR)}
        modules["gateway.mjs"] = gateway if gateway is not None else resolve_preimage()
        for name, payload in modules.items():
            (roots["base"] / name).write_bytes(payload)
            (roots["base"] / name).chmod(0o600)
        self.modules = modules
        self.publisher_pair = {
            "git-publish.mjs": sha(modules["git-publish.mjs"]),
            "workspace-access.mjs": sha(modules["workspace-access.mjs"]),
        }
        self.config = {
            "accountLabel": account,
            "fleetRouting": {"enabled": True, "routes": [
                {"hostRef": "studio-a", "url": "http://127.0.0.1:1/a"},
                {"hostRef": "studio-b", "url": "http://127.0.0.1:1/b"},
            ]},
            "maxPerSessionConcurrency": 8,
            "maxQueuedPerSession": 16,
            "fleetStatus": {"enabled": True},
            "repositoryWorkspaces": {
                "enabled": True,
                "allowedRepositories": ["mastermind", "macro", "terminal"],
            },
            "gitPublish": svc._typed_git_config(home, closed_repositories=True),
        }
        self.config_bytes = json.dumps(
            self.config, indent=2, sort_keys=True).encode("utf-8")
        roots["config"].write_bytes(self.config_bytes)
        roots["config"].chmod(0o600)
        deps = roots["base"] / "node_modules"
        deps.mkdir(parents=True, exist_ok=True)
        package = deps / "fixture-package"
        package.mkdir(exist_ok=True)
        (package / "index.js").write_text("export const fixture = 1;\n", encoding="utf-8")
        plist = {
            "Label": self.label,
            "ProgramArguments": svc._expected_argv(
                node, roots["gateway"], roots["config"]),
            "RunAtLoad": True,
        }
        self.plist_bytes = plistlib.dumps(plist)
        roots["plist"].write_bytes(self.plist_bytes)
        roots["plist"].chmod(0o600)
        self.manifest = {
            "version": svc.MANIFEST_VERSION,
            "account": account,
            "label": self.label,
            "files": {name: sha(payload) for name, payload in modules.items()},
            "configHash": sha(self.config_bytes),
            "plistHash": sha(self.plist_bytes),
            "source": str(home / "source"),
            "node": str(node),
            "backend": str(backend),
            "host": "127.0.0.1",
            "port": PORT,
            "nodeHash": svc._stable_regular_file_hash(node, label="node"),
            "backendHash": svc._stable_regular_file_hash(backend, label="backend"),
            "dependencyTreeHash": svc._dependency_tree_hash(deps),
        }
        self.write_manifest()

    def write_manifest(self) -> None:
        self.manifest_bytes = json.dumps(
            self.manifest, indent=2, sort_keys=True).encode("utf-8")
        self.roots["manifest"].write_bytes(self.manifest_bytes)
        self.roots["manifest"].chmod(0o600)

    @property
    def manifest_sha256(self) -> str:
        return sha(self.manifest_bytes)

    def preserved_blobs(self) -> dict:
        """The incumbent git-blob pins for the synthetic preserved fleet modules.

        The gateway pin stays the real predecessor blob: the fixture must not
        redefine the expectation for the module under test.
        """
        blobs = {name: git_blob_sha1(payload)
                 for name, payload in self.modules.items()}
        blobs["gateway.mjs"] = PREIMAGE_GIT_BLOB
        return blobs

    def patches(self):
        """Patch the incumbent pins onto this synthetic install."""
        pair = dict(self.publisher_pair)
        return [
            mock.patch.dict(svc.FLEET_V10_PRESERVED_GIT_BLOBS,
                            self.preserved_blobs(), clear=True),
            mock.patch.dict(svc.FLEET_V10_PUBLISHER_PATCH_SHA256, pair, clear=True),
            mock.patch.dict(svc.FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256,
                            pair, clear=True),
            mock.patch.dict(svc.FLEET_V10_POST_MERGE_PUBLISHER_PREDECESSOR_SHA256,
                            pair, clear=True),
            mock.patch.dict(svc.FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256,
                            pair, clear=True),
            mock.patch.object(svc, "FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256",
                              pair["git-publish.mjs"]),
        ]

    def publisher_source(self, home: Path) -> Path:
        """A source directory holding the synthetic publisher modules.

        The incumbent publisher route validates the whole reviewed source
        bundle before it touches the installation.
        """
        source = home / "publisher-source"
        source.mkdir(parents=True, exist_ok=True)
        for name in svc.STAGE_FILES:
            payload = self.modules.get(
                name, f"// synthetic source {name}\n".encode("utf-8"))
            (source / name).write_bytes(payload)
        return source


class Base(unittest.TestCase):
    """Shared synthetic install, launcher stub and argument builder."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.home_ctx = isolated_home()
        self.home, self.roots = self.home_ctx.__enter__()
        self.addCleanup(self.home_ctx.__exit__, None, None, None)
        self.install = Install(self.home, self.roots, self.tmp)
        for patch in self.install.patches():
            patch.start()
            self.addCleanup(patch.stop)

    def args(self, *, preflight: bool = False, account: str = ACCOUNT,
             manifest_sha256: str | None = None) -> mock.Mock:
        source = self.home / "source"
        source.mkdir(parents=True, exist_ok=True)
        return mock.Mock(
            account=account, port=PORT, source=str(source),
            node=str(self.install.node), backend=str(self.install.backend),
            fabric_only=False, modern_fabric_protocol=None,
            enable_repository_workspaces=False,
            os_commission_config_sha256=None,
            c1_fleet_git_failure_compat=True,
            publisher_only_fleet_v10=False,
            publisher_expected_manifest_sha256=(
                self.install.manifest_sha256
                if manifest_sha256 is None else manifest_sha256),
            publisher_preflight_only=preflight,
        )

    def stopped(self):
        return mock.patch.object(
            svc, "_run", _launchd_run("stopped", self.roots["plist"]))

    def running(self):
        return mock.patch.object(
            svc, "_run", _launchd_run("running", self.roots["plist"]))

    def call(self, args):
        buffer = io.StringIO()
        with mock.patch("sys.stdout", buffer):
            svc.cmd_upgrade(args)
        return json.loads(buffer.getvalue())

    def gateway_sha(self) -> str:
        return sha((self.roots["base"] / "gateway.mjs").read_bytes())

    def applied_pin(self, *, paper=False, live_native=False):
        """A complete retained intent, actual one-field pin and selected bridge.

        Only the native generation context and cohort data are synthetic;
        read_transaction, the exact Paper planner and start/state owners run.
        """
        pool = self.home / "native-pool"
        pool.write_bytes(b"selected native bridge")
        pool.chmod(0o600)
        before = copy.deepcopy(self.install.config)
        before["fleetStatus"].update(fabricLauncherPath=str(pool),
                                    fabricLauncherSha256=sha(b"previous bridge"))
        if paper:
            before["paperDesign"] = svc._paper_design_config(self.home,
                rel=svc.PAPER_RUNTIME_V10_REL, bridge_sha256=svc.PAPER_V10_BRIDGE_SHA256)
        after = copy.deepcopy(before)
        after["fleetStatus"]["fabricLauncherSha256"] = sha(pool.read_bytes())
        config_before, config_after = map(svc._fabric_release_json, (before, after))
        old_manifest = {**self.install.manifest, "configHash": sha(config_before)}
        new_manifest = {**old_manifest, "configHash": sha(config_after)}
        manifest_before, manifest_after = map(svc._fabric_release_json,
                                             (old_manifest, new_manifest))
        path = _write_pin_transaction(self.roots, config_before=config_before,
            config_after=config_after, manifest_before=manifest_before,
            manifest_after=manifest_after)
        if live_native:
            # The live proof must return this exact selected identity. It is the
            # one completed historical successor, not a new native selection.
            binding = {
                "successor_digest": RETAINED_SUCCESSOR_DIGEST,
                "target_generation": RETAINED_TARGET_GENERATION,
                "expected_selection": {
                    "schema": "native-code-selection.v1",
                    "generation": "c" * 64,
                    "previous": "d" * 64,
                    "sequence": 23,
                },
                "pool_target": str(pool),
                "pool_previous": sha(b"previous bridge"),
                "pool_bridge": sha(pool.read_bytes()),
                "phase": "SELECTED",
            }
        else:
            binding = {"successor_digest": "a" * 64, "target_generation": "b" * 64,
                "expected_selection": {"generation": "c" * 64, "sequence": 24},
                "pool_target": str(pool), "pool_previous": sha(b"previous bridge"),
                "pool_bridge": sha(pool.read_bytes()), "phase": "SELECTED"}
        plan = json.loads((path / "plan.json").read_bytes())
        plan.update({k: v for k, v in binding.items() if k != "phase"})
        plan["successor_bundle"] = str(self.home / "native-successor")
        plan_bytes = svc._fabric_release_json(plan)
        (path / "plan.json").write_bytes(plan_bytes)
        for name, value in {
            "intent.json": {"schema": pin.SCHEMA, "planSha256": sha(plan_bytes)},
            "result.json": {"schema": pin.SCHEMA, "planSha256": sha(plan_bytes), "effect": "APPLIED"},
        }.items():
            (path / name).write_bytes(svc._fabric_release_json(value))
            (path / name).chmod(0o600)
        self.roots["config"].write_bytes(config_after)
        self.install.config_bytes, self.install.config = config_after, after
        self.install.manifest = new_manifest
        self.install.write_manifest()
        self.native_context_events, self.native_context_active = [], False
        self.native_purposes = []
        if live_native:
            return path, plan, binding

        @contextmanager
        def native(args):
            self.native_context_events.append(("enter", args.operation))
            self.native_purposes.append(getattr(args, "retained_proof_purpose", ""))
            self.native_context_active = True
            try:
                yield binding
            finally:
                self.native_context_active = False
                self.native_context_events.append(("exit", args.operation))

        patch = mock.patch.object(svc, "_pin_native_context", native)
        patch.start(); self.addCleanup(patch.stop)
        if paper:
            # Fixture HOME deliberately excludes the repository. Load the
            # exact pure planner as fixture source, then supply synthetic
            # cohort data; do not weaken the installer's path guard.
            source_path = Path(svc.__file__).with_name("paper_v20_fleet_cohorts.py")
            source = source_path.read_bytes()
            self.assertEqual(sha(source), svc.FLEET_V20_COHORT_SOURCE_SHA256)
            cohort = ModuleType("_c1_test_frozen_paper")
            exec(compile(source, str(source_path), "exec"), cohort.__dict__)
            original = dict(cohort.COHORTS[ACCOUNT])
            original.update(manifest_sha256=sha(manifest_after),
                config_sha256=sha(config_after), plist_sha256=sha(self.install.plist_bytes),
                file_count=len(new_manifest["files"]),
                nonpaper_sha256=cohort._canonical_hash(
                    {k: v for k, v in after.items() if k != "paperDesign"}))
            cohort.COHORTS[ACCOUNT] = original
            selection = cohort.plan_selection(ACCOUNT, manifest_bytes=manifest_after,
                config_bytes=config_after, plist_bytes=self.install.plist_bytes, home=self.home)
            patch = mock.patch.object(svc, "_frozen_paper_fleet_module", return_value=cohort)
            patch.start(); self.addCleanup(patch.stop)
            self.roots["config"].write_bytes(selection["configBytes"])
            self.install.config_bytes = selection["configBytes"]
            self.install.config = json.loads(selection["configBytes"])
            self.install.manifest = selection["manifest"]
            self.install.write_manifest()
        return path, plan, binding

    def pruned_bootstrap_rollout(self, *, diverge=False, altered_receipt=False):
        """Point the real native proof at a pruned-bootstrap fixture.

        The production proof script and publication lock stay in place. Only
        the historical bootstrap reader is replaced, and it still refuses to
        invent the missing artifact.
        """
        store = self.home / "native-code-releases"
        store.mkdir(mode=0o700)
        store.chmod(0o700)
        pool = self.home / "native-pool"
        old = {"schema": "native-code-selection.v1", "generation": "c" * 64,
               "previous": "d" * 64, "sequence": 23}
        plan = {
            "digest": RETAINED_SUCCESSOR_DIGEST,
            "store": str(store),
            "expected_selection": old,
            "target_generation": RETAINED_TARGET_GENERATION,
            "entries": {"pool": {
                "target": str(pool),
                "previous": sha(b"previous bridge"),
                "bridge": sha(pool.read_bytes()),
            }},
        }
        bundle = self.home / "native-successor"
        bundle.mkdir(mode=0o700)
        (bundle / "PLAN.json").write_text(json.dumps(plan))
        receipt = b"altered-receipt" if altered_receipt else b"exact-retained-receipt"
        (bundle / "receipt.json").write_bytes(receipt)
        current = {"schema": "native-code-selection.v1",
                   "generation": CURRENT_GENERATION,
                   "previous": CURRENT_PREVIOUS, "sequence": 26}
        (store / "CURRENT.json").write_text(json.dumps(current))
        (store / "VERIFIED.json").write_text(json.dumps([
            RETAINED_TARGET_GENERATION, CURRENT_GENERATION, CURRENT_PREVIOUS]))
        if diverge:
            (store / "DIVERGE").write_text("1")
        rollout = self.home / "fixture-rollout"
        rollout.mkdir(mode=0o700)
        (rollout / "native_install.py").write_text(
            "import json\n"
            "from pathlib import Path\n"
            "def read_successor(bundle):\n"
            " raise FileNotFoundError('historical bootstrap artifact pruned')\n"
            "def read_retained_successor_after_bootstrap_prune(bundle):\n"
            " receipt=(Path(bundle)/'receipt.json').read_bytes()\n"
            " if receipt!=b'exact-retained-receipt':\n"
            "  raise ValueError('retained successor evidence changed')\n"
            " return json.loads((Path(bundle)/'PLAN.json').read_text()), {}\n"
            "def _upgrade_entries(p, complete=False):\n"
            " raw=Path(p['entries']['pool']['target']).read_bytes()\n"
            " if raw!=b'selected native bridge':\n"
            "  raise ValueError('ingress does not match reviewed bridge')\n"
        )
        (rollout / "native_generation.py").write_text(
            "import json\n"
            "from pathlib import Path\n"
            "POINTER_SCHEMA='native-code-selection.v1'\n"
            "def current(store):\n"
            " store=Path(store)\n"
            " value=json.loads((store/'CURRENT.json').read_text())\n"
            " if not (store/'DIVERGE').exists():\n"
            "  return value\n"
            " count_path=store/'proof-calls'\n"
            " count=int(count_path.read_text()) if count_path.exists() else 0\n"
            " count_path.write_text(str(count+1))\n"
            " if count>=1:\n"
            "  value=dict(value); value['sequence']=value['sequence']+1\n"
            " return value\n"
            "def verify(store, identity):\n"
            " allowed=json.loads((Path(store)/'VERIFIED.json').read_text())\n"
            " if identity not in allowed: raise ValueError('unverified generation')\n"
        )
        real_run = svc.subprocess.run
        self.proof_invocations = []

        def wrapped(argv, *args, **kwargs):
            argv = list(argv)
            code_at = next((index for index, item in enumerate(argv)
                            if isinstance(item, str) and "import native_install as i" in item),
                           None)
            if code_at is not None:
                argv[code_at + 1] = str(rollout)
                account = argv[code_at + 4]
                operation = argv[code_at + 5]
                purpose = argv[code_at + 6] if len(argv) > code_at + 6 else ""
                self.proof_invocations.append((account, operation, purpose))
            return real_run(argv, *args, **kwargs)

        patch = mock.patch.object(svc.subprocess, "run", side_effect=wrapped)
        patch.start()
        self.addCleanup(patch.stop)
        return store

    def native_generation(self):
        import importlib.util
        rollout = (Path(svc.__file__).resolve().parents[2]
                   / "ops/native_fabric/quota_continuity/rollout")
        spec = importlib.util.spec_from_file_location(
            "c1_pin_generation", rollout / "native_generation.py")
        generation = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(generation)
        return generation


class CompilerTests(Base):
    """The compiler is a pure, fully pinned source transform."""

    def setUp(self):
        super().setUp()
        self.preimage = resolve_preimage()

    def test_missing_object_fails_without_a_fallback(self):
        with self.assertRaisesRegex(AssertionError, "missing input"):
            offline_blob("0" * 40)

    def test_preimage_is_the_exact_pinned_public_object(self):
        self.assertEqual(
            (len(self.preimage), sha(self.preimage), git_blob_sha1(self.preimage)),
            (PREIMAGE_SIZE, PREIMAGE_SHA256, PREIMAGE_GIT_BLOB))
        self.assertEqual(
            (compat.PREIMAGE_SIZE, compat.PREIMAGE_SHA256, compat.PREIMAGE_GIT_BLOB),
            (PREIMAGE_SIZE, PREIMAGE_SHA256, PREIMAGE_GIT_BLOB))

    def test_compiler_reconstructs_the_complete_successor(self):
        successor = compat.compile_successor(self.preimage)
        self.assertEqual(
            (len(successor), sha(successor), git_blob_sha1(successor)),
            (SUCCESSOR_SIZE, SUCCESSOR_SHA256, SUCCESSOR_GIT_BLOB))
        self.assertEqual(
            (compat.SUCCESSOR_SIZE, compat.SUCCESSOR_SHA256,
             compat.SUCCESSOR_GIT_BLOB),
            (SUCCESSOR_SIZE, SUCCESSOR_SHA256, SUCCESSOR_GIT_BLOB))

    def test_successor_diff_is_exactly_the_two_intended_regions(self):
        report = compat.diff_report(self.preimage, compat.compile_successor(self.preimage))
        self.assertEqual(
            (report["hunks"], report["addedLines"], report["removedLines"]),
            (2, 24, 8))
        text = compat.compile_successor(self.preimage).decode("utf-8")
        self.assertNotIn("TYPED_GIT_PRECHECK_REFUSED", text)
        for code in ("TYPED_GIT_READONLY_INSPECTION_REFUSED",
                     "TYPED_GIT_EFFECT_UNQUALIFIED",
                     "TYPED_GIT_REQUIRES_LOCAL_STUDIO_SESSION"):
            self.assertIn(code, text)

    def test_preserved_guard_stays_identical_and_ahead_of_dispatch(self):
        successor = compat.compile_successor(self.preimage)
        guard = compat.guard_report(successor)
        self.assertTrue(guard["guardPreserved"])
        self.assertTrue(guard["guardPrecedesDispatch"])
        text = successor.decode("utf-8")
        self.assertIn(compat.GUARD_BLOCK, text)
        self.assertLess(text.index(compat.GUARD_BLOCK),
                        text.index(compat.DISPATCH_MARKER))

    def test_refusals_for_a_changed_appended_or_ambiguous_preimage(self):
        mutated = bytearray(self.preimage)
        mutated[1000] ^= 0x01
        cases = {
            "PREIMAGE_SHA256_REFUSED": bytes(mutated),
            "PREIMAGE_SIZE_REFUSED": self.preimage + b"\n// tail\n",
            "CATCH_AMBIGUOUS": self.preimage.replace(
                compat.LEGACY_CATCH_BLOCK.encode("utf-8"),
                compat.LEGACY_CATCH_BLOCK.encode("utf-8") * 2),
            "BOUNDARY_AMBIGUOUS": self.preimage.replace(
                compat.INSERTION_ANCHOR.encode("utf-8"), b"", 1),
            "PREIMAGE_ALREADY_PATCHED": compat.compile_successor(self.preimage),
        }
        for code, payload in cases.items():
            with self.subTest(code=code):
                with self.assertRaises(compat.CompatError) as ctx:
                    compat.compile_successor(payload)
                self.assertEqual(ctx.exception.code, code)

    def test_a_modified_successor_is_refused(self):
        successor = bytearray(compat.compile_successor(self.preimage))
        successor[-2] ^= 0x20
        with self.assertRaises(compat.CompatError) as ctx:
            compat.verify_successor(bytes(successor))
        self.assertEqual(ctx.exception.code, "SUCCESSOR_SHA256_REFUSED")

    def test_the_classifier_never_inspects_or_serializes_the_exception(self):
        for token in ("JSON.stringify", "Object.keys", ".stack", ".message",
                      "Object.getOwnPropertyNames", ".stderr", ".command"):
            self.assertNotIn(token, compat.CLASSIFIER_BLOCK)
        self.assertIn("_error", compat.CLASSIFIER_BLOCK)

    def test_the_compiler_has_no_runtime_listener_or_installer_surface(self):
        import ast

        source = Path(compat.__file__).read_text(encoding="utf-8")
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        for forbidden in ("socket", "subprocess", "urllib", "http", "requests",
                          "shutil", "tempfile"):
            self.assertNotIn(forbidden, imported)
        self.assertNotIn("launchctl", source)


class OwnerTransactionTests(Base):
    """The closed chatgpt1 gateway-only transition inside the incumbent owner."""

    def test_preflight_reports_exact_before_and_target_hashes(self):
        report = self.call(self.args(preflight=True))
        self.assertEqual(report["preflight"], True)
        self.assertEqual(report["effect"], "NOT_APPLIED")
        self.assertEqual(report["account"], ACCOUNT)
        self.assertEqual(report["originalManifestSha256"], self.install.manifest_sha256)
        self.assertEqual(report["preimageGatewaySha256"], PREIMAGE_SHA256)
        self.assertEqual(report["targetGatewaySha256"], SUCCESSOR_SHA256)
        self.assertEqual(report["targetGatewaySize"], SUCCESSOR_SIZE)
        self.assertEqual(report["sourceDiff"]["hunks"], 2)
        self.assertTrue(report["preservedGuard"]["guardPrecedesDispatch"])
        self.assertEqual(report["fleetRoutesPreserved"], 2)
        self.assertEqual(report["concurrencyPreserved"], [8, 16])
        self.assertEqual(report["nativePoolPin"]["state"], "ABSENT")
        self.assertFalse(report["serviceStarted"])

    def test_preflight_is_read_only_and_works_while_the_service_runs(self):
        with self.running():
            report = self.call(self.args(preflight=True))
        self.assertFalse(report["serviceStopped"])
        self.assertIsNone(report["blocker"])
        self.assertEqual(self.gateway_sha(), PREIMAGE_SHA256)
        self.assertEqual(sha(self.roots["manifest"].read_bytes()),
                         self.install.manifest_sha256)

    def test_apply_replaces_only_the_gateway_and_its_manifest_digest(self):
        before_config = self.roots["config"].read_bytes()
        before_publisher = (self.roots["base"] / "git-publish.mjs").read_bytes()
        before_fleet = (self.roots["base"] / "fleet-routing.mjs").read_bytes()
        with self.stopped():
            receipt = self.call(self.args())
        self.assertEqual(receipt["effect"], "APPLIED")
        self.assertEqual(receipt["targetGatewaySha256"], SUCCESSOR_SHA256)
        self.assertFalse(receipt["serviceStarted"])
        self.assertEqual(self.roots["config"].read_bytes(), before_config)
        self.assertEqual((self.roots["base"] / "git-publish.mjs").read_bytes(),
                         before_publisher)
        self.assertEqual((self.roots["base"] / "fleet-routing.mjs").read_bytes(),
                         before_fleet)
        self.assertEqual(self.gateway_sha(), SUCCESSOR_SHA256)
        manifest = json.loads(self.roots["manifest"].read_text(encoding="utf-8"))
        self.assertEqual(manifest["files"]["gateway.mjs"], SUCCESSOR_SHA256)
        self.assertEqual(manifest["configHash"], sha(before_config))
        self.assertEqual(manifest["dependencyTreeHash"],
                         self.install.manifest["dependencyTreeHash"])

    def test_a_foreign_account_is_refused(self):
        with self.stopped():
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_upgrade(self.args(account="chatgpt3"))
        self.assertIn("enrolled chatgpt1 owner", str(ctx.exception))

    def test_an_unrecognized_publisher_pair_is_refused(self):
        foreign = {"git-publish.mjs": "0" * 64, "workspace-access.mjs": "1" * 64}
        with mock.patch.dict(svc.FLEET_V10_PUBLISHER_PATCH_SHA256, foreign, clear=True), \
             mock.patch.dict(svc.FLEET_V10_MERGE_PUBLISHER_PREDECESSOR_SHA256, foreign, clear=True), \
             mock.patch.dict(svc.FLEET_V10_POST_MERGE_PUBLISHER_PREDECESSOR_SHA256, foreign, clear=True), \
             mock.patch.dict(svc.FLEET_V10_MERGE_PUBLISHER_PATCH_SHA256, foreign, clear=True), \
             mock.patch.object(svc, "FLEET_V10_PREVIOUS_CLOSED_PUBLISHER_SHA256",
                               foreign["git-publish.mjs"]):
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_upgrade(self.args())
        self.assertIn("unrecognized prior publisher identity", str(ctx.exception))

    def test_a_config_drift_is_refused(self):
        drifted = copy.deepcopy(self.install.config)
        drifted["fleetRouting"]["enabled"] = False
        self.roots["config"].write_bytes(
            json.dumps(drifted, indent=2, sort_keys=True).encode("utf-8"))
        manifest = json.loads(self.roots["manifest"].read_text(encoding="utf-8"))
        manifest["configHash"] = sha(self.roots["config"].read_bytes())
        self.roots["manifest"].write_bytes(
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
        with self.assertRaises(SystemExit) as ctx:
            svc.cmd_upgrade(self.args(
                manifest_sha256=sha(self.roots["manifest"].read_bytes())))
        self.assertIn("original scoped capabilities changed", str(ctx.exception))

    def test_a_manifest_cas_mismatch_is_refused(self):
        with self.assertRaises(SystemExit) as ctx:
            svc.cmd_upgrade(self.args(manifest_sha256="0" * 64))
        self.assertIn("installed manifest CAS mismatch", str(ctx.exception))

    def test_a_loaded_service_is_refused(self):
        with self.running():
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_upgrade(self.args())
        self.assertIn("while service is loaded", str(ctx.exception))

    def test_an_indeterminate_launchd_state_is_not_a_stop_proof(self):
        """A nonzero launchctl result is not proof that the service stopped."""
        def indeterminate(cmd, check=True, timeout=30.0):
            return svc.CmdResult(1, "", "launchctl: unexpected error\n")

        with mock.patch.object(svc, "_run", indeterminate):
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_upgrade(self.args())
        self.assertIn("indeterminate", str(ctx.exception))
        self.assertEqual(self.gateway_sha(), PREIMAGE_SHA256)

    def test_the_preflight_reports_an_indeterminate_stop_state_as_a_blocker(self):
        def indeterminate(cmd, check=True, timeout=30.0):
            return svc.CmdResult(1, "", "launchctl: unexpected error\n")

        with mock.patch.object(svc, "_run", indeterminate):
            report = self.call(self.args(preflight=True))
        self.assertFalse(report["serviceStopped"])
        self.assertIn("indeterminate", report["blocker"])
        self.assertEqual(self.gateway_sha(), PREIMAGE_SHA256)

    def test_source_drift_between_preflight_and_apply_is_refused(self):
        with self.stopped():
            gateway = self.roots["base"] / "gateway.mjs"
            payload = bytearray(gateway.read_bytes())
            payload[0] ^= 0x20
            gateway.write_bytes(bytes(payload))
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_upgrade(self.args())
        self.assertTrue("original installation changed" in str(ctx.exception)
                        or "hash mismatch" in str(ctx.exception))
        self.assertEqual(sha(self.roots["manifest"].read_bytes()),
                         self.install.manifest_sha256)

    def test_lifecycle_lock_contention_is_refused(self):
        lock_path = self.roots["state"] / svc.C2_LIFECYCLE_LOCK_NAME
        lock_path.touch(mode=0o600)
        lock_path.chmod(0o600)
        holder = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.addCleanup(os.close, holder)
        fcntl.flock(holder, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with self.stopped():
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_upgrade(self.args())
        self.assertIn("already in progress", str(ctx.exception))

    def test_a_failure_before_or_between_the_writes_restores_the_original(self):
        real_write = svc._atomic_write_bytes
        for fail_on in (1, 2):
            with self.subTest(fail_on=fail_on):
                calls = {"n": 0}

                def flaky(path, data, mode=svc.FILE_MODE):
                    calls["n"] += 1
                    if calls["n"] == fail_on:
                        raise OSError("interrupted")
                    return real_write(path, data, mode)

                with self.stopped():
                    with mock.patch.object(svc, "_atomic_write_bytes",
                                           side_effect=flaky):
                        with self.assertRaises(SystemExit) as ctx:
                            svc.cmd_upgrade(self.args())
                self.assertIn("NOT_APPLIED", str(ctx.exception))
                self.assertEqual(self.gateway_sha(), PREIMAGE_SHA256)
                self.assertEqual(sha(self.roots["manifest"].read_bytes()),
                                 self.install.manifest_sha256)

    def test_a_failure_after_the_manifest_commit_is_effect_unknown(self):
        real_verify = svc._verify_staged_install
        calls = {"n": 0}

        def flaky_verify(*args, **kw):
            calls["n"] += 1
            if calls["n"] >= 2:
                raise SystemExit("post-commit verification failed")
            return real_verify(*args, **kw)

        with self.stopped():
            with mock.patch.object(svc, "_verify_staged_install",
                                   side_effect=flaky_verify):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_upgrade(self.args())
        self.assertIn("EFFECT_UNKNOWN", str(ctx.exception))
        self.assertEqual(self.gateway_sha(), SUCCESSOR_SHA256)

    def test_foreign_bytes_during_recovery_are_refused(self):
        real_write = svc._atomic_write_bytes
        calls = {"n": 0}

        def hostile(path, data, mode=svc.FILE_MODE):
            calls["n"] += 1
            if calls["n"] == 1:
                real_write(path, b"foreign bytes\n", mode)
                raise OSError("interrupted")
            return real_write(path, data, mode)

        with self.stopped():
            with mock.patch.object(svc, "_atomic_write_bytes", side_effect=hostile):
                with self.assertRaises(SystemExit) as ctx:
                    svc.cmd_upgrade(self.args())
        self.assertIn("EFFECT_UNKNOWN", str(ctx.exception))

    def test_the_generic_restage_refusal_is_retained(self):
        pin_dir = self.roots["state"] / "native-pool-pin"
        pin_dir.mkdir(parents=True, exist_ok=True)
        pin_dir.chmod(0o700)
        args = self.args()
        args.c1_fleet_git_failure_compat = False
        with self.assertRaises(SystemExit) as ctx:
            svc.cmd_upgrade(args)
        self.assertIn("NATIVE_POOL_PIN_PROFILE_REQUIRES_PIN_OWNER", str(ctx.exception))

    def _assert_pending_status_owner_blocks_formatter(self, *, paper):
        self.applied_pin(paper=paper)
        record = self.roots["state"] / "fleet-status-module-successor"
        record.mkdir(mode=0o700)
        (record / "PLAN.json").write_text('{"phase":"PENDING"}\n')
        preserved = self.install.preserved_blobs()
        original_gateway = (self.roots["base"] / "gateway.mjs").read_bytes()
        original_manifest = self.roots["manifest"].read_bytes()
        original_plan = (record / "PLAN.json").read_bytes()
        for preflight in (True, False):
            with self.subTest(preflight=preflight), self.stopped():
                with self.assertRaisesRegex(
                        SystemExit, "C1_FLEET_STATUS_SUCCESSOR_REQUIRES_OWNER"):
                    self.call(self.args(preflight=preflight))
            self.assertEqual((self.roots["base"] / "gateway.mjs").read_bytes(),
                             original_gateway)
            self.assertEqual(self.roots["manifest"].read_bytes(), original_manifest)
            self.assertEqual((record / "PLAN.json").read_bytes(), original_plan)
            self.assertEqual(self.install.preserved_blobs(), preserved)

    def test_pending_status_owner_blocks_pin_then_formatter(self):
        self._assert_pending_status_owner_blocks_formatter(paper=False)

    def test_pending_status_owner_blocks_paper_then_formatter(self):
        self._assert_pending_status_owner_blocks_formatter(paper=True)

    def test_a_retained_pending_pin_blocks_the_transition(self):
        _write_pin_transaction(
            self.roots,
            config_before=self.install.config_bytes,
            config_after=self.install.config_bytes,
            manifest_before=self.install.manifest_bytes,
            manifest_after=self.install.manifest_bytes)
        with self.assertRaises(SystemExit) as ctx:
            svc.cmd_upgrade(self.args())
        self.assertIn("retained native-pool pin", str(ctx.exception))
        self.assertEqual(self.gateway_sha(), PREIMAGE_SHA256)

    def test_a_retained_applied_pin_is_qualified_and_preserved(self):
        path, _, _ = self.applied_pin()
        original = {p.name: p.read_bytes() for p in path.iterdir()}
        with self.stopped():
            receipt = self.call(self.args())
        self.assertEqual(receipt["effect"], "APPLIED")
        self.assertEqual(receipt["nativePoolPin"]["state"], "COMPLETE")
        self.assertTrue(receipt["nativePoolPin"]["applicable"])
        self.assertTrue((path / "plan.json").exists())
        self.assertTrue((path / "result.json").exists())
        self.assertEqual(original, {p.name: p.read_bytes() for p in path.iterdir()})
        self.assertEqual(self.native_context_events, [("enter", "apply"), ("exit", "apply")])
        self.assertEqual(self.native_purposes, [svc.C1_GATEWAY_RETAINED_PROOF_PURPOSE])


class SelectedPinCompositionTests(Base):
    def test_native_context_encloses_both_gateway_writes_and_retained_proof(self):
        self.applied_pin()
        original_write = svc._atomic_write_bytes
        writes = []

        def checked(path, data, mode=svc.FILE_MODE):
            self.assertTrue(self.native_context_active)
            writes.append(path)
            return original_write(path, data, mode)

        with self.stopped(), mock.patch.object(svc, "_atomic_write_bytes", side_effect=checked):
            self.assertEqual(self.call(self.args())["effect"], "APPLIED")
        self.assertEqual(writes, [self.roots["base"] / "gateway.mjs", self.roots["manifest"]])
        self.assertFalse(self.native_context_active)

    def test_preview_uses_read_only_native_context_and_preserves_all_records(self):
        path, _, _ = self.applied_pin()
        before = {p.name: p.read_bytes() for p in path.iterdir()}
        with self.running(), mock.patch.object(svc, "_atomic_write_bytes") as write:
            result = self.call(self.args(preflight=True))
        self.assertEqual(result["effect"], "NOT_APPLIED")
        self.assertEqual(self.native_context_events, [("enter", "preview"), ("exit", "preview")])
        self.assertEqual(self.native_purposes, [svc.C1_GATEWAY_RETAINED_PROOF_PURPOSE])
        write.assert_not_called()
        self.assertEqual(before, {p.name: p.read_bytes() for p in path.iterdir()})

    def test_selected_phase_and_current_bridge_are_required_before_any_write(self):
        _, _, binding = self.applied_pin()
        with self.stopped(), mock.patch.object(svc, "_atomic_write_bytes") as write:
            binding["phase"] = "PREVIOUS"
            with self.assertRaisesRegex(SystemExit, "FUTURE_PIN_NOT_READY"):
                self.call(self.args())
            binding["phase"] = "SELECTED"
            Path(binding["pool_target"]).write_bytes(b"foreign bridge")
            with self.assertRaisesRegex(SystemExit, "FUTURE_PIN_NOT_READY"):
                self.call(self.args())
        write.assert_not_called()
        self.assertEqual(self.gateway_sha(), PREIMAGE_SHA256)

    def test_retained_intent_and_closed_plan_shape_are_required(self):
        path, plan, _ = self.applied_pin()
        with self.stopped(), mock.patch.object(svc, "_atomic_write_bytes") as write:
            (path / "intent.json").write_bytes(svc._fabric_release_json({
                "schema": pin.SCHEMA, "planSha256": "0" * 64}))
            with self.assertRaisesRegex(SystemExit, "INTENT_REFUSED"):
                self.call(self.args())
            plan["foreign"] = True
            (path / "plan.json").write_bytes(svc._fabric_release_json(plan))
            with self.assertRaisesRegex(SystemExit, "RETAINED_PLAN_REFUSED"):
                self.call(self.args())
        write.assert_not_called()

    def test_completed_pin_and_accepted_paper_then_formatter_compose_in_all_owners(self):
        path, plan, _ = self.applied_pin(paper=True)
        original = {p.name: p.read_bytes() for p in path.iterdir()}
        config = self.roots["config"].read_bytes()
        with self.running():
            preview = self.call(self.args(preflight=True))
        self.assertTrue(preview["nativePoolPin"]["paperSuccessor"])
        with self.stopped():
            result = self.call(self.args())
        self.assertEqual(result["effect"], "APPLIED")
        self.assertEqual(config, self.roots["config"].read_bytes())
        self.assertEqual(original, {p.name: p.read_bytes() for p in path.iterdir()})
        pin.require_start(svc, ACCOUNT, self.roots)
        raw = {k: v for k, v in original.items() if k.startswith(("config.", "manifest."))}
        self.assertEqual(pin.state(svc, self.roots, raw, plan), "COMPLETE")
        changed = json.loads(config)
        changed["maxPerSessionConcurrency"] += 1
        self.roots["config"].write_bytes(svc._fabric_release_json(changed))
        with self.assertRaisesRegex(SystemExit, "FUTURE_PIN_NOT_READY"):
            pin.require_start(svc, ACCOUNT, self.roots)
        with self.assertRaisesRegex(SystemExit, "FOREIGN_STATE"):
            pin.state(svc, self.roots, raw, plan)

    def test_matching_hashes_cannot_replace_the_exact_retained_pin_transformation(self):
        path, plan, _ = self.applied_pin()
        altered = json.loads((path / "config.after.json").read_bytes())
        altered["maxQueuedPerSession"] += 1
        config = svc._fabric_release_json(altered)
        manifest = json.loads((path / "manifest.after.json").read_bytes())
        manifest["configHash"] = sha(config)
        manifest = svc._fabric_release_json(manifest)
        (path / "config.after.json").write_bytes(config)
        (path / "manifest.after.json").write_bytes(manifest)
        plan.update(config_after=sha(config), manifest_after=sha(manifest))
        plan_bytes = svc._fabric_release_json(plan)
        (path / "plan.json").write_bytes(plan_bytes)
        (path / "intent.json").write_bytes(svc._fabric_release_json(
            {"schema": pin.SCHEMA, "planSha256": sha(plan_bytes)}))
        (path / "result.json").write_bytes(svc._fabric_release_json(
            {"schema": pin.SCHEMA, "planSha256": sha(plan_bytes), "effect": "APPLIED"}))
        with self.stopped(), mock.patch.object(svc, "_atomic_write_bytes") as write:
            with self.assertRaisesRegex(SystemExit, "RETAINED_BYTES_REFUSED"):
                self.call(self.args())
        write.assert_not_called()

    def test_unresolved_result_never_becomes_an_applied_pin(self):
        path, plan, _ = self.applied_pin()
        (path / "result.json").write_bytes(svc._fabric_release_json({
            "schema": pin.SCHEMA, "planSha256": pin.plan_sha(svc, plan), "effect": "UNKNOWN"}))
        with self.stopped(), mock.patch.object(svc, "_atomic_write_bytes") as write:
            with self.assertRaisesRegex(SystemExit, "FUTURE_PIN_NOT_READY"):
                self.call(self.args())
        write.assert_not_called()


class PrunedBootstrapFormatterTests(Base):
    """Missing historical bootstrap: formatter preview and apply share one proof."""

    def setUp(self):
        super().setUp()
        self.pin_path, self.pin_plan, _ = self.applied_pin(live_native=True)
        self.store = self.pruned_bootstrap_rollout()
        self.purpose = svc.C1_GATEWAY_RETAINED_PROOF_PURPOSE
        self.before_modules = {
            path.name: path.read_bytes()
            for path in self.roots["base"].iterdir() if path.is_file()}
        self.before_pin = {path.name: path.read_bytes() for path in self.pin_path.iterdir()}
        self.before_pointer = (self.store / "CURRENT.json").read_text()

    def test_missing_bootstrap_preview_and_gateway_apply_share_proof(self):
        with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_PIN_SUCCESSOR_REFUSED"):
            with pin.selected_applied_context(svc, ACCOUNT, self.roots, operation="apply"):
                self.fail("generic native apply admitted without the closed purpose")
        with self.assertRaisesRegex(SystemExit, "INPUT_REFUSED"):
            with pin.selected_applied_context(
                    svc, ACCOUNT, self.roots, operation="reconcile"):
                self.fail("generic native reconcile admitted")
        reconcile = SimpleNamespace(
            account=ACCOUNT, successor_bundle=self.home / "native-successor",
            successor_plan_sha256=RETAINED_SUCCESSOR_DIGEST, operation="reconcile")
        with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_PIN_SUCCESSOR_REFUSED"):
            with svc._pin_native_context(reconcile):
                self.fail("reconcile reached publication")
        with self.assertRaisesRegex(SystemExit, "INPUT_REFUSED"):
            with pin.selected_applied_context(
                    svc, "chatgpt4", self.roots, operation="apply",
                    retained_proof_purpose=self.purpose):
                self.fail("foreign account admitted")
        with self.assertRaisesRegex(SystemExit, "INPUT_REFUSED"):
            with pin.selected_applied_context(
                    svc, ACCOUNT, self.roots, operation="apply",
                    retained_proof_purpose="foreign-purpose"):
                self.fail("foreign purpose admitted")
        self.assertEqual(self.before_modules["gateway.mjs"],
                         (self.roots["base"] / "gateway.mjs").read_bytes())

        self.proof_invocations.clear()
        with self.running():
            preview = self.call(self.args(preflight=True))
        self.assertEqual(preview["effect"], "NOT_APPLIED")
        self.assertEqual(preview["nativePoolPin"]["state"], "COMPLETE")
        self.assertTrue(all(item[1:] == ("preview", self.purpose)
                            for item in self.proof_invocations))
        generation = self.native_generation()
        with generation.publication_lock(self.store):
            pass
        self.assertEqual(self.before_modules,
                         {path.name: path.read_bytes()
                          for path in self.roots["base"].iterdir() if path.is_file()})

        self.proof_invocations.clear()
        original_write = svc._atomic_write_bytes
        held = []

        def locked_write(path, data, mode=svc.FILE_MODE):
            try:
                with generation.publication_lock(self.store):
                    held.append(False)
            except ValueError as exc:
                self.assertIn("native publication already in progress", str(exc))
                held.append(True)
            return original_write(path, data, mode)

        with self.stopped(), mock.patch.object(
                svc, "_atomic_write_bytes", side_effect=locked_write):
            receipt = self.call(self.args())
        self.assertEqual(receipt["effect"], "APPLIED")
        self.assertTrue(held)
        self.assertTrue(all(item is True for item in held))
        self.assertGreaterEqual(len(self.proof_invocations), 2)
        self.assertTrue(all(item == (ACCOUNT, "apply", self.purpose)
                            for item in self.proof_invocations))
        modules = {path.name: path.read_bytes()
                   for path in self.roots["base"].iterdir() if path.is_file()}
        self.assertEqual(sha(modules["gateway.mjs"]), SUCCESSOR_SHA256)
        unchanged = {"gateway.mjs", "manifest.json"}
        self.assertEqual(
            {name: payload for name, payload in modules.items() if name not in unchanged},
            {name: payload for name, payload in self.before_modules.items()
             if name not in unchanged})
        self.assertEqual(self.before_pin,
                         {path.name: path.read_bytes() for path in self.pin_path.iterdir()})
        self.assertEqual((self.store / "CURRENT.json").read_text(), self.before_pointer)
        self.assertFalse((self.store / "proof-calls").exists())
        manifest = json.loads(self.roots["manifest"].read_text())
        self.assertEqual(manifest["files"]["gateway.mjs"], SUCCESSOR_SHA256)
        self.assertEqual(manifest["configHash"], sha(self.roots["config"].read_bytes()))
        before_manifest = manifest
        with mock.patch.object(svc, "_frozen_paper_fleet_module",
                               return_value=SimpleNamespace(COHORTS={})):
            pin.require_start(svc, ACCOUNT, self.roots)
        self.assertEqual(json.loads(self.roots["manifest"].read_text()), before_manifest)
        self.assertEqual((self.store / "CURRENT.json").read_text(), self.before_pointer)

    def test_changed_selection_refuses_before_gateway_publication(self):
        (self.store / "DIVERGE").write_text("1")
        with self.stopped(), mock.patch.object(svc, "_atomic_write_bytes") as write:
            with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_PIN_SUCCESSOR_CHANGED"):
                self.call(self.args())
        write.assert_not_called()
        self.assertEqual((self.roots["base"] / "gateway.mjs").read_bytes(),
                         self.before_modules["gateway.mjs"])
        self.assertEqual(self.before_pin,
                         {path.name: path.read_bytes() for path in self.pin_path.iterdir()})

    def test_altered_retained_receipt_refuses_preview_and_apply(self):
        (self.home / "native-successor" / "receipt.json").write_bytes(b"altered-receipt")
        for preflight in (True, False):
            with self.subTest(preflight=preflight), self.stopped():
                with self.assertRaisesRegex(SystemExit, "NATIVE_POOL_PIN_SUCCESSOR_REFUSED"):
                    self.call(self.args(preflight=preflight))
        self.assertEqual((self.roots["base"] / "gateway.mjs").read_bytes(),
                         self.before_modules["gateway.mjs"])

    def test_unqualified_paper_state_refuses_before_gateway_publication(self):
        drifted = json.loads(self.roots["config"].read_bytes())
        drifted["paperDesign"] = {"generation": "unqualified"}
        self.roots["config"].write_bytes(svc._fabric_release_json(drifted))
        unqualified = SimpleNamespace(COHORTS={})
        with self.stopped(), mock.patch.object(svc, "_atomic_write_bytes") as write, \
                mock.patch.object(svc, "_frozen_paper_fleet_module",
                                  return_value=unqualified):
            with self.assertRaisesRegex(
                    SystemExit, "retained native-pool pin is not the current installed state"):
                self.call(self.args())
        write.assert_not_called()
        self.assertEqual((self.roots["base"] / "gateway.mjs").read_bytes(),
                         self.before_modules["gateway.mjs"])


class PublisherLineageTests(Base):
    """The publisher-v10 lineage keeps working for old and new C1 generations."""

    def publisher_args(self, install, roots, source):
        return mock.Mock(
            account=install.account, port=PORT, source=str(source),
            node=str(install.node), backend=str(install.backend),
            fabric_only=False, modern_fabric_protocol=None,
            enable_repository_workspaces=False,
            os_commission_config_sha256=None,
            publisher_only_fleet_v10=True, c1_fleet_git_failure_compat=False,
            publisher_expected_manifest_sha256=sha(roots["manifest"].read_bytes()),
            publisher_preflight_only=False)

    def install_successor_gateway(self, install, roots):
        (roots["base"] / "gateway.mjs").write_bytes(
            compat.compile_successor(install.modules["gateway.mjs"]))
        manifest = json.loads(roots["manifest"].read_text(encoding="utf-8"))
        manifest["files"]["gateway.mjs"] = SUCCESSOR_SHA256
        roots["manifest"].write_bytes(
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))

    def test_the_c1_successor_is_accepted_for_chatgpt1(self):
        self.install_successor_gateway(self.install, self.roots)
        source = self.install.publisher_source(self.home)
        with self.stopped():
            with mock.patch.object(svc, "_atomic_write_bytes") as writer:
                with mock.patch("sys.stdout", io.StringIO()):
                    svc.cmd_upgrade(
                        self.publisher_args(self.install, self.roots, source))
        self.assertTrue(writer.called)

    def test_an_arbitrary_gateway_is_refused_by_the_publisher_route(self):
        (self.roots["base"] / "gateway.mjs").write_bytes(b"// arbitrary gateway\n")
        manifest = json.loads(self.roots["manifest"].read_text(encoding="utf-8"))
        manifest["files"]["gateway.mjs"] = sha(b"// arbitrary gateway\n")
        self.roots["manifest"].write_bytes(
            json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8"))
        source = self.install.publisher_source(self.home)
        with self.stopped():
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_upgrade(self.publisher_args(self.install, self.roots, source))
        self.assertIn("preserved fleet generation changed", str(ctx.exception))

    def test_the_successor_recognition_is_chatgpt1_scoped(self):
        other_ctx = isolated_home("chatgpt3")
        other_home, other_roots = other_ctx.__enter__()
        self.addCleanup(other_ctx.__exit__, None, None, None)
        other = Install(other_home, other_roots, self.tmp, account="chatgpt3")
        for patch in other.patches():
            patch.start()
            self.addCleanup(patch.stop)
        self.install_successor_gateway(other, other_roots)
        source = other.publisher_source(other_home)
        with mock.patch.object(
                svc, "_run", _launchd_run("stopped", other_roots["plist"])):
            with self.assertRaises(SystemExit) as ctx:
                svc.cmd_upgrade(self.publisher_args(other, other_roots, source))
        self.assertIn("preserved fleet generation changed", str(ctx.exception))


class NativePoolPinForwardTests(unittest.TestCase):
    """The retained native-pool pin keeps its predicates and gains one exact
    forward-selected successor for the C1 gateway correction."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "home"
        self.home.mkdir(mode=0o700)
        env = mock.patch.dict(os.environ, {"HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)
        # The synthetic retained manifest is outside every frozen Paper
        # cohort. The separate composition suite exercises the real planner.
        paper = mock.patch.object(svc, "_frozen_paper_fleet_module",
                                  return_value=SimpleNamespace(COHORTS={}))
        paper.start()
        self.addCleanup(paper.stop)
        self.roots = {name: self.home / f"{name}.json" for name in
                      ("config", "manifest", "plist")}
        for path in self.roots.values():
            path.touch(mode=0o600)
            path.chmod(0o600)
        self.config = json.dumps({"a": 1}, indent=2, sort_keys=True).encode("utf-8")
        self.config_before = json.dumps(
            {"a": 0}, indent=2, sort_keys=True).encode("utf-8")
        self.manifest = json.dumps({
            "version": 2, "account": ACCOUNT,
            "files": {"gateway.mjs": PREIMAGE_SHA256},
        }, indent=2, sort_keys=True).encode("utf-8")
        self.manifest_before = json.dumps({
            "version": 2, "account": ACCOUNT,
            "files": {"gateway.mjs": "0" * 64},
        }, indent=2, sort_keys=True).encode("utf-8")
        self.roots["config"].write_bytes(self.config)
        self.roots["manifest"].write_bytes(self.manifest)
        self.plan = {
            "account": ACCOUNT, "uid": os.getuid(),
            "manifest_before": sha(self.manifest_before),
            "manifest_after": sha(self.manifest),
            "config_before": sha(self.config_before),
            "config_after": sha(self.config),
            "config_mode": 0o600, "manifest_mode": 0o600,
        }
        self.raw = {"config.before.json": self.config_before,
                    "config.after.json": self.config,
                    "manifest.before.json": self.manifest_before,
                    "manifest.after.json": self.manifest}

    def successor(self) -> bytes:
        manifest = json.loads(self.manifest)
        manifest["files"]["gateway.mjs"] = SUCCESSOR_SHA256
        return json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    def forward(self, account=ACCOUNT, plan=None, raw=None,
                current=None, manifest=None):
        return pin._c1_fleet_git_failure_postpin_start(
            svc, account, self.roots, plan or self.plan, raw or self.raw,
            self.config if current is None else current,
            self.successor() if manifest is None else manifest)

    def test_the_exact_successor_is_forward_selected_for_chatgpt1(self):
        self.assertTrue(self.forward())

    def test_no_other_account_is_forward_selected(self):
        for account in ("chatgpt3", "admin-business", "chatgpt2-personal"):
            with self.subTest(account=account):
                self.assertFalse(self.forward(account=account))

    def test_an_altered_config_manifest_or_pin_is_refused(self):
        self.assertFalse(self.forward(current=b"{}"))
        self.assertFalse(self.forward(manifest=self.manifest))
        self.assertFalse(self.forward(plan=dict(self.plan, manifest_after="0" * 64)))
        foreign = json.loads(self.manifest)
        foreign["files"]["gateway.mjs"] = "0" * 64
        raw = {**self.raw, "manifest.after.json": json.dumps(
            foreign, indent=2, sort_keys=True).encode("utf-8")}
        self.assertFalse(self.forward(raw=raw))

    def test_the_successor_manifest_is_derived_only_from_the_retained_record(self):
        self.assertEqual(pin.c1_gateway_successor_manifest(svc, self.plan, self.raw),
                         self.successor())
        self.assertIsNone(pin.c1_gateway_successor_manifest(
            svc, dict(self.plan, account="chatgpt3"), self.raw))
        self.assertIsNone(pin.c1_gateway_successor_manifest(
            svc, dict(self.plan, manifest_after="0" * 64), self.raw))

    def test_the_real_start_gate_accepts_the_successor_and_refuses_drift(self):
        """Exercise require_start itself with a synthetic sealed pin successor."""
        from contextlib import contextmanager

        state_root = self.home / "state"
        state_root.mkdir(mode=0o700)
        pin_root = state_root / "native-pool-pin"
        pin_root.mkdir(mode=0o700)
        roots = {**self.roots, "state": state_root}
        native_pool = self.home / "pool"
        native_pool.write_bytes(b"qualified-native-pool")
        pool_digest = sha(native_pool.read_bytes())
        plan = {
            **self.plan, "schema": pin.SCHEMA, "account": ACCOUNT,
            "uid": os.getuid(), "pool_target": str(native_pool),
            "pool_bridge": pool_digest,
            "successor_bundle": str(self.home / "successor"),
            "successor_digest": "a" * 64,
        }
        (pin_root / "plan.json").write_bytes(svc._fabric_release_json(plan))
        (pin_root / "plan.json").chmod(0o600)
        result = {"schema": pin.SCHEMA, "planSha256": pin.plan_sha(svc, plan),
                  "effect": "APPLIED"}
        (pin_root / "result.json").write_bytes(svc._fabric_release_json(result))
        (pin_root / "result.json").chmod(0o600)

        @contextmanager
        def native(_args):
            yield {"phase": "SELECTED"}

        # The frozen Paper v20 cohort owner reads its own reviewed source
        # outside the temporary HOME. This seat is not in that cohort, so an
        # empty cohort is the faithful stand-in for the sibling predicate.
        cohort = mock.Mock()
        cohort.COHORTS = {}

        self.roots["config"].write_bytes(self.config)
        self.roots["manifest"].write_bytes(self.successor())
        with mock.patch.object(svc, "_pin_native_context", native), \
             mock.patch.object(svc, "_frozen_paper_fleet_module", return_value=cohort), \
             mock.patch.object(pin, "read_transaction", return_value=(plan, self.raw)):
            pin.require_start(svc, ACCOUNT, roots)
            with mock.patch.object(svc, "_stable_regular_file_hash",
                                   return_value="b" * 64):
                with self.assertRaisesRegex(SystemExit, "FUTURE_PIN_NOT_READY"):
                    pin.require_start(svc, ACCOUNT, roots)
            altered = json.loads(self.successor())
            altered["files"]["gateway.mjs"] = "0" * 64
            self.roots["manifest"].write_bytes(
                json.dumps(altered, indent=2, sort_keys=True).encode("utf-8"))
            with self.assertRaisesRegex(SystemExit, "FUTURE_PIN_NOT_READY"):
                pin.require_start(svc, ACCOUNT, roots)

    def test_pending_states_stay_pending_and_a_foreign_state_refuses(self):
        self.roots["config"].write_bytes(self.config_before)
        self.roots["manifest"].write_bytes(self.manifest_before)
        self.assertEqual(pin.state(svc, self.roots, self.raw, self.plan), "OLD")
        self.roots["config"].write_bytes(self.config)
        self.assertEqual(pin.state(svc, self.roots, self.raw, self.plan),
                         "CONFIG_ONLY")
        self.roots["manifest"].write_bytes(self.manifest)
        self.assertEqual(pin.state(svc, self.roots, self.raw, self.plan), "COMPLETE")
        self.roots["manifest"].write_bytes(self.successor())
        self.assertEqual(pin.state(svc, self.roots, self.raw, self.plan), "COMPLETE")
        self.roots["manifest"].write_bytes(b"{}\n")
        with self.assertRaises(SystemExit) as ctx:
            pin.state(svc, self.roots, self.raw, self.plan)
        self.assertIn("FOREIGN_STATE", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
