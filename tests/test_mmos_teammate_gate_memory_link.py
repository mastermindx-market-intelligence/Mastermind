"""Gate patch for lane HM: the memory-link tools and the read-only history
archive. A teammate may call ONLY the MCP tool names its gate config lists
(exact, memory-link namespace only), and may never write its history/."""
import json

from test_mmos_teammate_gate import Rig, teammate_gate  # noqa: F401


def _rig(tmp_path, names):
    rig = Rig(tmp_path)
    cfg = dict(rig.config)
    cfg["allow_mcp_tools"] = names
    rig.config_path.write_text(json.dumps(cfg))
    return rig


def test_listed_memory_tool_allowed(tmp_path):
    rig = _rig(tmp_path, ["mcp__memory-link__memory_recall"])
    rig.allowed("mcp__memory-link__memory_recall", {"query": "x"})


def test_unlisted_memory_tool_refused(tmp_path):
    rig = _rig(tmp_path, ["mcp__memory-link__memory_recall"])
    rig.refused("mcp__memory-link__memory_save", {"summary": "x" * 20})


def test_no_list_means_no_mcp(tmp_path):
    rig = Rig(tmp_path)
    rig.refused("mcp__memory-link__memory_recall", {"query": "x"})


def test_foreign_namespace_in_list_refuses_config(tmp_path):
    rig = _rig(tmp_path, ["mcp__t3-code__delegate_task"])
    proc = rig.call("mcp__t3-code__delegate_task", {})
    assert proc.returncode == 2


def test_fetch_tool_never_allowed_even_if_listed(tmp_path):
    rig = _rig(tmp_path, ["mcp__memory-link__memory_recall", "WebFetch"])
    proc = rig.call("WebFetch", {"url": "http://192.0.2.1/"})
    assert proc.returncode == 2


def test_allow_list_must_be_list(tmp_path):
    rig = _rig(tmp_path, "mcp__memory-link__memory_recall")
    proc = rig.call("mcp__memory-link__memory_recall", {})
    assert proc.returncode == 2


def test_history_is_readable_but_not_writable(tmp_path):
    rig = Rig(tmp_path)
    hist = rig.home / "history"
    hist.mkdir()
    (hist / "INDEX.md").write_text("index\n")
    rig.allowed("Read", {"file_path": str(hist / "INDEX.md")})
    rig.refused("Write", {"file_path": str(hist / "INDEX.md"),
                          "content": "x"})
    rig.refused("Edit", {"file_path": str(hist / "new.md"),
                         "old_string": "a", "new_string": "b"})
