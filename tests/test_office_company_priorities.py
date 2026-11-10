"""Actual strategy loader -> boot -> executive_state -> signed fixed READ. No writers."""

import asyncio, json, os, subprocess, dataclasses
from pathlib import Path
import httpx, pytest
from control_plane import ceo_boot_packet, strategic_state
from integrations.business_mcp_auth.jwt_verifier import JwtAuthenticator
from integrations.business_mcp_auth.mcp_adapter import MastermindTokenVerifier
from integrations.mastermind_executive_app.company_priorities_transport import (
    CompanyPrioritiesTransport,
    PATH,
)
from integrations.mastermind_executive_app.gateway import CeoIngressReadGateway
from tests.test_mastermind_executive_app_asgi import (
    _client,
    _git_repo,
    _read_policy,
    _submit_policy,
    _FakeJwksCache,
    _read_token,
    _submit_token,
    _token,
    rsa_key,
    NOW,
)


class Sink:
    def emit(self, event):
        pass


@pytest.fixture
def owned(tmp_path, monkeypatch, rsa_key):
    root = tmp_path / "source"
    (root / "config").mkdir(parents=True)
    original = (
        Path(strategic_state.__file__).resolve().parents[1]
        / "config/strategic_state.yml"
    )
    (root / "config/strategic_state.yml").write_bytes(original.read_bytes())
    sha = _git_repo(root)
    monkeypatch.setattr(
        ceo_boot_packet,
        "load_strategic_state",
        lambda: strategic_state.load_strategic_state(
            root / "config/strategic_state.yml"
        ),
    )
    inner, settings = _client(rsa_key, mastermind_root=root)
    from integrations.mastermind_executive_app.app import create_app

    # Actual existing combined-read setting, as in installed OS composition.
    inner_app = create_app(
        dataclasses.replace(settings, allow_submit_authorized_reads=True)
    )
    clock = [NOW]

    def pair(policy):
        auth = JwtAuthenticator(policy=policy, jwks_cache=_FakeJwksCache(rsa_key))
        return (
            MastermindTokenVerifier(
                authenticator=auth,
                policy=policy,
                now=lambda: clock[0],
                audit_sink=Sink(),
            ),
            auth,
        )

    owner = CompanyPrioritiesTransport(
        inner_app,
        read_pair=pair(_read_policy()),
        submit_pair=pair(_submit_policy()),
        clock=lambda: clock[0],
    )
    return owner, sha, clock


async def request(owner, token, body=None, path=PATH, **kw):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=owner),
        base_url="https://mcp.mastermind-x.com",
        headers={"Authorization": "Bearer " + token},
    ) as c:
        return await c.post(path, json={} if body is None else body, **kw)


def test_actual_owner_signed_read_and_source_export(owned, rsa_key):
    owner, sha, clock = owned

    async def run():
        response = await request(owner, _read_token(rsa_key))
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["source"]["revision"] == sha
        assert value["authority"] == "advisory_and_orientation_only"
        assert {x["id"] for x in value["priorities"] if x["status"] == "active"} == {
            "CORE_INTELLIGENCE_PRODUCTIZATION",
            "PREMIUM_PRODUCT_EXPERIENCE",
            "DISTRIBUTION_AND_REVENUE",
            "AUTONOMY_FORCE_MULTIPLIER",
        }
        assert set(value["phase_review_criteria"]) == {
            "SELL_READY",
            "AUTONOMY_BASELINE",
        }
        assert not any(
            k in value
            for k in [
                "permission",
                "critical_path",
                "adopted_direction",
                "ready",
                "runtime_db",
            ]
        )
        combined = await request(owner, _submit_token(rsa_key))
        assert combined.status_code == 200
        # Independent authenticated reads retain the same immutable source; each
        # carries its own observation time and may cross a wall-clock second.
        from datetime import datetime
        combined_source = combined.json()["source"]
        assert set(combined_source) == set(value["source"])
        assert {k: v for k, v in combined_source.items() if k != "observed_at"} == {
            k: v for k, v in value["source"].items() if k != "observed_at"
        }
        for source in (value["source"], combined_source):
            assert source["observed_at"].endswith("Z")
            assert datetime.fromisoformat(source["observed_at"]).utcoffset().total_seconds() == 0
        if os.environ.get("MMOS_COMPANY_FIXTURE"):
            Path(os.environ["MMOS_COMPANY_FIXTURE"]).write_text(
                json.dumps(
                    {
                        "schema": "mastermind.office_company_source_fixture.v1",
                        "clock": {"verified_at": clock[0]},
                        "response": value,
                        "combined_response": combined.json(),
                        "premises": [
                            "actual canonical loader and strategy bytes in disposable committed Git source",
                            "actual boot/executive_state and signed RS256 READ/combined verifiers",
                            "inprocess ASGI; no installed source seal/native auth/host service/Runtime effect; no evaluated gate/critical-path projection",
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

    asyncio.run(run())


@pytest.mark.parametrize(
    "kind",
    [
        "foreign_subject",
        "expired",
        "workspace_scope",
        "foreign_audience",
        "extra_body",
        "query",
    ],
)
def test_wrong_owner_scope_expiry_and_selector_are_refused(owned, rsa_key, kind):
    owner, _, clock = owned
    token = (
        _token(rsa_key, scope="mastermind.workspace.read")
        if kind == "workspace_scope"
        else _read_token(
            rsa_key,
            **(
                {"sub": "foreign"}
                if kind == "foreign_subject"
                else (
                    {"exp": NOW - 60, "iat": NOW - 120, "nbf": NOW - 120}
                    if kind == "expired"
                    else (
                        {"scope": "mastermind.workspace.read"}
                        if kind == "workspace_scope"
                        else (
                            {"aud": "https://wrong.invalid"}
                            if kind == "foreign_audience"
                            else {}
                        )
                    )
                )
            ),
        )
    )
    response = asyncio.run(
        request(
            owner,
            token,
            body={"work_ref": "WS:FOREIGN"} if kind == "extra_body" else {},
            path=PATH + "?work_ref=WS:FOREIGN" if kind == "query" else PATH,
        )
    )
    assert response.status_code in (400, 401, 403), response.text
    assert "north_star" not in response.text


def test_expiry_during_source_read_withholds_all_company_text(owned, rsa_key):
    owner, _, clock = owned
    inner = owner._inner

    async def late(scope, receive, send):
        await inner(scope, receive, send)
        clock[0] += 2000

    owner._inner = late
    r = asyncio.run(request(owner, _read_token(rsa_key)))
    assert r.status_code == 401 and "north_star" not in r.text


def test_legacy_summary_still_valid_and_new_authority_is_closed():
    summary, error = ceo_boot_packet.load_strategic_summary()
    assert error is None
    assert CeoIngressReadGateway._valid_strategic_summary(summary)
    legacy = {
        k: summary[k]
        for k in ("schema", "company_phase", "north_star", "p0", "constraints")
    }
    assert CeoIngressReadGateway._valid_strategic_summary(legacy)
    summary["authored_orientation"]["authority"] = "may_execute"
    assert not CeoIngressReadGateway._valid_strategic_summary(summary)


def test_actual_os_constructor_registers_the_same_fixed_read_owner(owned, rsa_key):
    from integrations.mastermind_executive_app.os_transport import (
        OsExecutiveTransportApp,
    )

    leaf, sha, clock = owned
    read, submit = leaf._pairs
    outer = OsExecutiveTransportApp(
        leaf._inner,
        submit_verifier=submit[0],
        submit_authenticator=submit[1],
        clock=lambda: clock[0],
        company_read_pair=read,
    )
    r = asyncio.run(request(outer, _read_token(rsa_key)))
    assert r.status_code == 200, r.text
    assert r.json()["source"]["revision"] == sha
    assert outer._company_read._pairs == (read, submit)


def test_policy_withdrawal_during_source_read_withholds_all_text(owned, rsa_key):
    owner, _, _ = owned
    inner = owner._inner

    async def late(scope, receive, send):
        await inner(scope, receive, send)
        auth = owner._pairs[0][1]
        auth._policy = dataclasses.replace(
            auth.policy, allowed_subject_digests=frozenset({"a" * 64})
        )

    owner._inner = late
    r = asyncio.run(request(owner, _read_token(rsa_key)))
    assert r.status_code == 401 and "north_star" not in r.text


def test_company_route_is_one_forward_addition_and_caddy_has_exact_fixed_profile(
    tmp_path,
):
    from ops.executive_os import (
        os_public_edge as edge,
        os_public_edge_transition as transition,
    )
    from tests.test_source_operation_public_edge import CURRENT_MANIFEST

    assert edge.POST_ROUTES == edge.PRE_COMPANY_PRIORITIES_POST_ROUTES + (PATH,)
    assert (
        edge.PRE_AUTHORIZATION_IDENTITY_GET_ROUTES,
        edge.PRE_COMPANY_PRIORITIES_POST_ROUTES,
    ) in edge.TRANSITION_ROUTE_PROFILES
    text = edge.render(CURRENT_MANIFEST, 49200)
    assert text.count(PATH) == 1
    source = tmp_path / "Caddyfile"
    source.write_text(text)
    # Native capability is explicit: adapt inert bytes, never run/reload/install.
    executable = Path("/opt/homebrew/bin/caddy")
    if executable.is_file():
        r = subprocess.run(
            [
                str(executable),
                "adapt",
                "--config",
                str(source),
                "--adapter",
                "caddyfile",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        config = json.loads(r.stdout)
        transition._locate(config, edge.asset_routes(CURRENT_MANIFEST), 49200)
        if os.environ.get("MMOS_COMPANY_CADDY"):
            Path(os.environ["MMOS_COMPANY_CADDY"]).write_text(r.stdout)
    else:
        # Linux source still checks exact render and one-route delta; native adapt
        # evidence is separately required, not silently claimed here.
        assert "path " + " ".join(edge.POST_ROUTES) + "\n" in text
