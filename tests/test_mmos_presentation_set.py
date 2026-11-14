"""B-PRES (PF-2 item 2): properties of tools/mmos_team_server/presentation_set.py.

Every test runs the writer as a subprocess against tmp-dir fixtures only —
no real root, no network, no server. The outside-member byte comparisons use
an independent top-level member scanner (json.JSONDecoder.raw_decode) so the
test does not share the implementation's span code.

Run:
  TMPDIR=/tmp env -u PYTHONPATH /opt/homebrew/bin/python3.12 -m pytest -q \
    -p no:cacheprovider tests/test_mmos_presentation_set.py
"""
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys

import pytest

TOOL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "mmos_team_server", "presentation_set.py")

VALUE = {
    "productName": "Mastermind OS",
    "teamMode": True,
    "lockedProviderProjectIds": ["11111111-2222-3333-4444-555555555555"],
    "links": [
        {"id": "work", "label": "Work", "url": "http://127.0.0.1:3100/MAS/issues"},
        {"id": "needs-you", "label": "Needs you",
         "url": "http://127.0.0.1:3100/MAS/inbox"},
    ],
}

# Odd whitespace (tabs, mixed spaces, blank lines), odd key order, no trailing
# newline — the byte-preservation property must hold on exactly this shape.
ODD_NO_PRES = (
    b'{\n\t"zeta" :  1 ,\n  "providerInstances": {"capacity_fabric": '
    b'{"enabled": true}},\n\n  "alpha" : [1,2,\n 3]\n}'
)
ODD_WITH_PRES = (
    b'{\n\t"zeta" :  1 ,\n "presentation" :  {"productName":"Old","teamMode":'
    b'false,"lockedProviderProjectIds":[],"links":[]} ,\n\n  "alpha" : [1,2,\n 3]\n}'
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def scan_members(data):
    """Independent scanner: top-level key -> (value_start, value_end) char
    offsets in the decoded text, plus the closing-brace offset and the end of
    the last member's value."""
    text = data.decode("utf-8")
    dec = json.JSONDecoder()

    def ws(i):
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        return i

    i = ws(0)
    assert text[i] == "{"
    i = ws(i + 1)
    spans = {}
    last_end = None
    while text[i] != "}":
        key, kend = dec.raw_decode(text, i)
        j = ws(kend)
        assert text[j] == ":"
        j = ws(j + 1)
        _val, vend = dec.raw_decode(text, j)
        spans[key] = (j, vend)
        last_end = vend
        i = ws(vend)
        if text[i] == ",":
            i = ws(i + 1)
    return text, spans, i, last_end


@pytest.fixture()
def settings(tmp_path):
    p = tmp_path / "home" / "userdata" / "settings.json"
    p.parent.mkdir(parents=True)
    p.write_bytes(ODD_NO_PRES)
    p.chmod(0o600)
    return p


@pytest.fixture()
def value_file(tmp_path):
    p = tmp_path / "value.json"
    p.write_text(json.dumps(VALUE), encoding="utf-8")
    return p


def run_tool(*args):
    return subprocess.run([sys.executable, TOOL, *args],
                          capture_output=True, text=True, timeout=60)


def do_apply(settings, value_file, receipt_dir, expect=None, extra=()):
    expect = expect if expect is not None else sha(settings.read_bytes())
    return run_tool("apply", "--settings", str(settings),
                    "--value-file", str(value_file),
                    "--expect-sha256", expect,
                    "--receipt-dir", str(receipt_dir), *extra)


def test_preimage_mismatch_refused_no_write(settings, value_file, tmp_path):
    before = settings.read_bytes()
    receipts = tmp_path / "receipts"
    r = do_apply(settings, value_file, receipts, expect="0" * 64)
    assert r.returncode != 0
    assert settings.read_bytes() == before
    # nothing was written anywhere: no receipt dir content
    assert not receipts.exists() or not list(receipts.iterdir())


def test_insert_outside_bytes_unchanged(settings, value_file, tmp_path):
    old = settings.read_bytes()
    _t, _s, _close, last_end = scan_members(old)
    p = len(old.decode("utf-8")[:last_end].encode("utf-8"))
    r = do_apply(settings, value_file, tmp_path / "receipts")
    assert r.returncode == 0, r.stderr
    new = settings.read_bytes()
    assert json.loads(new)["presentation"] == VALUE
    # prefix before the insertion point is byte-identical ...
    assert new[:p] == old[:p]
    # ... and the suffix from the insertion point is byte-identical once the
    # inserted member text is removed.
    _t2, spans2, _c2, _l2 = scan_members(new)
    vs, ve = spans2["presentation"]
    text2 = new.decode("utf-8")
    # inserted text runs from p to the end of the presentation value; the key
    # and colon are part of the insertion for a new member.
    key_start = text2.rfind('"presentation"', 0, vs)
    ins_start = len(text2[:key_start].encode("utf-8"))
    ins_end = len(text2[:ve].encode("utf-8"))
    # the comma before the new member is insertion too
    while ins_start > p and text2[ins_start - 1] in " \t\r\n,":
        ins_start -= 1
    assert ins_start == p
    reconstructed = new[:ins_start] + new[ins_end:]
    assert reconstructed == old


def test_replace_outside_bytes_unchanged(settings, value_file, tmp_path):
    settings.write_bytes(ODD_WITH_PRES)
    settings.chmod(0o600)
    old = settings.read_bytes()
    _t, spans, _c, _l = scan_members(old)
    vs_old, ve_old = spans["presentation"]
    pb = lambda s, i: len(s[:i].encode("utf-8"))
    r = do_apply(settings, value_file, tmp_path / "receipts")
    assert r.returncode == 0, r.stderr
    new = settings.read_bytes()
    assert json.loads(new)["presentation"] == VALUE
    _t2, spans2, _c2, _l2 = scan_members(new)
    vs_new, ve_new = spans2["presentation"]
    text, text2 = old.decode("utf-8"), new.decode("utf-8")
    # everything before the value span (incl. the odd-spaced key and colon)
    assert new[:pb(text2, vs_new)] == old[:pb(text, vs_old)]
    # everything after the value span
    assert new[pb(text2, ve_new):] == old[pb(text, ve_old):]


def test_symlink_refused(settings, value_file, tmp_path):
    target = tmp_path / "real.json"
    target.write_bytes(ODD_NO_PRES)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    r = do_apply(link, value_file, tmp_path / "receipts")
    assert r.returncode != 0
    assert target.read_bytes() == ODD_NO_PRES
    assert link.is_symlink()


@pytest.mark.parametrize("bad", [
    {**VALUE, "productName": ""},
    {**VALUE, "productName": "   "},
    {**VALUE, "productName": 7},
    {**VALUE, "teamMode": "true"},
    {**VALUE, "teamMode": 1},
    {**VALUE, "lockedProviderProjectIds": "x"},
    {**VALUE, "lockedProviderProjectIds": [""]},
    {**VALUE, "lockedProviderProjectIds": [5]},
    {**VALUE, "links": "x"},
    {**VALUE, "links": [{"id": "work", "label": "Work"}]},
    {**VALUE, "links": [{"id": "work", "label": "Work",
                          "url": "ftp://x/y"}]},
    {**VALUE, "links": [{"id": "Bad ID", "label": "Work",
                          "url": "http://x/y"}]},
    {**VALUE, "links": [{"id": "work", "label": " ",
                          "url": "http://x/y"}]},
    {**VALUE, "links": [{"id": "work", "label": "Work",
                          "url": "http://x/y", "extra": 1}]},
    {**VALUE, "extraKey": 1},
    {"productName": "x"},
    [1, 2],
    "presentation",
])
def test_bad_values_refused(settings, value_file, tmp_path, bad):
    value_file.write_text(json.dumps(bad), encoding="utf-8")
    before = settings.read_bytes()
    r = do_apply(settings, value_file, tmp_path / "receipts")
    assert r.returncode != 0
    assert settings.read_bytes() == before


def test_undo_restores_identical_bytes(settings, value_file, tmp_path):
    old = settings.read_bytes()
    receipts = tmp_path / "receipts"
    assert do_apply(settings, value_file, receipts).returncode == 0
    assert settings.read_bytes() != old
    r = run_tool("undo", "--settings", str(settings),
                 "--receipt-dir", str(receipts))
    assert r.returncode == 0, r.stderr
    assert settings.read_bytes() == old
    assert sha(settings.read_bytes()) == sha(old)


def test_undo_refused_after_foreign_write(settings, value_file, tmp_path):
    receipts = tmp_path / "receipts"
    assert do_apply(settings, value_file, receipts).returncode == 0
    foreign = settings.read_bytes() + b"\n"
    settings.write_bytes(foreign)
    r = run_tool("undo", "--settings", str(settings),
                 "--receipt-dir", str(receipts))
    assert r.returncode != 0
    assert settings.read_bytes() == foreign


def test_real_root_refused_without_flag(tmp_path, value_file, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    real = tmp_path / ".mastermind" / "t3-team" / "home" / "userdata" / "settings.json"
    real.parent.mkdir(parents=True)
    real.write_bytes(ODD_NO_PRES)
    real.chmod(0o600)
    before = real.read_bytes()
    r = do_apply(real, value_file, tmp_path / "receipts")
    assert r.returncode != 0
    assert real.read_bytes() == before
    # the principal's explicit flag unlocks exactly this guard
    r2 = do_apply(real, value_file, tmp_path / "receipts",
                  extra=("--real-root-ok",))
    assert r2.returncode == 0, r2.stderr
    assert json.loads(real.read_bytes())["presentation"] == VALUE


def test_mode_preserved_0600(settings, value_file, tmp_path):
    assert stat.S_IMODE(settings.stat().st_mode) == 0o600
    assert do_apply(settings, value_file, tmp_path / "receipts").returncode == 0
    assert stat.S_IMODE(settings.stat().st_mode) == 0o600
    # undo preserves the mode too
    r = run_tool("undo", "--settings", str(settings),
                 "--receipt-dir", str(tmp_path / "receipts"))
    assert r.returncode == 0
    assert stat.S_IMODE(settings.stat().st_mode) == 0o600


def test_mode_preserved_other(settings, value_file, tmp_path):
    settings.chmod(0o640)
    assert do_apply(settings, value_file, tmp_path / "receipts").returncode == 0
    assert stat.S_IMODE(settings.stat().st_mode) == 0o640


def test_plan_writes_nothing(settings, value_file, tmp_path):
    before = settings.read_bytes()
    r = run_tool("plan", "--settings", str(settings),
                 "--value-file", str(value_file))
    assert r.returncode == 0, r.stderr
    assert sha(before) in r.stdout
    assert "absent" in r.stdout.lower()
    assert "presentation" in r.stdout
    assert settings.read_bytes() == before
    assert not (tmp_path / "receipts").exists()
    # plan with a matching expect passes; with a wrong expect it reports and
    # exits nonzero, still writing nothing
    r2 = run_tool("plan", "--settings", str(settings),
                  "--value-file", str(value_file),
                  "--expect-sha256", sha(before))
    assert r2.returncode == 0
    r3 = run_tool("plan", "--settings", str(settings),
                  "--value-file", str(value_file),
                  "--expect-sha256", "0" * 64)
    assert r3.returncode != 0
    assert settings.read_bytes() == before


def test_receipt_contents(settings, value_file, tmp_path):
    old = settings.read_bytes()
    receipts = tmp_path / "receipts"
    assert do_apply(settings, value_file, receipts).returncode == 0
    new = settings.read_bytes()
    receipt = json.loads((receipts / "receipt.json").read_text())
    assert receipt["before_sha256"] == sha(old)
    assert receipt["after_sha256"] == sha(new)
    assert receipt["settings_path"] == str(settings)
    assert "time_utc" in receipt
    # preimage copy is byte-identical (compared by hash, never printed)
    pre = (receipts / "preimage.bin").read_bytes()
    assert sha(pre) == sha(old)
    assert stat.S_IMODE((receipts / "preimage.bin").stat().st_mode) == 0o600
    assert stat.S_IMODE(receipts.stat().st_mode) == 0o700


def test_undo_refused_when_receipt_tampered(settings, value_file, tmp_path):
    receipts = tmp_path / "receipts"
    assert do_apply(settings, value_file, receipts).returncode == 0
    rp = receipts / "receipt.json"
    receipt = json.loads(rp.read_text())
    receipt["after_sha256"] = "0" * 64
    rp.write_text(json.dumps(receipt))
    current = settings.read_bytes()
    r = run_tool("undo", "--settings", str(settings),
                 "--receipt-dir", str(receipts))
    assert r.returncode != 0
    assert settings.read_bytes() == current


def test_duplicate_presentation_key_refused(settings, value_file, tmp_path):
    settings.write_bytes(
        b'{"presentation": {"productName":"A","teamMode":false,'
        b'"lockedProviderProjectIds":[],"links":[]}, '
        b'"presentation": {"productName":"B","teamMode":false,'
        b'"lockedProviderProjectIds":[],"links":[]}}')
    settings.chmod(0o600)
    before = settings.read_bytes()
    r = do_apply(settings, value_file, tmp_path / "receipts")
    assert r.returncode != 0
    assert settings.read_bytes() == before


def test_no_argument_defaults():
    # every path is required: a bare invocation must fail without touching
    # anything (argparse usage error)
    r = run_tool("apply")
    assert r.returncode != 0
    r2 = run_tool()
    assert r2.returncode != 0


def test_empty_object_insert(tmp_path, value_file):
    p = tmp_path / "settings.json"
    p.write_bytes(b"{ }")
    p.chmod(0o600)
    r = do_apply(p, value_file, tmp_path / "receipts")
    assert r.returncode == 0, r.stderr
    data = json.loads(p.read_bytes())
    assert data["presentation"] == VALUE
    assert p.read_bytes().startswith(b"{ ")
    assert p.read_bytes().endswith(b" }")


def test_compact_file_insert(tmp_path, value_file):
    p = tmp_path / "settings.json"
    p.write_bytes(b'{"a":1,"b":[2,3]}')
    p.chmod(0o600)
    old = p.read_bytes()
    r = do_apply(p, value_file, tmp_path / "receipts")
    assert r.returncode == 0, r.stderr
    new = p.read_bytes()
    assert new.startswith(b'{"a":1,"b":[2,3]}'.rstrip(b"}"))
    assert json.loads(new)["presentation"] == VALUE
    # suffix after the insertion is the original closing brace
    assert new.endswith(b"}")
    assert old[:-1] == new[:len(old) - 1]


# ---------------------------------------------------------------------------
# F1: the real-root fence must hold by file IDENTITY, not only by string.
# The tool's REAL_ROOT is overridable for tests via MMOS_PRESENTATION_REAL_ROOT
# (or the module attribute); every fixture here is a tmp dir, never a real root.
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_real_root(tmp_path, monkeypatch):
    """A tmp dir standing in for the real team root, via the test override."""
    root = tmp_path / "teamroot"
    settings = root / "home" / "userdata" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_bytes(ODD_NO_PRES)
    settings.chmod(0o600)
    monkeypatch.setenv("MMOS_PRESENTATION_REAL_ROOT", str(root))
    return root, settings


def _fs_case_insensitive(tmp_path):
    probe = tmp_path / "CaseProbe"
    probe.write_text("")
    return (tmp_path / "caseprobe").exists()


def test_real_root_case_variant_refused(fake_real_root, value_file, tmp_path):
    root, settings = fake_real_root
    before = settings.read_bytes()
    if _fs_case_insensitive(tmp_path):
        # same file through a case-variant spelling of the root component
        variant = str(settings).replace(str(root), str(root).upper(), 1)
        assert variant != str(settings)
        assert os.path.exists(variant)  # same file on a case-insensitive FS
    else:
        # case-sensitive FS: reach the root through a symlinked alias dir;
        # the fence must still refuse (identity walk on the resolved path)
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        variant = str(alias / "home" / "userdata" / "settings.json")
    expect = sha(before)
    r = do_apply(variant, value_file, tmp_path / "receipts", expect=expect)
    assert r.returncode != 0, "case/alias variant bypassed the real-root fence"
    assert settings.read_bytes() == before
    # the principal's flag still unlocks exactly this root
    r2 = do_apply(variant, value_file, tmp_path / "receipts2", expect=expect,
                  extra=("--real-root-ok",))
    assert r2.returncode == 0, r2.stderr
    assert json.loads(settings.read_bytes())["presentation"] == VALUE


def test_real_root_symlinked_parent_refused(fake_real_root, value_file, tmp_path):
    root, settings = fake_real_root
    before = settings.read_bytes()
    alias = tmp_path / "parentalias"
    alias.symlink_to(root, target_is_directory=True)
    through = alias / "home" / "userdata" / "settings.json"
    r = do_apply(through, value_file, tmp_path / "receipts")
    assert r.returncode != 0
    assert settings.read_bytes() == before


@pytest.mark.parametrize("suffix", ["/", "/./"])
def test_real_root_trailing_slash_and_dot_segment_refused(
        fake_real_root, value_file, tmp_path, suffix):
    _root, settings = fake_real_root
    before = settings.read_bytes()
    if suffix == "/":
        variant = str(settings) + "/"
    else:
        variant = str(settings.parent) + "/./" + settings.name
    r = do_apply(variant, value_file, tmp_path / "receipts", expect=sha(before))
    assert r.returncode != 0
    assert settings.read_bytes() == before


def test_real_root_exact_case_control_refused(fake_real_root, value_file, tmp_path):
    _root, settings = fake_real_root
    before = settings.read_bytes()
    r = do_apply(settings, value_file, tmp_path / "receipts")
    assert r.returncode != 0
    assert settings.read_bytes() == before


def test_fence_refuses_when_identity_unestablished(fake_real_root, value_file,
                                                   tmp_path):
    root, settings = fake_real_root
    before = settings.read_bytes()
    # an ancestor component is a regular file: stat fails with ENOTDIR, not
    # not-found — the fence must refuse, not allow
    notdir = settings / "under"
    r = do_apply(notdir, value_file, tmp_path / "receipts", expect=sha(before))
    assert r.returncode != 0
    assert settings.read_bytes() == before
    # a missing ancestor: identity cannot be established — refuse
    missing = root / "no-such-dir" / "settings.json"
    r2 = do_apply(missing, value_file, tmp_path / "receipts2",
                  expect=sha(before))
    assert r2.returncode != 0
    assert settings.read_bytes() == before


def test_fence_refuses_on_stat_permission_error(fake_real_root, value_file,
                                                tmp_path):
    _root, settings = fake_real_root
    before = settings.read_bytes()
    expect = sha(before)
    settings.parent.chmod(0o000)  # search denied: stat raises EACCES
    try:
        r = do_apply(settings, value_file, tmp_path / "receipts", expect=expect)
        assert r.returncode != 0
    finally:
        settings.parent.chmod(0o700)
    assert settings.read_bytes() == before


# ---------------------------------------------------------------------------
# F2: a foreign write between the preimage sha check and os.replace must not
# be clobbered. The writer re-reads and re-hashes the destination immediately
# before the replace (pre_replace_recheck, called from atomic_write's
# pre_replace hook) and aborts PREIMAGE_CHANGED; the readback compares the
# ON-DISK bytes to the planned bytes. These tests import the writer in
# process to monkeypatch the hook; all fixtures stay in tmp dirs.
# ---------------------------------------------------------------------------

def load_writer_module():
    spec = importlib.util.spec_from_file_location(
        "presentation_set_under_test", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_apply_aborts_foreign_write_before_replace(settings, value_file,
                                                   tmp_path, monkeypatch,
                                                   capsys):
    mod = load_writer_module()
    orig = mod.pre_replace_recheck
    foreign = json.dumps(
        {"FOREIGN_MARKER": "concurrent-writer-was-here"}).encode("utf-8")

    def hook(path, expected_sha):
        # the foreign write lands after staging, immediately before replace
        with open(path, "wb") as fh:
            fh.write(foreign)
        return orig(path, expected_sha)

    monkeypatch.setattr(mod, "pre_replace_recheck", hook)
    with pytest.raises(SystemExit) as exc:
        mod.main(["apply", "--settings", str(settings),
                  "--value-file", str(value_file),
                  "--expect-sha256", sha(settings.read_bytes()),
                  "--receipt-dir", str(tmp_path / "receipts")])
    assert exc.value.code != 0
    assert "PREIMAGE_CHANGED" in capsys.readouterr().err
    # the foreign bytes survive; no replace happened; no temp left behind
    assert settings.read_bytes() == foreign
    assert not list(settings.parent.glob(".settings.json.tmp.*"))
    run_dir = tmp_path / "run"
    assert not run_dir.exists() or not list(run_dir.glob(".settings.json.tmp.*"))


def test_undo_aborts_foreign_write_before_replace(settings, value_file,
                                                  tmp_path, monkeypatch,
                                                  capsys):
    mod = load_writer_module()
    assert do_apply(settings, value_file, tmp_path / "receipts").returncode == 0
    orig = mod.pre_replace_recheck
    foreign = settings.read_bytes() + b'\n{"FOREIGN_MARKER": 1}'

    def hook(path, expected_sha):
        with open(path, "wb") as fh:
            fh.write(foreign)
        return orig(path, expected_sha)

    monkeypatch.setattr(mod, "pre_replace_recheck", hook)
    with pytest.raises(SystemExit) as exc:
        mod.main(["undo", "--settings", str(settings),
                  "--receipt-dir", str(tmp_path / "receipts")])
    assert exc.value.code != 0
    assert "PREIMAGE_CHANGED" in capsys.readouterr().err
    assert settings.read_bytes() == foreign
    assert not list(settings.parent.glob(".settings.json.tmp.*"))


def test_readback_compares_on_disk_bytes_to_planned(settings, value_file,
                                                    tmp_path, monkeypatch,
                                                    capsys):
    mod = load_writer_module()
    real_atomic_write = mod.atomic_write

    def foreign_after_replace(path, text, mode, staging_dir=None, **kw):
        real_atomic_write(path, text, mode, staging_dir=staging_dir, **kw)
        with open(path, "ab") as fh:
            fh.write(b"\n")  # a foreign write landing after the replace

    monkeypatch.setattr(mod, "atomic_write", foreign_after_replace)
    with pytest.raises(SystemExit) as exc:
        mod.main(["apply", "--settings", str(settings),
                  "--value-file", str(value_file),
                  "--expect-sha256", sha(settings.read_bytes()),
                  "--receipt-dir", str(tmp_path / "receipts")])
    assert exc.value.code == 1
    assert "READBACK FAILED" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# F3: undo must refuse a receipt written for a DIFFERENT settings file, even
# when the current sha matches the receipt's after-sha (identical after-bytes
# are easy: two files differing only in the old presentation value).
# ---------------------------------------------------------------------------

def test_undo_refuses_receipt_for_other_settings_file(tmp_path, value_file):
    base = {"providerInstances": {"x": {"enabled": True}}, "a": 1}
    pres_a = {**VALUE, "productName": "OldA"}
    pres_b = {**VALUE, "productName": "OldB"}
    a = tmp_path / "A.json"
    b = tmp_path / "B.json"
    a.write_bytes(json.dumps({**base, "presentation": pres_a}).encode("utf-8"))
    b.write_bytes(json.dumps({**base, "presentation": pres_b}).encode("utf-8"))
    a.chmod(0o600)
    b.chmod(0o600)
    assert do_apply(a, value_file, tmp_path / "rcptA").returncode == 0
    assert do_apply(b, value_file, tmp_path / "rcptB").returncode == 0
    after_b = b.read_bytes()
    assert a.read_bytes() == after_b  # identical after-sha, different preimage
    r = run_tool("undo", "--settings", str(b),
                 "--receipt-dir", str(tmp_path / "rcptA"))
    assert r.returncode != 0, "undo accepted a receipt for another file"
    assert b.read_bytes() == after_b


def test_undo_refuses_tampered_receipt_settings_path(settings, value_file,
                                                     tmp_path):
    receipts = tmp_path / "receipts"
    assert do_apply(settings, value_file, receipts).returncode == 0
    rp = receipts / "receipt.json"
    receipt = json.loads(rp.read_text())
    receipt["settings_path"] = str(tmp_path / "elsewhere.json")
    rp.write_text(json.dumps(receipt))
    current = settings.read_bytes()
    r = run_tool("undo", "--settings", str(settings),
                 "--receipt-dir", str(receipts))
    assert r.returncode != 0
    assert settings.read_bytes() == current


# ---------------------------------------------------------------------------
# F4: a receipt dir that already holds a receipt is refused — a second apply
# into the same dir used to O_TRUNC the first preimage/receipt, destroying
# the first undo path. Fresh dir per apply.
# ---------------------------------------------------------------------------

def test_apply_refuses_reused_receipt_dir(settings, value_file, tmp_path):
    receipts = tmp_path / "receipts"
    original = settings.read_bytes()
    assert do_apply(settings, value_file, receipts).returncode == 0
    first_after = settings.read_bytes()
    v2 = {**VALUE, "productName": "Second"}
    vf2 = tmp_path / "v2.json"
    vf2.write_text(json.dumps(v2), encoding="utf-8")
    r = do_apply(settings, vf2, receipts)
    assert r.returncode != 0, "apply reused a receipt dir and clobbered it"
    assert settings.read_bytes() == first_after
    # the first undo path is intact: preimage still the ORIGINAL bytes
    assert sha((receipts / "preimage.bin").read_bytes()) == sha(original)
    ru = run_tool("undo", "--settings", str(settings),
                  "--receipt-dir", str(receipts))
    assert ru.returncode == 0, ru.stderr
    assert settings.read_bytes() == original
    # a fresh dir for the next apply still works
    assert do_apply(settings, vf2, tmp_path / "receipts2").returncode == 0


# ---------------------------------------------------------------------------
# F6: an empty object with interior whitespace ({  }, {\n}, {\t}) must be
# accepted, and the interior whitespace preserved on insert (every original
# byte stays outside the presentation member).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("data", [b"{  }", b"{\n}", b"{\t}", b"{}", b"{ }",
                                  b"  {  }"])
def test_empty_object_interior_whitespace_preserved(tmp_path, value_file,
                                                    data):
    p = tmp_path / "settings.json"
    p.write_bytes(data)
    p.chmod(0o600)
    r = do_apply(p, value_file, tmp_path / "receipts")
    assert r.returncode == 0, r.stderr
    new = p.read_bytes()
    assert json.loads(new)["presentation"] == VALUE
    # independent reconstruction: removing the inserted member (and its
    # leading whitespace/comma) must reproduce the original byte for byte
    text2, spans2, _c2, _l2 = scan_members(new)
    _vs, ve = spans2["presentation"]
    key_start = text2.rfind('"presentation"', 0, _vs)
    ins_start = key_start
    while ins_start > 0 and text2[ins_start - 1] in " \t\r\n,":
        ins_start -= 1
    assert (text2[:ins_start] + text2[ve:]).encode("utf-8") == data


# ---------------------------------------------------------------------------
# F7: a symlinked receipt dir is refused like a symlinked settings path —
# no write through the link and no chmod side effect on its target.
# ---------------------------------------------------------------------------

def test_symlinked_receipt_dir_refused(settings, value_file, tmp_path):
    target = tmp_path / "wide_target"
    target.mkdir()
    target.chmod(0o755)
    rlink = tmp_path / "rcpt_link"
    rlink.symlink_to(target, target_is_directory=True)
    before = settings.read_bytes()
    r = do_apply(settings, value_file, rlink)
    assert r.returncode != 0
    assert settings.read_bytes() == before
    assert stat.S_IMODE(target.stat().st_mode) == 0o755
    assert not list(target.iterdir())


# ---------------------------------------------------------------------------
# F10: a lone surrogate in any value string is a clean refusal in
# validate_value — no UnicodeEncodeError traceback, nothing written.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["productName", "locked", "label"])
def test_lone_surrogate_refused_cleanly(settings, value_file, tmp_path, field):
    bad = json.loads(json.dumps(VALUE))
    if field == "productName":
        bad["productName"] = "\ud800"
    elif field == "locked":
        bad["lockedProviderProjectIds"] = ["\ud800"]
    else:
        bad["links"][0]["label"] = "\ud800"
    value_file.write_text(json.dumps(bad), encoding="utf-8")
    before = settings.read_bytes()
    r = do_apply(settings, value_file, tmp_path / "receipts")
    assert r.returncode != 0
    assert "Traceback" not in r.stderr
    assert settings.read_bytes() == before


def test_env_root_absent_allows_unrelated_tmp_file(tmp_path, value_file,
                                                   monkeypatch):
    # override pointing at a nonexistent dir: no identity to fence, and an
    # unrelated tmp settings file must still be writable (no false refusal)
    monkeypatch.setenv("MMOS_PRESENTATION_REAL_ROOT",
                       str(tmp_path / "does-not-exist"))
    p = tmp_path / "settings.json"
    p.write_bytes(ODD_NO_PRES)
    p.chmod(0o600)
    r = do_apply(p, value_file, tmp_path / "receipts")
    assert r.returncode == 0, r.stderr
    assert json.loads(p.read_bytes())["presentation"] == VALUE

# ---------------------------------------------------------------------------
# PF-3b (a): the env override never MOVES the fence. ~/.mastermind/t3-team is
# always fenced; MMOS_PRESENTATION_REAL_ROOT only ADDS a fenced root. HOME is
# a fake home in these tests (expanduser follows HOME), never the real one.
# ---------------------------------------------------------------------------

def run_tool_env(env_extra, *args):
    env = dict(os.environ)
    env.update(env_extra)
    return subprocess.run([sys.executable, TOOL, *args], env=env,
                          capture_output=True, text=True, timeout=60)


def _fake_home_root(tmp_path):
    home = tmp_path / "fakehome"
    s = home / ".mastermind" / "t3-team" / "home" / "userdata" / "settings.json"
    s.parent.mkdir(parents=True)
    s.write_bytes(ODD_NO_PRES)
    s.chmod(0o600)
    return home, s


def test_env_override_does_not_unfence_default_root(tmp_path, value_file):
    home, s = _fake_home_root(tmp_path)
    other = tmp_path / "other-root"
    other.mkdir()
    before = s.read_bytes()
    r = run_tool_env({"HOME": str(home),
                      "MMOS_PRESENTATION_REAL_ROOT": str(other)},
                     "apply", "--settings", str(s),
                     "--value-file", str(value_file),
                     "--expect-sha256", sha(before),
                     "--receipt-dir", str(tmp_path / "r1"))
    assert r.returncode != 0, "env override moved the fence off t3-team"
    assert s.read_bytes() == before


def test_env_override_adds_a_fenced_root(tmp_path, value_file):
    home, _ = _fake_home_root(tmp_path)
    extra = tmp_path / "extra-root"
    p = extra / "settings.json"
    extra.mkdir()
    p.write_bytes(ODD_NO_PRES)
    p.chmod(0o600)
    before = p.read_bytes()
    r = run_tool_env({"HOME": str(home),
                      "MMOS_PRESENTATION_REAL_ROOT": str(extra)},
                     "apply", "--settings", str(p),
                     "--value-file", str(value_file),
                     "--expect-sha256", sha(before),
                     "--receipt-dir", str(tmp_path / "r2"))
    assert r.returncode != 0
    assert p.read_bytes() == before


def test_real_root_ok_still_unlocks_default_root(tmp_path, value_file):
    home, s = _fake_home_root(tmp_path)
    r = run_tool_env({"HOME": str(home)},
                     "apply", "--settings", str(s),
                     "--value-file", str(value_file),
                     "--expect-sha256", sha(s.read_bytes()),
                     "--receipt-dir", str(tmp_path / "r3"), "--real-root-ok")
    assert r.returncode == 0, r.stderr
    assert json.loads(s.read_bytes())["presentation"] == VALUE


# PF-3b (b) / REV-PRESFIX F11: a receipt dir reached through ANY symlinked
# ancestor is refused (resolved path must equal the absolute path).

def test_receipt_dir_under_symlinked_parent_refused(settings, value_file,
                                                    tmp_path):
    target = tmp_path / "parent_target"
    target.mkdir()
    alias = tmp_path / "parent_alias"
    alias.symlink_to(target, target_is_directory=True)
    before = settings.read_bytes()
    r = do_apply(settings, value_file, alias / "receipts")
    assert r.returncode != 0
    assert "symlink" in r.stderr
    assert settings.read_bytes() == before
    assert not (target / "receipts").exists()
