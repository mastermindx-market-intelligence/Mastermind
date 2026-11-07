"""Focused integration tests for the fixed project-knowledge recipe capture
engine against the REAL protected Macro owner bytes.

Honest execution states, never a shim claim:

* The protected source bytes come from the parent-supplied environment
  ``MM_TEST_MACRO_OWNER_ROOT`` (an existing Macro owner Git holding the
  protected commit); the canonical valid workstream/decision fixtures below
  are provided read-only by the parent.  When that fixture is unavailable on
  this host, every integration test SKIPS with that reason stated - no fake
  parser, no fake package, no ``sys.modules`` stand-in positive.
* The engine under test is the real installed module imported from this
  repository; the captured parser and recipe compiler bytes are executed as
  the actual protected code, never as copies or re-implementations.
* Child tests run the real fixed entry as an isolated child when the
  installed bounded runner is importable here, and skip honestly otherwise.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from control_plane.agentos_project_knowledge_recipe import (  # noqa: E402
    CAPTURE_SCHEMA,
    REPOSITORY,
    compile_project_knowledge_recipe,
    restore_project_knowledge_recipe,
)

PROTECTED_MACRO_SHA = "a8a5d3523614777d88eb2579d6efab52cd862e33"
OWNER_ROOT = os.environ.get("MM_TEST_MACRO_OWNER_ROOT")
FIXTURE_UNAVAILABLE = "MM_TEST_MACRO_OWNER_ROOT fixture unavailable on this host"

CAPTURE_LIMIT = 524288
WS_LIMIT = 131072
DECISION_LIMIT = 16384
FILE_LIMIT = 32768
CODE_LIMIT = 1048576

ACTOR_STAMP = "a" * 64
ACTOR_REF = "workspace:" + ACTOR_STAMP
BINDING_DIGEST = "d" * 64
DECISION_DATE = "2026-11-04"
KEY = "ALPHA"
WORK_REF = "WS:" + KEY

_FILE_ADD_SCHEMA = "mastermind.project_file_add_request.v1"
_PREFERENCE_SET_SCHEMA = "mastermind.project_preference_set_request.v1"
_PREFERENCE_DECISION_KEY = "PROJECT-COMMUNICATION-PREFERENCE-" + KEY
_DECISION_PATH = "agentos/decisions/DEC-" + _PREFERENCE_DECISION_KEY + ".md"
_WS_PATH = "agentos/workstreams/WS-" + KEY + ".md"

_READ_COMMANDS = ("rev-parse", "ls-tree", "cat-file", "show")
_GIT_ENV = {
    "GIT_AUTHOR_NAME": "chairman",
    "GIT_AUTHOR_EMAIL": "c@example.invalid",
    "GIT_COMMITTER_NAME": "chairman",
    "GIT_COMMITTER_EMAIL": "c@example.invalid",
}
COMMIT_DATE = "2026-11-04T09:00:00+00:00"


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_workstream(with_preference_pointer=False):
    """A canonical WS record the actual protected parser accepts."""
    decisions = ["- DEC:EARLIER-CALL\n"]
    if with_preference_pointer:
        decisions.append("- DEC:" + _PREFERENCE_DECISION_KEY + "\n")
    return (
        "---\n"
        "schema: agentos.workstream.v1\n"
        "key: ALPHA\n"
        "title: Project knowledge capture\n"
        "objective: Expose bounded project knowledge to the workspace.\n"
        "status: active\n"
        "program: mmos-core\n"
        "repos:\n"
        "- macro\n"
        "owner: chairman\n"
        "class: build\n"
        "blast_radius: reversible\n"
        "ambiguity: specified\n"
        "waves:\n"
        "- id: wave-1\n"
        "  title: Reader modules\n"
        "  status: done\n"
        "next_action: Land the reader.\n"
        "decisions:\n"
        + "".join(decisions) +
        "artifacts:\n"
        "- research/notes.md\n"
        "---\n\n"
        "Knowledge capture workstream body.\n"
    )


def preference_decision(answer, evidence_stamp):
    """A canonical fixed-key preference decision the protected law accepts."""
    return (
        "---\n"
        "schema: agentos.decision.v1\n"
        'decided_at: "' + DECISION_DATE + '"\n'
        "key: " + _PREFERENCE_DECISION_KEY + "\n"
        "question: How should this project communicate with its owner?\n"
        "answer: " + answer + "\n"
        "rationale: Explicit project-scoped communication preference supplied"
        " through the authorized project editor.\n"
        "alternatives:\n"
        "- option: Leave the preference unset\n"
        "  why_not: The authorized editor requested this value.\n"
        "evidence:\n"
        "- project-authoring-request:" + evidence_stamp + "\n"
        "affects:\n"
        "- WS:ALPHA\n"
        "confidence: high\n"
        "reversibility: easy\n"
        "decided_by: " + ACTOR_REF + "\n"
        "project_preference:\n"
        "  schema: agentos.project_preference.v1\n"
        "  work_ref: WS:ALPHA\n"
        "  kind: COMMUNICATION\n"
        "  value: " + answer + "\n"
        "  origin:\n"
        "    kind: USER_EDIT\n"
        "    actor_ref: " + ACTOR_REF + "\n"
        "    source_ref: null\n"
        "    source_revision: null\n"
        "  last_edit:\n"
        "    actor_ref: " + ACTOR_REF + "\n"
        "    request_sha256: " + evidence_stamp + "\n"
        "---\n\n"
    )


def earlier_decision():
    return (
        "---\n"
        "schema: agentos.decision.v1\n"
        'decided_at: "2026-01-10"\n'
        "key: EARLIER-CALL\n"
        "question: Which repo hosts the store?\n"
        "answer: Macro.\n"
        "rationale: Existing Git plus AgentOS is the only store.\n"
        "alternatives:\n"
        "- option: (none considered)\n"
        "  why_not: No alternative was considered.\n"
        "evidence:\n"
        "- agentos/workstreams/WS-ALPHA.md\n"
        "affects:\n"
        "- WS:ALPHA\n"
        "confidence: high\n"
        "reversibility: easy\n"
        "decided_by: chairman\n"
        "---\n\n"
        "Recorded earlier.\n"
    )


def owner_bytes(relative):
    """The ACTUAL protected bytes at the pinned commit, from the owner Git."""
    if not OWNER_ROOT:
        # Portable integration fixtures carry exact protected Git bytes, not
        # an alternate parser. Native source-qualification tests below still
        # require their explicit real Git owner and never count this as one.
        import base64,zlib
        fixture=json.loads((REPO_ROOT/'tests/fixtures/project-knowledge-recipe-canonical-a8a5.json').read_bytes())
        assert fixture['commit']==PROTECTED_MACRO_SHA
        source=fixture['owner' if relative=='scripts/agentos.py' else 'recipe']
        assert source['path']==relative
        raw=zlib.decompress(base64.b64decode(source['zlib_base64'],validate=True))
        assert hashlib.sha256(raw).hexdigest()==source['content_sha256']
        assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==source['git_blob_sha']
        return raw.decode('utf-8')
    result = subprocess.run(
        ["git", "-C", OWNER_ROOT, "show", PROTECTED_MACRO_SHA + ":" + relative],
        capture_output=True, timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError("owner fixture cannot serve " + relative)
    return result.stdout.decode("utf-8")


class _RecordingRunner:
    """An equivalent bounded runner that records commands and environments."""

    def __init__(self):
        self.commands = []
        self.envs = []

    @staticmethod
    def _decode(raw):
        try:
            return raw.decode("utf-8"), False
        except UnicodeDecodeError:
            return raw.decode("utf-8", "replace"), True

    def __call__(self, argv, *, cwd, timeout, max_bytes, env=None, input_bytes=None):
        self.commands.append([os.fspath(item) for item in argv])
        self.envs.append(dict(env) if env is not None else None)
        try:
            proc = subprocess.run(
                [os.fspath(item) for item in argv],
                cwd=os.fspath(cwd), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"code": None, "stdout": "", "stderr": "", "timed_out": True,
                    "invalid_utf8": False, "limit_exceeded": False}
        stdout, bad_out = self._decode(proc.stdout)
        stderr, bad_err = self._decode(proc.stderr)
        limit_exceeded = len(proc.stdout) + len(proc.stderr) > max_bytes
        return {"code": proc.returncode, "stdout": stdout, "stderr": stderr,
                "timed_out": False, "invalid_utf8": bad_out or bad_err,
                "limit_exceeded": limit_exceeded}


def git(root, *argv, date=COMMIT_DATE):
    env = dict(os.environ, **_GIT_ENV)
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    result = subprocess.run(
        ["git", *argv], cwd=root, env=env, capture_output=True, timeout=60,
    )
    if result.returncode != 0:
        raise AssertionError(
            "git %s failed: %s" % (" ".join(argv), result.stderr.decode("utf-8", "replace"))
        )
    return result.stdout.decode("utf-8")


def _file_request(display_name, content):
    return {
        "schema": _FILE_ADD_SCHEMA,
        "request_id": "mmos-project-file-add-" + "b" * 40,
        "work_ref": WORK_REF,
        "source_commit": None,  # filled by the caller
        "base_revision": None,  # filled by the caller
        "file": {"display_name": display_name, "media_type": "text/markdown",
                 "content_utf8": content},
    }


def _preference_request(value, base_revision, expected=None, stamp="e" * 40):
    return {
        "schema": _PREFERENCE_SET_SCHEMA,
        "request_id": "mmos-project-preference-set-" + stamp,
        "work_ref": WORK_REF,
        "source_commit": None,
        "base_revision": base_revision,
        "expected_preference_revision": expected,
        "value": value,
    }


def derived_media_path(request, ext="md"):
    file_id = hashlib.sha256(json.dumps(
        {"principal_scope": ACTOR_STAMP, "request_id": request["request_id"],
         "work_ref": WORK_REF},
        sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    return "agentos/project-files/WS-" + KEY + "/" + file_id + "." + ext


class _BaseIntegration(unittest.TestCase):
    """Shared throwaway-repo plumbing for real protected-byte integration."""

    @classmethod
    def setUpClass(cls):
        if not OWNER_ROOT or not os.path.isdir(OWNER_ROOT):
            raise unittest.SkipTest(FIXTURE_UNAVAILABLE)
        probe = subprocess.run(
            ["git", "-C", OWNER_ROOT, "cat-file", "-t", PROTECTED_MACRO_SHA],
            capture_output=True, timeout=60,
        )
        if probe.returncode != 0 or probe.stdout.decode().strip() != "commit":
            raise unittest.SkipTest(FIXTURE_UNAVAILABLE)
        cls.parser_text = owner_bytes("scripts/agentos.py")
        cls.compiler_text = owner_bytes("scripts/project_knowledge_recipes.py")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wpkr-test-", dir=tempfile.gettempdir()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "macro"
        self.write_owner_code(self.root)
        self.runner = _RecordingRunner()

    def write_owner_code(self, root):
        (root / "scripts").mkdir(parents=True, exist_ok=True)
        (root / "scripts" / "agentos.py").write_text(self.parser_text, encoding="utf-8")
        (root / "scripts" / "project_knowledge_recipes.py").write_text(
            self.compiler_text, encoding="utf-8")

    def fresh_repo(self):
        """A second throwaway repo; every prepared leg pins its own HEAD."""
        root = self.tmp / ("macro-" + str(len(list(self.tmp.iterdir()))))
        root.mkdir()
        self.write_owner_code(root)
        return root

    def commit(self, extra_files=(), ws_text=None, dec_text=None,
               include_compiler=True, include_ws=True, root=None):
        root = self.root if root is None else root
        files = [
            ("scripts/agentos.py", self.parser_text),
            ("agentos/decisions/DEC-EARLIER-CALL.md", earlier_decision()),
        ]
        if include_ws:
            files.append((_WS_PATH,
                          canonical_workstream() if ws_text is None else ws_text))
        if include_compiler:
            files.insert(1, ("scripts/project_knowledge_recipes.py",
                             self.compiler_text))
        if dec_text is not None:
            files.append((_DECISION_PATH, dec_text))
        files.extend(extra_files)
        for relative, text in files:
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        git(root, "init", "-q", ".")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "fixtures")
        return git(root, "rev-parse", "HEAD").strip()

    def compile(self, request, commit, actor_ref=ACTOR_REF,
                permission_binding_digest=BINDING_DIGEST,
                decision_date=DECISION_DATE, root=None, **kwargs):
        return compile_project_knowledge_recipe(
            macro_root=self.root if root is None else root,
            expected_macro_sha=commit,
            request=request,
            actor_ref=actor_ref,
            permission_binding_digest=permission_binding_digest,
            decision_date=decision_date,
            runner=self.runner,
            **kwargs,
        )

    def restore(self, request, commit, snapshot, binding, runner=None,
                root=None, **kwargs):
        return restore_project_knowledge_recipe(
            macro_root=self.root if root is None else root,
            expected_macro_sha=commit,
            request=request,
            actor_ref=ACTOR_REF,
            permission_binding_digest=BINDING_DIGEST,
            initial_snapshot=snapshot,
            source_binding=binding,
            runner=self.runner if runner is None else runner,
            **kwargs,
        )


class CompileSignature(unittest.TestCase):
    """The closed public API: no module, callback, compiler, or code-body
    parameter can ever be forged onto it."""

    def test_signature_is_closed_typed_tuple(self):
        compile_params = inspect.signature(compile_project_knowledge_recipe).parameters
        self.assertEqual(
            set(compile_params),
            {"macro_root", "expected_macro_sha", "request", "actor_ref",
             "permission_binding_digest", "decision_date", "runner", "timeout", "code_root", "code_commit"},
        )
        restore_params = inspect.signature(restore_project_knowledge_recipe).parameters
        self.assertEqual(
            set(restore_params),
            {"macro_root", "expected_macro_sha", "request", "actor_ref",
             "permission_binding_digest", "initial_snapshot", "source_binding",
             "runner", "timeout", "code_root", "code_commit"},
        )
        for value in compile_params.values():
            self.assertIs(value.kind, inspect.Parameter.KEYWORD_ONLY)
        for value in restore_params.values():
            self.assertIs(value.kind, inspect.Parameter.KEYWORD_ONLY)

    def test_module_does_not_export_a_public_reader_path(self):
        import control_plane.agentos_project_knowledge_recipe as module

        public = [name for name in module.__all__]
        self.assertEqual(
            sorted(public),
            ["compile_project_knowledge_recipe", "restore_project_knowledge_recipe"],
        )


class CompilePositive(_BaseIntegration):

    def test_display_names_follow_actual_utf8_case_insensitive_owner_law(self):
        commit = self.commit()
        for name,media,suffix in [("计划.md","text/markdown","md"),
                                   ("notes.MD","text/markdown","md"),
                                   ("notes (final).txt","text/plain","txt")]:
            with self.subTest(name=name):
                request=_file_request(name,"Literal 中文\r\n")
                request["source_commit"]=commit
                request["base_revision"]=sha256_text(canonical_workstream())
                request["file"]["media_type"]=media
                capture=self.compile(request,commit)
                file=next(image for image in capture["recipe"]["postimages"] if image["path"].startswith("agentos/project-files/"))
                self.assertTrue(file["path"].endswith("."+suffix))
                self.assertEqual(file["content_utf8"],request["file"]["content_utf8"])
                self.assertIn(name,next(image for image in capture["recipe"]["postimages"] if image["path"].startswith("agentos/workstreams/"))["content_utf8"])
        for name in ["计"*42+".md","bad\nname.md","../private.md","notes.exe"]:
            with self.subTest(rejected=name):
                request=_file_request(name,"Literal")
                request["source_commit"]=commit
                request["base_revision"]=sha256_text(canonical_workstream())
                with self.assertRaisesRegex(ValueError,"project_knowledge_recipe_unavailable"):
                    self.compile(request,commit)

    def test_file_add_positive_exact_postimages_and_binding(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        content = "Hello 文件 🌊\r\nsecond line\ttab\r\n"
        request = _file_request("notes.md", content)
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        capture = self.compile(request, commit)
        self.assertEqual(set(capture), {"schema", "recipe", "initial_snapshot", "source_binding"})
        self.assertEqual(capture["schema"], CAPTURE_SCHEMA)
        recipe = capture["recipe"]
        self.assertEqual(recipe["schema"], "mastermind.project_knowledge_recipe.v1")
        self.assertEqual(recipe["state"], "DRAFT_ONLY")
        self.assertEqual(recipe["action"], "project_file_add")
        self.assertEqual(recipe["work_ref"], WORK_REF)
        self.assertEqual(recipe["request_id"], request["request_id"])
        self.assertEqual(recipe["captured_commit"], commit)
        self.assertEqual(recipe["permission_binding_digest"], BINDING_DIGEST)
        media_path = derived_media_path(request)
        self.assertEqual(
            [image["path"] for image in recipe["postimages"]],
            [media_path, _WS_PATH],
        )
        media, ws_post = recipe["postimages"]
        self.assertEqual(media["content_utf8"], content)  # literal CRLF + CJK + emoji
        self.assertEqual(media["content_sha256"], sha256_text(content))
        self.assertIsNone(media["expected_preimage_sha256"])
        self.assertEqual(ws_post["content_sha256"], sha256_text(ws_post["content_utf8"]))
        self.assertEqual(ws_post["expected_preimage_sha256"], sha256_text(ws_text))
        self.assertIn("project_files:", ws_post["content_utf8"])
        self.assertIn("- file_id: ", ws_post["content_utf8"])
        self.assertEqual(
            capture["initial_snapshot"],
            {"workstream_text": ws_text, "decision_text": None,
             "decision_date": DECISION_DATE},
        )
        binding = capture["source_binding"]
        self.assertEqual(set(binding), {"compiler", "owner"})
        for role, path, text in (
            ("compiler", "scripts/project_knowledge_recipes.py", self.compiler_text),
            ("owner", "scripts/agentos.py", self.parser_text),
        ):
            self.assertEqual(
                binding[role],
                {"repository": REPOSITORY, "commit": commit, "path": path,
                 "content_sha256": sha256_text(text)},
            )
        encoded = json.dumps(capture, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":"))
        self.assertLessEqual(len(encoded.encode("utf-8")), CAPTURE_LIMIT)

    def test_file_add_readonly_git_only_and_sanitized_env(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        request = _file_request("notes.txt", "plain 情報\r\n")
        request["file"]["media_type"] = "text/plain"
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        before_env = dict(os.environ)
        self.compile(request, commit)
        self.assertEqual(dict(os.environ), before_env)
        self.assertTrue(self.runner.commands)
        for argv, env in zip(self.runner.commands, self.runner.envs):
            self.assertEqual(argv[:4], ["git", "--no-optional-locks",
                                        "--no-replace-objects", "-C"])
            self.assertIn(argv[5], _READ_COMMANDS)
            git_keys = {key for key in env if key.upper().startswith("GIT_")}
            self.assertEqual(
                git_keys, {"GIT_NO_LAZY_FETCH", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM"}
            )
            self.assertEqual(env["GIT_NO_LAZY_FETCH"], "1")
            self.assertEqual(env["GIT_CONFIG_GLOBAL"], os.devnull)
            self.assertEqual(env["GIT_CONFIG_SYSTEM"], os.devnull)

    def test_preference_new_positive(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        request = _preference_request("Daily two-line summaries.", sha256_text(ws_text))
        request["source_commit"] = commit
        capture = self.compile(request, commit)
        recipe = capture["recipe"]
        self.assertEqual(recipe["action"], "project_preference_set")
        decision_post, ws_post = recipe["postimages"]
        self.assertEqual(decision_post["path"], _DECISION_PATH)
        self.assertIsNone(decision_post["expected_preimage_sha256"])
        self.assertEqual(capture["initial_snapshot"]["decision_text"], None)
        self.assertIn("Daily two-line summaries.", decision_post["content_utf8"])
        self.assertIn("- DEC:" + _PREFERENCE_DECISION_KEY, ws_post["content_utf8"])

    def test_preference_edit_positive_preserves_origin(self):
        stamp = "c" * 64
        dec_text = preference_decision("Daily two-line summaries.", stamp)
        ws_text = canonical_workstream(with_preference_pointer=True)
        commit = self.commit(dec_text=dec_text, ws_text=ws_text)
        request = _preference_request(
            "Weekly digests 只報 📮", sha256_text(ws_text),
            expected=sha256_text(dec_text), stamp="f" * 40,
        )
        request["source_commit"] = commit
        capture = self.compile(request, commit)
        snapshot = capture["initial_snapshot"]
        self.assertEqual(snapshot["decision_text"], dec_text)
        self.assertEqual(snapshot["workstream_text"], ws_text)
        decision_post = capture["recipe"]["postimages"][0]
        self.assertEqual(decision_post["expected_preimage_sha256"], sha256_text(dec_text))
        self.assertIn("kind: USER_EDIT", decision_post["content_utf8"])
        self.assertIn("Weekly digests 只報 📮", decision_post["content_utf8"])
        self.assertIn("project-authoring-request:" + stamp, decision_post["content_utf8"])

    def test_restore_recompiles_snapshot_without_current_record_reads(self):
        for prepared in self._prepared():
            request = prepared["request"]
            commit = prepared["commit"]
            before = len(prepared["runner"].commands)
            capture = self.restore(
                request, commit, prepared["capture"]["initial_snapshot"],
                prepared["capture"]["source_binding"], runner=prepared["runner"],
                root=prepared["root"],
            )
            self.assertEqual(capture["recipe"], prepared["capture"]["recipe"])
            self.assertEqual(capture["initial_snapshot"], prepared["capture"]["initial_snapshot"])
            self.assertEqual(capture["source_binding"], prepared["capture"]["source_binding"])
            restore_commands = prepared["runner"].commands[before:]
            for argv in restore_commands:
                self.assertIn(argv[5], _READ_COMMANDS)
                if argv[5] == "show":
                    target = argv[-1]
                    self.assertTrue(target.startswith(commit + ":scripts/"), target)

    def test_restore_uses_original_code_when_current_head_advances(self):
        prepared = self._prepared()[0]
        root, original = prepared["root"], prepared["commit"]
        # This later helper must never execute during restoration; the current
        # WS body also deliberately differs from the frozen original snapshot.
        current = self.commit(root=root, ws_text=canonical_workstream() + "\nChanged later.\n",
            extra_files=[("scripts/project_knowledge_recipes.py", "raise RuntimeError('CURRENT CODE MUST NOT RUN')\n")])
        self.assertNotEqual(current, original)
        before = len(prepared["runner"].commands)
        restored = self.restore(prepared["request"], current,
            prepared["capture"]["initial_snapshot"], prepared["capture"]["source_binding"],
            runner=prepared["runner"], root=root)
        self.assertEqual(restored, prepared["capture"])
        commands = prepared["runner"].commands[before:]
        self.assertTrue(any("merge-base" in argv for argv in commands))
        for argv in commands:
            if "show" in argv:
                self.assertTrue(argv[-1].startswith(original + ":scripts/"), argv)

    def test_restore_rejects_nonancestor_original_code(self):
        prepared = self._prepared()[0]
        root = prepared["root"]
        git(root, "checkout", "--orphan", "unrelated", "-q")
        current = self.commit(root=root, ws_text=canonical_workstream() + "\nUnrelated root.\n")
        with self.assertRaisesRegex(ValueError, "project_knowledge_recipe_unavailable"):
            self.restore(prepared["request"], current,
                prepared["capture"]["initial_snapshot"], prepared["capture"]["source_binding"],
                runner=prepared["runner"], root=root)

    def _prepared(self):
        prepared = []
        # Leg one: a file add pinned in its own throwaway repo.
        root = self.fresh_repo()
        commit = self.commit(root=root)
        ws_text = canonical_workstream()
        file_request = _file_request("notes.md", "Hello 文件 🌊\r\n")
        file_request["source_commit"] = commit
        file_request["base_revision"] = sha256_text(ws_text)
        runner = _RecordingRunner()
        prepared.append({
            "commit": commit, "request": file_request, "runner": runner,
            "root": root,
            "capture": compile_project_knowledge_recipe(
                macro_root=root, expected_macro_sha=commit,
                request=file_request, actor_ref=ACTOR_REF,
                permission_binding_digest=BINDING_DIGEST,
                decision_date=DECISION_DATE, runner=runner),
        })
        # Leg two: a preference edit pinned in another throwaway repo.
        root = self.fresh_repo()
        stamp = "c" * 64
        dec_text = preference_decision("Daily two-line summaries.", stamp)
        ws_text = canonical_workstream(with_preference_pointer=True)
        commit = self.commit(root=root, dec_text=dec_text, ws_text=ws_text)
        pref_request = _preference_request(
            "Weekly digests.", sha256_text(ws_text),
            expected=sha256_text(dec_text), stamp="f" * 40,
        )
        pref_request["source_commit"] = commit
        runner = _RecordingRunner()
        prepared.append({
            "commit": commit, "request": pref_request, "runner": runner,
            "root": root,
            "capture": compile_project_knowledge_recipe(
                macro_root=root, expected_macro_sha=commit,
                request=pref_request, actor_ref=ACTOR_REF,
                permission_binding_digest=BINDING_DIGEST,
                decision_date=DECISION_DATE, runner=runner),
        })
        return prepared


class CompileRefusals(_BaseIntegration):

    UNAVAILABLE = "project_knowledge_recipe_unavailable"

    def _refused(self, callable_thing):
        with self.assertRaises(ValueError) as caught:
            callable_thing()
        self.assertEqual(str(caught.exception), self.UNAVAILABLE)
        self.assertIsInstance(caught.exception, ValueError)

    def test_hostile_extra_fields_refused_before_any_read(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        request["hostile"] = {"paths": ["/etc"], "grant": "all"}
        self._refused(lambda: self.compile(request, commit))
        self.assertEqual(self.runner.commands, [])

    def test_wrong_schema_stamp_and_commit_refused_before_any_read(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        wrong_schema = _file_request("notes.md", "x")
        wrong_schema["schema"] = "mastermind.project_file_add_request.v2"
        wrong_schema["source_commit"] = commit
        wrong_schema["base_revision"] = sha256_text(ws_text)
        self._refused(lambda: self.compile(wrong_schema, commit))
        bad_stamp = _file_request("notes.md", "x")
        bad_stamp["request_id"] = "mmos-project-file-add-not-a-stamp"
        bad_stamp["source_commit"] = commit
        bad_stamp["base_revision"] = sha256_text(ws_text)
        self._refused(lambda: self.compile(bad_stamp, commit))
        changed_cas = _file_request("notes.md", "x")
        changed_cas["source_commit"] = "f" * 40
        changed_cas["base_revision"] = sha256_text(ws_text)
        self._refused(lambda: self.compile(changed_cas, commit))
        self.assertEqual(self.runner.commands, [])

    def test_head_movement_refuses(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        (self.root / "scripts" / "agentos.py").write_text(
            self.parser_text + "\n# moved\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "moved")
        self._refused(lambda: self.compile(request, commit))
        self.assertEqual(len(self.runner.commands), 1)
        self.assertEqual(self.runner.commands[0][5], "rev-parse")

    def test_symlinked_code_refuses(self):
        link = self.root / "scripts" / "project_knowledge_recipes.py"
        link.unlink()
        os.symlink("agentos.py", link)
        commit = self.commit(include_compiler=False)
        listing = git(self.root, "ls-tree", commit, "scripts/project_knowledge_recipes.py")
        self.assertTrue(listing.startswith("120000 blob "), listing)
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        self._refused(lambda: self.compile(request, commit))

    def test_missing_code_refuses(self):
        (self.root / "scripts" / "project_knowledge_recipes.py").unlink()
        commit = self.commit(include_compiler=False)
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        self._refused(lambda: self.compile(request, commit))

    def test_oversized_code_and_workstream_refuse(self):
        commit = self.commit(
            extra_files=[("scripts/project_knowledge_recipes.py",
                          self.compiler_text + "\n#" + "x" * (CODE_LIMIT + 64))])
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        self._refused(lambda: self.compile(request, commit))
        commit = self.commit(
            ws_text=canonical_workstream().replace(
                "Knowledge capture workstream body.",
                "Knowledge capture workstream body. " + "詰" * WS_LIMIT))
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(
            canonical_workstream().replace(
                "Knowledge capture workstream body.",
                "Knowledge capture workstream body. " + "詰" * WS_LIMIT))
        self._refused(lambda: self.compile(request, commit))

    def test_invalid_utf8_workstream_refuses(self):
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        target = self.root / "agentos" / "workstreams" / ("WS-" + KEY + ".md")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(ws_text.encode("utf-8").replace(b"body.", b"b\xff\xfed."))
        git(self.root, "init", "-q", ".")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "fixtures")
        commit = git(self.root, "rev-parse", "HEAD").strip()
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        self._refused(lambda: self.compile(request, commit))

    def test_missing_workstream_refuses(self):
        commit = self.commit(include_ws=False)
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(canonical_workstream())
        self._refused(lambda: self.compile(request, commit))

    def test_preimage_collision_refuses(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text + "tampered")
        self._refused(lambda: self.compile(request, commit))

    def test_existing_media_path_refuses_and_never_overwrites(self):
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        media_path = derived_media_path(request)
        target = self.root / media_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("already recorded", encoding="utf-8")
        commit = self.commit()
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        listing = git(self.root, "ls-tree", commit, media_path)
        self.assertIn("100644 blob", listing)
        self._refused(lambda: self.compile(request, commit))
        result = git(self.root, "show", commit + ":" + _WS_PATH)
        self.assertNotIn('"file_id"', result)

    def test_preference_conflicts_refuse(self):
        stamp = "c" * 64
        dec_text = preference_decision("Daily two-line summaries.", stamp)
        ws_text = canonical_workstream(with_preference_pointer=True)
        commit = self.commit(dec_text=dec_text, ws_text=ws_text)
        request = _preference_request(
            "Weekly digests.", sha256_text(ws_text), expected=None, stamp="f" * 40)
        request["source_commit"] = commit
        self._refused(lambda: self.compile(request, commit))
        request = _preference_request(
            "Weekly digests.", sha256_text(ws_text),
            expected=sha256_text(dec_text)[:-1] + "0", stamp="f" * 40)
        request["source_commit"] = commit
        self._refused(lambda: self.compile(request, commit))

    def test_oversized_decision_record_refuses(self):
        stamp = "c" * 64
        dec_text = preference_decision("Daily two-line summaries.", stamp)
        big_body = dec_text + "\n" + "\u8a3b" * DECISION_LIMIT
        ws_text = canonical_workstream(with_preference_pointer=True)
        commit = self.commit(dec_text=big_body, ws_text=ws_text)
        request = _preference_request(
            "Weekly digests.", sha256_text(ws_text),
            expected=sha256_text(big_body), stamp="f" * 40)
        request["source_commit"] = commit
        self._refused(lambda: self.compile(request, commit))

    def test_ambient_git_environment_is_sanitized(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "ambient\r\n")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        poison = {
            "GIT_DIR": str(self.tmp / "elsewhere.git"),
            "GIT_WORK_TREE": str(self.tmp),
            "GIT_INDEX_FILE": str(self.tmp / "index"),
            "GIT_OBJECT_DIRECTORY": str(self.tmp / "objects"),
            "GIT_NO_LAZY_FETCH": "0",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "url.file:///tmp/poison.insteadOf",
            "GIT_CONFIG_VALUE_0": str(self.root),
            "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(self.tmp / "alt"),
        }
        before = dict(os.environ)
        try:
            os.environ.update(poison)
            capture = self.compile(request, commit)
        finally:
            os.environ.clear()
            os.environ.update(before)
        self.assertEqual(capture["recipe"]["action"], "project_file_add")
        self.assertEqual(dict(os.environ), before)
        for env in self.runner.envs:
            for key in poison:
                if key == "GIT_NO_LAZY_FETCH":
                    # Re-pinned by the engine itself, never inherited.
                    self.assertEqual(env["GIT_NO_LAZY_FETCH"], "1")
                else:
                    self.assertNotIn(key, env)

    def test_timeout_and_binding_shapes_refuse_without_reads(self):
        commit = self.commit()
        ws_text = canonical_workstream()
        request = _file_request("notes.md", "x")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        self._refused(lambda: self.compile(request, commit, timeout=0))
        self._refused(lambda: self.compile(request, commit, timeout=16))
        self._refused(lambda: self.compile(request, commit, timeout=True))
        self._refused(lambda: self.compile(
            request, commit, actor_ref="workspace:zz"))
        self._refused(lambda: self.compile(
            request, commit, permission_binding_digest="DD" * 32))
        self._refused(lambda: self.compile(request, commit, decision_date="2026-02-30"))
        self.assertEqual(self.runner.commands, [])


class RestoreRefusals(_BaseIntegration):

    UNAVAILABLE = "project_knowledge_recipe_unavailable"

    def setUp(self):
        super().setUp()
        self.commit_sha = self.commit()
        self.ws_text = canonical_workstream()
        self.request = _file_request("notes.md", "restore 文 🌊\r\n")
        self.request["source_commit"] = self.commit_sha
        self.request["base_revision"] = sha256_text(self.ws_text)
        self.capture = compile_project_knowledge_recipe(
            macro_root=self.root, expected_macro_sha=self.commit_sha,
            request=self.request, actor_ref=ACTOR_REF,
            permission_binding_digest=BINDING_DIGEST,
            decision_date=DECISION_DATE, runner=_RecordingRunner())
        self.snapshot = copy.deepcopy(self.capture["initial_snapshot"])
        self.binding = copy.deepcopy(self.capture["source_binding"])

    def _refused(self, callable_thing):
        with self.assertRaises(ValueError) as caught:
            callable_thing()
        self.assertEqual(str(caught.exception), self.UNAVAILABLE)

    def test_tampered_source_binding_refuses(self):
        self.binding["owner"]["content_sha256"] = "0" * 64
        self._refused(lambda: self.restore(self.request, self.commit_sha,
                                           self.snapshot, self.binding))
        self.binding = copy.deepcopy(self.capture["source_binding"])
        self.binding["owner"]["commit"] = "f" * 40
        self._refused(lambda: self.restore(self.request, self.commit_sha,
                                           self.snapshot, self.binding))
        self.binding = copy.deepcopy(self.capture["source_binding"])
        self.binding["owner"]["path"] = "scripts/other.py"
        self._refused(lambda: self.restore(self.request, self.commit_sha,
                                           self.snapshot, self.binding))
        self.binding = copy.deepcopy(self.capture["source_binding"])
        self.binding["compiler"]["repository"] = "other/market-intelligence"
        self._refused(lambda: self.restore(self.request, self.commit_sha,
                                           self.snapshot, self.binding))
        self.binding = copy.deepcopy(self.capture["source_binding"])
        self.binding["extra"] = {}
        self._refused(lambda: self.restore(self.request, self.commit_sha,
                                           self.snapshot, self.binding))

    def test_tampered_actor_stamp_and_snapshot_refuse(self):
        self.snapshot["decision_date"] = "2026-02-30"
        with self.assertRaises(ValueError) as caught:
            restore_project_knowledge_recipe(
                macro_root=self.root, expected_macro_sha=self.commit_sha,
                request=self.request, actor_ref=ACTOR_REF,
                permission_binding_digest=BINDING_DIGEST,
                initial_snapshot=self.snapshot, source_binding=self.binding,
                runner=_RecordingRunner())
        self.assertEqual(str(caught.exception), self.UNAVAILABLE)
        self.snapshot = copy.deepcopy(self.capture["initial_snapshot"])
        self.snapshot["workstream_text"] = self.snapshot["workstream_text"] + " "
        self._refused(lambda: self.restore(self.request, self.commit_sha,
                                           self.snapshot, self.binding))
        self.snapshot = copy.deepcopy(self.capture["initial_snapshot"])
        self.snapshot["extra"] = 1
        self._refused(lambda: self.restore(self.request, self.commit_sha,
                                           self.snapshot, self.binding))
        self._refused(lambda: restore_project_knowledge_recipe(
            macro_root=self.root, expected_macro_sha=self.commit_sha,
            request=self.request, actor_ref="workspace:" + "z" * 64,
            permission_binding_digest=BINDING_DIGEST,
            initial_snapshot=self.snapshot, source_binding=self.binding,
            runner=_RecordingRunner()))

    def test_preference_restore_with_wrong_expected_revision_refuses(self):
        stamp = "c" * 64
        dec_text = preference_decision("Daily two-line summaries.", stamp)
        ws_text = canonical_workstream(with_preference_pointer=True)
        root = self.fresh_repo()
        commit = self.commit(root=root, dec_text=dec_text, ws_text=ws_text)
        request = _preference_request(
            "Weekly digests.", sha256_text(ws_text),
            expected=sha256_text(dec_text), stamp="f" * 40)
        request["source_commit"] = commit
        capture = compile_project_knowledge_recipe(
            macro_root=root, expected_macro_sha=commit, request=request,
            actor_ref=ACTOR_REF, permission_binding_digest=BINDING_DIGEST,
            decision_date=DECISION_DATE, runner=_RecordingRunner())
        bad = copy.deepcopy(request)
        bad["expected_preference_revision"] = sha256_text(dec_text)[:-1] + "0"
        self._refused(lambda: restore_project_knowledge_recipe(
            macro_root=root, expected_macro_sha=commit, request=bad,
            actor_ref=ACTOR_REF, permission_binding_digest=BINDING_DIGEST,
            initial_snapshot=capture["initial_snapshot"],
            source_binding=capture["source_binding"],
            runner=_RecordingRunner()))

    def test_restore_refuses_when_head_moved(self):
        (self.root / "scripts" / "agentos.py").write_text(
            self.parser_text + "\n# moved\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "moved")
        self._refused(lambda: self.restore(self.request, self.commit_sha,
                                           self.snapshot, self.binding))


class EntryChild(unittest.TestCase):
    """The fixed private child: one frame in, one capture line out."""

    @classmethod
    def setUpClass(cls):
        if not OWNER_ROOT or not os.path.isdir(OWNER_ROOT):
            raise unittest.SkipTest(FIXTURE_UNAVAILABLE)
        try:
            from control_plane.ceo_boot_packet import bounded_subprocess_runner  # noqa: F401
        except ImportError:
            raise unittest.SkipTest(
                "installed bounded runner unavailable on this host")
        cls.entry = REPO_ROOT / "scripts" / "agentos_project_knowledge_recipe_entry.py"
        if not cls.entry.is_file():
            raise unittest.SkipTest("fixed entry not installed in this tree")

    def _run(self, frame, commit, root, mode="prepare"):
        payload = json.dumps(frame, ensure_ascii=False).encode("utf-8")
        return subprocess.run(
            [sys.executable, str(self.entry),
             "--macro-root", str(root),
             "--expected-macro-sha", commit,
             "--mode", mode, "--timeout", "10"],
            input=payload, capture_output=True, timeout=120,
        )

    def test_prepare_child_emits_one_canonical_capture(self):
        tmp = Path(tempfile.mkdtemp(prefix="wpkr-child-", dir=tempfile.gettempdir()))
        self.addCleanup(shutil.rmtree, tmp, True)
        root = tmp / "macro"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "agentos.py").write_text(
            owner_bytes("scripts/agentos.py"), encoding="utf-8")
        (root / "scripts" / "project_knowledge_recipes.py").write_text(
            owner_bytes("scripts/project_knowledge_recipes.py"), encoding="utf-8")
        ws_text = canonical_workstream()
        (root / "agentos" / "workstreams").mkdir(parents=True)
        (root / "agentos" / "workstreams" / ("WS-" + KEY + ".md")).write_text(
            ws_text, encoding="utf-8")
        env = dict(os.environ, **_GIT_ENV, GIT_AUTHOR_DATE=COMMIT_DATE,
                   GIT_COMMITTER_DATE=COMMIT_DATE)
        subprocess.run(["git", "init", "-q", "."], cwd=root, env=env,
                       capture_output=True, timeout=60)
        subprocess.run(["git", "add", "-A"], cwd=root, env=env,
                       capture_output=True, timeout=60)
        subprocess.run(["git", "commit", "-q", "-m", "fixtures"], cwd=root,
                       env=env, capture_output=True, timeout=60)
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                                capture_output=True, timeout=60
                                ).stdout.decode().strip()
        request = _file_request("notes.md", "child 文 🌊\r\n")
        request["source_commit"] = commit
        request["base_revision"] = sha256_text(ws_text)
        frame = {
            "schema": "mastermind.project_knowledge_recipe_capture_request.v1",
            "request": request,
            "trusted": {"actor_ref": ACTOR_REF,
                        "permission_binding_digest": BINDING_DIGEST,
                        "decision_date": DECISION_DATE},
        }
        result = self._run(frame, commit, root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        lines = result.stdout.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        capture = json.loads(lines[0])
        self.assertEqual(capture["schema"], CAPTURE_SCHEMA)
        self.assertEqual(capture["recipe"]["state"], "DRAFT_ONLY")
        # restore mode over the same private frame
        frame_restore = dict(frame)
        frame_restore["initial_snapshot"] = capture["initial_snapshot"]
        frame_restore["source_binding"] = capture["source_binding"]
        result = self._run(frame_restore, commit, root, mode="restore")
        self.assertEqual(result.returncode, 0, result.stderr)
        restored = json.loads(result.stdout.decode("utf-8").splitlines()[0])
        self.assertEqual(restored["recipe"], capture["recipe"])

    def test_hostile_frames_refuse_with_no_stdout(self):
        commit = "a" * 40
        root = Path(tempfile.gettempdir())
        frame = {
            "schema": "mastermind.project_knowledge_recipe_capture_request.v1",
            "request": {"any": "thing"},
            "trusted": {"actor_ref": ACTOR_REF,
                        "permission_binding_digest": BINDING_DIGEST,
                        "decision_date": DECISION_DATE},
        }
        result = self._run(frame, commit, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        self.assertEqual(result.stderr, b"project_knowledge_recipe_unavailable\n")
        bad_trusted = dict(frame)
        bad_trusted["trusted"] = {"actor_ref": "workspace:open",
                                  "permission_binding_digest": BINDING_DIGEST,
                                  "decision_date": DECISION_DATE}
        result = self._run(bad_trusted, commit, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        extra = dict(frame)
        extra["provider"] = "choose-one"
        result = self._run(extra, commit, root)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")
        result = subprocess.run(
            [sys.executable, str(self.entry), "--macro-root", str(root),
             "--expected-macro-sha", commit, "--mode", "prepare"],
            input=b"{not json", capture_output=True, timeout=60,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")


if __name__ == "__main__":
    unittest.main()


class SeparateCodeData(_BaseIntegration):
    """Real immutable canonical code C and independent retained DATA N."""
    def separated(self):
        code=self.commit()
        data=self.tmp/"data"
        git(self.tmp,"clone",str(self.root),str(data))
        ws=canonical_workstream()+"\nDATA N body retained independently.\n"
        (data/_WS_PATH).write_text(ws)
        # Future DATA tree code is never activated by this private compiler.
        (data/COMPILER_RELATIVE).write_text("raise RuntimeError('DATA CODE MUST NOT EXECUTE')\n")
        git(data,"add","-A");git(data,"commit","-m","Synthetic DATA generation N")
        current=git(data,"rev-parse","HEAD").strip()
        request=_file_request("计划.MD","Exact DATA file 中文\r\n")
        request.update(source_commit=current,base_revision=sha256_text(ws))
        return code,data,current,request

    def test_code_c_data_n_next_edit_and_original_restore(self):
        code,data,current,request=self.separated()
        capture=self.compile(request,current,root=data,code_root=self.root,code_commit=code)
        self.assertEqual(capture["recipe"]["captured_commit"],current)
        self.assertEqual({ref["commit"] for ref in capture["source_binding"].values()},{code})
        self.assertIn("DATA N body",capture["initial_snapshot"]["workstream_text"])
        for argv in self.runner.commands:
            if argv[5]=="show" and ":scripts/" in argv[-1]:
                self.assertEqual(argv[4],str(self.root));self.assertTrue(argv[-1].startswith(code+":"))
        # Separate normal upstream landing of the actual fixed compiler's two
        # postimages in the synthetic DATA Git; configured code root stays C.
        for image in capture["recipe"]["postimages"]:
            path=data/image["path"];path.parent.mkdir(parents=True,exist_ok=True);path.write_text(image["content_utf8"])
        git(data,"add","-A");git(data,"commit","-m","Synthetic canonical source landing")
        next_commit=git(data,"rev-parse","HEAD").strip()
        ws=(data/_WS_PATH).read_text()
        preference=_preference_request("Literal next preference\n中文",sha256_text(ws))
        preference["source_commit"]=next_commit
        second=self.compile(preference,next_commit,root=data,code_root=self.root,code_commit=code)
        self.assertEqual(second["recipe"]["captured_commit"],next_commit)
        self.assertEqual({ref["commit"] for ref in second["source_binding"].values()},{code})
        self.assertIn("DATA N body",second["initial_snapshot"]["workstream_text"])
        restored=self.restore(request,next_commit,capture["initial_snapshot"],capture["source_binding"],
            root=data,code_root=self.root,code_commit=code)
        self.assertEqual(restored,capture)
        self.assertEqual(git(self.root,"rev-parse","HEAD").strip(),code)

    def test_unpaired_or_foreign_code_pin_refuses(self):
        code,data,current,request=self.separated()
        for flags in [{"code_root":self.root},{"code_commit":code},{"code_root":self.root,"code_commit":current}]:
            with self.subTest(flags=flags),self.assertRaisesRegex(ValueError,"project_knowledge_recipe_unavailable"):
                self.compile(request,current,root=data,**flags)

    def test_code_head_movement_during_capture_refuses(self):
        code,data,current,request=self.separated()
        moved=[False]
        def runner(argv,**kwargs):
            result=self.runner(argv,**kwargs)
            if not moved[0] and argv[4]==str(self.root) and argv[5]=="show" and argv[-1]==code+":"+COMPILER_RELATIVE:
                moved[0]=True;(self.root/"moved.txt").write_text("new configured code head\n")
                git(self.root,"add","moved.txt");git(self.root,"commit","-m","Move code pin during capture")
            return result
        with self.assertRaisesRegex(ValueError,"project_knowledge_recipe_unavailable"):
            compile_project_knowledge_recipe(macro_root=data,expected_macro_sha=current,request=request,
                actor_ref=ACTOR_REF,permission_binding_digest=BINDING_DIGEST,decision_date=DECISION_DATE,
                code_root=self.root,code_commit=code,runner=runner)
        self.assertTrue(moved[0])

    def test_real_fixed_child_executes_code_c_and_reads_data_n(self):
        code,data,current,request=self.separated()
        frame={"schema":"mastermind.project_knowledge_recipe_capture_request.v1","request":request,
            "trusted":{"actor_ref":ACTOR_REF,"permission_binding_digest":BINDING_DIGEST,"decision_date":DECISION_DATE}}
        result=subprocess.run([sys.executable,str(REPO_ROOT/"scripts/agentos_project_knowledge_recipe_entry.py"),
            "--macro-root",str(data),"--expected-macro-sha",current,"--mode","prepare",
            "--code-root",str(self.root),"--code-commit",code],input=json.dumps(frame).encode(),capture_output=True,timeout=120)
        self.assertEqual(result.returncode,0,result.stderr)
        capture=json.loads(result.stdout)
        self.assertEqual(capture["recipe"]["captured_commit"],current)
        self.assertEqual(capture["source_binding"]["compiler"]["commit"],code)
        self.assertIn("DATA N body",capture["initial_snapshot"]["workstream_text"])

    def test_nominal_adapter_preserves_code_refs_c_and_cas_n(self):
        from unittest.mock import patch
        from control_plane.installed_project_knowledge_compiler import InstalledProjectKnowledgeCompiler
        from integrations.mastermind_workspace_app.knowledge_recipe_adapter import ProjectKnowledgeRecipeAdapter
        from tests.test_knowledge_publisher_events import granted
        code,data,current,request=self.separated()
        _,_,who,contexts=granted("add_project_file",{"work_ref":"WS:ALPHA","permission_digest":"3"*64})
        permission=contexts.bind(who,action="add_project_file",work_ref="WS:ALPHA")
        facade=InstalledProjectKnowledgeCompiler(macro_root=data)
        # Explicit test bridge only; actual nominal installed issuance remains
        # the S7 collector owner, never inferred from this callback or metadata.
        def read(_facade,*,mode,request,actor_ref,permission_binding_digest,decision_date,initial_snapshot,source_binding):
            common=dict(macro_root=data,expected_macro_sha=current,request=request,actor_ref=actor_ref,
                permission_binding_digest=permission_binding_digest,code_root=self.root,code_commit=code,runner=self.runner)
            return (compile_project_knowledge_recipe(**common,decision_date=decision_date) if mode=="prepare" else
                restore_project_knowledge_recipe(**common,initial_snapshot=initial_snapshot,source_binding=source_binding))
        with patch.object(InstalledProjectKnowledgeCompiler,"_read",read):
            adapter=ProjectKnowledgeRecipeAdapter(facade)
            prepared=adapter.prepare(request=request,principal=who,permission=permission,decision_date=DECISION_DATE)
            self.assertEqual(adapter.recipe(prepared)["captured_commit"],current)
            self.assertEqual({ref["commit"] for ref in prepared.private_payload()["source_binding"].values()},{code})
            restored=adapter.restore(private_payload=prepared.private_payload(),trusted_recipe_fingerprint=prepared.fingerprint_sha256,
                principal=who,permission=permission)
            self.assertEqual(adapter.recipe(restored),adapter.recipe(prepared))


COMPILER_RELATIVE="scripts/project_knowledge_recipes.py"
