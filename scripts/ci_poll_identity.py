"""Prospective CI cooldown poll identity for ``gh pr view`` / ``gh pr checks``.

Standard-library only and self-contained.  Designed to be embedded verbatim in
the installed anti-waste hook immediately before the existing ``_poll_key``
helper; the hook keeps its 300s cooldown state, watch/mutation/refusal regexes
and run-view handling unchanged and consults this helper for the
``gh pr view`` / ``gh pr checks`` numeric poll targets.

``ci_pr_poll_identity(command, cwd)`` returns a scoped cooldown key, or
``None`` when the command is not a classifiable poll.  ``None`` means "no
anti-waste evidence for this invocation" and never authorizes or refuses
anything by itself.
"""

import os
import re

__all__ = ["ci_pr_poll_identity"]

_VERB_KINDS = {"checks": "pr-checks", "view": "pr-view"}
_ID_SCAN_WINDOW = 12

# Original status-field signal.  Applied to a quote-masked tail so a jq
# program such as --jq '.state' is never read as a requested status field.
_VIEW_STATUS_RE = re.compile(
    r"statusCheckRollup|mergeStateStatus|reviewDecision|mergedAt|mergeCommit"
    r"|isDraft|\bstate\b",
    re.I,
)

# Source facts carried in the key; status fields are deliberately NOT carried,
# so rotating them cannot mint a fresh cooldown key.
_SOURCE_FIELDS = (
    "author",
    "baseRefName",
    "baseRefOid",
    "body",
    "commits",
    "comments",
    "files",
    "headRefName",
    "headRefOid",
    "title",
)
_STATUS_FIELDS = frozenset(
    (
        "statusCheckRollup",
        "mergeStateStatus",
        "reviewDecision",
        "mergedAt",
        "mergeCommit",
        "isDraft",
        "state",
    )
)
_FIELD_ALIASES = {name.lower(): name for name in _SOURCE_FIELDS}
_FIELD_ALIASES.update({name.lower(): name for name in _STATUS_FIELDS})


def _quoted_spans(text):
    """Return inclusive (start, end) spans of quoted regions in ``text``."""
    spans = []
    quote = None
    start = 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                spans.append((start, i + 1))
                quote = None
        elif ch in "\"'":
            quote = ch
            start = i
    if quote:
        # Unterminated quote: fence the remainder as quoted text.
        spans.append((start, len(text)))
    return spans


def _in_spans(spans, pos):
    return any(begin <= pos < end for begin, end in spans)


def _mask_quotes(text):
    spans = _quoted_spans(text)
    return "".join(
        " " if _in_spans(spans, i) else ch for i, ch in enumerate(text)
    )


def _segments(command):
    """Split a compound shell command on unquoted ``;&|`` and newlines."""
    parts = []
    cur = []
    quote = None
    for ch in command:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in ";&|\n":
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _tokens(text):
    """Whitespace tokens as (value, start_offset); quotes stripped from values."""
    toks = []
    cur = []
    start = None
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
            else:
                cur.append(ch)
            continue
        if ch in "\"'":
            if start is None:
                start = i
            quote = ch
            continue
        if ch.isspace():
            if cur:
                toks.append(("".join(cur), start))
                cur = []
                start = None
            continue
        if start is None:
            start = i
        cur.append(ch)
    if cur:
        toks.append(("".join(cur), start))
    return toks


def _target_index(toks, j):
    """(id, token index) of the numeric target after the verb, else None."""
    expect_value = False
    for k in range(j + 1, min(j + 1 + _ID_SCAN_WINDOW, len(toks))):
        tok = toks[k][0]
        if expect_value:
            expect_value = False
            continue
        if tok.startswith("-"):
            if "=" not in tok:
                expect_value = True
            continue
        if tok.isdigit():
            return tok, k
        return None
    return None


def _match_invocation(toks, i, verb, spans):
    """Match ``gh [flags] pr [flags] <verb> [flags] <numeric>`` from token i."""
    seen_pr = False
    expect_value = False
    for j in range(i + 1, len(toks)):
        tok, pos = toks[j]
        if expect_value:
            expect_value = False
            continue
        if _in_spans(spans, pos):
            break
        if tok == "pr" and not seen_pr:
            seen_pr = True
            continue
        if tok.startswith("-"):
            if "=" not in tok and not (tok.startswith("-R") and tok != "-R"):
                expect_value = True
            continue
        if not seen_pr:
            return None  # a different subcommand tree, e.g. gh repo view
        if tok.lower() != verb:
            return None  # pr <other verb>, e.g. gh pr merge (hook-owned)
        target = _target_index(toks, j)
        if not target:
            return None
        pid, k = target
        id_pos = toks[k][1]
        if _in_spans(spans, id_pos):
            return None
        return pid, id_pos
    return None


def _find_invocation(segment, verb):
    """First unquoted ``gh pr <verb> <numeric>`` invocation as (id, tail_start)."""
    spans = _quoted_spans(segment)
    toks = _tokens(segment)
    for i, (tok, pos) in enumerate(toks):
        if tok.lower() != "gh" or _in_spans(spans, pos):
            continue
        found = _match_invocation(toks, i, verb, spans)
        if found is not None:
            return found
    return None


def _repo_from_tokens(tokens):
    """Normalized explicit -R/--repo owner/repo value, or None."""
    for i, tok in enumerate(tokens):
        val = None
        if tok == "--repo" or tok == "-R":
            nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
            if nxt and not nxt.startswith("-"):
                val = nxt
        elif tok.startswith("--repo="):
            val = tok[len("--repo="):]
        elif tok.startswith("-R="):
            val = tok[len("-R="):]
        elif tok.startswith("-R") and len(tok) > 2 and tok[2] != "-":
            val = tok[2:]
        if val:
            val = val.strip().strip("'\"").strip().lower()
            if val and not val.startswith("-"):
                return val
    return None


def _json_fields(tokens):
    """Requested --json field names; --jq values are never consumed."""
    fields = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--json":
            j = i + 1
            while j < len(tokens) and not tokens[j].startswith("-"):
                fields.append(tokens[j])
                j += 1
            i = j
            continue
        if tok.startswith("--json="):
            fields.append(tok[len("--json="):])
        i += 1
    out = []
    for chunk in fields:
        out.extend(part.strip() for part in chunk.split(","))
    return [part for part in out if part]


def _scope(tokens, cwd):
    """Repository-aware scope token, or None when no safe scope exists."""
    repo = _repo_from_tokens(tokens)
    if repo:
        return "repo:" + repo
    if not isinstance(cwd, str):
        return None
    raw = cwd.strip()
    if not raw:
        return None
    try:
        path = os.path.normpath(raw)
    except Exception:
        return None
    if not os.path.isabs(path):
        return None
    return "cwd:" + path


def ci_pr_poll_identity(command, cwd=""):
    """Cooldown key for a recognized gh pr view/checks poll, else None.

    Keys carry the numeric target, a repository scope (normalized explicit
    ``-R/--repo owner/repo`` before or after the subcommand, or the canonical
    absolute ``cwd`` path when the repository is omitted), and, when source
    facts are requested, the deterministic sorted source field-set.
    Status-only and status-tail requests share one key per target+scope so
    rotating status fields cannot bypass the cooldown.  Unknown-scope polls
    (no repo, no usable cwd) return ``None`` rather than an unscoped key that
    could collide across repositories.
    """
    if not isinstance(command, str):
        return None
    for segment in _segments(command):
        found = _find_invocation(segment, "checks")
        kind = _VERB_KINDS["checks"]
        if found is None:
            found = _find_invocation(segment, "view")
            kind = _VERB_KINDS["view"]
        if found is None:
            continue
        pid, tail_start = found
        tokens = [tok for tok, _pos in _tokens(segment)]
        scope = _scope(tokens, cwd)
        if scope is None:
            return None
        base = f"{kind}:{pid}|{scope}"
        if kind == "pr-checks":
            return base
        src = set()
        status_req = False
        for name in _json_fields(tokens):
            canon = _FIELD_ALIASES.get(name.lower())
            if canon is None:
                continue
            if canon in _STATUS_FIELDS:
                status_req = True
            else:
                src.add(canon)
        if src:
            return f"{base}|src={','.join(sorted(src))}"
        has_json = any(token == "--json" or token.startswith("--json=") for token in tokens)
        if status_req or (not has_json and _VIEW_STATUS_RE.search(_mask_quotes(segment[tail_start:]))):
            return base
        return None
    return None


def ci_pr_poll_mutation_keys(command, cwd, state):
    """Existing material-mutation invalidation, scoped to the affected PR."""
    keys = set()
    for segment in _segments(command):
        scope = _scope([token for token, _ in _tokens(segment)], cwd)
        if scope is None:
            continue
        for verb in ("edit", "ready", "merge", "close", "reopen", "review", "comment"):
            found = _find_invocation(segment, verb)
            if found is None:
                continue
            number, _ = found
            prefixes = (f"pr-view:{number}|{scope}", f"pr-checks:{number}|{scope}")
            keys.update(key for key in state if any(
                key == prefix or key.startswith(prefix + "|") for prefix in prefixes
            ))
    return keys
