"""Actual offer reader/check and streaming edge; synthetic account and provider.

Requires the pinned Macro #7143 sources on PYTHONPATH as a disposable offline
fixture. It is not an installed cross-repository import adapter or a live grant.
"""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from engine import provider_subscription_catalog_opencode as offers
from engine import provider_subscription_guard_opencode as guard
from control_plane import opencode_go_stream as stream
from control_plane.opencode_go_pooled_transport import (
    AccountChoice, OpenCodeGoTransportContractError, ProviderRequest,
)

NOW = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)
MODEL = "glm-5.3-flash"


def snapshot():
    # Fixtures are in the actual producer repository, not a copied model catalog.
    root = Path(offers.__file__).parents[1] / "tests/fixtures/opencode_go"
    return offers.Metadata(
        offers.parse_models(json.loads((root / "inventory.json").read_text()), observed_at=NOW.isoformat()),
        offers.parse_terms((root / "terms.mdx").read_text(), observed_at=NOW.isoformat()),
    )


def exercise(tmp_path, change=None, expire_during_key=False):
    initial = snapshot()
    state = {"metadata": initial, "now": NOW}
    trace = []
    workspace = tmp_path / "workspace.txt"
    workspace.write_text("completed-tool-result")
    req = ProviderRequest("chat/completions", "persistent-session", {}, json.dumps({
        "model": MODEL, "stream": True,
        "messages": [{"role": "user", "content": "continue"},
                     {"role": "tool", "tool_call_id": "done-1", "content": workspace.read_text()}],
    }).encode())
    expected = guard.model_offer_digest(initial, MODEL)

    def check(request):
        model = json.loads(request.body)["model"]
        guard.check_request_offer(state["metadata"], model_id=model, protocol="openai-chat",
            now=state["now"].isoformat(), expected_offer_digest=expected,
            expected_policy_digest=initial.terms.policy_digest,
            review_valid_until=(NOW + timedelta(minutes=30)).isoformat())
        trace.append("offer_checked")

    def key(_account):
        trace.append("key_loaded")
        if expire_during_key:
            state["now"] += timedelta(minutes=31)
        return "synthetic-key"

    class Reply:
        status = 200
        def getheaders(self):
            return [("content-type", "text/event-stream")]
        def read1(self, _):
            return b"data: [DONE]\n\n"
        def close(self):
            trace.append("response_closed")

    class Connection:
        sock = None
        def request(self, method, path, body, headers):
            trace.append("POST")
            assert body == req.body
            assert headers["x-opencode-session"] == "persistent-session"
        def getresponse(self):
            return Reply()
        def close(self):
            trace.append("connection_closed")

    if change:
        state["metadata"] = change(initial)
    try:
        result = stream.stream_single_account(req,
            choice=AccountChoice("go", "a" * 64, "account-a"),
            credential_loader=key, request_check=check,
            on_chunk=lambda data: trace.append("chunk"),
            connection_factory=lambda *a, **kw: Connection())
    except OpenCodeGoTransportContractError:
        result = None
    assert workspace.read_text() == "completed-tool-result"
    return result, trace


def test_valid_offer_reaches_one_stream_with_existing_tool_context(tmp_path):
    receipt, trace = exercise(tmp_path)
    assert receipt.terminal_observed
    assert trace == ["offer_checked", "key_loaded", "offer_checked", "POST", "chunk", "response_closed", "connection_closed"]


def test_unrelated_model_release_does_not_break_running_model(tmp_path):
    receipt, trace = exercise(tmp_path, lambda m: replace(m,
        inventory=replace(m.inventory, model_ids=m.inventory.model_ids + ("new-unreviewed-model",))))
    assert receipt.terminal_observed and trace.count("POST") == 1


@pytest.mark.parametrize("change", [
    lambda m: replace(m, inventory=replace(m.inventory, model_ids=tuple(x for x in m.inventory.model_ids if x != MODEL))),
    lambda m: replace(m, inventory=replace(m.inventory, observed_at="2026-09-14T16:59:59Z")),
    lambda m: replace(m, terms=replace(m.terms, horizon_fractions=("0.1", "0.5", "1"))),
    lambda m: replace(m, terms=replace(m.terms, policy_digest="e" * 64)),
])
def test_bad_metadata_blocks_before_key_or_post_and_preserves_workspace(tmp_path, change):
    receipt, trace = exercise(tmp_path, change)
    assert receipt is None and trace == []


def test_expiry_during_key_acquisition_is_rechecked_before_post(tmp_path):
    receipt, trace = exercise(tmp_path, expire_during_key=True)
    assert receipt is None and trace == ["offer_checked", "key_loaded", "connection_closed"]
