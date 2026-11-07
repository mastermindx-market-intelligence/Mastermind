"""Actual native archive owner inside inert sealed Git capture; no live records."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import zlib

import pytest

from common import workspace_project_archive_contract as wire
from control_plane import agentos_project_archive as source
from control_plane.installed_project_read_binding import InstalledProjectReadUnavailable
from integrations.executive_mcp.installed import InstalledBootPacketCollector, _default_packet_runner
from integrations.executive_mcp.schemas import GatewayError
from tests.test_installed_product_acceptance_context import fixture
from tests.test_agentos_project_direction_source import WS

WORK = "WS:ARCHIVE-TEST"
ACTIVE = "WS:UNDECLARED-TEST"
REFS = [WORK, ACTIVE]
ARCHIVE = """archive:
  schema: agentos.workstream_archive.v1
  state: ARCHIVED
  archived_on: 2026-11-04
  archived_by: Synthetic archive fixture principal
  reason: Explicit source declaration only.
"""


def record(*, archived=True, status="done"):
    value = WS.replace("DIRECTION-TEST", "ARCHIVE-TEST" if archived else "UNDECLARED-TEST")
    value = value.replace("status: active", "status: " + status)
    return value.replace("decisions: [DEC:CURRENT]\naccepted_direction: DEC:CURRENT\n", ARCHIVE if archived else "")


def bound(tmp_path, monkeypatch, mutation=None, *, archived=True):
    collector, _, seen = fixture(tmp_path)
    macro = seen["macro"]
    data = json.loads((Path(__file__).parent / "fixtures/agentos-project-archive-owner.json").read_bytes())
    for path, item in data["files"].items():
        raw = zlib.decompress(base64.b64decode(item["zlib_base64"], validate=True))
        assert hashlib.sha256(raw).hexdigest() == item["sha256"]
        target = macro / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    for ref, text in [(WORK, record(archived=True) if archived else record(archived=True).replace(ARCHIVE, "")),
                      (ACTIVE, record(archived=False))]:
        (macro / ("agentos/workstreams/WS-" + ref[3:] + ".md")).write_text(text)
    subprocess.run(["git", "-C", str(macro), "add", "."], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(macro), "commit", "-qm", "inert archive fixture"], check=True, capture_output=True)
    seen["sha"] = subprocess.check_output(["git", "-C", str(macro), "rev-parse", "HEAD"], text=True).strip()
    seen["record"] = macro / "agentos/workstreams/WS-ARCHIVE-TEST.md"
    monkeypatch.setattr(source, "_SOURCE_ROOT", seen["code"])
    def runner(argv, **limits):
        seen["calls"].append((list(argv), dict(limits)))
        if argv[0] == "git":
            return _default_packet_runner(argv, **limits)
        child = Path(argv[argv.index("--macro-root") + 1]); seen["child_macro"] = child
        value = source.read_from_macro_owner(macro_root=child,
            expected_macro_sha=argv[argv.index("--expected-macro-sha") + 1],
            work_refs=json.loads(argv[argv.index("--work-refs-json") + 1]), timeout=float(argv[-1]))
        if mutation: mutation(value, child, seen)
        return {"code": 0, "stdout": json.dumps(value), "timed_out": False,
                "limit_exceeded": False, "invalid_utf8": False}
    collector._runner = runner
    return collector, seen


def acquire(collector, seen, refs=None):
    return collector.project_archive_reader(macro_root=seen["macro"]).read(
        work_refs=REFS if refs is None else refs, expected_current_macro_sha=seen["sha"])


def test_actual_parser_and_archive_helper_return_only_explicit_archives(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch)
    sample = acquire(collector, seen)
    assert sample["availability"] == "AVAILABLE" and len(sample["items"]) == 1
    row = sample["items"][0]
    assert row["work_ref"] == WORK and row["archive"]["archived_on"] == "2026-11-04"
    assert row["source"]["commit"] == seen["sha"] and sample["can_restore"] is False
    assert sample["coverage"] == {"kind": "QUALIFIED_CATALOGUE_SAMPLE", "supplied_count": 2,
                                 "observed_count": 2, "company_total": None}
    assert "Private workstream body" not in json.dumps(sample)
    calls = [(a, b) for a, b in seen["calls"] if a[0] != "git"]
    assert len(calls) == 1 and calls[0][1]["max_bytes"] == 131072
    assert calls[0][0][1:3] == ["-I", "-B"]
    assert calls[0][0][3].endswith("/scripts/agentos_project_archive_entry.py")
    assert seen["child_macro"] != seen["macro"] and not seen["child_macro"].exists()


def test_absence_is_available_empty_sample_not_company_zero(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch, archived=False)
    sample = acquire(collector, seen)
    assert sample["items"] == [] and sample["coverage"]["observed_count"] == 2
    assert sample["coverage"]["company_total"] is None


@pytest.mark.parametrize("kind", ["live", "materialized", "body", "commit", "foreign", "restore", "partial"])
def test_unqualified_or_changed_child_never_publishes_partial_archive(tmp_path, monkeypatch, kind):
    def mutate(value, child, seen):
        if kind in ("live", "materialized"):
            path = seen["record"] if kind == "live" else child / "agentos/workstreams/WS-ARCHIVE-TEST.md"
            raw = path.read_bytes(); path.write_bytes(b"transient change"); path.write_bytes(raw)
        elif kind == "body": value["items"][0]["private"] = "not public"
        elif kind == "commit": value["source_commit"] = "f" * 40
        elif kind == "foreign": value["items"][0]["work_ref"] = "WS:FOREIGN"
        elif kind == "restore": value["can_restore"] = True
        else: value["coverage"]["observed_count"] = 1
    collector, seen = bound(tmp_path, monkeypatch, mutate)
    with pytest.raises(GatewayError): acquire(collector, seen)
    assert not seen["child_macro"].exists()


@pytest.mark.parametrize("kind", ["bare", "forged", "copied", "other_owner", "callback", "context"])
def test_read_binding_never_accepts_lookalike_or_changed_reader(tmp_path, monkeypatch, kind):
    collector, seen = bound(tmp_path, monkeypatch)
    reader = collector.project_archive_reader(macro_root=seen["macro"])
    candidate = source.AgentOsProjectArchiveReader(macro_root=seen["macro"])
    candidate._installed_context_owner = collector
    candidate._installed_context_binding = reader._installed_context_binding
    if kind == "forged": candidate._installed_reader_binding = {"owner": collector}
    elif kind == "copied": candidate._installed_reader_binding = reader._installed_reader_binding
    elif kind == "other_owner": candidate = reader; candidate._installed_context_owner = copy.copy(collector)
    elif kind == "callback":
        candidate = reader
        monkeypatch.setattr(InstalledBootPacketCollector, "read_project_archive", lambda *a, **k: pytest.fail("changed reader invoked"))
    elif kind == "context": candidate = reader; collector._expected_source_sha = "f" * 40
    with pytest.raises(InstalledProjectReadUnavailable):
        candidate.read(work_refs=REFS, expected_current_macro_sha=seen["sha"])
    assert seen["calls"] == []


def test_wrong_catalogue_revision_refuses_before_child(tmp_path, monkeypatch):
    collector, seen = bound(tmp_path, monkeypatch)
    reader = collector.project_archive_reader(macro_root=seen["macro"])
    with pytest.raises(GatewayError): reader.read(work_refs=REFS, expected_current_macro_sha="f" * 40)
    assert not any(argv[0] != "git" for argv, _ in seen["calls"])


def test_frame_has_no_caller_selected_members_or_revision():
    from tests.test_workspace_project_direction_read import request
    principal = request()["principal"]
    frame = {"schema": wire.FRAME_SCHEMA, "operation": wire.OPERATION, "principal": principal}
    assert wire.validate_frame(frame) == frame
    for key, value in [("selection", {}), ("work_refs", REFS), ("macro_sha", "a" * 40), ("path", "/private")]:
        with pytest.raises(ValueError): wire.validate_frame(dict(frame, **{key: value}))
