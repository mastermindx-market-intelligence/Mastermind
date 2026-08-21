"""Regression fence: no executable/config surface in THIS repo may construct an
ANONYMOUS read of the canonical Macro repository (Sol Day-6 AMENDMENT clause E).

Context: the canonical Macro repo (`mastermindx-market-intelligence/macro`, also
historically hosted under `chriswong6031-creator/macro`) is flipping PUBLIC -> PRIVATE.
Anonymous reads that work today against the public repo -- a raw.githubusercontent.com
fetch, a GitHub Pages URL, a jsdelivr `gh` CDN pull, an unauthenticated Contents API call,
or a bare HTTPS clone/fetch/ls-remote -- all 404 post-flip. `data_layer/macro_refresh.py`
already carries the authenticated seam (MACRO_GIT_REMOTE / MACRO_GIT_SSH_COMMAND, see
DEC:B1-MACRO-PRIVATE-CUTOVER); this file is the PERMANENT fence that stops any OTHER
executable or config surface from silently reintroducing an anonymous read.

Precision is mandatory: the patterns are keyed on the two canonical Macro owners PLUS
the `macro` repo name, never on the bare host. `raw.githubusercontent.com`,
`cdn.jsdelivr.net`, and `github.com` all carry lawful third-party traffic in this repo
(e.g. the Supabase SDK from jsdelivr in app/static/account.js) and must pass by
construction -- see test_supabase_sdk_url_is_not_flagged below.

The one known, deliberate exception -- `data_layer/macro_refresh.py`'s `_REMOTE` default,
which preserves today's exact behavior when `MACRO_GIT_REMOTE` is unset and makes an
unconfigured post-flip host fail LOUDLY (404) rather than silently -- is allowlisted by
exact (file, matched-string) pair, not by weakening any pattern. See _ALLOWLIST below;
it is asserted to still exist and still match, so the exception stays reviewable rather
than silently rotting into a blanket exemption.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_THIS_FILE = Path(__file__).resolve()

# The canonical Macro repo's owners (current + the historical alias it was reachable
# under). Keying every pattern on {owner}/macro -- never on the bare host -- is what
# lets lawful third-party traffic on the same hosts pass by construction.
_OWNERS = ("mastermindx-market-intelligence", "chriswong6031-creator")
_REPO = "macro"
_OWNER_ALT = "|".join(re.escape(o) for o in _OWNERS)

# The five anonymous-read shapes named in the commission. Each is deliberately narrow:
# owner(s) + "/macro" (or ".../macro" for Pages), never the bare host.
_BANNED_PATTERNS: dict[str, re.Pattern] = {
    "raw_githubusercontent": re.compile(
        rf"raw\.githubusercontent\.com/(?:{_OWNER_ALT})/{_REPO}\b"),
    "github_io_pages": re.compile(
        rf"(?:{_OWNER_ALT})\.github\.io/{_REPO}\b"),
    "jsdelivr_gh": re.compile(
        rf"cdn\.jsdelivr\.net/gh/(?:{_OWNER_ALT})/{_REPO}\b"),
    "api_github_contents": re.compile(
        rf"api\.github\.com/repos/(?:{_OWNER_ALT})/{_REPO}/(?:contents|git/blobs|git/trees)\b"),
    "bare_clone_url": re.compile(
        rf"https://github\.com/(?:{_OWNER_ALT})/{_REPO}(?:\.git)?\b"),
}

# --- allowlist ------------------------------------------------------------------
# Exactly ONE known, explicitly-reasoned exception. Keyed on (relative_path, the exact
# matched substring) -- NOT a per-file or per-pattern blanket exemption, so any OTHER
# banned occurrence in the same file (or a different match text) still fails the guard.
_ALLOWLIST: dict[tuple[str, str], str] = {
    ("data_layer/macro_refresh.py",
     "https://github.com/mastermindx-market-intelligence/macro.git"): (
        "DEC:B1-MACRO-PRIVATE-CUTOVER -- _REMOTE's default preserves today's exact "
        "behavior when MACRO_GIT_REMOTE is unset (the public-HTTPS form, unchanged "
        "pre-flip and on the symlink-covered VPS). Post-flip, an unconfigured host's "
        "clone/fetch then 404s LOUDLY instead of silently stranding the checkout. "
        "Deliberate default, not a leaked anonymous read."
    ),
    ("tests/test_macro_refresh.py",
     "https://github.com/mastermindx-market-intelligence/macro.git"): (
        "DEC:B1-MACRO-PRIVATE-CUTOVER -- _PUBLIC_HTTPS_REMOTE in that file's Section E "
        "is a TEST CONSTANT asserting the production _REMOTE default resolves to the "
        "public HTTPS form when MACRO_GIT_REMOTE is unset; it is compared against, "
        "never used to perform a real clone/fetch (every subprocess.run call in that "
        "section is monkeypatched)."
    ),
}

_ALLOWED_EXTS = {".py", ".sh", ".js", ".ts", ".yml", ".yaml", ".json", ".toml"}
# Top-level directories excluded from the walk per the commission's scope, plus
# `vendor` (added here, not in the original scope list): vendor/macro_src is the
# gitignored (.gitignore: "vendor/macro_src/"), build-managed sparse checkout of the
# Macro repo ITSELF -- data_layer/macro_refresh.py's ensure_clone()/refresh() populate
# it from the live remote at test/build time. Its contents are the Macro repo's own
# files (verified live: a real `git remote -v` inside it points at
# mastermindx-market-intelligence/macro), not Mastermind source this repo owns or
# authors -- scanning it would just flag Macro's own config against itself, which is
# out of this repo's authority to fix and irrelevant to "does MASTERMIND construct an
# anonymous read". Confirmed non-vacuous by excluding it: without this exclusion the
# guard fired on vendor/macro_src/config.yml (a mastermindx-market-intelligence.github.io
# reference inside the vendored macro repo's OWN config file) the moment a prior test
# in this run happened to populate the checkout.
_EXCLUDED_TOP_DIRS = {"docs", "research", "vendor"}


def _is_excluded(path: Path) -> bool:
    rel = path.relative_to(_ROOT)
    parts = rel.parts
    if "worktrees" in parts:          # other sessions' nested checkouts, not our content
        return True
    if parts and parts[0] in _EXCLUDED_TOP_DIRS:
        return True
    if path.suffix.lower() == ".md":
        return True
    if path == _THIS_FILE:
        return True
    return False


def _iter_scanned_files():
    for path in _ROOT.rglob("*"):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        if path.suffix not in _ALLOWED_EXTS:
            continue
        if _is_excluded(path):
            continue
        yield path


def find_anonymous_macro_reads(text: str) -> list[str]:
    """Return the list of banned-shape names matched anywhere in `text`.

    A pure function so it can be exercised directly with synthetic strings (the
    non-vacuity tests below) as well as against real file contents (the repo walk).
    """
    return [shape for shape, pattern in _BANNED_PATTERNS.items() if pattern.search(text)]


@pytest.fixture(scope="module")
def violations() -> dict[str, list[tuple[str, str]]]:
    """Walk every in-scope file once. Returns {relpath: [(shape, matched_text), ...]}
    for every banned hit NOT covered by the exact-match allowlist."""
    found: dict[str, list[tuple[str, str]]] = {}
    for path in _iter_scanned_files():
        try:
            text = path.read_text(errors="ignore")
        except Exception:  # noqa: BLE001 - unreadable file is not this guard's concern
            continue
        rel = str(path.relative_to(_ROOT))
        for shape, pattern in _BANNED_PATTERNS.items():
            for m in pattern.finditer(text):
                matched = m.group(0)
                if (rel, matched) in _ALLOWLIST:
                    continue
                found.setdefault(rel, []).append((shape, matched))
    return found


# ---------------------------------------------------------------------------
# the fence itself
# ---------------------------------------------------------------------------

def test_no_anonymous_macro_reads_in_executable_or_config_surfaces(violations):
    """No *.py/*.sh/*.js/*.ts/*.yml/*.yaml/*.json/*.toml file may construct an
    anonymous read of the canonical Macro repo, outside the one explicit allowlist
    entry. A hit here means a NEW anonymous read was introduced -- either remove it
    (use the authenticated data_layer.macro_refresh seam / MACRO_GIT_REMOTE +
    MACRO_GIT_SSH_COMMAND) or, if genuinely deliberate, add a narrowly-scoped,
    reasoned entry to _ALLOWLIST citing the authorizing decision. Never widen a
    pattern to make a hit disappear."""
    assert not violations, (
        f"Anonymous Macro repo read(s) found outside the allowlist: {violations}")


def test_allowlist_entry_is_visible_and_still_matches():
    """Every allowlisted exception must still exist verbatim in its file, still
    match the pattern shape it claims to be exempted from, and cite its authorizing
    decision -- proves each exception is live and reviewable, not a stale or vacuous
    entry quietly widening into a blanket exemption. Both known entries share the
    same underlying string (the production public-HTTPS default): one is the real
    default in data_layer/macro_refresh.py, the other is a test constant in
    tests/test_macro_refresh.py that asserts against it (never performs a real
    clone/fetch) -- kept as two entries, one per file, so each is independently
    reviewable and neither silently covers for drift in the other."""
    assert len(_ALLOWLIST) == 2, (
        f"expected exactly two allowlist entries (the production _REMOTE default in "
        f"data_layer/macro_refresh.py, and the mirroring test constant in "
        f"tests/test_macro_refresh.py), found {len(_ALLOWLIST)}: {list(_ALLOWLIST)}")
    for (rel, matched), reason in _ALLOWLIST.items():
        path = _ROOT / rel
        assert path.exists(), f"allowlisted file {rel} no longer exists"
        text = path.read_text()
        assert matched in text, (
            f"allowlisted string {matched!r} no longer appears verbatim in {rel} -- "
            f"the exception is stale; remove it from _ALLOWLIST")
        assert _BANNED_PATTERNS["bare_clone_url"].search(matched), (
            "allowlist entry no longer matches the 'bare_clone_url' shape it is "
            "exempted from")
        assert "DEC:B1-MACRO-PRIVATE-CUTOVER" in reason, (
            "allowlist entry must cite its authorizing decision")


def test_supabase_sdk_url_is_not_flagged():
    """Precision guard: lawful third-party assets on the SAME hosts the banned
    patterns key on (jsdelivr, github.io, raw.githubusercontent.com) must pass by
    construction -- the guard bans {owner}/macro shapes, never the bare host."""
    supabase_url = "https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/dist/umd/supabase.js"
    assert not find_anonymous_macro_reads(supabase_url), (
        "the Supabase SDK jsdelivr URL must never be flagged by an {owner}/macro guard")
    target = _ROOT / "app" / "static" / "account.js"
    if target.exists():
        text = target.read_text()
        assert "supabase-js" in text, (
            "expected app/static/account.js to still reference the Supabase SDK -- "
            "if it no longer does, this precision check needs a new real example")
        assert not find_anonymous_macro_reads(text), (
            "app/static/account.js (a real file using the jsdelivr host lawfully) "
            "must not be flagged by the anonymous-Macro-read guard")


def test_owners_and_repo_constants_are_the_canonical_ones():
    """Guards the guard: if these constants drift, every pattern silently stops
    matching anything real and the fence goes blind."""
    assert _OWNERS == ("mastermindx-market-intelligence", "chriswong6031-creator")
    assert _REPO == "macro"


# ---------------------------------------------------------------------------
# non-vacuity: each banned shape must actually fire on synthetic text containing it
# ---------------------------------------------------------------------------

def test_non_vacuity_raw_githubusercontent():
    text = ("fetch('https://raw.githubusercontent.com/"
            "mastermindx-market-intelligence/macro/main/site/index.json')")
    assert "raw_githubusercontent" in find_anonymous_macro_reads(text)


def test_non_vacuity_github_io_pages():
    text = ("const url = 'https://mastermindx-market-intelligence.github.io/"
            "macro/site/index.json';")
    assert "github_io_pages" in find_anonymous_macro_reads(text)


def test_non_vacuity_jsdelivr_gh():
    text = ("import data from "
            "'https://cdn.jsdelivr.net/gh/chriswong6031-creator/macro@main/site/index.json'")
    assert "jsdelivr_gh" in find_anonymous_macro_reads(text)


def test_non_vacuity_api_github_contents():
    text = ('requests.get("https://api.github.com/repos/'
            'mastermindx-market-intelligence/macro/contents/site/index.json")')
    assert "api_github_contents" in find_anonymous_macro_reads(text)


def test_non_vacuity_bare_clone_url():
    text = ('subprocess.run(["git", "clone", '
            '"https://github.com/mastermindx-market-intelligence/macro.git", dest])')
    assert "bare_clone_url" in find_anonymous_macro_reads(text)


def test_non_vacuity_second_owner_alias_also_fires():
    """The historical owner alias must trip the same shapes as the current owner --
    a fence keyed on only one owner would miss reads against the alias."""
    text = "https://raw.githubusercontent.com/chriswong6031-creator/macro/main/x.json"
    assert "raw_githubusercontent" in find_anonymous_macro_reads(text)
