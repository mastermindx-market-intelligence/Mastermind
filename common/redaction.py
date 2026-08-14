"""Bounded, shape-redacting sanitizer for externally-produced error text.

Any string that originates OUTSIDE this process — a Supabase error body, the
Claude Code SDK's exception repr, a ``requests`` exception carrying the full
request URL — must pass through :func:`sanitize_external_text` before it reaches
an HTTP client or a log file.  We do not control what an upstream puts in its
own error text, which is exactly why forwarding it has to be bounded rather than
trusted.

The approach is copied from ``ops/executive_os/acceptance.py``
(``_sanitize_refusal_fragment`` / ``_refusal_detail``), which bounds
operator-visible refusal reasons for Executive OS control commands.  That module
is deliberately left untouched: it sits in the acceptance proof path and carries
harness-specific rules this one must not inherit (see "Divergences" below).

Order of operations (LOAD-BEARING, pinned by ``tests/test_secret_redaction.py``)

1. exact known secrets (longest first, so a prefix of one cannot survive)
2. control characters -> space
3. JWT-shaped tokens
4. known-prefix credentials (``sb_secret_``, ``sk-ant-``, ...)
5. hex runs >= 32
6. base64url-ish runs >= 32
7. whitespace collapse to a single line
8. hard length bound with a visible truncation marker

Redaction MUST complete before the length bound.  Truncating first can cut a
secret-shaped run below the 32-character match threshold, and the surviving
prefix would then be printed verbatim.

Divergences from the acceptance-path reference, both deliberate:

* No Git-object-id exemption.  The acceptance harness exempts exactly-40
  lowercase hex because its proof premise is an exact-SHA comparison and those
  refusals must stay readable.  No client-facing error here needs to print a
  SHA, so exempting that shape would only create a hole for any 40-hex secret.
* Exact-secret redaction is seeded from the process environment by default
  (:func:`environment_secrets`), so the credentials this repo actually holds are
  removed by identity and not merely by shape.  Shape rules are the backstop,
  not the primary guarantee.

Known bound, stated rather than papered over: ``/`` is excluded from the token
class so that filesystem paths and URLs survive redaction.  A secret in the
*standard* base64 alphabet that happens to contain ``/`` is therefore split into
runs, and a residue shorter than 32 characters could survive shape redaction
alone.  Every credential this repo holds is hex or base64url (Supabase JWT and
``sb_secret_``, Anthropic ``sk-ant-``, Polygon/Massive API keys), and all of
them are covered by identity through :func:`environment_secrets`.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping

__all__ = [
    "REDACTION",
    "DEFAULT_LIMIT",
    "TRUNCATION_MARKER",
    "environment_secrets",
    "sanitize_external_text",
]

REDACTION = "<redacted>"
TRUNCATION_MARKER = "...[truncated]"
DEFAULT_LIMIT = 300

# An exact secret shorter than this is not worth matching: it is far more likely
# to be a flag value ("true", "none") that happens to live in a ``*_KEY`` env var
# than a credential, and redacting common short words would corrupt the message
# we are trying to make readable.
_MIN_EXACT_SECRET_LEN = 8

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

# Every JWT header is the base64url of ``{"...``, i.e. it starts with ``eyJ``.
# Anchoring there keeps the rule from matching ordinary dotted text (hostnames,
# module paths, sentences) while collapsing a whole three-segment token into one
# marker instead of three.  The trailing segment is optional: ``alg:none`` tokens
# carry an empty signature.
#
# The lookbehind excludes ONLY alphanumerics, deliberately.  A wider class would
# have to exclude ``=``, and a credential's single most common position in error
# text is immediately after one (``apikey=eyJ…``, ``token=sb_secret_…``) -- the
# exact case these rules exist for.
_JWT_RE = re.compile(
    r"(?<![0-9A-Za-z])"
    r"eyJ[0-9A-Za-z+/=_-]{4,}\.[0-9A-Za-z+/=_-]{4,}(?:\.[0-9A-Za-z+/=_-]*)?"
)

# Credential formats that are recognisable by prefix.  These are matched with a
# tail of only 8+ characters so that a SHORT prefixed key -- one that would slip
# under the 32-character shape threshold below -- is still redacted.
_SECRET_PREFIXES = (
    "sb_secret_",       # Supabase secret (service-role) key, current format
    "sb_publishable_",  # Supabase publishable key, current format
    "sbp_",             # Supabase Management API personal token
    "sk-ant-",          # Anthropic API key / OAuth token
    "sk-",              # OpenAI-style secret key
    "github_pat_",      # GitHub fine-grained PAT
    "ghp_",             # GitHub personal access token
    "gho_",             # GitHub OAuth token
    "ghs_",             # GitHub server-to-server token
)
# Same lookbehind reasoning as the JWT rule: a short prefixed key sitting in a
# query string (``&apiKey=sk-abcdefghij``) is under every shape threshold, so if
# ``=`` blocked this rule nothing else would catch it.
_PREFIXED_SECRET_RE = re.compile(
    r"(?<![0-9A-Za-z])"
    r"(?:" + "|".join(re.escape(prefix) for prefix in _SECRET_PREFIXES) + r")"
    r"[0-9A-Za-z+/=_-]{8,}"
)

# The token class is a strict superset of hex, so the token rule alone would
# already redact every hex run.  The hex rule exists to REDUCE over-redaction: it
# runs first with narrower boundaries, so ``sessionid_<32 hex>`` loses only the
# digest (``sessionid_<redacted>``) instead of the whole run.
_HEX_SECRET_RE = re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{32,}(?![0-9A-Za-z])")
_TOKEN_SECRET_RE = re.compile(
    r"(?<![0-9A-Za-z+=_-])[0-9A-Za-z+=_-]{32,}(?![0-9A-Za-z+=_-])"
)

# Environment variables whose NAME contains one of these markers are treated as
# holding a credential.  Over-collection is the safe direction: redacting a path
# out of an error message costs a little context, leaking a key costs the key.
_ENV_SECRET_NAME_MARKERS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
)


def environment_secrets(
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    """Return credential values found in the environment, longest first.

    Read at call time, never cached: the process environment is mutated by
    deploys and by tests, and a cached snapshot would silently stop covering a
    rotated key.
    """

    env = os.environ if environ is None else environ
    found: set[str] = set()
    for name, value in env.items():
        upper = str(name).upper()
        if not any(marker in upper for marker in _ENV_SECRET_NAME_MARKERS):
            continue
        text = str(value or "").strip()
        if len(text) >= _MIN_EXACT_SECRET_LEN:
            found.add(text)
    return tuple(sorted(found, key=len, reverse=True))


def sanitize_external_text(
    value: object,
    *,
    extra_secrets: Iterable[str] = (),
    limit: int = DEFAULT_LIMIT,
    include_environment: bool = True,
) -> str:
    """Render externally-produced text as a bounded, single-line, redacted string.

    ``value`` is coerced with :func:`str`; ``None`` becomes ``""``.  Upstream
    error bodies are not guaranteed to hand back a string, and a non-string
    leaking into a response body is its own defect.

    Returns ``""`` when nothing survives.  Callers that must always produce a
    message are responsible for their own fallback text -- inventing one here
    would put words in an upstream's mouth.
    """

    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)

    secrets: set[str] = {
        item.strip()
        for item in extra_secrets
        if isinstance(item, str) and len(item.strip()) >= _MIN_EXACT_SECRET_LEN
    }
    if include_environment:
        secrets.update(environment_secrets())
    # Longest first: redacting a short secret that is a prefix of a longer one
    # would leave the longer one's tail in place.
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, REDACTION)

    text = _CONTROL_CHARS_RE.sub(" ", text)
    text = _JWT_RE.sub(REDACTION, text)
    text = _PREFIXED_SECRET_RE.sub(REDACTION, text)
    text = _HEX_SECRET_RE.sub(REDACTION, text)
    text = _TOKEN_SECRET_RE.sub(REDACTION, text)
    text = " ".join(text.split())

    if limit > 0 and len(text) > limit:
        text = text[:limit] + TRUNCATION_MARKER
    return text
