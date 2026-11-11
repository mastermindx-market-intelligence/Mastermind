"""Tests for the redacted PBR decision-case fixtures (schema pbr.decision_case_fixture.v1).

Stdlib only. The fixtures are redacted, provenance-pinned extracts of
production decision rows (capture 2026-10-22T073549Z, manifest sha256
4c55f3f8...); the builder ``_build_decision_cases.py`` must regenerate every
fixture byte-for-byte from the original capture extracts.

Seat ruling SR-1: narrative / PM prose is never committed. Every
whitespace-bearing string in ``records``, ``fills`` and ``derived`` is a
``pbr.prose_digest.v1`` object; the originals stay outside the repository and
the tests that need them run only when PBR_DECISION_CASE_INPUT_DIR is set.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
FIXTURE_DIR = TESTS_DIR / "fixtures" / "pbr" / "decision_cases"
BUILDER = FIXTURE_DIR / "_build_decision_cases.py"

SCHEMA = "pbr.decision_case_fixture.v1"
MANIFEST_SHA256 = "4c55f3f8df454ecfcb2742b0b7bec5043ac35d4919a66026888541fa4bf976aa"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
DECISION_ID = re.compile(r"^decision\.v1\.[0-9a-f]{24}$")
PROSE_DIGEST = "pbr.prose_digest.v1"
DECLARED_TERMS = ["earnings", "held_without_active_plan", "no live thesis", "single-source", "starter"]
DIGEST_KEYS = {"redacted", "sha256", "length", "iso_dates", "period_labels", "terms"}
# Builder-authored sections that may keep whitespace-bearing strings verbatim.
BUILDER_AUTHORED = {"capture", "redaction", "linkage_note", "external_facts"}
DOC = FIXTURE_DIR.parent / "DECISION_CASES.md"
LEAK_MIN_CHARS = 24

EXPECTED = {
    "mu_2026-10-02_entry": ("regression", "A14", "MU"),
    "mu_2026-10-05_amendment": ("regression", "A15", "MU"),
    "mu_2026-10-22_planless_summary": ("regression", "A15", "MU"),
    "cn_688062_2026-08-12_sizing": ("regression", "A16", "688062.SS"),
    "xom_2026-08-12_positive_control": ("positive_control", "none", "XOM"),
}

# Byte-regeneration needs the original (non-redacted) capture extracts, which are
# evidence, not repository content. Point PBR_DECISION_CASE_INPUT_DIR at a directory
# holding case_rows.jsonl, case_fills.jsonl and the capture MANIFEST.json to run it.
INPUT_DIR = Path(os.environ.get("PBR_DECISION_CASE_INPUT_DIR", "/nonexistent/pbr-decision-case-inputs"))
INPUTS = (INPUT_DIR / "case_rows.jsonl", INPUT_DIR / "case_fills.jsonl", INPUT_DIR / "MANIFEST.json")


def load(case_id: str) -> dict:
    return json.loads((FIXTURE_DIR / f"{case_id}.json").read_text(encoding="utf-8"))


def all_fixtures() -> dict:
    return {case_id: load(case_id) for case_id in EXPECTED}


def record_by_line(fixture: dict, line_index: int) -> dict:
    for record in fixture["records"]:
        if record["line_index_0based"] == line_index:
            return record
    raise AssertionError(f"line {line_index} not among records")


def is_digest(value) -> bool:
    return isinstance(value, dict) and value.get("redacted") == PROSE_DIGEST


def walk(obj, path=()):
    """Yield (path, leaf) for every digest object and every non-container leaf."""
    if is_digest(obj):
        yield path, obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from walk(value, path + (key,))
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            yield from walk(value, path + (index,))
    else:
        yield path, obj


def has_whitespace(value) -> bool:
    return isinstance(value, str) and any(ch.isspace() for ch in value)


PATH_TOKEN = re.compile(r"\.?([A-Za-z_]+)(?:@(\d+))?|\[(\d+)\]")


def resolve(fixture: dict, path: str):
    """Resolve a DECISION_CASES.md field path; ``records@N`` selects by line index."""
    current = fixture
    for key, line, index in PATH_TOKEN.findall(path):
        if key:
            current = current[key]
            if line:
                current = record_by_line({"records": current}, int(line))
        else:
            current = current[int(index)]
    return current


def doc_digest_rows() -> dict:
    """Map case_id -> [(path, sha12, length, iso_dates, period_labels, terms)] from the doc tables."""
    rows: dict = {}
    case_id = None
    for line in DOC.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"^## (\S+)\.json ", line)
        if heading:
            case_id = heading.group(1)
            rows[case_id] = []
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if case_id and len(cells) == 6 and re.fullmatch(r"`[0-9a-f]{12}`", cells[1]):
            def listed(cell):
                return [] if cell == "—" else [item.strip().strip("`") for item in cell.split(",")]

            path, sha12 = cells[0].strip("`"), cells[1].strip("`")
            rows[case_id].append((path, sha12, int(cells[2]), listed(cells[3]), listed(cells[4]), listed(cells[5])))
    return rows


def require_inputs(test: unittest.TestCase) -> None:
    if not all(path.exists() for path in INPUTS):
        test.skipTest(
            f"original capture extracts not present at {INPUT_DIR} (set PBR_DECISION_CASE_INPUT_DIR); "
            "they are evidence kept outside the public repository (SR-1)"
        )


def original_prose() -> dict:
    """sha256 -> original text for every whitespace-bearing string in the input rows and fills.

    Also indexes the ``". "``-split sentences, which ``derived.summary_and_memo_sentences`` digests.
    """
    found: dict = {}
    for path in INPUTS[:2]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for _, leaf in walk(json.loads(line)["row"]):
                if not has_whitespace(leaf):
                    continue
                for text in [leaf] + [part.strip() for part in leaf.split(". ")]:
                    if has_whitespace(text):
                        found[hashlib.sha256(text.encode("utf-8")).hexdigest()] = text
    return found


class DecisionCaseFixtureTests(unittest.TestCase):
    def test_all_five_fixtures_load_with_schema_case_id_and_role(self):
        for case_id, (role, defect_ref, ticker) in EXPECTED.items():
            with self.subTest(case_id=case_id):
                fixture = load(case_id)
                self.assertEqual(fixture["schema"], SCHEMA)
                self.assertEqual(fixture["case_id"], case_id)
                self.assertEqual(fixture["case_role"], role)
                self.assertEqual(fixture["defect_ref"], defect_ref)
                self.assertEqual(fixture["ticker"], ticker)
                self.assertEqual(fixture["capture"]["manifest_sha256"], MANIFEST_SHA256)
                for key in (
                    "capture",
                    "provenance",
                    "redaction",
                    "records",
                    "fills",
                    "linkage_note",
                    "external_facts",
                    "derived",
                    "records_sha256",
                ):
                    self.assertIn(key, fixture)

    def test_provenance_hashes_are_hex64_and_decision_ids_match(self):
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                self.assertTrue(fixture["provenance"])
                for prov in fixture["provenance"]:
                    self.assertRegex(prov["line_sha256"], HEX64)
                    self.assertRegex(prov["source_file_sha256"], HEX64)
                    self.assertRegex(prov["decision_id"], DECISION_ID)
                for fill in fixture["fills"]:
                    self.assertRegex(fill["line_sha256"], HEX64)

    def test_records_sha256_recomputes(self):
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                payload = json.dumps(
                    fixture["records"], sort_keys=True, ensure_ascii=False, separators=(",", ":")
                )
                self.assertEqual(hashlib.sha256(payload.encode("utf-8")).hexdigest(), fixture["records_sha256"])

    def test_redaction_dropped_perception_input_and_filtered_holdings(self):
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                for record in fixture["records"]:
                    self.assertNotIn("perception_input", record["row"])
                    # Filtered to the case ticker; legitimately empty when the
                    # case ticker was exited out of that record's holdings.
                    self.assertTrue(
                        all(h["ticker"] == fixture["ticker"] for h in record["row"]["holdings"])
                    )
                    self.assertTrue(
                        all(h["ticker"] == fixture["ticker"] for h in record["row"]["effective_holdings"])
                    )

    def test_mu_entry_falsifier_names_2026_10_22_and_external_fact_predates_asof(self):
        fixture = load("mu_2026-10-02_entry")
        record = record_by_line(fixture, 75)
        falsifier = record["case_holding"]["falsifier"]
        self.assertTrue(is_digest(falsifier))
        self.assertIn("2026-10-22", falsifier["iso_dates"])
        self.assertIn("Q4 FY2026", falsifier["period_labels"])
        asof = date.fromisoformat(record["row"]["asof"])
        dated = [f for f in fixture["external_facts"] if "event_date" in f]
        self.assertTrue(dated)
        self.assertTrue(
            any(date.fromisoformat(f["event_date"]) < asof for f in dated),
            "expected an external fact with event_date before the record asof",
        )
        for fact in fixture["external_facts"]:
            self.assertEqual(fact["verification_status"], "cited_by_audit_not_refetched")

    def test_mu_entry_fills_are_exactly_the_settlement_linked_ones(self):
        fixture = load("mu_2026-10-02_entry")
        record = record_by_line(fixture, 75)
        linked_ids = set(record["row"]["settlement_fill_ids"])
        fill_ids = {f["row"]["fill_id"] for f in fixture["fills"]}
        self.assertTrue(fill_ids)
        self.assertEqual(fill_ids, fill_ids & linked_ids)
        for fill in fixture["fills"]:
            self.assertEqual(fill["linked_decision_ids"], [record["decision_id"]])

    def test_mu_amendment_records_falsifier_and_exit_plan_changes(self):
        fixture = load("mu_2026-10-05_amendment")
        changes = fixture["derived"]["case_holding_changes"]
        self.assertIn("falsifier", changes)
        self.assertIn("exit_plan", changes)
        self.assertNotEqual(changes["falsifier"]["old"], changes["falsifier"]["new"])
        self.assertNotEqual(changes["exit_plan"]["old"], changes["exit_plan"]["new"])
        # The dated, quarter-specific falsifier was replaced by one naming no date.
        self.assertEqual(changes["falsifier"]["old"]["iso_dates"], ["2026-10-22"])
        self.assertEqual(changes["falsifier"]["new"]["iso_dates"], [])
        falsifier_changes = fixture["derived"]["case_row_falsifier_changes"]
        self.assertNotEqual(falsifier_changes["old"], falsifier_changes["new"])
        self.assertEqual(fixture["fills"], [])

    def test_planless_summary_mu_absent_and_planless_sentence_present(self):
        fixture = load("mu_2026-10-22_planless_summary")
        record_89 = record_by_line(fixture, 89)
        self.assertIsNone(record_89["case_holding"])
        self.assertIsNone(record_89["case_effective_holding"])
        self.assertFalse(fixture["derived"]["ticker_in_holdings"]["89"])
        sentences = fixture["derived"]["summary_and_memo_sentences"]
        self.assertTrue(
            any(
                {"held_without_active_plan", "no live thesis"} & set(s["sentence"]["terms"])
                for s in sentences
                if s["line_index_0based"] == 89
            )
        )
        reasons = [e["entry"]["reason"] for e in fixture["derived"]["mu_exit_decisions"]]
        self.assertTrue(any("no live thesis" in reason["terms"] for reason in reasons))
        self.assertTrue(fixture["derived"]["mu_exit_decisions"])
        self.assertTrue(fixture["derived"]["mu_requested_exit_decisions"])

    def test_cn_688062_weight_is_medium_cap_and_rationale_says_starter(self):
        fixture = load("cn_688062_2026-08-12_sizing")
        record_35 = record_by_line(fixture, 35)
        self.assertEqual(record_35["case_holding"]["weight"], 0.12)
        self.assertEqual(record_35["case_holding"]["conviction"], "medium")
        self.assertIn("starter", record_35["case_holding"]["rationale"]["terms"])
        self.assertIn("single-source", record_35["case_holding"]["rationale"]["terms"])
        cap_reference = fixture["derived"]["cap_reference"]
        self.assertEqual(cap_reference["file"], "brain/decision_submission.py")
        self.assertEqual(cap_reference["line"], 450)
        self.assertEqual(cap_reference["caps"], {"high": 0.18, "medium": 0.12, "low": 0.06})
        self.assertIn('"conviction_caps"', cap_reference["quote"])

    def test_xom_positive_control_has_records_and_both_fills(self):
        fixture = load("xom_2026-08-12_positive_control")
        self.assertEqual([r["line_index_0based"] for r in fixture["records"]], [38, 39, 40])
        self.assertTrue(all(r["case_holding"]["ticker"] == "XOM" for r in fixture["records"]))
        self.assertTrue(record_by_line(fixture, 38)["case_holding"]["falsifier"]["sha256"].startswith("b3278894a5b4"))
        self.assertTrue(all(f["row"]["ticker"] == "XOM" for f in fixture["fills"]))
        self.assertEqual(sorted(f["row"]["fill_id"][:8] for f in fixture["fills"]), ["8d9c94d7", "a805e529"])
        linked = {f["row"]["fill_id"][:8]: f["linked_decision_ids"] for f in fixture["fills"]}
        self.assertEqual(linked["a805e529"], [])
        self.assertEqual(linked["8d9c94d7"], [record_by_line(fixture, 40)["decision_id"]])

    def test_no_prose_outside_builder_authored_sections(self):
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                leaks = [
                    path
                    for path, leaf in walk(fixture)
                    if has_whitespace(leaf)
                    and path[0] not in BUILDER_AUTHORED
                    and path[:2] != ("derived", "cap_reference")
                ]
                self.assertEqual(leaks, [])
                self.assertTrue(any(is_digest(leaf) for _, leaf in walk(fixture["records"])))

    def test_prose_digests_are_well_formed(self):
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                policy = fixture["redaction"]["prose_digest"]
                self.assertEqual(policy["schema"], PROSE_DIGEST)
                self.assertEqual(policy["declared_terms"], DECLARED_TERMS)
                for path, leaf in walk(fixture):
                    if not is_digest(leaf):
                        continue
                    self.assertEqual(set(leaf), DIGEST_KEYS, path)
                    self.assertRegex(leaf["sha256"], HEX64)
                    self.assertIsInstance(leaf["length"], int)
                    self.assertGreaterEqual(leaf["length"], 3)
                    for iso in leaf["iso_dates"]:
                        date.fromisoformat(iso)
                    self.assertEqual(len(leaf["iso_dates"]), len(set(leaf["iso_dates"])))
                    self.assertEqual(leaf["terms"], [t for t in DECLARED_TERMS if t in leaf["terms"]])

    def test_decision_cases_doc_digest_tables_match_fixtures(self):
        text = DOC.read_text(encoding="utf-8")
        self.assertNotIn("Decisive quotes (verbatim)", text)
        rows = doc_digest_rows()
        self.assertEqual(sorted(rows), sorted(EXPECTED))
        for case_id, entries in rows.items():
            with self.subTest(case_id=case_id):
                self.assertTrue(entries)
                fixture = load(case_id)
                for path, sha12, length, iso_dates, period_labels, terms in entries:
                    digest = resolve(fixture, path)
                    self.assertTrue(is_digest(digest), path)
                    self.assertEqual(digest["sha256"][:12], sha12, path)
                    self.assertEqual(digest["length"], length, path)
                    self.assertEqual(digest["iso_dates"], iso_dates, path)
                    self.assertEqual(digest["period_labels"], period_labels, path)
                    self.assertEqual(digest["terms"], terms, path)

    def test_every_digest_matches_an_original_prose_string(self):
        require_inputs(self)
        originals = original_prose()
        for case_id, fixture in all_fixtures().items():
            with self.subTest(case_id=case_id):
                policy = fixture["redaction"]["prose_digest"]
                iso = re.compile(policy["iso_date_pattern"])
                period = re.compile(policy["period_label_pattern"])
                for path, leaf in walk(fixture):
                    if not is_digest(leaf):
                        continue
                    self.assertIn(leaf["sha256"], originals, path)
                    text = originals[leaf["sha256"]]
                    self.assertEqual(leaf["length"], len(text), path)
                    self.assertEqual(leaf["iso_dates"], list(dict.fromkeys(iso.findall(text))), path)
                    self.assertEqual(leaf["period_labels"], list(dict.fromkeys(period.findall(text))), path)
                    self.assertEqual(
                        leaf["terms"], [t for t in DECLARED_TERMS if t in text.lower()], path
                    )

    def test_no_original_prose_is_committed_under_fixtures(self):
        require_inputs(self)
        corpus_parts = []
        for path in sorted(FIXTURE_DIR.parent.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            corpus_parts.append(text)
            if path.suffix == ".json":
                corpus_parts.extend(leaf for _, leaf in walk(json.loads(text)) if isinstance(leaf, str))
        corpus = "\n".join(corpus_parts)
        leaked = sorted(
            {
                text[:40]
                for text in original_prose().values()
                if len(text) >= LEAK_MIN_CHARS and text in corpus
            }
        )
        self.assertEqual(leaked, [], "original production prose found in committed fixture files")

    def test_regeneration_reproduces_identical_bytes(self):
        require_inputs(self)
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "decision_cases"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(BUILDER),
                    str(INPUTS[0]),
                    str(INPUTS[1]),
                    str(INPUTS[2]),
                    str(out_dir),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for case_id in EXPECTED:
                regenerated = (out_dir / f"{case_id}.json").read_bytes()
                committed = (FIXTURE_DIR / f"{case_id}.json").read_bytes()
                self.assertEqual(
                    regenerated, committed, f"{case_id}.json does not regenerate byte-for-byte"
                )


if __name__ == "__main__":
    unittest.main()
