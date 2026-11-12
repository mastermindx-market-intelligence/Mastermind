"""Credential redaction for Hermes history export.

redact(text) -> (text, Counter of kind -> n). Replaces credential-shaped
strings with [REDACTED:<kind>:<first 8 hex of sha256 of the match>].
Idempotent: existing markers are never re-redacted. Ordinary prose, bare
40-hex git SHAs and UUIDs are left untouched.
"""
import hashlib
import re
from collections import Counter

__all__ = ["redact"]

_MARKER = re.compile(r"\[REDACTED:[a-z_]+:[0-9a-f]{8}\]")

# Ordered alternatives; first match at the leftmost position wins.
_MASTER = re.compile(
    r"(?P<pem>-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
    # Unterminated (truncated print): header, optional escaped/real newlines, then body chars.
    r"|-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----(?:\\n|\\r|\s)*[A-Za-z0-9+/=](?:[A-Za-z0-9+/=]|\\n|\\r|\s)*)"
    r"|(?P<url_scheme>[A-Za-z][A-Za-z0-9+.-]*://)(?P<url_user>[^\s/:@]+):(?P<url_pw>[^\s@/]+)@"
    r"|(?i:bearer)\s+(?P<bearer_tok>[A-Za-z0-9._~+/\-]{20,}=*)"
    r"|(?P<jwt>\beyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)"
    r"|(?P<sk>\bsk-[A-Za-z0-9_\-]{20,})"
    r"|(?P<github>\b(?:ghp_|gho_|ghs_|ghu_)[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,})"
    r"|(?P<slack>\bxox[abposr]-[A-Za-z0-9\-]{10,}|\bxapp-[A-Za-z0-9\-]{10,})"
    r"|(?P<aws>\b(?:AKIA|ASIA)[A-Z0-9]{16}\b)"
    r"|(?P<google>\bAIza[A-Za-z0-9_\-]{35}\b)"
    r"|(?P<kv_qkw>\b(?i:password|passwd|secret|token|api[_-]?key|auth))"
    r"(?P<kv_qsep>\s*[=:]\s*)(?P<kv_q>[\"'])(?P<kv_qval>[^\"'\n]{8,})(?P=kv_q)"
    r"|(?P<kv_kw>\b(?i:password|passwd|secret|token|api[_-]?key|auth))"
    r"(?P<kv_sep>\s*[=:]\s*)(?P<kv_val>[^\s\"'<>\[\]{},;]{8,})"
)


def _marker(kind, secret):
    digest = hashlib.sha256(secret.encode("utf-8", "replace")).hexdigest()[:8]
    return f"[REDACTED:{kind}:{digest}]"


def _replace(m):
    if m.group("pem") is not None:
        return _marker("pem", m.group("pem"))
    if m.group("url_pw") is not None:
        return m.group("url_scheme") + m.group("url_user") + ":" + _marker("url_password", m.group("url_pw")) + "@"
    if m.group("bearer_tok") is not None:
        prefix = m.group(0)[: m.start("bearer_tok") - m.start(0)]
        return prefix + _marker("bearer", m.group("bearer_tok"))
    for kind in ("jwt", "sk", "github", "slack", "aws", "google"):
        if m.group(kind) is not None:
            return _marker(kind, m.group(kind))
    if m.group("kv_qval") is not None:
        return m.group("kv_qkw") + m.group("kv_qsep") + m.group("kv_q") + _marker("kv_secret", m.group("kv_qval")) + m.group("kv_q")
    if m.group("kv_val") is not None:
        return m.group("kv_kw") + m.group("kv_sep") + _marker("kv_secret", m.group("kv_val"))
    return m.group(0)  # unreachable


def _redact_segment(text, counts):
    def sub(m):
        replacement = _replace(m)
        if replacement != m.group(0):
            # count once per replacement, keyed by kind
            for kind in ("pem", "url_password", "bearer", "jwt", "sk", "github", "slack", "aws", "google", "kv_secret"):
                if f"[REDACTED:{kind}:" in replacement:
                    counts[kind] += 1
                    break
        return replacement

    return _MASTER.sub(sub, text)


def redact(text):
    """Redact credential-shaped strings. Returns (new_text, Counter).

    None passes through (NULL message content). Existing [REDACTED:...]
    markers are protected, so redact(redact(x)) == redact(x).
    """
    if text is None:
        return None, Counter()
    counts = Counter()
    parts = []
    last = 0
    for m in _MARKER.finditer(text):
        parts.append(_redact_segment(text[last:m.start()], counts))
        parts.append(m.group(0))
        last = m.end()
    parts.append(_redact_segment(text[last:], counts))
    return "".join(parts), counts
