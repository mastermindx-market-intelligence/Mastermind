"""Tests for the workspace project knowledge contract and capture modules.

Two honest tiers, kept separate by name:

* Synthetic contract tests (``Contract*Tests``, ``Refusal*Tests``) run in any
  normal repository checkout: they need only ``common`` and ``control_plane``
  and never fake a parser or a common module.
* Real-source integration tests (``Integration*Tests``) exercise the actual
  Macro validator and the actual f55 knowledge recipes.  They import both from
  the tree named by ``MM_TEST_MACRO_OWNER_ROOT`` (the parent sets it to the
  actual Macro checkout) and copy the actual ``scripts/agentos.py`` into a
  throwaway Git repository, so positive authority is the real parser, never a
  stub embedded here.  When that variable is absent, exactly those tests skip
  with an honest reason and the synthetic tier still runs.

The tests never mutate global interpreter state: no ``sys.modules`` fakes, no
timezone changes, no ambient Git configuration.  Every fixture lives in a
throwaway temp Git repository created with explicit author/committer
environments, and every Git clock in the fixtures is a fixed, real instant
with a non-UTC offset so UTC normalization is observable.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from common.workspace_project_knowledge_contract import (
    CATALOGUE_SCHEMA,
    MAX_DISPLAY_NAME,
    MAX_MATCHED_RECORDS,
    MAX_MEMORY_VALUE,
    MAX_SCANNED_RECORDS,
    MAX_SOURCE_BODY,
    PREFERENCE_SCHEMA,
    SOURCE_SCHEMA,
    ContractInvalid,
    empty_memory,
    unavailable_catalogue,
    unavailable_memory,
    unavailable_source,
    validate_catalogue,
    validate_memory,
    validate_preference_payload,
    validate_selection,
    validate_source,
)
from control_plane.agentos_project_knowledge import (
    PREFERENCE_KEY_PREFIX,
    read_project_communication_preference,
    read_project_knowledge_catalogue,
    read_project_knowledge_source,
)
from control_plane.ceo_boot_packet import bounded_subprocess_runner

OWNER_ROOT = Path(os.environ.get("MM_TEST_MACRO_OWNER_ROOT", "") or "")
HAS_OWNER_PARSER = OWNER_ROOT.is_dir() and (OWNER_ROOT / "scripts" / "agentos.py").is_file()
HAS_OWNER_RECIPES = HAS_OWNER_PARSER and (
    OWNER_ROOT / "scripts" / "project_knowledge_recipes.py"
).is_file()
_SKIP_PARSER = (
    "MM_TEST_MACRO_OWNER_ROOT with scripts/agentos.py not provided — "
    "real-Macro-parser integration skipped; synthetic contract tests still run"
)
_SKIP_RECIPES = (
    "MM_TEST_MACRO_OWNER_ROOT with scripts/project_knowledge_recipes.py not "
    "provided — real-recipe postimage integration skipped"
)

WORK_REF = "WS:ALPHA"
PREFERENCE_KEY = PREFERENCE_KEY_PREFIX + "ALPHA"
PREFERENCE_PATH = "agentos/decisions/DEC-" + PREFERENCE_KEY + ".md"
COMMIT_STAMP = "b" * 40
ACTOR = "workspace:" + "a" * 64
PREFERENCE_VALUE = "以后请用中文写周报。"
# A real instant with a non-UTC offset; normalization must yield 06:30:00Z.
COMMIT_DATE = "2026-02-01T12:00:00+05:30"
COMMIT_DATE_UTC = "2026-02-01T06:30:00Z"

FILE_NAME = "notes.md"
FILE_BODY = "# uploaded notes\n\n中文 body line.\n"


def hex_(count, seed):
    return (seed * count)[:count]


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_workstream():
    """A canonical WS record the actual parser accepts."""
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
        "- DEC:EARLIER-CALL\n"
        "artifacts:\n"
        "- research/notes.md\n"
        "---\n\n"
        "Knowledge capture workstream body.\n"
    )


def canonical_decision():
    return (
        "---\n"
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
        "decided_at: 2026-01-10\n"
        "---\n\n"
        "Recorded earlier.\n"
    )


def canonical_discovery():
    return (
        "---\n"
        "key: PARSER-LANDMINE\n"
        "claim: The captured parser validates canonical records.\n"
        "falsifier: python3 scripts/agentos.py validate exits non-zero\n"
        "so_what: Readers reuse the parser.\n"
        "kind: architecture\n"
        "verified_at: 2026-01-15\n"
        "verified_by: scripts/agentos.py validate\n"
        "scope:\n"
        "- WS:ALPHA\n"
        "confidence: verified\n"
        "---\n\n"
        "Evidence, not policy.\n"
    )


def canonical_handoff():
    return (
        "---\n"
        "workstream: WS:ALPHA\n"
        "session: s1\n"
        "model: fable\n"
        "mission: Repair the readers.\n"
        "state_before: Readers wrong.\n"
        "changed:\n"
        "- path: control_plane/agentos_project_knowledge.py\n"
        "  what: Repaired capture.\n"
        "verified:\n"
        "- command: python3 -m pytest tests/test_agentos_project_knowledge.py\n"
        "unverified: []\n"
        "unresolved:\n"
        "- Nothing open.\n"
        "next_actions:\n"
        "- The currently assigned receiver must run the suite and reconcile drift.\n"
        "do_not_redo:\n"
        "- Do not rebuild the parser.\n"
        "danger_areas:\n"
        "- Budget trips.\n"
        "ended_because: complete\n"
        "---\n\n"
        "Handoff body.\n"
    )


def decision_named(key, body_line):
    """A canonical decision associated with WS:ALPHA and nothing else."""
    return (
        "---\n"
        "key: " + key + "\n"
        "question: Question " + key + "?\n"
        "answer: Answer " + key + ".\n"
        "rationale: Rationale " + key + ".\n"
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
        "decided_at: 2026-01-11\n"
        "---\n\n"
        + body_line + "\n"
    )


GIT_ENV = {
    "GIT_AUTHOR_NAME": "chairman",
    "GIT_AUTHOR_EMAIL": "c@example.invalid",
    "GIT_COMMITTER_NAME": "chairman",
    "GIT_COMMITTER_EMAIL": "c@example.invalid",
}


def git(root, *argv, date=None):
    env = dict(os.environ, **GIT_ENV)
    if date is not None:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    result = subprocess.run(
        ["git", *argv], cwd=root, env=env, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(argv), result.stderr))
    return result.stdout


def build_repo(root, files, commit_date=COMMIT_DATE):
    """A throwaway immutable-at-pin Macro-shaped Git repository."""
    scripts = root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OWNER_ROOT / "scripts" / "agentos.py", scripts / "agentos.py")
    for relative, text in files:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    git(root, "init", "-q", ".")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "fixtures", date=commit_date)
    return git(root, "rev-parse", "HEAD").strip()


def blob_revision(root, commit, path):
    return git(root, "rev-parse", commit + ":" + path).strip()


def load_recipes():
    spec = importlib.util.spec_from_file_location(
        "_mmos_owner_project_knowledge_recipes",
        OWNER_ROOT / "scripts" / "project_knowledge_recipes.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _BaseIntegration(unittest.TestCase):
    """Shared throwaway-repo plumbing for real-parser integration tests."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wpk-test-", dir=tempfile.gettempdir()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = self.tmp / "macro"
        self.root.mkdir()

    def _canonical_files(self, artifacts=None, decisions=None, extra=()):
        ws = canonical_workstream()
        if artifacts is not None or decisions is not None:
            lines = ws.splitlines(True)
            if artifacts is not None:
                start = lines.index("artifacts:\n")
                end = next(i for i in range(start + 1, len(lines))
                           if not lines[i].startswith("- "))
                lines[start + 1:end] = ["- " + entry + "\n" for entry in artifacts]
            if decisions is not None:
                start = lines.index("decisions:\n")
                end = next(i for i in range(start + 1, len(lines))
                           if not lines[i].startswith("- "))
                lines[start + 1:end] = ["- DEC:" + key + "\n" for key in decisions]
            ws = "".join(lines)
        files = [
            ("agentos/workstreams/WS-ALPHA.md", ws),
            ("agentos/decisions/DEC-EARLIER-CALL.md", canonical_decision()),
            ("agentos/discoveries/DSC-PARSER-LANDMINE.md", canonical_discovery()),
            ("agentos/handoffs/HND-ALPHA-2026-02-01.md", canonical_handoff()),
            ("research/notes.md", "# notes\n\ncaptured artifact body.\n"),
        ]
        files.extend(extra)
        return files

    def build(self, files, commit_date=COMMIT_DATE):
        self.commit = build_repo(self.root, files, commit_date=commit_date)
        return self.commit

    def catalogue(self, commit=None, work_ref=WORK_REF, runner=bounded_subprocess_runner):
        return read_project_knowledge_catalogue(
            macro_root=self.root,
            expected_macro_sha=commit or self.commit,
            work_ref=work_ref,
            runner=runner,
        )

    def preference(self, commit=None, work_ref=WORK_REF, runner=bounded_subprocess_runner):
        return read_project_communication_preference(
            macro_root=self.root,
            expected_macro_sha=commit or self.commit,
            work_ref=work_ref,
            runner=runner,
        )

    def open_source(self, source_ref, expected_revision, commit=None, work_ref=WORK_REF):
        return read_project_knowledge_source(
            macro_root=self.root,
            expected_macro_sha=commit or self.commit,
            work_ref=work_ref,
            source_ref=source_ref,
            expected_revision=expected_revision,
            runner=bounded_subprocess_runner,
        )

    def assertUnavailable(self, dto, reason):
        self.assertEqual(dto["availability"], "UNAVAILABLE")
        self.assertEqual(dto["reason_codes"], [reason])
        self.assertIsNone(dto.get("source"))
        self.assertIsNone(dto.get("project"))
        self.assertIsNone(dto.get("document"))
        self.assertIsNone(dto.get("memory"))


class ContractSelectionTests(unittest.TestCase):
    """Closed contract tier: canonical colon refs and scalar rules."""

    def test_canonical_colon_work_ref(self):
        self.assertEqual(validate_selection("WS:ALPHA"), "WS:ALPHA")
        self.assertEqual(validate_selection("WS:PROJECT-COMMUNICATION-PREFERENCE-ALPHA"),
                         "WS:PROJECT-COMMUNICATION-PREFERENCE-ALPHA")
        long_key = "A" * 64
        self.assertEqual(validate_selection("WS:" + long_key), "WS:" + long_key)

    def test_work_ref_rejects_dash_and_bad_shapes(self):
        for bad in (
            "WS-ALPHA",
            "ALPHA",
            "ws:alpha",
            "WS:alpha",
            "WS:A",
            "WS:" + "A" * 65,
            "WS:ALPHA X",
            "WS:ALPHA:",
            "WS:",
            "",
            None,
            7,
        ):
            with self.assertRaises(ContractInvalid):
                validate_selection(bad)

    def test_preference_key_is_dynamic(self):
        self.assertEqual(PREFERENCE_KEY_PREFIX + "ALPHA",
                         "PROJECT-COMMUNICATION-PREFERENCE-ALPHA")
        self.assertNotIn("PREFERENCE-KEY", PREFERENCE_KEY_PREFIX + "ALPHA")

    def test_control_characters_reflected_everywhere(self):
        catalogue = {
            "schema": CATALOGUE_SCHEMA,
            "selection": {"work_ref": "WS:ALPHA"},
            "availability": "AVAILABLE",
            "reason_codes": [],
            "source": {
                "repository": "mastermindx-market-intelligence/macro",
                "commit": "a" * 40,
                "workstream_sha256": sha256_text("ws"),
            },
            "project": {
                "title": "bad\x00title",
                "files": [],
                "records": [],
                "memory": {"state": "EMPTY", "source_ref": None, "revision": None},
                "coverage": {
                    "files": {"state": "COMPLETE", "declared": 0, "listed": 0, "omitted": 0},
                    "records": {
                        "state": "BOUNDED_SAMPLE",
                        "scanned": 1,
                        "matched": 0,
                        "omitted": 0,
                        "invalid": 0,
                    },
                },
            },
        }
        with self.assertRaises(ContractInvalid):
            validate_catalogue(catalogue)
        for bad in ("\x01", "\x1f", "\x7f", "\u0080", "\u009f"):
            catalogue["project"]["title"] = "bad" + bad + "title"
            with self.assertRaises(ContractInvalid):
                validate_catalogue(catalogue)
        for good in ("\n", "\r", "\t"):
            catalogue["project"]["title"] = "line" + good + "break"
            self.assertEqual(validate_catalogue(catalogue)["project"]["title"],
                             "line" + good + "break")

    def test_byte_budgets_are_utf8_bytes(self):
        payload = {
            "schema": "agentos.project_preference.v1",
            "work_ref": "WS:ALPHA",
            "kind": "COMMUNICATION",
            "value": "中" * 666,  # 1998 UTF-8 bytes
            "origin": {"kind": "USER_EDIT", "actor_ref": ACTOR,
                       "source_ref": None, "source_revision": None},
            "last_edit": {"actor_ref": ACTOR, "request_sha256": hex_(64, "c")},
        }
        self.assertEqual(validate_preference_payload(payload)["value"], "中" * 666)
        payload["value"] = "中" * 667  # 2001 UTF-8 bytes
        with self.assertRaises(ContractInvalid):
            validate_preference_payload(payload)
        payload["value"] = "x" * (MAX_MEMORY_VALUE + 1)
        with self.assertRaises(ContractInvalid):
            validate_preference_payload(payload)

    def test_source_document_body_hash_and_budget(self):
        base = {
            "schema": SOURCE_SCHEMA,
            "selection": {"work_ref": "WS:ALPHA", "source_ref": "project-file.v1." + hex_(64, "f")},
            "availability": "AVAILABLE",
            "reason_codes": [],
            "source": {
                "repository": "mastermindx-market-intelligence/macro",
                "commit": "a" * 40,
                "path": "research/notes.md",
                "revision": "1" * 40,
                "content_sha256": None,
                "committed_at": COMMIT_DATE_UTC,
            },
            "document": {
                "title": "notes.md",
                "media_type": "text/markdown",
                "content_utf8": FILE_BODY,
                "content_sha256": None,
            },
        }
        base["source"]["content_sha256"] = sha256_text(FILE_BODY)
        base["document"]["content_sha256"] = sha256_text(FILE_BODY)
        self.assertEqual(validate_source(base)["document"]["content_utf8"], FILE_BODY)
        base["document"]["content_sha256"] = sha256_text("other")
        with self.assertRaises(ContractInvalid):
            validate_source(base)
        huge = "x" * (MAX_SOURCE_BODY + 1)
        base["document"]["content_utf8"] = huge
        base["document"]["content_sha256"] = sha256_text(huge)
        with self.assertRaises(ContractInvalid):
            validate_source(base)

    def test_memory_origin_shapes(self):
        memory = {
            "schema": PREFERENCE_SCHEMA,
            "selection": {"work_ref": "WS:ALPHA"},
            "availability": "AVAILABLE",
            "reason_codes": [],
            "source": {
                "repository": "mastermindx-market-intelligence/macro",
                "commit": "a" * 40,
                "path": PREFERENCE_PATH,
                "revision": "1" * 40,
                "content_sha256": sha256_text("dec"),
                "committed_at": COMMIT_DATE_UTC,
            },
            "memory": {
                "value": PREFERENCE_VALUE,
                "origin": {"kind": "USER_EDIT", "actor_ref": ACTOR,
                           "source_ref": None, "source_revision": None},
                "last_edit": {"actor_ref": ACTOR, "request_sha256": hex_(64, "c")},
            },
        }
        self.assertEqual(validate_memory(memory)["availability"], "AVAILABLE")
        memory["memory"]["origin"] = {
            "kind": "CONVERSATION",
            "actor_ref": ACTOR,
            "source_ref": "session-reply-" + hex_(64, "5"),
            "source_revision": hex_(64, "7"),
        }
        self.assertEqual(validate_memory(memory)["memory"]["origin"]["kind"], "CONVERSATION")
        memory["memory"]["origin"]["source_ref"] = "session-reply-nothex"
        with self.assertRaises(ContractInvalid):
            validate_memory(memory)
        memory["memory"]["origin"] = {
            "kind": "USER_EDIT", "actor_ref": ACTOR,
            "source_ref": "session-reply-" + hex_(64, "5"), "source_revision": None,
        }
        with self.assertRaises(ContractInvalid):
            validate_memory(memory)

    def test_unavailable_builders_are_closed(self):
        catalogue = unavailable_catalogue("WS:ALPHA", "SOURCE_CHANGED")
        self.assertEqual(catalogue["schema"], CATALOGUE_SCHEMA)
        self.assertIsNone(catalogue["source"])
        self.assertIsNone(catalogue["project"])
        self.assertEqual(catalogue["reason_codes"], ["SOURCE_CHANGED"])
        source = unavailable_source("WS:ALPHA", "project-record.v1." + hex_(64, "1"), "RECORD_NOT_FOUND")
        self.assertIsNone(source["document"])
        self.assertIsNone(source["source"])
        memory = unavailable_memory("WS:ALPHA", "CONFLICT")
        self.assertIsNone(memory["memory"])
        self.assertIsNone(memory["source"])
        empty = empty_memory("WS:ALPHA")
        self.assertEqual(empty["availability"], "EMPTY")
        self.assertEqual(empty["reason_codes"], [])
        self.assertIsNone(empty["source"])
        with self.assertRaises(ContractInvalid):
            unavailable_catalogue("WS:ALPHA", "NOT_A_REASON")
        with self.assertRaises(ContractInvalid):
            unavailable_catalogue("WS-ALPHA", "SOURCE_CHANGED")


class _StubRunner:
    """A bounded-runner double for refusal paths only; never fakes a parser."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        item = self._results[min(len(self.calls) - 1, len(self._results) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def _ok(stdout):
    return {
        "code": 0, "stdout": stdout, "stderr": "",
        "timed_out": False, "limit_exceeded": False, "invalid_utf8": False,
    }


class RefusalCaptureTests(unittest.TestCase):
    """Fail-closed tier: refusal DTOs carry no private payload, anywhere."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wpk-refusal-", dir=tempfile.gettempdir()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.commit = "a" * 40

    def test_missing_root_is_unavailable_for_all_three(self):
        root = self.tmp / "absent"
        for read in (
            read_project_knowledge_catalogue,
            read_project_communication_preference,
        ):
            dto = read(macro_root=root, expected_macro_sha=self.commit,
                       work_ref=WORK_REF, runner=bounded_subprocess_runner)
            self.assertEqual(dto["availability"], "UNAVAILABLE")
            self.assertEqual(dto["reason_codes"], ["SOURCE_UNAVAILABLE"])
            self.assertIsNone(dto.get("source"))
            self.assertIsNone(dto.get("project"))
            self.assertIsNone(dto.get("memory"))
        source = read_project_knowledge_source(
            macro_root=root, expected_macro_sha=self.commit, work_ref=WORK_REF,
            source_ref="project-file.v1." + hex_(64, "1"),
            expected_revision=self.commit, runner=bounded_subprocess_runner,
        )
        self.assertEqual(source["reason_codes"], ["SOURCE_UNAVAILABLE"])
        self.assertIsNone(source["document"])

    def test_bad_arguments_fail_closed(self):
        with self.assertRaises(ContractInvalid):
            read_project_knowledge_catalogue(
                macro_root=self.tmp, expected_macro_sha=self.commit,
                work_ref="WS-ALPHA", runner=bounded_subprocess_runner,
            )
        with self.assertRaises(ContractInvalid):
            read_project_knowledge_source(
                macro_root=self.tmp, expected_macro_sha=self.commit,
                work_ref=WORK_REF, source_ref="not-a-ref",
                expected_revision=self.commit, runner=bounded_subprocess_runner,
            )
        with self.assertRaises(ContractInvalid):
            read_project_knowledge_source(
                macro_root=self.tmp, expected_macro_sha=self.commit,
                work_ref=WORK_REF, source_ref="project-file.v1." + hex_(64, "1"),
                expected_revision="zzz", runner=bounded_subprocess_runner,
            )
        for sha in ("a" * 39, "A" * 40, "", None, 5):
            dto = read_project_knowledge_catalogue(
                macro_root=self.tmp, expected_macro_sha=sha,
                work_ref=WORK_REF, runner=bounded_subprocess_runner,
            )
            self.assertEqual(dto["reason_codes"], ["SOURCE_UNAVAILABLE"])
        for timeout in (0, -1, 16, True, None):
            dto = read_project_knowledge_catalogue(
                macro_root=self.tmp, expected_macro_sha=self.commit,
                work_ref=WORK_REF, runner=bounded_subprocess_runner, timeout=timeout,
            )
            self.assertEqual(dto["reason_codes"], ["SOURCE_UNAVAILABLE"])

    def test_runner_failures_map_to_closed_reasons(self):
        cases = [
            (_StubRunner([OSError("boom")]), "SOURCE_UNAVAILABLE"),
            (_StubRunner([{"code": 1, "stdout": "", "stderr": "x",
                           "timed_out": False, "limit_exceeded": False,
                           "invalid_utf8": False}]), "SOURCE_UNAVAILABLE"),
            (_StubRunner([_ok("0" * 40), {"code": 0, "stdout": "", "stderr": "",
                                          "timed_out": False, "limit_exceeded": True,
                                          "invalid_utf8": False}]), "CONTENT_OVER_BUDGET"),
            (_StubRunner([{"code": 0, "stdout": "", "stderr": "", "timed_out": True,
                           "limit_exceeded": False, "invalid_utf8": False}]), "SOURCE_UNAVAILABLE"),
            (_StubRunner([{"code": 0, "stdout": "", "stderr": "", "timed_out": False,
                           "limit_exceeded": False, "invalid_utf8": True}]), "SOURCE_UNAVAILABLE"),
            (_StubRunner(["not-a-dict"]), "SOURCE_UNAVAILABLE"),
        ]
        for runner, reason in cases:
            dto = read_project_knowledge_catalogue(
                macro_root=self.tmp, expected_macro_sha="0" * 40,
                work_ref=WORK_REF, runner=runner,
            )
            self.assertEqual(dto["reason_codes"], [reason])
            self.assertIsNone(dto["project"])
            self.assertIsNone(dto["source"])

    def test_cumulative_budget_trips_closed(self):
        class _FatRunner(_StubRunner):
            def __call__(self, argv, **kwargs):
                result = super().__call__(argv, **kwargs)
                if result.get("limit_exceeded") or len(self.calls) < 2:
                    return result  # the HEAD read stays truthful
                return dict(result, stdout="x" * (4 * 1048576))

        runner = _FatRunner([_ok("0" * 40)])
        dto = read_project_knowledge_catalogue(
            macro_root=self.tmp, expected_macro_sha="0" * 40,
            work_ref=WORK_REF, runner=runner,
        )
        self.assertIn(dto["reason_codes"][0], ("CONTENT_OVER_BUDGET", "SOURCE_UNAVAILABLE"))
        self.assertIsNone(dto["project"])


class IntegrationKnowledgeTests(_BaseIntegration):
    """Real-Macro-parser tier: positive authority from MM_TEST_MACRO_OWNER_ROOT."""

    def setUp(self):
        if not HAS_OWNER_PARSER:
            self.skipTest(_SKIP_PARSER)
        super().setUp()

    def test_colon_ref_catalogue_utc_and_blob_revisions(self):
        self.build(self._canonical_files())
        dto = self.catalogue()
        self.assertEqual(dto["schema"], CATALOGUE_SCHEMA)
        self.assertEqual(dto["availability"], "AVAILABLE")
        self.assertEqual(dto["selection"], {"work_ref": "WS:ALPHA"})
        self.assertEqual(dto["source"]["commit"], self.commit)
        self.assertEqual(dto["project"]["title"], "Project knowledge capture")
        files = dto["project"]["files"]
        self.assertEqual(len(files), 1)
        row = files[0]
        self.assertEqual(row["path"], "research/notes.md")
        self.assertEqual(row["state"], "READABLE")
        self.assertEqual(row["repository"], "macro")
        self.assertEqual(row["revision"], blob_revision(self.root, self.commit, "research/notes.md"))
        self.assertEqual(row["display_name"], "notes.md")
        self.assertEqual(row["origin"], {"kind": "DECLARED_ARTIFACT", "actor_ref": None,
                                         "request_sha256": None})
        self.assertEqual(row["viewer_relation"], "UNKNOWN")
        records = dto["project"]["records"]
        self.assertEqual([row["kind"] for row in records],
                         ["WORKSTREAM", "DECISION", "DISCOVERY", "HANDOFF"])
        self.assertIsNone(records[0]["authored_at"])
        by_kind = {row["kind"]: row for row in records}
        self.assertEqual(by_kind["DECISION"]["authored_at"], "2026-01-10")
        self.assertEqual(by_kind["DISCOVERY"]["authored_at"], "2026-01-15")
        self.assertIsNone(by_kind["HANDOFF"]["authored_at"])
        self.assertEqual(by_kind["HANDOFF"]["title"],"Repair the readers.")
        self.assertEqual(by_kind["DECISION"]["path"], "agentos/decisions/DEC-EARLIER-CALL.md")
        for row in records:
            self.assertEqual(row["committed_at"], COMMIT_DATE_UTC)
            self.assertTrue(row["committed_at"].endswith("Z"))
            self.assertEqual(row["revision"], blob_revision(self.root, self.commit, row["path"]))
            self.assertRegex(row["source_ref"], r"^project-record\.v1\.[0-9a-f]{64}$")
        coverage = dto["project"]["coverage"]
        self.assertEqual(coverage["files"], {"state": "COMPLETE", "declared": 1,
                                             "listed": 1, "omitted": 0})
        sample = coverage["records"]
        self.assertEqual(sample["state"], "BOUNDED_SAMPLE")
        self.assertEqual(sample["matched"], len(records))
        self.assertGreaterEqual(sample["scanned"], sample["matched"])
        self.assertLessEqual(sample["invalid"], sample["scanned"])
        self.assertEqual(dto["project"]["memory"],
                         {"state": "EMPTY", "source_ref": None, "revision": None})

    def test_open_returns_exact_bytes_hash_and_blob_revision(self):
        self.build(self._canonical_files())
        dto = self.catalogue()
        row = dto["project"]["files"][0]
        document = self.open_source(row["source_ref"], row["revision"])
        self.assertEqual(document["availability"], "AVAILABLE")
        expected = "# notes\n\ncaptured artifact body.\n"
        self.assertEqual(document["document"]["content_utf8"], expected)
        self.assertEqual(document["document"]["content_sha256"], sha256_text(expected))
        self.assertEqual(document["source"]["content_sha256"], sha256_text(expected))
        self.assertEqual(document["source"]["revision"],
                         blob_revision(self.root, self.commit, "research/notes.md"))
        self.assertEqual(document["source"]["committed_at"], COMMIT_DATE_UTC)
        self.assertEqual(document["document"]["media_type"], "text/markdown")

    def test_no_body_on_unknown_ref_or_bad_revision(self):
        self.build(self._canonical_files())
        dto = self.catalogue()
        row = dto["project"]["files"][0]
        stale = self.open_source(row["source_ref"], "0" * 40)
        self.assertUnavailable(stale, "SOURCE_CHANGED")
        foreign = self.open_source("project-file.v1." + hex_(64, "9"), row["revision"])
        self.assertUnavailable(foreign, "RECORD_NOT_FOUND")
        foreign_record = self.open_source("project-record.v1." + hex_(64, "8"), row["revision"])
        self.assertUnavailable(foreign_record, "RECORD_NOT_FOUND")

    def test_cross_repo_artifact_is_never_read(self):
        self.build(self._canonical_files(
            artifacts=[
                "research/notes.md",
                "terminal:app/main.md",
                "https://example.invalid/elsewhere.md",
                "research/absent.md",
                "research/data.json",
                "../../etc/passwd",
                "research\\..\\evil.md",
            ],
            extra=[("research/data.json", "{}\n"), ("app/main.md", "terminal body\n")],
        ))
        dto = self.catalogue()
        self.assertEqual(dto["availability"], "AVAILABLE")
        rows = {row["path"]: row for row in dto["project"]["files"]}
        self.assertEqual(rows["research/notes.md"]["state"], "READABLE")
        terminal = rows["app/main.md"]
        self.assertEqual(terminal["state"], "UNSUPPORTED_SOURCE")
        self.assertEqual(terminal["repository"], "terminal")
        self.assertIsNone(terminal["revision"])
        url = next(row for row in dto["project"]["files"]
                   if row["state"] == "UNSUPPORTED_SOURCE" and row["repository"] is None)
        self.assertIsNone(url["path"])
        self.assertEqual(rows["research/absent.md"]["state"], "SOURCE_MISSING")
        json_row = rows["research/data.json"]
        self.assertEqual(json_row["state"], "UNSUPPORTED_SOURCE")
        self.assertEqual(json_row["repository"], "macro")
        traversal = next(row for row in dto["project"]["files"]
                         if row["state"] == "SOURCE_INVALID")
        self.assertIsNone(traversal["path"])
        self.assertIsNone(traversal["repository"])
        self.assertLessEqual(len(traversal["display_name"]), MAX_DISPLAY_NAME)
        leaked = json.dumps(dto)
        self.assertNotIn("../../etc/passwd", leaked)
        self.assertNotIn("research\\..\\evil.md", leaked)
        self.assertEqual(dto["project"]["coverage"]["files"]["state"], "COMPLETE")
        self.assertEqual(dto["project"]["coverage"]["files"]["declared"], 7)
        for source_ref, reason in (
            (url["source_ref"], "UNSUPPORTED_SOURCE"),
            (terminal["source_ref"], "UNSUPPORTED_SOURCE"),
            (rows["research/absent.md"]["source_ref"], "SOURCE_UNAVAILABLE"),
            (json_row["source_ref"], "UNSUPPORTED_SOURCE"),
            (traversal["source_ref"], "SOURCE_INVALID"),
        ):
            document = self.open_source(source_ref, "0" * 40)
            self.assertEqual(document["reason_codes"], [reason])
            self.assertIsNone(document["document"])

    def test_control_character_body_is_refused_on_open(self):
        self.build(self._canonical_files(
            artifacts=["research/notes.md", "research/secret.md"],
            extra=[("research/secret.md", "safe\u0080line\n")]))
        dto = self.catalogue()
        row = next(row for row in dto["project"]["files"]
                   if row["path"] == "research/secret.md")
        self.assertEqual(row["state"], "READABLE")
        document = self.open_source(row["source_ref"], row["revision"])
        self.assertUnavailable(document, "SOURCE_INVALID")

    def test_bom_and_crlf_bytes_are_preserved(self):
        body = "﻿# Title\r\n\r\nbody line.\r\n"
        self.build(self._canonical_files(
            artifacts=["research/notes.md", "research/bom.md"],
            extra=[("research/bom.md", body)],
        ))
        dto = self.catalogue()
        row = next(row for row in dto["project"]["files"] if row["path"] == "research/bom.md")
        document = self.open_source(row["source_ref"], row["revision"])
        self.assertEqual(document["availability"], "AVAILABLE")
        self.assertEqual(document["document"]["content_utf8"], body)
        self.assertEqual(document["document"]["content_sha256"], sha256_text(body))


    def test_bare_discovery_topic_is_not_an_explicit_workstream_association(self):
        files=self._canonical_files()
        files=[(path,text.replace("- WS:ALPHA\n","- ALPHA\n") if "/discoveries/" in path else text) for path,text in files]
        self.build(files)
        dto=self.catalogue()
        self.assertEqual(dto["availability"],"AVAILABLE")
        self.assertFalse(any(row["kind"]=="DISCOVERY" for row in dto["project"]["records"]))
        self.assertEqual(dto["project"]["coverage"]["records"]["invalid"],0)


class IntegrationRecipeTests(_BaseIntegration):
    """Real-f55-recipe tier: postimages are generated by the actual recipes."""

    def setUp(self):
        if not HAS_OWNER_RECIPES:
            self.skipTest(_SKIP_RECIPES)
        super().setUp()

    def _materialize(self, *, file_content=None, ws_override=None,
                     pref_override=None, skip_pref=False):
        recipes = load_recipes()
        ws_text = canonical_workstream()
        file_req = {
            "schema": recipes.SCHEMA_FILE_ADD_REQUEST,
            "request_id": "mmos-project-file-add-" + hex_(40, "a"),
            "work_ref": WORK_REF,
            "source_commit": COMMIT_STAMP,
            "base_revision": sha256_text(ws_text),
            "file": {"display_name": FILE_NAME, "media_type": "text/markdown",
                     "content_utf8": FILE_BODY},
        }
        recipe = recipes.build_project_file_add(
            file_req, actor_ref=ACTOR, permission_binding_digest=hex_(64, "c"),
            captured_commit=COMMIT_STAMP, workstream_text=ws_text,
        )
        images = {image["path"]: image["content_utf8"] for image in recipe["postimages"]}
        file_ref = recipe["postimages"][0]["path"]
        file_sha = recipe["postimages"][0]["content_sha256"]
        ws_pointer = images["agentos/workstreams/WS-ALPHA.md"]
        ws_final = ws_override if ws_override is not None else ws_pointer
        pref_text = None
        if not skip_pref:
            pref_req = {
                "schema": recipes.SCHEMA_PREFERENCE_SET_REQUEST,
                "request_id": "mmos-project-preference-set-" + hex_(40, "d"),
                "work_ref": WORK_REF,
                "source_commit": COMMIT_STAMP,
                "base_revision": sha256_text(ws_final),
                "expected_preference_revision": None,
                "value": PREFERENCE_VALUE,
            }
            pref_recipe = recipes.build_project_preference_set(
                pref_req, actor_ref=ACTOR, permission_binding_digest=hex_(64, "e"),
                captured_commit=COMMIT_STAMP, workstream_text=ws_final,
                decision_text=None, decision_date="2026-01-20",
            )
            pref_images = {image["path"]: image["content_utf8"]
                           for image in pref_recipe["postimages"]}
            pref_text = pref_override if pref_override is not None else pref_images[PREFERENCE_PATH]
            ws_final = pref_images["agentos/workstreams/WS-ALPHA.md"]
        body = file_content if file_content is not None else FILE_BODY
        self.build(self._canonical_files() [:0] + [
            ("agentos/workstreams/WS-ALPHA.md", ws_final),
            ("agentos/decisions/DEC-EARLIER-CALL.md", canonical_decision()),
            ("agentos/discoveries/DSC-PARSER-LANDMINE.md", canonical_discovery()),
            ("agentos/handoffs/HND-ALPHA-2026-02-01.md", canonical_handoff()),
            ("research/notes.md", "# notes\n\ncaptured artifact body.\n"),
            (file_ref, body),
        ] + ([(PREFERENCE_PATH, pref_text)] if pref_text else []))
        return {"file_ref": file_ref, "file_sha": file_sha, "ws1": ws_pointer}

    def test_recipe_roundtrip_file_and_preference(self):
        self._materialize()
        dto = self.catalogue()
        self.assertEqual(dto["availability"], "AVAILABLE")
        upload = next(row for row in dto["project"]["files"]
                      if row["origin"]["kind"] == "PRINCIPAL_UPLOAD")
        self.assertTrue(upload["path"].startswith("agentos/project-files/WS-ALPHA/"))
        self.assertTrue(upload["path"].endswith(".md"))
        self.assertRegex(upload["path"].split("/")[-1][:-3], r"^[0-9a-f]{64}$")
        self.assertEqual(upload["display_name"], FILE_NAME)
        self.assertEqual(upload["content_sha256"], sha256_text(FILE_BODY))
        self.assertEqual(upload["origin"]["actor_ref"], ACTOR)
        self.assertEqual(upload["revision"], blob_revision(self.root, self.commit, upload["path"]))
        document = self.open_source(upload["source_ref"], upload["revision"])
        self.assertEqual(document["availability"], "AVAILABLE")
        self.assertEqual(document["document"]["content_utf8"], FILE_BODY)
        self.assertEqual(document["document"]["content_sha256"], sha256_text(FILE_BODY))
        self.assertEqual(document["source"]["revision"], upload["revision"])
        preference = self.preference()
        self.assertEqual(preference["availability"], "AVAILABLE")
        self.assertEqual(preference["memory"]["value"], PREFERENCE_VALUE)
        self.assertEqual(preference["memory"]["origin"],
                         {"kind": "USER_EDIT", "actor_ref": ACTOR,
                          "source_ref": None, "source_revision": None})
        self.assertEqual(preference["memory"]["last_edit"]["actor_ref"], ACTOR)
        self.assertEqual(preference["source"]["path"], PREFERENCE_PATH)
        self.assertEqual(preference["source"]["revision"],
                         blob_revision(self.root, self.commit, PREFERENCE_PATH))
        self.assertEqual(preference["source"]["committed_at"], COMMIT_DATE_UTC)
        self.assertEqual(preference["selection"], {"work_ref": "WS:ALPHA"})
        memory = dto["project"]["memory"]
        self.assertEqual(memory["state"], "AVAILABLE")
        self.assertEqual(memory["revision"], blob_revision(self.root, self.commit, PREFERENCE_PATH))
        rows = dto["project"]["records"]
        pref_row = next(row for row in rows if row["kind"] == "PROJECT_PREFERENCE")
        self.assertEqual(memory["source_ref"], pref_row["source_ref"])
        self.assertEqual(pref_row["path"], PREFERENCE_PATH)
        self.assertEqual(pref_row["authored_at"], "2026-01-20")
        self.assertIn("DEC-PROJECT-COMMUNICATION-PREFERENCE-ALPHA", json.dumps(dto))
        self.assertNotIn("PREFERENCE-KEY.md", json.dumps(dto))

    def test_upload_declared_sha_is_checked_against_real_bytes(self):
        self._materialize(file_content=FILE_BODY + "\nextra tail\n")
        dto = self.catalogue()
        upload = next(row for row in dto["project"]["files"]
                      if row["origin"]["kind"] == "PRINCIPAL_UPLOAD")
        self.assertEqual(upload["state"], "READABLE")
        self.assertEqual(upload["content_sha256"], sha256_text(FILE_BODY))
        document = self.open_source(upload["source_ref"], upload["revision"])
        self.assertUnavailable(document, "SOURCE_MISMATCH")

    def test_other_work_preference_is_conflict_never_empty(self):
        self._materialize()
        pref_text = (self.root / PREFERENCE_PATH).read_text(encoding="utf-8")
        self.assertIn("affects:\n- WS:ALPHA\n", pref_text)
        # Keep the canonical fixed-key record but anchor it to another work.
        (self.root / PREFERENCE_PATH).write_text(
            pref_text.replace("affects:\n- WS:ALPHA\n", "affects:\n- WS:BETA\n"),
            encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "other-work", date=COMMIT_DATE)
        head = git(self.root, "rev-parse", "HEAD").strip()
        dto = self.catalogue(commit=head)
        self.assertEqual(dto["availability"], "AVAILABLE")
        self.assertEqual(dto["project"]["memory"]["state"], "UNAVAILABLE")
        preference = self.preference(commit=head)
        self.assertUnavailable(preference, "CONFLICT")

    def test_superseded_preference_is_conflict(self):
        self._materialize()
        pref_text = (self.root / PREFERENCE_PATH).read_text(encoding="utf-8")
        (self.root / PREFERENCE_PATH).write_text(
            pref_text.replace("decided_by:", "superseded_by: DEC:LATER-KEY\ndecided_by:", 1),
            encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "supersede", date=COMMIT_DATE)
        head = git(self.root, "rev-parse", "HEAD").strip()
        preference = self.preference(commit=head)
        self.assertUnavailable(preference, "CONFLICT")

    def test_missing_workstream_pointer_is_conflict(self):
        state = self._materialize()
        # The fixed-key record exists but the WS is the pointerless preimage.
        (self.root / "agentos/workstreams/WS-ALPHA.md").write_text(
            state["ws1"], encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "pointerless", date=COMMIT_DATE)
        head = git(self.root, "rev-parse", "HEAD").strip()
        preference = self.preference(commit=head)
        self.assertUnavailable(preference, "CONFLICT")

    def test_absent_preference_is_empty_with_no_invented_value(self):
        self._materialize(skip_pref=True)
        dto = self.catalogue()
        self.assertEqual(dto["project"]["memory"],
                         {"state": "EMPTY", "source_ref": None, "revision": None})
        preference = self.preference()
        self.assertEqual(preference["availability"], "EMPTY")
        self.assertEqual(preference["reason_codes"], [])
        self.assertIsNone(preference["memory"])
        self.assertIsNone(preference["source"])

    def test_duplicate_upload_metadata_is_conflict(self):
        state = self._materialize()
        ws1 = state["ws1"]
        head, sep, rest = ws1.partition("project_files:\n")
        lines = rest.splitlines(True)
        end = 0
        while end < len(lines) and lines[end].startswith((" ", "-")) \
                and not lines[end].startswith("---"):
            end += 1
        entry = lines[:end]
        duplicated = head + "project_files:\n" + "".join(entry) + "".join(entry) + "".join(lines[end:])
        (self.root / "agentos/workstreams/WS-ALPHA.md").write_text(duplicated, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "duplicate", date=COMMIT_DATE)
        dto = self.catalogue(commit=git(self.root, "rev-parse", "HEAD").strip())
        self.assertUnavailable(dto, "CONFLICT")

    def test_malformed_upload_metadata_is_source_invalid(self):
        state = self._materialize()
        ws1 = state["ws1"]
        broken = ws1.replace("display_name: " + FILE_NAME,
                             "display_name: " + FILE_NAME + "\n  extra_field: x", 1)
        (self.root / "agentos/workstreams/WS-ALPHA.md").write_text(broken, encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "malformed", date=COMMIT_DATE)
        dto = self.catalogue(commit=git(self.root, "rev-parse", "HEAD").strip())
        self.assertUnavailable(dto, "SOURCE_INVALID")


class IntegrationDriftBoundsTests(_BaseIntegration):
    """Drift, bounded-sample and immutability tier over the real parser."""

    def setUp(self):
        if not HAS_OWNER_PARSER:
            self.skipTest(_SKIP_PARSER)
        super().setUp()

    def test_head_drift_before_and_after_with_blob_revision_membership(self):
        self.build(self._canonical_files())
        first = self.catalogue()
        self.assertEqual(first["availability"], "AVAILABLE")
        old_row = first["project"]["files"][0]
        target = self.root / "research" / "notes.md"
        target.write_text("# notes\n\nchanged body.\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "second", date="2026-03-01T09:00:00-08:00")
        new_commit = git(self.root, "rev-parse", "HEAD").strip()
        stale = self.catalogue(commit=self.commit)
        self.assertUnavailable(stale, "SOURCE_CHANGED")
        stale_open = self.open_source(old_row["source_ref"], old_row["revision"],
                                      commit=self.commit)
        self.assertUnavailable(stale_open, "SOURCE_CHANGED")
        second = self.catalogue(commit=new_commit)
        self.assertEqual(second["availability"], "AVAILABLE")
        new_row = second["project"]["files"][0]
        self.assertNotEqual(new_row["revision"], old_row["revision"])
        self.assertNotEqual(new_row["source_ref"], old_row["source_ref"])
        self.assertEqual(new_row["revision"],
                         blob_revision(self.root, new_commit, "research/notes.md"))
        moved = self.open_source(old_row["source_ref"], old_row["revision"], commit=new_commit)
        self.assertUnavailable(moved, "RECORD_NOT_FOUND")
        mixed = self.open_source(new_row["source_ref"], old_row["revision"], commit=new_commit)
        self.assertUnavailable(mixed, "SOURCE_CHANGED")
        good = self.open_source(new_row["source_ref"], new_row["revision"], commit=new_commit)
        self.assertEqual(good["document"]["content_utf8"], "# notes\n\nchanged body.\n")
        self.assertEqual(good["source"]["committed_at"], "2026-03-01T17:00:00Z")

    def test_bounded_sample_window_and_matched_cap(self):
        count = 130
        keys = ["BOUND-%03d" % index for index in range(count)]
        extra = [("agentos/decisions/DEC-%s.md" % key, decision_named(key, "Body %s." % key))
                 for key in keys]
        self.build(self._canonical_files(decisions=["EARLIER-CALL"] + keys, extra=extra))
        dto = self.catalogue()
        coverage = dto["project"]["coverage"]["records"]
        self.assertEqual(coverage["scanned"], MAX_SCANNED_RECORDS)
        self.assertEqual(coverage["matched"], MAX_MATCHED_RECORDS)
        self.assertEqual(coverage["invalid"], 0)
        self.assertGreater(coverage["omitted"], 0)
        self.assertGreaterEqual(coverage["omitted"],
                                coverage["matched"] - len(dto["project"]["records"]))
        rows = dto["project"]["records"]
        self.assertEqual(len(rows), MAX_MATCHED_RECORDS)
        self.assertEqual(rows[0]["kind"], "WORKSTREAM")
        self.assertTrue(all(row["kind"] in {"WORKSTREAM", "DECISION", "DISCOVERY", "HANDOFF",
                                            "PROJECT_PREFERENCE"} for row in rows))

    def test_oversize_file_and_record_are_counted_not_silent(self):
        huge_body = "y" * (MAX_SOURCE_BODY + 900)
        self.build(self._canonical_files(
            artifacts=["research/notes.md", "research/big.md"],
            decisions=["EARLIER-CALL", "HUGE-CALL"],
            extra=[
                ("research/big.md", "# big\n" + "x" * (MAX_SOURCE_BODY + 8000) + "\n"),
                ("agentos/decisions/DEC-HUGE-CALL.md", decision_named("HUGE-CALL", huge_body)),
            ],
        ))
        dto = self.catalogue()
        self.assertEqual(dto["availability"], "AVAILABLE")
        big = next(row for row in dto["project"]["files"] if row["path"] == "research/big.md")
        self.assertEqual(big["state"], "CONTENT_OVER_BUDGET")
        self.assertEqual(big["revision"],
                         blob_revision(self.root, self.commit, "research/big.md"))
        refused = self.open_source(big["source_ref"], big["revision"])
        self.assertUnavailable(refused, "CONTENT_OVER_BUDGET")
        coverage = dto["project"]["coverage"]["records"]
        self.assertEqual(coverage["invalid"], 1)
        self.assertNotIn("DEC-HUGE-CALL.md", json.dumps(dto["project"]["records"]))

    def test_unknown_workstream_reflects_closed_without_leaking(self):
        self.build(self._canonical_files())
        dto = self.catalogue(work_ref="WS:UNRELATED")
        self.assertUnavailable(dto, "RECORD_NOT_FOUND")
        preference = self.preference(work_ref="WS:UNRELATED")
        self.assertUnavailable(preference, "RECORD_NOT_FOUND")
        self.assertNotIn("Project knowledge capture", json.dumps(dto))

    def test_workstream_without_macro_repo_is_source_invalid(self):
        files = self._canonical_files()
        swapped = []
        for relative, body in files:
            if relative == "agentos/workstreams/WS-ALPHA.md":
                body = body.replace("repos:\n- macro\n", "repos:\n- terminal\n")
            swapped.append((relative, body))
        self.build(swapped)
        self.assertUnavailable(self.catalogue(), "SOURCE_INVALID")
        self.assertUnavailable(self.preference(), "SOURCE_INVALID")

    def test_reader_never_mutates_the_source_tree(self):
        self.build(self._canonical_files())
        self.catalogue()
        self.preference()
        dto = self.catalogue()
        row = dto["project"]["files"][0]
        self.open_source(row["source_ref"], row["revision"])
        self.assertEqual(git(self.root, "status", "--porcelain").strip(), "")


def test_arbitrary_actor_labels_are_not_canonical_workspace_principals():
    import copy
    payload={"schema":"agentos.project_preference.v1","work_ref":WORK_REF,"kind":"COMMUNICATION","value":"Literal preference",
        "origin":{"kind":"USER_EDIT","actor_ref":ACTOR,"source_ref":None,"source_revision":None},
        "last_edit":{"actor_ref":ACTOR,"request_sha256":"c"*64}}
    validate_preference_payload(payload)
    for field in ("origin","last_edit"):
        invalid=copy.deepcopy(payload);invalid[field]["actor_ref"]="workspace:principal-alpha"
        try: validate_preference_payload(invalid)
        except ContractInvalid: pass
        else: raise AssertionError("arbitrary actor label accepted")


def test_custom_python_mapping_is_refused_without_dispatching_its_methods():
    calls=[]
    class Custom(dict):
        def items(self): calls.append("items");return super().items()
    try: validate_catalogue(Custom())
    except ContractInvalid: pass
    else: raise AssertionError("custom mapping accepted")
    assert calls==[]
