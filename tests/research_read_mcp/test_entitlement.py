"""Closed Research Read grant loader and total entitlement_for. No network."""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import inspect
import json
import os
import re
import sys
from pathlib import Path

import pytest

from control_plane.principal_projection import (
    NeutralPrincipalProjection,
    neutral_principal_projection,
)
from integrations.business_mcp_auth.contracts import load_resource_policy
from integrations.research_read_mcp import entitlement as entitlement_module
from integrations.research_read_mcp.entitlement import (
    CONTENT_CLASSES,
    GRANT_SCHEMA,
    MAX_GRANT_BYTES,
    MAX_GRANT_ENTRIES,
    MAX_QUOTE_LIMIT_CHARS,
    MIN_QUOTE_LIMIT_CHARS,
    REQUIRED_CONTENT_CLASS,
    GrantRefused,
    ResearchEntitlement,
    ResearchGrant,
    ResearchGrantEntry,
    entitlement_for,
    load_research_grant,
    parse_research_grant,
)

ROOT = Path(__file__).resolve().parents[2]
GRANT_PATH = ROOT / "config" / "research_read_mcp" / "grant.example.json"
POLICY_PATH = ROOT / "config" / "business_mcp" / "research_policy.example.json"
POLICY = "mastermind-research-read-v1"
OTHER_POLICY = "other-research-policy"
GRANT_ID = "research-read-example-v1"
ZERO = "0" * 64
ONES = "1" * 64
TWOS = "2" * 64
THREES = "3" * 64
FIXED = "research grant refused"
NOW = 1_800_000_000
ENTRY_EXP = 1_900_000_000
TOKEN_EXP = 2_000_000_000
EXPIRED_ENTRY = 1_700_000_000
EXPIRED_TOKEN = 1_500_000_000
FUTURE = 4_102_444_800
ISSUER = "https://identity.example.invalid/"
RESOURCE = "https://research-mcp.example.invalid/mcp/research/v1"
FULL_CLASSES = ["catalog_metadata", "report_text", "evidence_passage"]
CATALOG_ONLY = ["catalog_metadata"]
NOWS = (
    NOW,
    ENTRY_EXP,
    TOKEN_EXP,
    2_100_000_000,
    None,
    True,
    1.5,
)


class _Refusal:
    def __init__(
        self,
        name: str,
        raw: bytes,
        distinctive: str,
        *,
        now: object = NOW,
        expected_policy_id: str = POLICY,
    ) -> None:
        self.name = name
        self.raw = raw
        self.distinctive = distinctive
        self.now = now
        self.expected_policy_id = expected_policy_id


def _entry(
    digest: str = ZERO,
    classes: object = None,
    quote: object = 1200,
    expires_at: object = FUTURE,
) -> dict[str, object]:
    selected: object = list(CATALOG_ONLY) if classes is None else classes
    return {
        "subject_digest": digest,
        "content_classes": selected,
        "quote_limit_chars": quote,
        "expires_at": expires_at,
    }


def _document(
    *,
    schema: object = GRANT_SCHEMA,
    grant_id: object = GRANT_ID,
    policy_id: object = POLICY,
    entries: object | None = None,
) -> dict[str, object]:
    if entries is None:
        entries = [_entry()]
    return {
        "schema": schema,
        "grant_id": grant_id,
        "policy_id": policy_id,
        "entries": entries,
    }


def _raw(document: dict[str, object]) -> bytes:
    return json.dumps(document, separators=(",", ":")).encode("ascii")


def _valid_raw() -> bytes:
    return _raw(_document(entries=[_entry(ZERO, FULL_CLASSES, 1200, FUTURE), _entry(ONES, CATALOG_ONLY, 1, FUTURE)]))


def _duplicate_top() -> bytes:
    payload = _raw(_document())
    return b'{"schema":"' + GRANT_SCHEMA.encode("ascii") + b'",' + payload[1:]


def _duplicate_entry_key() -> bytes:
    entry = json.dumps(_entry(), separators=(",", ":")).encode("ascii")
    duplicated = b'{"subject_digest":"' + ZERO.encode("ascii") + b'",' + entry[1:]
    return (
        b'{"schema":"' + GRANT_SCHEMA.encode("ascii") + b'",'
        b'"grant_id":"' + GRANT_ID.encode("ascii") + b'",'
        b'"policy_id":"' + POLICY.encode("ascii") + b'",'
        b'"entries":[' + duplicated + b"]}"
    )


def _refusal_cases() -> list[_Refusal]:
    too_many = [_entry(f"{index:064x}") for index in range(MAX_GRANT_ENTRIES + 1)]
    return [
        _Refusal("non-ascii", b"\xff\xfe", "\xff"),
        _Refusal("invalid-json", b'{"broken"', "broken"),
        _Refusal("duplicate-top-key", _duplicate_top(), GRANT_SCHEMA),
        _Refusal("duplicate-entry-key", _duplicate_entry_key(), ZERO),
        _Refusal("nan", _raw(_document()).replace(b"1200", b"NaN", 1), "NaN"),
        _Refusal("infinity", _raw(_document()).replace(b"1200", b"Infinity", 1), "Infinity"),
        _Refusal("not-object", b"[]", "[]"),
        _Refusal("unknown-top-key", _raw({**_document(), "extra_top": "DISTINCT_TOP"}), "DISTINCT_TOP"),
        _Refusal("missing-top-key", _raw({key: value for key, value in _document().items() if key != "grant_id"}), "entries"),
        _Refusal("wrong-schema", _raw(_document(schema="not-the-grant-schema")), "not-the-grant-schema"),
        _Refusal("bad-grant-id", _raw(_document(grant_id="NO")), "NO"),
        _Refusal("bad-policy-id", _raw(_document(policy_id="NO")), "NO", expected_policy_id="NO"),
        _Refusal("policy-mismatch", _raw(_document(policy_id=OTHER_POLICY)), OTHER_POLICY),
        _Refusal("entries-not-list", _raw(_document(entries={"not": "a-list"})), "a-list"),
        _Refusal("entries-empty", _raw(_document(entries=[])), "entries"),
        _Refusal("too-many-entries", _raw(_document(entries=too_many)), f"{MAX_GRANT_ENTRIES + 1:064x}"),
        _Refusal(
            "unknown-entry-key",
            _raw(_document(entries=[{**_entry(), "extra_entry": "DISTINCT_ENTRY"}])),
            "DISTINCT_ENTRY",
        ),
        _Refusal(
            "missing-entry-key",
            _raw(_document(entries=[{key: value for key, value in _entry().items() if key != "expires_at"}])),
            "quote_limit_chars",
        ),
        _Refusal("bad-digest", _raw(_document(entries=[_entry("G" * 64)])), "G" * 64),
        _Refusal("digest-not-str", _raw(_document(entries=[_entry(digest=123)])), "123"),
        _Refusal("duplicate-subject", _raw(_document(entries=[_entry(ZERO), _entry(ZERO)])), ZERO),
        _Refusal("classes-not-list", _raw(_document(entries=[_entry(classes="catalog_metadata")])), "catalog_metadata"),
        _Refusal(
            "class-not-str",
            _raw(_document(entries=[_entry(classes=["catalog_metadata", 7])])),
            "7",
        ),
        _Refusal("classes-empty", _raw(_document(entries=[_entry(classes=[])])), "content_classes"),
        _Refusal(
            "duplicate-class",
            _raw(_document(entries=[_entry(classes=["catalog_metadata", "catalog_metadata"])])),
            "catalog_metadata",
        ),
        _Refusal(
            "unknown-class",
            _raw(_document(entries=[_entry(classes=["catalog_metadata", "not_a_real_class"])])),
            "not_a_real_class",
        ),
        _Refusal(
            "missing-catalog",
            _raw(_document(entries=[_entry(classes=["report_text"])])),
            "report_text",
        ),
        _Refusal("quote-bool", _raw(_document(entries=[_entry(quote=True)])), "true"),
        _Refusal("quote-not-int", _raw(_document(entries=[_entry(quote="1200")])), "1200"),
        _Refusal("quote-zero", _raw(_document(entries=[_entry(quote=0)])), "0"),
        _Refusal("quote-above-max", _raw(_document(entries=[_entry(quote=12001)])), "12001"),
        _Refusal("expires-bool", _raw(_document(entries=[_entry(expires_at=True)])), "true", now=0),
        _Refusal("expires-not-int", _raw(_document(entries=[_entry(expires_at="4102444800")])), "4102444800"),
        _Refusal("expires-eq-now", _raw(_document(entries=[_entry(expires_at=NOW)])), str(NOW), now=NOW),
        _Refusal("expires-before-now", _raw(_document(entries=[_entry(expires_at=NOW - 1)])), str(NOW - 1)),
        _Refusal("now-true", _valid_raw(), "True", now=True),
        _Refusal("now-float", _valid_raw(), "1.5", now=1.5),
    ]


def _projection(
    *,
    digest: str = ZERO,
    policy: str = POLICY,
    expires_at: int = TOKEN_EXP,
) -> NeutralPrincipalProjection:
    return neutral_principal_projection(
        policy_id=policy,
        issuer=ISSUER,
        issuer_digest=hashlib.sha256(ISSUER.encode("utf-8")).hexdigest(),
        resource=RESOURCE,
        subject_digest=digest,
        client_ref="example-client",
        scopes=("mastermind.research.read",),
        issued_at=1_400_000_000,
        expires_at=expires_at,
        jti_digest=None,
    )


@dataclasses.dataclass(frozen=True, slots=True)
class _SubProjection(NeutralPrincipalProjection):
    pass


class _Duck:
    def __init__(self, source: NeutralPrincipalProjection) -> None:
        for field in dataclasses.fields(source):
            setattr(self, field.name, getattr(source, field.name))


def _manual_grant(policy: str, expires_at: int) -> ResearchGrant:
    return ResearchGrant(
        schema=GRANT_SCHEMA,
        grant_id=GRANT_ID,
        policy_id=policy,
        entries=(
            ResearchGrantEntry(
                subject_digest=ZERO,
                content_classes=frozenset(FULL_CLASSES),
                quote_limit_chars=1200,
                expires_at=expires_at,
            ),
            ResearchGrantEntry(
                subject_digest=ONES,
                content_classes=frozenset(CATALOG_ONLY),
                quote_limit_chars=1,
                expires_at=expires_at,
            ),
        ),
        sha256="ab" * 32,
    )


def _live_document(expires_at: int, policy: str = POLICY) -> bytes:
    return _raw(
        _document(
            policy_id=policy,
            entries=[
                _entry(ZERO, FULL_CLASSES, 1200, expires_at),
                _entry(ONES, CATALOG_ONLY, 1, expires_at),
            ],
        )
    )


def _c4_holds(projection: object, grants: object, now: object) -> bool:
    """Independent seam §C.4 predicate. True only when an entitlement is due."""

    if type(projection) is not NeutralPrincipalProjection:
        return False
    if type(grants) is not ResearchGrant:
        return False
    if type(now) is not int:
        return False
    if projection.policy_id != grants.policy_id:
        return False
    token_expires_at = projection.expires_at
    if type(token_expires_at) is not int or not token_expires_at > now:
        return False
    digest = projection.subject_digest
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        return False
    matches = [entry for entry in grants.entries if entry.subject_digest == digest]
    if len(matches) != 1:
        return False
    try:
        live = matches[0].expires_at > now
    except TypeError:
        return False
    return bool(live)


def _assert_refused(path: str, **kwargs: object) -> None:
    with pytest.raises(GrantRefused) as caught:
        load_research_grant(
            path,
            expected_policy_id=POLICY,
            now=NOW,
            expected_owner_uid=kwargs.get("expected_owner_uid", os.geteuid()),
            expected_sha256=kwargs.get("expected_sha256"),
        )
    message = str(caught.value)
    assert message == FIXED
    assert path not in message


def test_e1_examples_load() -> None:
    raw = GRANT_PATH.read_bytes()
    grant = parse_research_grant(raw, expected_policy_id=POLICY, now=NOW)
    assert isinstance(grant, ResearchGrant)
    assert len(grant.entries) == 2
    assert grant.sha256 == hashlib.sha256(raw).hexdigest()
    assert grant.schema == GRANT_SCHEMA
    assert grant.grant_id == GRANT_ID
    assert grant.policy_id == POLICY
    by_digest = {entry.subject_digest: entry for entry in grant.entries}
    assert set(by_digest) == {ZERO, ONES}
    full = by_digest[ZERO]
    assert full.content_classes == frozenset(FULL_CLASSES)
    assert full.quote_limit_chars == 1200
    assert full.expires_at == FUTURE
    canary = by_digest[ONES]
    assert canary.content_classes == frozenset(CATALOG_ONLY)
    assert canary.quote_limit_chars == 1
    assert canary.expires_at == FUTURE
    with POLICY_PATH.open(encoding="utf-8") as handle:
        policy = load_resource_policy(json.load(handle))
    assert policy.required_scopes == ("mastermind.research.read",)
    assert policy.policy_id == grant.policy_id
    assert policy.resource == RESOURCE
    assert policy.resource_metadata_url == (
        "https://research-mcp.example.invalid/.well-known/oauth-protected-resource/mcp/research/v1"
    )
    assert policy.issuer == ISSUER
    assert policy.allowed_subject_digests == (ZERO,)


@pytest.mark.parametrize("case", _refusal_cases(), ids=lambda case: case.name)
def test_e2_refusal_table(case: _Refusal) -> None:
    assert case.distinctive not in FIXED
    with pytest.raises(GrantRefused) as caught:
        parse_research_grant(
            case.raw,
            expected_policy_id=case.expected_policy_id,
            now=case.now,
        )
    message = str(caught.value)
    assert message == FIXED
    assert case.distinctive not in message


def test_e3_secure_load(tmp_path: Path) -> None:
    raw = _valid_raw()
    digest = hashlib.sha256(raw).hexdigest()
    assert digest != "0" * 64
    target = tmp_path / "grant.json"
    target.write_bytes(raw)
    os.chmod(target, 0o644)
    loaded = load_research_grant(
        str(target),
        expected_policy_id=POLICY,
        now=NOW,
        expected_owner_uid=os.geteuid(),
    )
    assert loaded == parse_research_grant(raw, expected_policy_id=POLICY, now=NOW)
    assert loaded.sha256 == digest
    checked = load_research_grant(
        str(target),
        expected_policy_id=POLICY,
        now=NOW,
        expected_owner_uid=os.geteuid(),
        expected_sha256=digest,
    )
    assert checked == loaded
    _assert_refused(str(target), expected_sha256="0" * 64)
    _assert_refused("grant.json")
    link = tmp_path / "grant-link.json"
    link.symlink_to(target)
    _assert_refused(str(link))
    for mode in (0o664, 0o666):
        os.chmod(target, mode)
        _assert_refused(str(target))
    os.chmod(target, 0o644)
    _assert_refused(str(target), expected_owner_uid=os.geteuid() + 1)
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (MAX_GRANT_BYTES + 1))
    os.chmod(oversized, 0o644)
    _assert_refused(str(oversized))
    _assert_refused(str(tmp_path))
    _assert_refused(str(tmp_path / "missing.json"))
    if os.geteuid() != 0:
        with pytest.raises(GrantRefused) as caught:
            load_research_grant(str(target), expected_policy_id=POLICY, now=NOW)
        assert str(caught.value) == FIXED
        assert str(target) not in str(caught.value)


def test_e4_entitlement_for_is_total() -> None:
    matching = _projection()
    projections = [
        matching,
        _projection(digest=TWOS),
        _projection(policy=OTHER_POLICY),
        _projection(expires_at=EXPIRED_TOKEN),
        dataclasses.asdict(matching),
        None,
        _SubProjection(**{field.name: getattr(matching, field.name) for field in dataclasses.fields(matching)}),
        _Duck(matching),
        _projection(digest=ONES),
    ]
    grants = [
        parse_research_grant(_live_document(ENTRY_EXP), expected_policy_id=POLICY, now=NOW),
        None,
        {"schema": GRANT_SCHEMA, "policy_id": POLICY},
        _manual_grant(POLICY, EXPIRED_ENTRY),
        parse_research_grant(
            _live_document(ENTRY_EXP, OTHER_POLICY),
            expected_policy_id=OTHER_POLICY,
            now=NOW,
        ),
        [ZERO, ONES],
    ]
    assert len(projections) >= 8
    assert len(grants) >= 6
    assert len(NOWS) >= 7
    cells = 0
    entitled = 0
    for projection in projections:
        for grant in grants:
            for moment in NOWS:
                cells += 1
                result = entitlement_for(projection, grant, now=moment)
                assert result is None or type(result) is ResearchEntitlement
                due = _c4_holds(projection, grant, moment)
                if due:
                    entitled += 1
                    assert type(result) is ResearchEntitlement
                    assert type(projection) is NeutralPrincipalProjection
                    assert type(grant) is ResearchGrant
                    matches = [entry for entry in grant.entries if entry.subject_digest == projection.subject_digest]
                    entry = matches[0]
                    assert result.subject_digest == projection.subject_digest
                    assert result.grant_id == grant.grant_id
                    assert result.policy_id == grant.policy_id
                    assert result.content_classes == entry.content_classes
                    assert result.quote_limit_chars == entry.quote_limit_chars
                    assert result.expires_at == min(entry.expires_at, projection.expires_at)
                else:
                    assert result is None
    assert cells == len(projections) * len(grants) * len(NOWS) == 378
    assert entitled == 3


def test_e5_no_tool_argument_and_ungranted_subject() -> None:
    signature = inspect.signature(entitlement_for)
    parameters = list(signature.parameters.values())
    assert [parameter.name for parameter in parameters] == ["projection", "grants", "now"]
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[1].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert parameters[2].kind is inspect.Parameter.KEYWORD_ONLY
    assert parameters[2].default is inspect.Parameter.empty
    grant = parse_research_grant(_live_document(ENTRY_EXP), expected_policy_id=POLICY, now=NOW)
    stranger = _projection(digest=THREES)
    for moment in NOWS:
        assert entitlement_for(stranger, grant, now=moment) is None


def test_e6_closed_record_and_content_classes() -> None:
    assert [field.name for field in dataclasses.fields(ResearchEntitlement)] == [
        "subject_digest",
        "grant_id",
        "policy_id",
        "content_classes",
        "quote_limit_chars",
        "expires_at",
    ]
    assert [field.name for field in dataclasses.fields(ResearchGrantEntry)] == [
        "subject_digest",
        "content_classes",
        "quote_limit_chars",
        "expires_at",
    ]
    assert [field.name for field in dataclasses.fields(ResearchGrant)] == [
        "schema",
        "grant_id",
        "policy_id",
        "entries",
        "sha256",
    ]
    for record in (ResearchGrantEntry, ResearchGrant, ResearchEntitlement):
        assert dataclasses.is_dataclass(record)
        assert record.__dataclass_params__.frozen is True
    assert CONTENT_CLASSES == (
        "catalog_metadata",
        "report_text",
        "evidence_passage",
        "rio_derived",
    )
    assert REQUIRED_CONTENT_CLASS == "catalog_metadata"
    assert (MIN_QUOTE_LIMIT_CHARS, MAX_QUOTE_LIMIT_CHARS) == (1, 12000)
    plain = parse_research_grant(
        _raw(_document(entries=[_entry(ZERO, ["catalog_metadata"], 1200, FUTURE)])),
        expected_policy_id=POLICY,
        now=NOW,
    )
    carried = parse_research_grant(
        _raw(_document(entries=[_entry(ZERO, ["catalog_metadata", "rio_derived"], 1200, FUTURE)])),
        expected_policy_id=POLICY,
        now=NOW,
    )
    projection = _projection(expires_at=FUTURE)
    plain_ent = entitlement_for(projection, plain, now=NOW)
    carried_ent = entitlement_for(projection, carried, now=NOW)
    assert plain_ent is not None and carried_ent is not None
    assert carried.entries[0].content_classes == frozenset({"catalog_metadata", "rio_derived"})
    assert carried_ent.content_classes == plain_ent.content_classes | frozenset({"rio_derived"})
    assert carried_ent.quote_limit_chars == plain_ent.quote_limit_chars == 1200
    assert carried_ent.expires_at == plain_ent.expires_at == FUTURE
    assert carried_ent.subject_digest == plain_ent.subject_digest == ZERO
    assert carried_ent.grant_id == plain_ent.grant_id
    assert carried_ent.policy_id == plain_ent.policy_id
    bounded = parse_research_grant(
        _raw(_document(entries=[_entry(ZERO, CATALOG_ONLY, MAX_QUOTE_LIMIT_CHARS, FUTURE)])),
        expected_policy_id=POLICY,
        now=NOW,
    )
    assert bounded.entries[0].quote_limit_chars == MAX_QUOTE_LIMIT_CHARS
    full_cap = [
        _entry(f"{index:064x}", CATALOG_ONLY, MIN_QUOTE_LIMIT_CHARS, FUTURE)
        for index in range(MAX_GRANT_ENTRIES)
    ]
    capped = parse_research_grant(
        _raw(_document(entries=full_cap)),
        expected_policy_id=POLICY,
        now=NOW,
    )
    assert len(capped.entries) == MAX_GRANT_ENTRIES
    with pytest.raises(GrantRefused) as caught:
        parse_research_grant(
            _raw(_document(entries=[_entry(classes=["report_text", "evidence_passage"])])),
            expected_policy_id=POLICY,
            now=NOW,
        )
    assert str(caught.value) == FIXED
    sample = capped.entries[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        sample.quote_limit_chars = 2
    with pytest.raises(dataclasses.FrozenInstanceError):
        capped.grant_id = "other-grant-id"
    with pytest.raises(dataclasses.FrozenInstanceError):
        carried_ent.policy_id = OTHER_POLICY


def test_e7_example_hygiene() -> None:
    forbidden = (
        "auth0.com",
        "eo0jf8us5mup7wd5",
        "secret",
        "client_id",
        "password",
        "@",
        "localhost",
    )
    digests = re.compile(r"[0-9a-f]{64}")
    for path in (GRANT_PATH, POLICY_PATH):
        text = path.read_text(encoding="utf-8")
        lowered = text.lower()
        for needle in forbidden:
            assert needle not in lowered
        found = digests.findall(lowered)
        assert found
        assert all(len(set(digest)) == 1 for digest in found)


def test_e8_import_inertness() -> None:
    tree = ast.parse(Path(entitlement_module.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            assert node.module is not None
            imported.append(node.module)
    assert imported

    def allowed(module: str) -> bool:
        if module in {
            "__future__",
            "control_plane.principal_projection",
            "integrations.research_read_mcp.contracts",
        }:
            return True
        root = module.split(".", 1)[0]
        if root in {"mcp", "starlette", "engine", "app", "jwt", "httpx"}:
            return False
        if module.startswith("integrations.business_mcp_auth"):
            return False
        if root in {"integrations", "control_plane"}:
            return False
        return root in sys.stdlib_module_names

    assert all(allowed(module) for module in imported)
    forbidden = ("mcp", "starlette", "integrations.business_mcp_auth", "engine", "app", "jwt", "httpx")
    for module in imported:
        for needle in forbidden:
            assert module != needle and not module.startswith(needle + ".")
