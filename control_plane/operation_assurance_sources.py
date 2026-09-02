"""control_plane.operation_assurance_sources — OLS-A2 AGENT_OS gather adapter.

Implements the sole I/O module of the bounded gather/source-compiler seam per
docs/superpowers/specs/2026-09-01-operation-assurance-a2-source-seam-design.md
Section 4. It reads Agent OS records (``agentos.workstream.v1`` /
``agentos.handoff.v1``) from a caller-supplied checkout DIRECTORY at ONE
explicitly pinned full-SHA revision, and emits the invocation-local
``mastermind.operation_assurance_source_facts.v1`` structure defined by this
module (Section 3 of the design: no protected predecessor wire exists; this
module defines and freezes it by executable test).

Boundary (binding, Section 4 + Section 8 no-rebuild):
    * this is the ONLY module in the OLS-A2 vertical with read I/O;
    * it never runs git, never shells out, never opens a network socket,
      never writes/caches/persists anything; re-gathering always produces a
      fresh structure;
    * frontmatter is a strict, minimal, CLOSED-field-set reader for exactly
      the two agentos schemas (agentos/schema/workstream.schema.yml and
      agentos/schema/handoff.schema.yml as mirrored below) — the record BODY
      (prose after the second ``---``) is never parsed;
    * a missing, unreadable, truncated, or malformed record becomes an
      explicit SOURCE_MISSING / SOURCE_PARTIAL / SOURCE_TRUNCATED fact, never
      a healthy default; nothing here ever asserts Freshness.CURRENT.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from pathlib import Path
from typing import Any

SOURCE_FACTS_SCHEMA = "mastermind.operation_assurance_source_facts.v1"

SOURCE_OWNER = "AGENT_OS"

WORKSTREAM_SCHEMA = "agentos.workstream.v1"
HANDOFF_SCHEMA = "agentos.handoff.v1"

# The frozen first target operation (design Section 5): the OLS-A2 vertical
# compiles exactly this workstream. Gathering is not limited to it (any
# agentos/workstreams|handoffs record present under the pinned checkout is
# read, bounded), but a SOURCE_MISSING fact is synthesized for this exact
# path when it is absent, because the compiler downstream requires an
# explicit fact rather than silent absence.
FIRST_TARGET_WORKSTREAM_KEY = "OPERATION-ASSURANCE"

_WORKSTREAM_GLOB = "agentos/workstreams/*.md"
_HANDOFF_GLOB = "agentos/handoffs/*.md"

MAX_FILE_BYTES = 262_144  # 256 KiB per record; generous for authored prose+frontmatter
MAX_TOTAL_BYTES = 8_388_608  # 8 MiB across one gather call
MAX_FILES_PER_FAMILY = 2048

_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_OBSERVED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:/+-]*$")
_SEAT_TOKEN_RE = re.compile(r"\((CHAIRMAN|CEO|COO|WORKER)\s+seat\)", re.IGNORECASE)

_WAVE_STATUS_VALUES = frozenset({"todo", "in_progress", "awaiting_ci", "done", "dropped"})
_WORKSTREAM_STATUS_VALUES = frozenset(
    {"proposed", "active", "blocked", "awaiting_ci", "awaiting_review", "done", "parked", "killed"}
)
_HANDOFF_MODEL_VALUES = frozenset({"fable", "opus", "sonnet", "haiku", "codex", "local", "sol"})
_HANDOFF_ENDED_BECAUSE_VALUES = frozenset(
    {"complete", "ci_handoff", "blocked", "context_budget", "crashed"}
)
_WAIT_KIND_VALUES = frozenset({"EXTERNAL_GATE", "INTENTIONAL_WAIT"})

STATUS_OK = "OK"
STATUS_SOURCE_MISSING = "SOURCE_MISSING"
STATUS_SOURCE_PARTIAL = "SOURCE_PARTIAL"
STATUS_SOURCE_TRUNCATED = "SOURCE_TRUNCATED"

CONFLICT_NONE = "NONE"
CONFLICT_CONFLICT = "CONFLICT"

# REPAIR B2 (Sol pre-review): the pinned revision is bound to the checkout
# read, without inflating the language into a full content attestation.
# GIT_HEAD_VERIFIED means repo_root's own .git ref metadata (read as plain
# files, never via subprocess) resolves to exactly the asserted revision.
# It is NOT a claim that the working tree's bytes are proven identical to
# that commit's tree objects (an uncommitted local modification could still
# diverge — that residual gap is disclosed, not hidden; see module
# docstring and DEVIATIONS in the OLS-A2 packet). CALLER_ASSERTED_UNVERIFIED
# means repo_root carries no readable git identity at all (a bare
# directory, or a `.git` this module could not resolve) — the revision is
# then exactly what it always was: the caller's own assertion, recorded,
# never silently promoted to "verified".
REVISION_BINDING_GIT_HEAD_VERIFIED = "GIT_HEAD_VERIFIED"
REVISION_BINDING_CALLER_ASSERTED_UNVERIFIED = "CALLER_ASSERTED_UNVERIFIED"
_REVISION_BINDING_VALUES = frozenset(
    {REVISION_BINDING_GIT_HEAD_VERIFIED, REVISION_BINDING_CALLER_ASSERTED_UNVERIFIED}
)

MAX_SOURCE_FACTS_JSON_BYTES = 8_388_608


class SourceGatherError(ValueError):
    """The whole gather call is refused. Carries a stable reason code."""

    def __init__(self, reason_code: str, message: str):
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


class _RecordParseError(ValueError):
    """Internal: one record's frontmatter is refused. Never escapes this module."""

    def __init__(self, reason_code: str, message: str):
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {message}")


def _dc_to_dict(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {f.name: _dc_to_dict(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, tuple):
        return [_dc_to_dict(v) for v in value]
    if isinstance(value, dict):
        return {k: _dc_to_dict(v) for k, v in value.items()}
    return value


@dataclasses.dataclass(frozen=True)
class FamilyCoverage:
    record_schema: str
    glob: str
    attempted: int
    ok: int
    truncated: bool


@dataclasses.dataclass(frozen=True)
class SourceFact:
    source_owner: str
    repo: str
    revision: str
    path: str
    record_schema: str
    content_digest: str
    observed_at: str
    status: str
    reason: str | None
    payload: dict | None
    conflict: str

    def source_ref(self) -> str:
        return f"{self.repo}@{self.revision}:{self.path}#sha256:{self.content_digest}"


@dataclasses.dataclass(frozen=True)
class SourceFacts:
    schema: str
    source_owner: str
    repo: str
    revision: str
    observed_at: str
    revision_binding: str
    coverage: tuple[FamilyCoverage, ...]
    facts: tuple[SourceFact, ...]

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "source_owner": self.source_owner,
            "repo": self.repo,
            "revision": self.revision,
            "observed_at": self.observed_at,
            "revision_binding": self.revision_binding,
            "coverage": [_dc_to_dict(c) for c in self.coverage],
            "facts": [_dc_to_dict(f) for f in self.facts],
        }

    # -----------------------------------------------------------------
    # REPAIR B1 (Sol pre-review): the invocation-local source-facts wire
    # accepted on ``--from-facts`` must be genuinely CLOSED, not merely a
    # field-copying passthrough. Every constraint the gather adapter itself
    # enforces at construction time is re-enforced here on ingest: closed
    # field sets at every level (top level, per-fact, per-coverage-entry,
    # per-OK-payload), closed enums, single repo/revision/observed_at
    # across every fact, coverage counts consistent with the facts actually
    # present, and — the one that matters most — every OK fact's payload is
    # RE-VALIDATED through the exact same bounded frontmatter shape/domain
    # validators the adapter used at gather time, never merely trusted
    # because it arrived pre-parsed.
    # -----------------------------------------------------------------

    _TOP_LEVEL_FIELDS = frozenset(
        {"schema", "source_owner", "repo", "revision", "observed_at", "revision_binding", "coverage", "facts"}
    )
    _COVERAGE_FIELDS = frozenset({"record_schema", "glob", "attempted", "ok", "truncated"})
    _FACT_FIELDS = frozenset(
        {
            "source_owner",
            "repo",
            "revision",
            "path",
            "record_schema",
            "content_digest",
            "observed_at",
            "status",
            "reason",
            "payload",
            "conflict",
        }
    )
    _FACT_STATUS_VALUES = frozenset(
        {STATUS_OK, STATUS_SOURCE_MISSING, STATUS_SOURCE_PARTIAL, STATUS_SOURCE_TRUNCATED}
    )
    _RECORD_SCHEMA_VALUES = frozenset({WORKSTREAM_SCHEMA, HANDOFF_SCHEMA})
    _CONFLICT_VALUES = frozenset({CONFLICT_NONE, CONFLICT_CONFLICT})
    _FULL_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> "SourceFacts":
        """The ONE canonical ingest entry point for a caller-supplied
        source-facts document (CLI ``--from-facts`` file or stdin bytes).
        Strict UTF-8, strict JSON (duplicate keys refused at EVERY nesting
        level via ``object_pairs_hook`` — including inside every fact's
        ``payload``), then the full closed-wire validation in
        :meth:`from_dict`.
        """
        if len(raw) > MAX_SOURCE_FACTS_JSON_BYTES:
            raise SourceGatherError("INPUT_TOO_LARGE", "source-facts document exceeds MAX_SOURCE_FACTS_JSON_BYTES")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"source-facts document is not valid UTF-8: {exc}") from exc
        doc = _strict_json_loads(text)
        return cls.from_dict(doc)

    @classmethod
    def from_dict(cls, doc: dict) -> "SourceFacts":
        if not isinstance(doc, dict):
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "source-facts document must be an object")
        unknown = set(doc.keys()) - cls._TOP_LEVEL_FIELDS
        if unknown:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"unknown top-level field(s) {sorted(unknown)}")
        missing = cls._TOP_LEVEL_FIELDS - set(doc.keys())
        if missing:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"missing top-level field(s) {sorted(missing)}")
        try:
            schema = doc["schema"]
            if schema != SOURCE_FACTS_SCHEMA:
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"schema must be {SOURCE_FACTS_SCHEMA!r}")
            source_owner = doc["source_owner"]
            if source_owner != SOURCE_OWNER:
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"source_owner must be {SOURCE_OWNER!r}")
            repo = doc["repo"]
            if not isinstance(repo, str) or not repo.strip():
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", "repo must be a non-empty string")
            revision = doc["revision"]
            if not isinstance(revision, str) or not _FULL_SHA_RE.match(revision):
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", "revision must be a full 40-hex commit SHA")
            observed_at = doc["observed_at"]
            if not isinstance(observed_at, str) or not _OBSERVED_AT_RE.match(observed_at):
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", "observed_at must be one UTC 'Z' cutoff timestamp")
            revision_binding = doc["revision_binding"]
            if revision_binding not in _REVISION_BINDING_VALUES:
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"revision_binding must be one of {sorted(_REVISION_BINDING_VALUES)}")

            coverage_raw = doc["coverage"]
            if not isinstance(coverage_raw, list):
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", "coverage must be a list")
            coverage_list = []
            seen_families: set[str] = set()
            for c in coverage_raw:
                if not isinstance(c, dict):
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", "each coverage entry must be an object")
                c_unknown = set(c.keys()) - cls._COVERAGE_FIELDS
                if c_unknown:
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"unknown coverage field(s) {sorted(c_unknown)}")
                c_missing = cls._COVERAGE_FIELDS - set(c.keys())
                if c_missing:
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"missing coverage field(s) {sorted(c_missing)}")
                rs = c["record_schema"]
                if rs not in cls._RECORD_SCHEMA_VALUES:
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"coverage.record_schema {rs!r} is not recognized")
                if rs in seen_families:
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"duplicate coverage entry for {rs!r}")
                seen_families.add(rs)
                attempted, ok = c["attempted"], c["ok"]
                truncated = c["truncated"]
                if type(attempted) is not int or attempted < 0:
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", "coverage.attempted must be a non-negative int")
                if type(ok) is not int or ok < 0 or ok > attempted:
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", "coverage.ok must be a non-negative int <= attempted")
                if type(truncated) is not bool:
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", "coverage.truncated must be a bool")
                coverage_list.append(
                    FamilyCoverage(record_schema=rs, glob=c["glob"], attempted=attempted, ok=ok, truncated=truncated)
                )
            if seen_families != cls._RECORD_SCHEMA_VALUES:
                raise SourceGatherError(
                    "INVALID_SOURCE_BUNDLE",
                    f"coverage must carry exactly one entry per family {sorted(cls._RECORD_SCHEMA_VALUES)}",
                )

            facts_raw = doc["facts"]
            if not isinstance(facts_raw, list):
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", "facts must be a list")
            facts_list: list[SourceFact] = []
            seen_paths: set[str] = set()
            for f in facts_raw:
                facts_list.append(cls._parse_and_revalidate_fact(f, repo=repo, revision=revision, observed_at=observed_at))
                if facts_list[-1].path in seen_paths:
                    raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"duplicate fact path {facts_list[-1].path!r}")
                seen_paths.add(facts_list[-1].path)

            cls._check_coverage_consistency(coverage_list, facts_list)

            return SourceFacts(
                schema=schema,
                source_owner=source_owner,
                repo=repo,
                revision=revision,
                observed_at=observed_at,
                revision_binding=revision_binding,
                coverage=tuple(coverage_list),
                facts=tuple(facts_list),
            )
        except SourceGatherError:
            raise
        except (KeyError, TypeError) as exc:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"malformed source-facts document: {exc}") from exc

    @classmethod
    def _parse_and_revalidate_fact(cls, f: object, *, repo: str, revision: str, observed_at: str) -> SourceFact:
        if not isinstance(f, dict):
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "each fact must be an object")
        unknown = set(f.keys()) - cls._FACT_FIELDS
        if unknown:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"unknown fact field(s) {sorted(unknown)}")
        missing = cls._FACT_FIELDS - set(f.keys())
        if missing:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"missing fact field(s) {sorted(missing)}")

        if f["source_owner"] != SOURCE_OWNER:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "every fact.source_owner must be AGENT_OS")
        if f["repo"] != repo:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "every fact.repo must equal the single top-level repo")
        if f["revision"] != revision:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "every fact.revision must equal the single top-level revision (single-revision rule)")
        if f["observed_at"] != observed_at:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "every fact.observed_at must equal the single top-level observed_at (single-cutoff rule)")

        record_schema = f["record_schema"]
        if record_schema not in cls._RECORD_SCHEMA_VALUES:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"fact.record_schema {record_schema!r} is not recognized")
        path = f["path"]
        expected_prefix = "agentos/workstreams/" if record_schema == WORKSTREAM_SCHEMA else "agentos/handoffs/"
        if not isinstance(path, str) or not path.startswith(expected_prefix) or not path.endswith(".md"):
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"fact.path {path!r} does not match its record_schema family")

        status = f["status"]
        if status not in cls._FACT_STATUS_VALUES:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"fact.status {status!r} is not recognized")

        digest = f["content_digest"]
        if not isinstance(digest, str):
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "fact.content_digest must be a string")
        if status == STATUS_SOURCE_TRUNCATED:
            if not digest.startswith(PREFIX_DIGEST_MARKER) or not cls._FULL_DIGEST_RE.match(digest[len(PREFIX_DIGEST_MARKER):]):
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", "a SOURCE_TRUNCATED fact.content_digest must carry the prefix-sha256: marker")
        else:
            if not cls._FULL_DIGEST_RE.match(digest):
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", "fact.content_digest must be a plain 64-hex sha256 digest")

        reason = f["reason"]
        if status == STATUS_OK:
            if reason is not None:
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", "an OK fact.reason must be null")
        elif not isinstance(reason, str) or not reason.strip():
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "a non-OK fact.reason must be a non-empty string")

        conflict = f["conflict"]
        if conflict not in cls._CONFLICT_VALUES:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"fact.conflict {conflict!r} is not recognized")

        payload = f["payload"]
        if status == STATUS_OK:
            try:
                if record_schema == WORKSTREAM_SCHEMA:
                    _revalidate_payload_shape(payload, _WORKSTREAM_SHAPES, _WORKSTREAM_REQUIRED, _validate_workstream_payload)
                else:
                    _revalidate_payload_shape(payload, _HANDOFF_SHAPES, _HANDOFF_REQUIRED, _validate_handoff_payload)
            except _RecordParseError as exc:
                raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"OK fact.payload at {path} failed re-validation: {exc}") from exc
        elif payload is not None:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", "a non-OK fact.payload must be null")

        return SourceFact(
            source_owner=f["source_owner"],
            repo=repo,
            revision=revision,
            path=path,
            record_schema=record_schema,
            content_digest=digest,
            observed_at=observed_at,
            status=status,
            reason=reason,
            payload=payload,
            conflict=conflict,
        )

    @staticmethod
    def _check_coverage_consistency(coverage_list: list[FamilyCoverage], facts_list: list[SourceFact]) -> None:
        for cov in coverage_list:
            family_facts = [fact for fact in facts_list if fact.record_schema == cov.record_schema]
            ok_count = sum(1 for fact in family_facts if fact.status == STATUS_OK)
            if ok_count != cov.ok:
                raise SourceGatherError(
                    "INVALID_SOURCE_BUNDLE",
                    f"coverage.ok={cov.ok} for {cov.record_schema} does not match {ok_count} OK facts present",
                )
            attempted_facts = sum(1 for fact in family_facts if fact.status != STATUS_SOURCE_MISSING)
            if not (attempted_facts <= cov.attempted <= len(family_facts)):
                raise SourceGatherError(
                    "INVALID_SOURCE_BUNDLE",
                    f"coverage.attempted={cov.attempted} for {cov.record_schema} is inconsistent with the {len(family_facts)} facts present",
                )
            any_truncated = any(fact.status == STATUS_SOURCE_TRUNCATED for fact in family_facts)
            if cov.truncated != any_truncated:
                raise SourceGatherError(
                    "INVALID_SOURCE_BUNDLE",
                    f"coverage.truncated={cov.truncated} for {cov.record_schema} does not match the facts present",
                )


# ---------------------------------------------------------------------------
# Minimal strict frontmatter reader
#
# Supports exactly the value shapes the two agentos schemas use: plain/quoted
# scalars, ">"-folded block scalars, flow lists ("[a, b]") and block
# sequences of scalars, and block sequences of one-line flow mappings
# ("- {a: b, c: d}") whose own values may recursively be scalars, flow
# lists, or flow mappings (covers a hypothetical schema-valid "wait: {...}"
# value on a wave item; no live record uses one today). Anything outside
# this closed grammar is refused.
# ---------------------------------------------------------------------------


def _split_frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise _RecordParseError("INVALID_SOURCE_BUNDLE", "no opening frontmatter delimiter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[1:i])
    raise _RecordParseError("INVALID_SOURCE_BUNDLE", "no closing frontmatter delimiter")


def _unquote(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == '"' and token[-1] == '"':
        body = token[1:-1]
        out = []
        i = 0
        while i < len(body):
            ch = body[i]
            if ch == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                if nxt in ('"', "\\"):
                    out.append(nxt)
                    i += 2
                    continue
            out.append(ch)
            i += 1
        return "".join(out)
    return token


def _parse_flow_value(text: str, pos: int) -> tuple[Any, int]:
    """Parse one flow-YAML value (scalar | [..] | {..}) starting at pos."""
    n = len(text)
    while pos < n and text[pos] in " \t":
        pos += 1
    if pos >= n:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "unexpected end of flow value")
    ch = text[pos]
    if ch == "[":
        items: list[Any] = []
        pos += 1
        while pos < n and text[pos] in " \t":
            pos += 1
        if pos < n and text[pos] == "]":
            return items, pos + 1
        while True:
            value, pos = _parse_flow_value(text, pos)
            items.append(value)
            while pos < n and text[pos] in " \t":
                pos += 1
            if pos >= n:
                raise _RecordParseError("UNSUPPORTED_SEMANTICS", "unterminated flow list")
            if text[pos] == ",":
                pos += 1
                continue
            if text[pos] == "]":
                return items, pos + 1
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", "malformed flow list")
    if ch == "{":
        obj: dict[str, Any] = {}
        pos += 1
        while pos < n and text[pos] in " \t":
            pos += 1
        if pos < n and text[pos] == "}":
            return obj, pos + 1
        while True:
            while pos < n and text[pos] in " \t":
                pos += 1
            key, pos = _parse_flow_scalar_token(text, pos, stop_chars=":")
            while pos < n and text[pos] in " \t":
                pos += 1
            if pos >= n or text[pos] != ":":
                raise _RecordParseError("UNSUPPORTED_SEMANTICS", "malformed flow mapping key")
            pos += 1
            value, pos = _parse_flow_value(text, pos)
            key_s = _unquote(key)
            if key_s in obj:
                raise _RecordParseError("DUPLICATE_KEY", f"duplicate key {key_s!r} in flow mapping")
            obj[key_s] = value
            while pos < n and text[pos] in " \t":
                pos += 1
            if pos >= n:
                raise _RecordParseError("UNSUPPORTED_SEMANTICS", "unterminated flow mapping")
            if text[pos] == ",":
                pos += 1
                continue
            if text[pos] == "}":
                return obj, pos + 1
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", "malformed flow mapping")
    # scalar (quoted or plain), stops at , ] } or end of string
    token, pos = _parse_flow_scalar_token(text, pos, stop_chars=",]}")
    return _scalar_value(_unquote(token)), pos


def _parse_flow_scalar_token(text: str, pos: int, *, stop_chars: str) -> tuple[str, int]:
    n = len(text)
    if pos < n and text[pos] == '"':
        start = pos
        pos += 1
        while pos < n:
            if text[pos] == "\\" and pos + 1 < n:
                pos += 2
                continue
            if text[pos] == '"':
                pos += 1
                return text[start:pos], pos
            pos += 1
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "unterminated quoted scalar")
    start = pos
    while pos < n and text[pos] not in stop_chars:
        pos += 1
    return text[start:pos].strip(), pos


def _scalar_value(token: str) -> Any:
    if token == "null" or token == "~" or token == "":
        return None
    if token in ("true", "True"):
        return True
    if token in ("false", "False"):
        return False
    if re.fullmatch(r"-?\d+", token):
        try:
            return int(token)
        except ValueError:  # pragma: no cover - defense in depth
            return token
    return token


def _parse_plain_or_quoted_scalar(text: str) -> Any:
    text = text.strip()
    if not text:
        return None
    if text[0] == '"':
        value, pos = _parse_flow_scalar_token(text, 0, stop_chars="")
        if pos != len(text):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", "trailing content after quoted scalar")
        return _unquote(value)
    return _scalar_value(text)


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _next_line_indent(lines: list[str], start: int) -> int | None:
    for j in range(start, len(lines)):
        if lines[j].strip():
            return _indent_of(lines[j])
    return None


def _parse_block_sequence_of_flow_mappings(lines: list[str], start: int, indent: int) -> tuple[list[dict], int]:
    items: list[dict] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _indent_of(line) != indent or not line.strip().startswith("-"):
            break
        rest = line.strip()[1:].strip()
        if not rest.startswith("{"):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", "expected an inline flow mapping list item")
        value, pos = _parse_flow_value(rest, 0)
        if pos != len(rest):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", "trailing content after flow mapping item")
        if not isinstance(value, dict):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", "expected a flow mapping list item")
        items.append(value)
        i += 1
    return items, i


def _parse_block_sequence_of_scalars(lines: list[str], start: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _indent_of(line) != indent or not line.strip().startswith("-"):
            break
        rest = line.strip()[1:].strip()
        items.append(_parse_plain_or_quoted_scalar(rest))
        i += 1
    return items, i


def _parse_folded_scalar(lines: list[str], start: int, base_indent: int) -> tuple[str, int]:
    i = start
    parts: list[str] = []
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            parts.append("")
            i += 1
            continue
        if _indent_of(line) <= base_indent:
            break
        parts.append(line.strip())
        i += 1
    # YAML folding: a blank line becomes a newline; consecutive content lines join with a space.
    text_lines: list[str] = []
    buf: list[str] = []
    for part in parts:
        if part == "":
            if buf:
                text_lines.append(" ".join(buf))
                buf = []
            text_lines.append("")
        else:
            buf.append(part)
    if buf:
        text_lines.append(" ".join(buf))
    folded = "\n".join(t for t in text_lines if t != "") if any(t == "" for t in text_lines) else " ".join(
        t for t in text_lines
    )
    return folded.strip(), i


# closed shape table: field -> "scalar" | "folded" | "flat_list" | "flow_mappings"
_WORKSTREAM_SHAPES = {
    "schema": "scalar",
    "key": "scalar",
    "title": "scalar",
    "objective": "folded",
    "status": "scalar",
    "program": "scalar",
    "repos": "flat_list",
    "owner": "scalar",
    "class": "scalar",
    "blast_radius": "scalar",
    "ambiguity": "scalar",
    "waves": "flow_mappings",
    "next_action": "folded",
    "p0": "scalar",
    "owns_paths": "flat_list",
    "depends_on": "flat_list",
    "blocked_by": "flat_list",
    "decisions": "flat_list",
    "discoveries": "flat_list",
    "landmines": "flat_list",
    "do_not_redo": "flat_list",
    "artifacts": "flat_list",
}
_WORKSTREAM_REQUIRED = frozenset(
    {
        "schema",
        "key",
        "title",
        "objective",
        "status",
        "program",
        "repos",
        "owner",
        "class",
        "blast_radius",
        "ambiguity",
        "waves",
        "next_action",
    }
)

_HANDOFF_SHAPES = {
    "schema": "scalar",
    "workstream": "scalar",
    "session": "scalar",
    "model": "scalar",
    "ended_because": "scalar",
    "mission": "folded",
    "state_before": "folded",
    "changed": "flow_mappings",
    "verified": "flow_mappings",
    "unverified": "flow_mappings",
    "unresolved": "flat_list",
    "next_actions": "flat_list",
    "do_not_redo": "flat_list",
    "danger_areas": "flat_list",
    "prs": "flat_list",
    "decisions": "flat_list",
    "discoveries": "flat_list",
}
_HANDOFF_REQUIRED = frozenset(
    {
        "schema",
        "workstream",
        "session",
        "model",
        "ended_because",
        "mission",
        "state_before",
        "changed",
        "verified",
        "unverified",
        "unresolved",
        "next_actions",
        "do_not_redo",
        "danger_areas",
    }
)


def _parse_frontmatter_by_shape(block: str, shapes: dict[str, str], required: frozenset) -> dict:
    lines = block.splitlines()
    result: dict[str, Any] = {}
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if _indent_of(line) != 0:
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"unexpected indentation at line {i + 1}")
        stripped = line.strip()
        if ":" not in stripped:
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"expected 'key: value' at line {i + 1}")
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        if key in result:
            raise _RecordParseError("DUPLICATE_KEY", f"duplicate frontmatter key {key!r}")
        shape = shapes.get(key)
        if shape is None:
            raise _RecordParseError("UNKNOWN_FIELD", f"unknown frontmatter field {key!r}")
        if shape == "scalar":
            if rest.startswith("[") or rest.startswith("{"):
                raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"{key} must be a scalar")
            result[key] = _parse_plain_or_quoted_scalar(rest)
            i += 1
        elif shape == "folded":
            if rest == ">":
                value, i = _parse_folded_scalar(lines, i + 1, _indent_of(line))
                result[key] = value
            elif rest and not rest.startswith("["):
                result[key] = _parse_plain_or_quoted_scalar(rest)
                i += 1
            else:
                raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"{key} must be a scalar or '>' block")
        elif shape == "flat_list":
            if rest.startswith("["):
                value, pos = _parse_flow_value(rest, 0)
                if pos != len(rest):
                    raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"trailing content after {key} flow list")
                if not isinstance(value, list):
                    raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"{key} must be a list")
                result[key] = value
                i += 1
            elif rest == "":
                item_indent = _next_line_indent(lines, i + 1)
                if item_indent is None or item_indent <= _indent_of(line):
                    result[key] = []
                    i += 1
                else:
                    items, i = _parse_block_sequence_of_scalars(lines, i + 1, item_indent)
                    result[key] = items
            else:
                raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"{key} must be a flow or block list")
        elif shape == "flow_mappings":
            # an EMPTY list is a valid answer for these fields (e.g. the
            # real agentos.handoff.v1 schema's own "unverified" contract) —
            # both the inline `key: []` and the bare `key:` (with no deeper
            # block following) spellings mean zero items, matching every
            # other list shape in this reader rather than refusing a
            # perfectly schema-valid record.
            if rest == "[]":
                result[key] = []
                i += 1
            elif rest != "":
                raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"{key} must be a block sequence or '[]'")
            else:
                item_indent = _next_line_indent(lines, i + 1)
                if item_indent is None or item_indent <= _indent_of(line):
                    result[key] = []
                    i += 1
                else:
                    items, i = _parse_block_sequence_of_flow_mappings(lines, i + 1, item_indent)
                    result[key] = items
        else:  # pragma: no cover - defense in depth, shape table is closed
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"unsupported shape for {key}")
    missing = required - set(result.keys())
    if missing:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"missing required field(s) {sorted(missing)}")
    return result


def _validate_wave(wave: dict) -> None:
    if not isinstance(wave, dict):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave entry must be a mapping")
    allowed = {"id", "title", "status", "pr", "depends_on", "next_action", "wait"}
    unknown = set(wave.keys()) - allowed
    if unknown:
        raise _RecordParseError("UNKNOWN_FIELD", f"unknown wave field(s) {sorted(unknown)}")
    if "id" not in wave or not isinstance(wave["id"], str) or not _TOKEN_RE.match(wave["id"]):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.id must be a canonical token")
    if "title" not in wave or not isinstance(wave["title"], str) or not wave["title"].strip():
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.title must be a non-empty string")
    if wave.get("status") not in _WAVE_STATUS_VALUES:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"wave.status {wave.get('status')!r} is not recognized")
    if "depends_on" in wave:
        deps = wave["depends_on"]
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.depends_on must be a list of wave ids")
    if "next_action" in wave and not isinstance(wave["next_action"], str):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.next_action must be a string")
    if "pr" in wave and not isinstance(wave["pr"], (int, list)):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.pr must be an int or a list")
    if "wait" in wave:
        _validate_wait(wave["wait"])


def _validate_wait(wait: object) -> None:
    # REPAIR FIX 4 (coordinator REQUEST_REPAIR, adversarial review): the
    # wait mapping is not part of the live agentos.workstream.v1 schema
    # today (this compiler defines it, per the design's own "schema-valid
    # wait object" language); validate its OWN closed field set exactly the
    # same way every other shape in this module is validated — an unknown
    # key refuses the record rather than being silently accepted (probe
    # p12: an `evil_field` inside `wait: {...}` was previously accepted).
    if not isinstance(wait, dict):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.wait must be a schema-valid wait mapping")
    allowed = {"kind", "review_after", "condition"}
    unknown = set(wait.keys()) - allowed
    if unknown:
        raise _RecordParseError("UNKNOWN_FIELD", f"unknown wave.wait field(s) {sorted(unknown)}")
    if wait.get("kind") not in _WAIT_KIND_VALUES:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.wait.kind must be EXTERNAL_GATE or INTENTIONAL_WAIT")
    if "review_after" in wait and not isinstance(wait["review_after"], str):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.wait.review_after must be a string")
    if "condition" in wait and not isinstance(wait["condition"], str):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "wave.wait.condition must be a string")


def _validate_workstream_payload(payload: dict) -> None:
    if payload.get("schema") != WORKSTREAM_SCHEMA:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "schema must be agentos.workstream.v1")
    if not isinstance(payload.get("key"), str) or not payload["key"]:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "key must be a non-empty string")
    if payload.get("status") not in _WORKSTREAM_STATUS_VALUES:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"status {payload.get('status')!r} is not recognized")
    waves = payload.get("waves")
    if not isinstance(waves, list) or not waves:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "waves must be a non-empty list")
    wave_ids: set[str] = set()
    for wave in waves:
        _validate_wave(wave)
        if wave["id"] in wave_ids:
            raise _RecordParseError("DUPLICATE_KEY", f"duplicate wave id {wave['id']!r}")
        wave_ids.add(wave["id"])
    for wave in waves:
        for dep in wave.get("depends_on") or []:
            if dep not in wave_ids:
                raise _RecordParseError("UNRESOLVED_REFERENCE", f"wave {wave['id']!r} depends on unknown wave {dep!r}")
    if derive_seat_token(str(payload.get("owner", ""))) is None:
        # design Section 4: the adapter derives the Steward Seat enum value
        # from the closed token grammar; zero or multiple matches make the
        # whole record an explicit SOURCE_PARTIAL fact (the seat is never
        # guessed from free prose).
        raise _RecordParseError(
            "UNSUPPORTED_SEMANTICS",
            "owner field does not resolve to exactly one (CHAIRMAN|CEO|COO|WORKER seat) token",
        )


def _validate_handoff_payload(payload: dict) -> None:
    if payload.get("schema") != HANDOFF_SCHEMA:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "schema must be agentos.handoff.v1")
    workstream = payload.get("workstream")
    if not isinstance(workstream, str) or not workstream.startswith("WS:"):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "workstream must be an exact WS:<KEY> identity")
    if payload.get("model") not in _HANDOFF_MODEL_VALUES:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"model {payload.get('model')!r} is not recognized")
    if payload.get("ended_because") not in _HANDOFF_ENDED_BECAUSE_VALUES:
        raise _RecordParseError(
            "UNSUPPORTED_SEMANTICS", f"ended_because {payload.get('ended_because')!r} is not recognized"
        )
    if "prs" in payload:
        prs = payload["prs"]
        if not isinstance(prs, list) or not all(isinstance(p, int) for p in prs):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", "prs must be a list of ints")


def _revalidate_payload_shape(payload: object, shapes: dict[str, str], required: frozenset, validator) -> None:
    """REPAIR B1: re-validate an OK fact's already-PARSED payload dict
    ingested via ``--from-facts`` against the exact same closed field set
    and domain validator the adapter uses at original gather time — an
    ingested payload is never merely trusted because it arrived pre-parsed.
    """
    if not isinstance(payload, dict):
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", "payload must be an object")
    unknown = set(payload.keys()) - set(shapes.keys())
    if unknown:
        raise _RecordParseError("UNKNOWN_FIELD", f"unknown payload field(s) {sorted(unknown)}")
    missing = required - set(payload.keys())
    if missing:
        raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"missing required payload field(s) {sorted(missing)}")
    for key, shape in shapes.items():
        if key not in payload:
            continue
        value = payload[key]
        if shape in ("scalar", "folded") and value is not None and not isinstance(value, str):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"payload.{key} must be a string")
        if shape in ("flat_list", "flow_mappings") and not isinstance(value, list):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"payload.{key} must be a list")
        if shape == "flow_mappings" and not all(isinstance(item, dict) for item in value):
            raise _RecordParseError("UNSUPPORTED_SEMANTICS", f"payload.{key} items must be objects")
    validator(payload)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    seen: dict[str, Any] = {}
    for key, val in pairs:
        if key in seen:
            raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"duplicate JSON key {key!r}")
        seen[key] = val
    return seen


def _strict_json_loads(text: str) -> Any:
    """REPAIR B1: duplicate JSON keys are refused at EVERY nesting level
    (top-level wire document, each fact, each coverage entry, and inside
    every fact's own ``payload``) — ``object_pairs_hook`` applies
    recursively, so this single strict loader closes the whole wire in one
    pass, mirroring ``operation_assurance_model``'s own strict-JSON
    discipline."""
    try:
        return json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except SourceGatherError:
        raise
    except json.JSONDecodeError as exc:
        raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"malformed JSON: {exc}") from exc


def parse_workstream_frontmatter(text: str) -> dict:
    block = _split_frontmatter(text)
    payload = _parse_frontmatter_by_shape(block, _WORKSTREAM_SHAPES, _WORKSTREAM_REQUIRED)
    _validate_workstream_payload(payload)
    return payload


def parse_handoff_frontmatter(text: str) -> dict:
    block = _split_frontmatter(text)
    payload = _parse_frontmatter_by_shape(block, _HANDOFF_SHAPES, _HANDOFF_REQUIRED)
    _validate_handoff_payload(payload)
    return payload


# ---------------------------------------------------------------------------
# Gather
# ---------------------------------------------------------------------------


def derive_seat_token(owner_field: str) -> str | None:
    """Closed token grammar (design Section 4): exactly one match required.

    "Exactly one match" counts RAW occurrences, before any case-insensitive
    dedup: two tokens for the same seat (even byte-identical, even only
    differing by case) are "multiple matches" per the design's own words,
    not "the same seat asserted twice" — REPAIR FIX 2 (coordinator
    REQUEST_REPAIR, adversarial review). The token matching itself stays
    case-insensitive (that half is per-design); only the match-COUNT rule
    changed from a deduped count to the raw count.
    """
    matches = _SEAT_TOKEN_RE.findall(owner_field or "")
    if len(matches) != 1:
        return None
    return matches[0].upper()


def _read_bounded(path: Path) -> tuple[bytes, bool]:
    with path.open("rb") as fh:
        raw = fh.read(MAX_FILE_BYTES + 1)
    truncated = len(raw) > MAX_FILE_BYTES
    if truncated:
        raw = raw[:MAX_FILE_BYTES]
    return raw, truncated


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


EMPTY_CONTENT_DIGEST = _digest(b"")

# REPAIR FIX 3 (coordinator REQUEST_REPAIR, adversarial review): a truncated
# record's digest is computed over only the MAX_FILE_BYTES prefix that was
# actually read, never the full file. Presenting that as an ordinary
# content_digest lets a digest-keyed supersession contract mistake a prefix
# digest for the real whole-record hash. Every prefix digest carries this
# marker so it can never be silently compared as if it were a full digest.
PREFIX_DIGEST_MARKER = "prefix-sha256:"


def _prefix_digest(raw: bytes) -> str:
    return PREFIX_DIGEST_MARKER + _digest(raw)


def _gather_family(
    repo_root: Path,
    glob: str,
    record_schema: str,
    parse_fn,
    repo: str,
    revision: str,
    observed_at: str,
    total_bytes: list[int],
) -> tuple[list[SourceFact], FamilyCoverage]:
    matches = sorted(repo_root.glob(glob))
    if len(matches) > MAX_FILES_PER_FAMILY:
        raise SourceGatherError("INPUT_TOO_LARGE", f"{glob} exceeds the per-family file ceiling")
    facts: list[SourceFact] = []
    ok = 0
    truncated_any = False
    for file_path in matches:
        rel_path = file_path.relative_to(repo_root).as_posix()
        raw, truncated = _read_bounded(file_path)
        total_bytes[0] += len(raw)
        if total_bytes[0] > MAX_TOTAL_BYTES:
            raise SourceGatherError("INPUT_TOO_LARGE", "gather exceeds the total-bytes ceiling")
        if truncated:
            truncated_any = True
            facts.append(
                SourceFact(
                    source_owner=SOURCE_OWNER,
                    repo=repo,
                    revision=revision,
                    path=rel_path,
                    record_schema=record_schema,
                    content_digest=_prefix_digest(raw),
                    observed_at=observed_at,
                    status=STATUS_SOURCE_TRUNCATED,
                    reason=f"record exceeds MAX_FILE_BYTES={MAX_FILE_BYTES}",
                    payload=None,
                    conflict=CONFLICT_NONE,
                )
            )
            continue
        digest = _digest(raw)
        try:
            text = raw.decode("utf-8", errors="strict")
            payload = parse_fn(text)
        except UnicodeDecodeError as exc:
            facts.append(
                SourceFact(
                    source_owner=SOURCE_OWNER,
                    repo=repo,
                    revision=revision,
                    path=rel_path,
                    record_schema=record_schema,
                    content_digest=digest,
                    observed_at=observed_at,
                    status=STATUS_SOURCE_PARTIAL,
                    reason=f"INVALID_UTF8: {exc}",
                    payload=None,
                    conflict=CONFLICT_NONE,
                )
            )
            continue
        except _RecordParseError as exc:
            facts.append(
                SourceFact(
                    source_owner=SOURCE_OWNER,
                    repo=repo,
                    revision=revision,
                    path=rel_path,
                    record_schema=record_schema,
                    content_digest=digest,
                    observed_at=observed_at,
                    status=STATUS_SOURCE_PARTIAL,
                    reason=str(exc),
                    payload=None,
                    conflict=CONFLICT_NONE,
                )
            )
            continue
        ok += 1
        facts.append(
            SourceFact(
                source_owner=SOURCE_OWNER,
                repo=repo,
                revision=revision,
                path=rel_path,
                record_schema=record_schema,
                content_digest=digest,
                observed_at=observed_at,
                status=STATUS_OK,
                reason=None,
                payload=payload,
                conflict=CONFLICT_NONE,
            )
        )
    coverage = FamilyCoverage(
        record_schema=record_schema,
        glob=glob,
        attempted=len(matches),
        ok=ok,
        truncated=truncated_any,
    )
    return facts, coverage


def _read_ref_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8", errors="strict").strip()
    except OSError:
        return None


def _resolve_git_dir(repo_root: Path) -> Path | None:
    dotgit = repo_root / ".git"
    if dotgit.is_dir():
        return dotgit
    if dotgit.is_file():
        content = _read_ref_text(dotgit)
        if content is None or not content.startswith("gitdir:"):
            return None
        target = content[len("gitdir:") :].strip()
        target_path = Path(target)
        resolved = target_path if target_path.is_absolute() else (repo_root / target_path)
        return resolved if resolved.is_dir() else None
    return None


def _resolve_ref_from_packed(git_dir: Path, ref_name: str) -> str | None:
    packed_text = _read_ref_text(git_dir / "packed-refs")
    if packed_text is None:
        return None
    for line in packed_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        parts = line.split(" ", 1)
        if len(parts) == 2 and parts[1] == ref_name and _FULL_SHA_RE.match(parts[0]):
            return parts[0]
    return None


def _resolve_git_head(repo_root: Path) -> str | None:
    """REPAIR B2 (Sol pre-review): pure-file-read resolution of a checkout's
    current HEAD commit — no subprocess, no network, no clock. Returns None
    (never raises) when repo_root carries no readable git identity, which
    the caller treats as CALLER_ASSERTED_UNVERIFIED rather than a refusal.
    Handles a plain `.git` directory, a worktree `.git` FILE
    (`gitdir: <path>`), a detached HEAD, a loose branch ref, and a packed
    ref (`packed-refs`) — the shapes real git checkouts and worktrees
    actually produce.
    """
    git_dir = _resolve_git_dir(repo_root)
    if git_dir is None:
        return None
    head_text = _read_ref_text(git_dir / "HEAD")
    if head_text is None:
        return None
    if _FULL_SHA_RE.match(head_text):
        return head_text
    if not head_text.startswith("ref:"):
        return None
    ref_name = head_text[len("ref:") :].strip()
    loose = _read_ref_text(git_dir / ref_name)
    if loose is not None and _FULL_SHA_RE.match(loose):
        return loose
    return _resolve_ref_from_packed(git_dir, ref_name)


def _mark_workstream_conflicts(facts: list[SourceFact]) -> list[SourceFact]:
    groups: dict[str, list[int]] = {}
    for idx, fact in enumerate(facts):
        if fact.record_schema != WORKSTREAM_SCHEMA or fact.status != STATUS_OK:
            continue
        key = fact.payload.get("key") if fact.payload else None
        if key is None:
            continue
        groups.setdefault(key, []).append(idx)
    out = list(facts)
    for idxs in groups.values():
        if len(idxs) > 1:
            for idx in idxs:
                out[idx] = dataclasses.replace(out[idx], conflict=CONFLICT_CONFLICT)
    return out


def gather_agent_os_source_facts(
    repo_root: str | Path,
    *,
    repo: str,
    revision: str,
    observed_at: str,
    target_workstream_key: str = FIRST_TARGET_WORKSTREAM_KEY,
) -> SourceFacts:
    """The sole I/O entry point of the OLS-A2 AGENT_OS gather adapter.

    Reads ``agentos/workstreams/*.md`` and ``agentos/handoffs/*.md`` under
    ``repo_root`` (a caller-supplied checkout directory), at the caller's
    asserted ``repo``/``revision``/``observed_at`` — this module never runs
    git and never reads a clock; it records the caller's assertion. Returns
    the invocation-local ``mastermind.operation_assurance_source_facts.v1``
    structure. Never writes, caches, or persists anything.
    """
    root = Path(repo_root)
    if not isinstance(repo, str) or not repo.strip():
        raise SourceGatherError("INVALID_SOURCE_BUNDLE", "repo must be a non-empty string")
    if not isinstance(revision, str) or not _FULL_SHA_RE.match(revision):
        raise SourceGatherError("INVALID_SOURCE_BUNDLE", "revision must be a full 40-hex commit SHA")
    if not isinstance(observed_at, str) or not _OBSERVED_AT_RE.match(observed_at):
        raise SourceGatherError("INVALID_SOURCE_BUNDLE", "observed_at must be one UTC 'Z' cutoff timestamp")
    if not root.is_dir():
        raise SourceGatherError("INVALID_SOURCE_BUNDLE", f"repo_root is not a directory: {root}")

    # REPAIR B2 (Sol pre-review): bind the pinned revision to the checkout
    # actually read, without any subprocess. A resolvable git HEAD that
    # disagrees with the caller's assertion is a hard, typed refusal —
    # never a silently accepted mismatch. An unresolvable/absent git
    # identity is not an error; it is disclosed as
    # CALLER_ASSERTED_UNVERIFIED rather than promoted to verified.
    resolved_head = _resolve_git_head(root)
    if resolved_head is not None and resolved_head != revision:
        raise SourceGatherError(
            "REVISION_MISMATCH",
            f"repo_root HEAD resolves to {resolved_head}, not the asserted revision {revision}",
        )
    revision_binding = (
        REVISION_BINDING_GIT_HEAD_VERIFIED if resolved_head == revision else REVISION_BINDING_CALLER_ASSERTED_UNVERIFIED
    )

    total_bytes = [0]
    ws_facts, ws_coverage = _gather_family(
        root, _WORKSTREAM_GLOB, WORKSTREAM_SCHEMA, parse_workstream_frontmatter, repo, revision, observed_at, total_bytes
    )
    ho_facts, ho_coverage = _gather_family(
        root, _HANDOFF_GLOB, HANDOFF_SCHEMA, parse_handoff_frontmatter, repo, revision, observed_at, total_bytes
    )

    all_facts = _mark_workstream_conflicts(ws_facts) + ho_facts

    target_path = f"agentos/workstreams/WS-{target_workstream_key}.md"
    has_target = any(
        f.record_schema == WORKSTREAM_SCHEMA and f.status == STATUS_OK and f.payload and f.payload.get("key") == target_workstream_key
        for f in all_facts
    )
    if not has_target and not any(f.path == target_path for f in all_facts):
        all_facts.append(
            SourceFact(
                source_owner=SOURCE_OWNER,
                repo=repo,
                revision=revision,
                path=target_path,
                record_schema=WORKSTREAM_SCHEMA,
                content_digest=EMPTY_CONTENT_DIGEST,
                observed_at=observed_at,
                status=STATUS_SOURCE_MISSING,
                reason=f"expected target workstream record WS:{target_workstream_key} absent from gather",
                payload=None,
                conflict=CONFLICT_NONE,
            )
        )

    all_facts.sort(key=lambda f: f.path)

    return SourceFacts(
        schema=SOURCE_FACTS_SCHEMA,
        source_owner=SOURCE_OWNER,
        repo=repo,
        revision=revision,
        observed_at=observed_at,
        revision_binding=revision_binding,
        coverage=(ws_coverage, ho_coverage),
        facts=tuple(all_facts),
    )
