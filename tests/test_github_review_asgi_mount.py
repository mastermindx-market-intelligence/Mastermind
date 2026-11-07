"""The GitHub webhook can be mounted without changing incumbent route behavior."""
import asyncio
import json

import pytest

from control_plane.github_review_host_config import (
    ReviewHostSettings, EXACT_REVIEW_DELIVERY_PATH,
)
from integrations.github_review_asgi_mount import GitHubReviewASGIMount
from integrations.github_review_ingress_asgi import GitHubReviewReceiver


class Inert:
    def webhook_secret(self, *, installation_id):
        raise AssertionError("disabled receiver must never ask for a secret")
    def read_pull_request(self, *, repository, pull_number):
        raise AssertionError("disabled receiver must never read GitHub")
    def read_current_permission(self, *, repository, login):
        raise AssertionError("disabled receiver must never check an actor")
    def admitted_command_ids(self):
        raise AssertionError("disabled receiver must never read Runtime")
    def admit_review_intent(self, *, decision, objective):
        raise AssertionError("disabled receiver must never write Runtime")


class Existing:
    def __init__(self):
        self.calls = []
    async def __call__(self, scope, receive, send):
        self.calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 418, "headers": []})
        await send({"type": "http.response.body", "body": b"existing"})


def receiver():
    owner = Inert()
    return GitHubReviewReceiver(
        settings=ReviewHostSettings(
            enabled=False, publication_enabled=False,
            expected_host="review.example.com", require_https=True,
            installation_id=4242, installation_ids=frozenset({4242}),
            repositories=frozenset({"example/repo"}),
            configured_reviewer="reviewer",
            authorized_actors=frozenset({"alice"}),
        ),
        secret_source=owner, pull_requests=owner, actors=owner, fabric=owner,
    )


def receiver_for(repository, *, installation_id=4242,
                 installation_ids=None, expected_host="review.example.com",
                 require_https=True):
    """A composed receiver for exactly one tenant, with no live port."""
    owner = Inert()
    return GitHubReviewReceiver(
        settings=ReviewHostSettings(
            enabled=False, publication_enabled=False,
            expected_host=expected_host, require_https=require_https,
            installation_id=installation_id,
            installation_ids=(
                frozenset({installation_id}) if installation_ids is None
                else frozenset(installation_ids)
            ),
            repositories=frozenset({repository}),
            configured_reviewer="reviewer",
            authorized_actors=frozenset({"alice"}),
        ),
        secret_source=owner, pull_requests=owner, actors=owner, fabric=owner,
    )


def invoke(app, *, path, raw_path=None):
    sent = []
    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        sent.append(message)
    scope = {
        "type": "http", "method": "POST", "path": path,
        "raw_path": raw_path if raw_path is not None else path.encode(),
        "query_string": b"", "scheme": "https", "headers": [],
    }
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"]


def test_inactive_mount_is_byte_preserving_for_existing_routes():
    old = Existing()
    mount = GitHubReviewASGIMount(existing_app=old)
    assert invoke(mount, path="/os/executive/submit") == 418
    assert invoke(mount, path=EXACT_REVIEW_DELIVERY_PATH) == 418
    assert old.calls == ["/os/executive/submit", EXACT_REVIEW_DELIVERY_PATH]


def test_explicit_receiver_only_intercepts_one_exact_path():
    old = Existing()
    mount = GitHubReviewASGIMount(existing_app=old, receiver=receiver())
    assert invoke(mount, path="/os/executive/submit") == 418
    assert old.calls == ["/os/executive/submit"]
    # Disabled mounts must preserve the incumbent route rather than shadow it.
    assert invoke(mount, path=EXACT_REVIEW_DELIVERY_PATH) == 418
    assert old.calls == ["/os/executive/submit", EXACT_REVIEW_DELIVERY_PATH]


def test_receiver_cannot_shadow_os_or_mcp_route():
    with pytest.raises(ValueError):
        ReviewHostSettings(
            enabled=False, publication_enabled=False,
            expected_host="review.example.com", require_https=True,
            delivery_path="/mcp", installation_id=4242,
            installation_ids=frozenset({4242}),
            repositories=frozenset({"example/repo"}),
            configured_reviewer="reviewer",
            authorized_actors=frozenset({"alice"}),
        )


# --- the host-owned multi-repository map ----------------------------------


def test_a_mixed_single_and_map_configuration_is_refused():
    with pytest.raises(TypeError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver=receiver(),
            receiver_map={(4242, "example/repo"): receiver_for("example/repo")},
        )


def test_an_empty_map_stays_the_default_off_posture():
    old = Existing()
    mount = GitHubReviewASGIMount(existing_app=old, receiver_map={})
    assert invoke(mount, path=EXACT_REVIEW_DELIVERY_PATH) == 418
    assert old.calls == [EXACT_REVIEW_DELIVERY_PATH]


def test_a_map_of_one_receiver_is_accepted():
    mount = GitHubReviewASGIMount(
        existing_app=Existing(),
        receiver_map={(4242, "example/repo"): receiver_for("example/repo")},
    )
    assert isinstance(mount, GitHubReviewASGIMount)


def test_a_map_value_must_be_the_exact_receiver():
    with pytest.raises(TypeError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={(4242, "example/repo"): object()},
        )


@pytest.mark.parametrize("key", [
    4242,
    (4242,),
    (4242, "example/repo", "extra"),
    "example/repo",
    (0, "example/repo"),
    (-1, "example/repo"),
    (True, "example/repo"),
    (4242, "not canonical"),
    (4242, 42),
])
def test_an_invalid_routing_key_is_refused(key):
    with pytest.raises((TypeError, ValueError)):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={key: receiver_for("example/repo")},
        )


def test_a_key_must_exactly_match_its_receiver_repository():
    with pytest.raises(ValueError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={(4242, "example/other"): receiver_for("example/repo")},
        )


def test_a_key_must_exactly_match_its_receiver_installation():
    with pytest.raises(ValueError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={(5252, "example/repo"): receiver_for("example/repo")},
        )


def test_a_routed_receiver_must_be_bound_to_one_repository():
    owner = Inert()
    both = GitHubReviewReceiver(
        settings=ReviewHostSettings(
            enabled=False, publication_enabled=False,
            expected_host="review.example.com", require_https=True,
            installation_id=4242, installation_ids=frozenset({4242}),
            repositories=frozenset({"example/repo", "example/other"}),
            configured_reviewer="reviewer",
            authorized_actors=frozenset({"alice"}),
        ),
        secret_source=owner, pull_requests=owner, actors=owner, fabric=owner,
    )
    with pytest.raises(ValueError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={(4242, "example/repo"): both},
        )


def test_a_routed_receiver_uses_only_its_active_installation_policy():
    selected = receiver_for("example/repo", installation_ids={4242, 5252})
    mount = GitHubReviewASGIMount(
        existing_app=Existing(), receiver_map={(4242, "example/repo"): selected},
    )
    assert mount._routing.tenant_count == 1
    assert selected._settings.review_policy().installation_ids == frozenset({4242})


def test_a_case_folded_tenant_collision_is_refused():
    with pytest.raises(ValueError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={
                (4242, "example/repo"): receiver_for("example/repo"),
                (4242, "Example/Repo"): receiver_for("Example/Repo"),
            },
        )


def test_a_duplicated_tenant_is_refused():
    with pytest.raises(ValueError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map=[
                ((4242, "example/repo"), receiver_for("example/repo")),
                ((4242, "example/repo"), receiver_for("example/repo")),
            ],
        )


def test_one_receiver_may_not_serve_two_tenants():
    shared = receiver_for("example/repo")
    with pytest.raises(ValueError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={
                (4242, "example/repo"): shared,
                (4242, "example/other"): shared,
            },
        )


def test_routed_receivers_must_share_one_ingress_host():
    with pytest.raises(ValueError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={
                (4242, "example/repo"): receiver_for("example/repo"),
                (4242, "example/other"): receiver_for(
                    "example/other", expected_host="other.example.com"),
            },
        )


def test_routed_receivers_must_share_one_tls_posture():
    with pytest.raises(ValueError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map={
                (4242, "example/repo"): receiver_for("example/repo"),
                (4242, "example/other"): receiver_for(
                    "example/other", require_https=False),
            },
        )


def test_a_map_entry_must_be_a_key_receiver_pair():
    with pytest.raises(TypeError):
        GitHubReviewASGIMount(
            existing_app=Existing(),
            receiver_map=[(4242, "example/repo")],
        )
