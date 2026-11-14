#!/usr/bin/env python3
"""B-PRES (PF-2 item 2): set the `presentation` key of a T3 server settings.json.

The running server watches settings.json (fs.watch on the directory, ~100 ms
debounce) and reloads it live; the picker lock is read per dispatch. This
writer edits ONLY the bytes of the top-level `presentation` member — replace
its value span if present, insert a new last member if absent — so every byte
outside that member is unchanged. No whole-file json.dump.

Subcommands (every path is required; nothing defaults to a real path):
  plan  --settings PATH --value-file JSON [--expect-sha256 HEX]
        Print the current sha256, whether `presentation` is present, and a
        unified diff of only that member. Writes nothing.
  apply --settings PATH --value-file JSON --expect-sha256 HEX --receipt-dir DIR
        Refuse unless the current sha256 equals --expect-sha256 (checked
        before the first write). Save the exact preimage bytes 0600 and a
        receipt JSON in the 0700 receipt dir BEFORE writing, re-read and
        re-hash the destination immediately before os.replace (abort
        PREIMAGE_CHANGED if it changed), write atomically with the file's
        mode preserved, then read back the ON-DISK bytes and verify them
        against the planned bytes, parse, presentation equality and
        outside-member byte equality.
  undo  --settings PATH --receipt-dir DIR
        Refuse unless the current sha256 equals the receipt's after-sha.
        Restore the exact preimage atomically; read back the sha.

A settings path at/under ~/.mastermind/t3-team is refused unless the explicit
--real-root-ok flag is given (the principal's flag). The fence holds by string
(exact and case-folded) AND by file identity: on a case-insensitive filesystem
a case-variant spelling of the root keeps its case through realpath, so the
candidate and every existing ancestor are also compared to the real root by
(st_dev, st_ino); when identity cannot be established the fence refuses. A
symlinked settings path is always refused. File contents are never printed
except the presentation member (in plan's diff). For tests only, the fenced
root is overridable via the MMOS_PRESENTATION_REAL_ROOT env var or the
REAL_ROOT module attribute; nothing else defaults to a real path.

Atomic replacement reuses team_roster.atomic_write (0600 temp, fsync,
os.replace, staging under <root>/run when derivable) — one writer pattern,
not a second divergent copy.

python3.12 stdlib only.
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_roster import atomic_write  # noqa: E402  (same-directory tool)

REAL_ROOT = "~/.mastermind/t3-team"
# Test-only override of the fenced root (tests point it at a tmp dir).
REAL_ROOT_ENV = "MMOS_PRESENTATION_REAL_ROOT"
LINK_ID_RE = re.compile(r"^[a-z0-9-]{1,32}$")
LINK_URL_RE = re.compile(r"^https?://[^\s/]+", re.IGNORECASE)
VALUE_KEYS = {"productName", "teamMode", "lockedProviderProjectIds", "links"}


def die(msg, code=2):
    print(f"presentation_set: {msg}", file=sys.stderr)
    raise SystemExit(code)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


class PreimageChangedError(RuntimeError):
    """The destination changed between the preimage check and os.replace."""


def pre_replace_recheck(path, expected_sha):
    """Re-read and re-hash the destination IMMEDIATELY before os.replace
    (F2). A foreign write after the first sha check aborts the replace:
    no replace, the staged temp is removed by atomic_write, and the caller
    reports PREIMAGE_CHANGED. A window still remains between this re-hash
    and os.replace; closing it needs the server's cooperation (see
    integrations/mmos/pf/PART_C_PRESENTATION.md)."""
    with open(path, "rb") as fh:
        current = fh.read()
    if sha256(current) != expected_sha:
        raise PreimageChangedError(
            f"destination {path} changed between the preimage check and the "
            f"replace (current sha256 {sha256(current)} != {expected_sha})")


def _under_root(candidate, root):
    return candidate == root or candidate.startswith(root + os.sep)


def _identity_fence(candidate, root_id, real_root, real_root_ok):
    """Walk the candidate and its existing ancestors; refuse when any is the
    real root by (st_dev, st_ino) — a case-variant spelling on a
    case-insensitive filesystem reaches the same directory even though
    realpath keeps the caller's case. When identity cannot be established
    (a missing ancestor, or a stat error other than not-found for the leaf),
    refuse rather than allow."""
    cur = candidate
    while True:
        try:
            st = os.stat(cur)
        except FileNotFoundError:
            if cur != candidate:
                die(f"cannot establish identity for settings path "
                    f"{candidate}: ancestor {cur} is missing; refusing")
            # leaf not found: the regular-file check below refuses it
        except OSError as exc:
            die(f"cannot establish identity for settings path {candidate}: "
                f"{exc}; refusing")
        else:
            if (st.st_dev, st.st_ino) == root_id and not real_root_ok:
                die(f"settings path {candidate} reaches the real team root "
                    f"{real_root} by file identity; refusing without "
                    "--real-root-ok (the principal's flag)")
        parent = os.path.dirname(cur)
        if parent == cur:
            return
        cur = parent


def guard_settings(path, real_root_ok):
    """Resolve and fence the settings path. Returns the absolute path.

    The fence is by string (exact and case-folded) AND by file identity, so
    a case-variant or symlinked-parent spelling of the real root is refused
    too. --real-root-ok (the principal's flag) unlocks exactly this root.
    """
    expanded = os.path.abspath(os.path.expanduser(path))
    real = os.path.realpath(expanded)
    real_root = os.path.realpath(os.path.expanduser(
        os.environ.get(REAL_ROOT_ENV) or REAL_ROOT))
    for candidate in (expanded, real):
        if (_under_root(candidate, real_root)
                or _under_root(candidate.casefold(), real_root.casefold())):
            if not real_root_ok:
                die(f"settings path {candidate} is under the real team root "
                    f"{real_root}; refusing without --real-root-ok "
                    "(the principal's flag)")
    try:
        root_st = os.stat(real_root)
    except FileNotFoundError:
        root_st = None  # real root absent: no identity to fence
    except OSError as exc:
        die(f"cannot stat real team root {real_root}: {exc}; refusing")
    if root_st is not None:
        if not stat.S_ISDIR(root_st.st_mode):
            die(f"real team root {real_root} is not a directory; refusing")
        root_id = (root_st.st_dev, root_st.st_ino)
        for candidate in (expanded, real):
            _identity_fence(candidate, root_id, real_root, real_root_ok)
    if os.path.islink(expanded):
        die(f"symlinked settings path refused: {expanded}")
    if not os.path.isfile(expanded):
        die(f"settings path is not a regular file: {expanded}")
    return expanded


def validate_value(value):
    """The presentation schema (contracts PresentationSettings): productName
    nonempty string, teamMode bool, lockedProviderProjectIds list of nonempty
    strings, links list of {id,label,url} with an http(s) url."""
    if not isinstance(value, dict):
        die("value file must be a JSON object")
    extra = set(value) - VALUE_KEYS
    missing = VALUE_KEYS - set(value)
    if extra:
        die(f"value has unknown keys: {', '.join(sorted(extra))}")
    if missing:
        die(f"value missing keys: {', '.join(sorted(missing))}")
    name = value["productName"]
    if not isinstance(name, str) or not name.strip():
        die("productName must be a nonempty string")
    if not isinstance(value["teamMode"], bool):
        die("teamMode must be a boolean")
    locked = value["lockedProviderProjectIds"]
    if not isinstance(locked, list) or any(
            not isinstance(p, str) or not p.strip() for p in locked):
        die("lockedProviderProjectIds must be a list of nonempty strings")
    links = value["links"]
    if not isinstance(links, list):
        die("links must be a list")
    for i, link in enumerate(links):
        if not isinstance(link, dict) or set(link) != {"id", "label", "url"}:
            die(f"links[{i}] must be an object with exactly id, label, url")
        if not isinstance(link["id"], str) or not LINK_ID_RE.fullmatch(link["id"]):
            die(f"links[{i}].id must match ^[a-z0-9-]{{1,32}}$")
        if not isinstance(link["label"], str) or not link["label"].strip():
            die(f"links[{i}].label must be a nonempty string")
        if not isinstance(link["url"], str) or not LINK_URL_RE.match(link["url"].strip()):
            die(f"links[{i}].url must be an http(s) URL with a host")


def scan_members(text):
    """Top-level member value spans of a JSON object text.

    Returns (spans, close_idx, last_end): key -> (value_start, value_end)
    character offsets, the closing-brace offset, and the end of the last
    member's value (None for an empty object). Duplicate `presentation` keys
    are refused — the edit target would be ambiguous.
    """
    dec = json.JSONDecoder()

    def ws(i):
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        return i

    i = ws(0)
    if i >= len(text) or text[i] != "{":
        die("settings.json is not a JSON object")
    i = ws(i + 1)
    spans = {}
    last_end = None
    while i < len(text) and text[i] != "}":
        key, kend = dec.raw_decode(text, i)
        if not isinstance(key, str):
            die("settings.json has a non-string top-level key")
        j = ws(kend)
        if j >= len(text) or text[j] != ":":
            die("settings.json member missing ':'")
        j = ws(j + 1)
        _value, vend = dec.raw_decode(text, j)
        if key == "presentation" and key in spans:
            die("settings.json has duplicate top-level 'presentation' keys; "
                "refusing an ambiguous edit")
        spans[key] = (j, vend)
        last_end = vend
        i = ws(vend)
        if i < len(text) and text[i] == ",":
            i = ws(i + 1)
    if i >= len(text) or text[i] != "}":
        die("settings.json object is not closed")
    if text[ws(i + 1):].strip():
        die("settings.json has trailing data after the top-level object")
    return spans, i, last_end


def load_settings(path):
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        die("settings.json is not valid UTF-8")
    try:
        parsed = json.loads(text)
    except ValueError as exc:
        die(f"settings.json does not parse: {exc}")
    if not isinstance(parsed, dict):
        die("settings.json top level is not an object")
    return data, text, parsed


def value_text_of(value):
    return json.dumps(value, indent=2, ensure_ascii=False)


def build_new_text(text, spans, close_idx, last_end, value):
    """Edit only the presentation member's bytes."""
    vt = value_text_of(value)
    if "presentation" in spans:
        vs, ve = spans["presentation"]
        return text[:vs] + vt + text[ve:]
    member = '"presentation": ' + vt
    if last_end is None:
        # empty object: mirror the whitespace that sat before the brace
        trail = " " if text[1:close_idx].strip() == "" and close_idx > 1 else ""
        return text[:close_idx] + member + trail + text[close_idx:]
    sep = "\n  " if "\n" in text else " "
    return text[:last_end] + "," + sep + member + text[last_end:]


def staging_dir_for(settings_path):
    """<root>/run when settings is <root>/home/userdata/settings.json and the
    run dir exists on the same device; else None (temp beside the file)."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(settings_path)))
    run = os.path.join(root, "run")
    try:
        if os.path.isdir(run) and os.stat(run).st_dev == os.stat(
                os.path.dirname(settings_path)).st_dev:
            return run
    except OSError:
        pass
    return None


def write_receipt(receipt_dir, settings_path, value_file, before, after):
    """Preimage bytes 0600 + receipt JSON, in a 0700 dir, BEFORE the write."""
    os.makedirs(receipt_dir, mode=0o700, exist_ok=True)
    st = os.stat(receipt_dir)
    if st.st_uid != os.getuid():
        die(f"receipt dir not owned by this user: {receipt_dir}")
    os.chmod(receipt_dir, 0o700)
    preimage = os.path.join(receipt_dir, "preimage.bin")
    fd = os.open(preimage, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(before)
            fh.flush()
            os.fsync(fh.fileno())
    except BaseException:
        os.unlink(preimage)
        raise
    os.chmod(preimage, 0o600)
    receipt = {
        "tool": "presentation_set.py",
        "settings_path": settings_path,
        "value_file": os.path.abspath(value_file),
        "before_sha256": sha256(before),
        "after_sha256": sha256(after),
        "time_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    rp = os.path.join(receipt_dir, "receipt.json")
    fd = os.open(rp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    return receipt


def read_receipt(receipt_dir):
    rp = os.path.join(receipt_dir, "receipt.json")
    pp = os.path.join(receipt_dir, "preimage.bin")
    if not os.path.isfile(rp) or not os.path.isfile(pp):
        die(f"receipt dir lacks receipt.json/preimage.bin: {receipt_dir}")
    try:
        with open(rp, encoding="utf-8") as fh:
            receipt = json.load(fh)
        with open(pp, "rb") as fh:
            preimage = fh.read()
    except (OSError, ValueError) as exc:
        die(f"cannot read receipt: {exc}")
    if sha256(preimage) != receipt.get("before_sha256"):
        die("receipt preimage does not match its before-sha; refusing")
    return receipt, preimage


def member_diff(text, spans, value):
    old = text[spans["presentation"][0]:spans["presentation"][1]] if (
        "presentation" in spans) else ""
    new = value_text_of(value)
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True), new.splitlines(keepends=True),
        fromfile="presentation (current)", tofile="presentation (proposed)",
        n=0))


def cmd_plan(args):
    path = guard_settings(args.settings, args.real_root_ok)
    data, text, _parsed = load_settings(path)
    spans, _close, _last = scan_members(text)
    with open(args.value_file, encoding="utf-8") as fh:
        value = json.load(fh)
    validate_value(value)
    current = sha256(data)
    print(f"settings: {path}")
    print(f"sha256: {current}")
    print(f"presentation: {'present' if 'presentation' in spans else 'absent'}")
    if args.expect_sha256:
        match = current == args.expect_sha256
        print(f"expect-sha256: {'MATCH' if match else 'MISMATCH'}")
    diff = member_diff(text, spans, value)
    print(diff if diff else "(presentation member unchanged)")
    if args.expect_sha256 and current != args.expect_sha256:
        raise SystemExit(2)


def cmd_apply(args):
    path = guard_settings(args.settings, args.real_root_ok)
    data, text, _parsed = load_settings(path)
    current = sha256(data)
    # preimage check BEFORE the first write of any kind
    if current != args.expect_sha256:
        die(f"preimage mismatch: current sha256 {current} != expected "
            f"{args.expect_sha256}; nothing written")
    with open(args.value_file, encoding="utf-8") as fh:
        value = json.load(fh)
    validate_value(value)
    spans, close_idx, last_end = scan_members(text)
    new_text = build_new_text(text, spans, close_idx, last_end, value)
    new_data = new_text.encode("utf-8")
    # the construction itself must preserve every outside byte
    verify_outside(text, spans, new_text, value)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    receipt = write_receipt(args.receipt_dir, path, args.value_file,
                            data, new_data)
    try:
        atomic_write(path, new_text, mode,
                     staging_dir=staging_dir_for(path),
                     pre_replace=lambda: pre_replace_recheck(path, current))
    except PreimageChangedError as exc:
        die(f"PREIMAGE_CHANGED: {exc}; nothing written")
    # readback: ON-DISK bytes vs the planned bytes, parse, presentation
    # equality, outside bytes, mode, sha
    back, back_text, back_parsed = load_settings(path)
    problems = []
    if back != new_data:
        problems.append("readback bytes differ from the planned bytes")
    if sha256(back) != receipt["after_sha256"]:
        problems.append("readback sha256 differs from the planned after-sha")
    if back_parsed.get("presentation") != value:
        problems.append("readback presentation does not equal the value")
    back_spans, _c, _l = scan_members(back_text)
    if not outside_equal(text, spans, back_text, back_spans):
        problems.append("readback bytes outside the member differ from preimage")
    if stat.S_IMODE(os.stat(path).st_mode) != mode:
        problems.append("readback file mode changed")
    if problems:
        die("READBACK FAILED: " + "; ".join(problems), code=1)
    print(f"applied: {path}")
    print(f"before_sha256: {receipt['before_sha256']}")
    print(f"after_sha256: {receipt['after_sha256']}")
    print(f"receipt: {os.path.join(args.receipt_dir, 'receipt.json')}")


def outside_equal(old_text, old_spans, new_text, new_spans):
    """Every byte outside the presentation member is unchanged."""
    if "presentation" in old_spans and "presentation" in new_spans:
        ovs, ove = old_spans["presentation"]
        nvs, nve = new_spans["presentation"]
        return (old_text[:ovs].encode("utf-8") == new_text[:nvs].encode("utf-8")
                and old_text[ove:].encode("utf-8") == new_text[nve:].encode("utf-8"))
    if "presentation" not in old_spans and "presentation" in new_spans:
        # insertion: removing the inserted member text (and its leading
        # comma/whitespace) must reproduce the old file byte for byte
        nvs, nve = new_spans["presentation"]
        key_start = new_text.rfind('"presentation"', 0, nvs)
        ins_start = key_start
        while ins_start > 0 and new_text[ins_start - 1] in " \t\r\n,":
            ins_start -= 1
        reconstructed = (new_text[:ins_start] + new_text[nve:]).encode("utf-8")
        return reconstructed == old_text.encode("utf-8")
    return False


def verify_outside(text, spans, new_text, value):
    new_spans, _c, _l = scan_members(new_text)
    if not outside_equal(text, spans, new_text, new_spans):
        die("internal error: constructed edit would change outside bytes; "
            "nothing written")
    if json.loads(new_text).get("presentation") != value:
        die("internal error: constructed edit does not carry the value; "
            "nothing written")


def cmd_undo(args):
    path = guard_settings(args.settings, args.real_root_ok)
    receipt, preimage = read_receipt(args.receipt_dir)
    with open(path, "rb") as fh:
        current = fh.read()
    if sha256(current) != receipt["after_sha256"]:
        die(f"current sha256 {sha256(current)} != receipt after-sha "
            f"{receipt['after_sha256']}; someone wrote since the apply; "
            "refusing to undo")
    mode = stat.S_IMODE(os.stat(path).st_mode)
    try:
        atomic_write(path, preimage.decode("utf-8"), mode,
                     staging_dir=staging_dir_for(path),
                     pre_replace=lambda: pre_replace_recheck(
                         path, receipt["after_sha256"]))
    except PreimageChangedError as exc:
        die(f"PREIMAGE_CHANGED: {exc}; nothing written")
    with open(path, "rb") as fh:
        back = fh.read()
    if back != preimage or sha256(back) != receipt["before_sha256"]:
        die("READBACK FAILED: restored bytes differ from the preimage",
            code=1)
    print(f"undone: {path}")
    print(f"restored_sha256: {receipt['before_sha256']}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="presentation_set.py",
        description="Set the presentation key of a T3 server settings.json, "
                    "editing only that member's bytes.")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p, need_value, need_expect, need_receipt):
        p.add_argument("--settings", required=True,
                       help="path to the server's settings.json (required)")
        if need_value:
            p.add_argument("--value-file", required=True,
                           help="JSON file holding the presentation value")
        if need_expect:
            p.add_argument("--expect-sha256", required=True,
                           help="sha256 the current file must have")
        else:
            p.add_argument("--expect-sha256", default=None,
                           help="optional sha256 check for plan")
        if need_receipt:
            p.add_argument("--receipt-dir", required=True,
                           help="directory for the preimage copy and receipt")
        p.add_argument("--real-root-ok", action="store_true",
                       help="the principal's explicit unlock for the real "
                            "team root (~/.mastermind/t3-team)")

    p_plan = sub.add_parser("plan", help="show sha/presence/member diff; "
                            "writes nothing")
    common(p_plan, True, False, False)
    p_plan.set_defaults(func=cmd_plan)
    p_apply = sub.add_parser("apply", help="set the presentation member")
    common(p_apply, True, True, True)
    p_apply.set_defaults(func=cmd_apply)
    p_undo = sub.add_parser("undo", help="restore the receipt's preimage")
    common(p_undo, False, False, True)
    p_undo.set_defaults(func=cmd_undo)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()