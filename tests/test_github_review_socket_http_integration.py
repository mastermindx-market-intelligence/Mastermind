"""Signed ASGI webhook -> real Unix socket -> canonical Runtime Job, default off.

This is a hermetic simulated socket listener using the existing owner adapter;
it DOES NOT claim that the installed ExecutiveControlService handler is bound.
"""
import asyncio
import datetime
import json
import time

import httpx

from control_plane.executive_runtime import Runtime, JobPayload
from control_plane.github_review_intent import sign_webhook_body
from control_plane.github_review_intent_ingress import PublishState
from control_plane.github_review_socket_owner import ExecutiveGitHubReviewSocketOwner
from integrations.github_review_host_composition import compose_github_review_host
from integrations.github_review_return import GitHubReviewReturn, ReviewReturnSourceMode
from integrations.github_review_socket_client import ExecutiveReviewSocketClient
from integrations.github_review_slack_thread import (
    ExecutiveSlackReviewThreads, SlackReviewResultNotifier, review_parent_body,
)
from test_github_review_publish_workflow import git_api
from test_github_review_runtime_adapter import decision
from integrations.slack_agent_dialogue.engine import SlackMessage
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient
from test_github_review_host_composition import Hook, _settings, credentials

REPO = "example/repo"
SHA = "a" * 40
SECRET = "test-webhook-secret"
DELIVERY_ID = "11111111-2222-3333-4444-555555555555"


def test_signed_webhook_over_real_socket_admits_once_not_a_worker_start(tmp_path):
    async def exercise():
        source_checks = []
        runtime = Runtime.at(tmp_path / "runtime")
        def source_guard(subject):
            assert subject.repository == REPO
            assert subject.pull_number == 42
            assert subject.frozen_head_sha == SHA
            source_checks.append(subject.command_id)
        notifications = []
        def trusted_parent_reader(subject, job_id, ts):
            # This fixture stands in for the installed host's authenticated
            # exact-channel Slack GET; no public socket body is trusted.
            assert subject.command_id == decision().command_id
            assert job_id == "JOB-001"
            assert ts == "1792699000.000001"
            assert notifications[0][0] == "C0CAUK8P8S3"
            return SlackMessage(
                ts=ts, author_user_id="U0BT71H4FQE",
                text=notifications[0][1],
            )
        owner = ExecutiveGitHubReviewSocketOwner(
            runtime=runtime, admission_guard=lambda: None,
            source_guard=source_guard,
            repositories=frozenset({REPO}),
            relay_bot_user_id="U0BT71H4FQE",
            parent_message_reader=trusted_parent_reader,
            parent_recorder=ExecutiveSlackReviewThreads(runtime=runtime).record_parent,
            parent_reserver=ExecutiveSlackReviewThreads(runtime=runtime).reserve_parent_send,
            parent_body_renderer=review_parent_body,
            worker_constraints={"eligible_quota_classes": ["codex-native"]},
        )
        socket_path = str(tmp_path / "ceo-ingress.sock")
        async def handle(reader, writer):
            try:
                raw = await asyncio.wait_for(reader.readline(), timeout=3.0)
                assert len(raw) <= 8192
                result = await asyncio.to_thread(
                    owner.handle_frame, json.loads(raw)
                )
                payload = {"ok": True, "result": result}
            except Exception:
                payload = {"ok": False, "error": {"code": "refused"}}
            writer.write(json.dumps(payload).encode() + b"\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        server = await asyncio.start_unix_server(handle, path=socket_path)
        requests = []
        notifications = []
        expires = datetime.datetime.fromtimestamp(
            time.time() + 2400, tz=datetime.timezone.utc
        ).isoformat().replace("+00:00", "Z")

        def auth_transport(request):
            assert request.url.path.endswith("/app/installations/4242/access_tokens")
            return httpx.Response(201, json={
                "token": "synthetic-fenced-app-token", "expires_at": expires,
                "permissions": {"metadata": "read", "contents": "read",
                                "pull_requests": "write"},
                "repositories": [{"full_name": REPO}],
            })

        def github_transport(request):
            requests.append((request.method, request.url.path))
            assert request.headers["authorization"] == "Bearer synthetic-fenced-app-token"
            if request.url.path.endswith("/collaborators/alice/permission"):
                return httpx.Response(200, json={
                    "user": {"login": "alice"},
                    "permission": "write", "role_name": "write",
                })
            if request.url.path.endswith("/pulls/42"):
                return httpx.Response(200, json={
                    "number": 42, "state": "open", "draft": False,
                    "head": {"sha": SHA, "repo": {"full_name": REPO}},
                    "base": {"sha": "b" * 40, "repo": {"full_name": REPO}},
                    "title": "Source review", "body": "Untrusted PR content",
                })
            raise AssertionError("unrecognized GitHub API request")

        relay = SlackWebApiDialogueClient(
            token="synthetic-test-token", workspace_id="T0BRD2AQXQV",
            channel_id="C0CAUK8P8S3", bot_user_id="U0BT71H4FQE",
        )
        async def post_parent(*, channel_id, text):
            notifications.append((channel_id, text))
            return SlackMessage(
                ts="1792699000.000001",
                author_user_id="U0BT71H4FQE", text=text,
            )
        relay.post_parent = post_parent
        app = compose_github_review_host(
            settings=_settings(), app_id=123,
            private_key_source=credentials,
            webhook_secret_source=Hook(),
            socket_client=ExecutiveReviewSocketClient(
                socket_path=socket_path
            ),
            relay_client=relay, publisher_login="reviewer-bot[bot]",
            app_token_http_client=httpx.Client(
                transport=httpx.MockTransport(auth_transport)
            ),
            github_http_client=httpx.Client(
                transport=httpx.MockTransport(github_transport)
            ),
        )

        body = json.dumps({
            "action": "labeled", "installation": {"id": 4242},
            "repository": {"full_name": REPO}, "number": 42,
            "pull_request": {
                "number": 42,
                "base": {"repo": {"full_name": REPO}},
            },
            "sender": {"login": "alice"},
            "label": {"name": "independent-review"},
        }).encode()

        async def deliver(*, signature=None):
            sent = []
            headers = [
                (b"host", b"review.example.com"),
                (b"content-type", b"application/json"),
                (b"x-github-event", b"pull_request"),
                (b"x-github-delivery", DELIVERY_ID.encode()),
                (b"x-hub-signature-256",
                 (signature or sign_webhook_body(secret=SECRET, body=body)).encode()),
            ]
            async def receive():
                return {"type": "http.request", "body": body, "more_body": False}
            async def send(event):
                sent.append(event)
            await app({
                "type": "http", "method": "POST",
                "path": app._settings.delivery_path,
                "raw_path": app._settings.delivery_path.encode(),
                "query_string": b"", "scheme": "https",
                "headers": headers,
            }, receive, send)
            return sent[0]["status"], json.loads(sent[1]["body"])

        try:
            assert (await deliver())[0] == 202
            status, info = await deliver()
            assert status == 200 and info["status"] == "ALREADY_ADMITTED"
            assert len(runtime.jobs.list_jobs()) == 1
            job = runtime.jobs.list_jobs()[0]
            assert job.status.value == "QUEUED"
            assert job.attempt_count == 0
            assert job.requested_authorities == ["READ"]
            assert job.allowed_write_paths == []
            assert len(source_checks) >= 3  # before and during commit
            assert len(notifications) == 1
            assert notifications[0][0] == "C0CAUK8P8S3"
            assert REPO not in notifications[0][1]
            # The public socket process must durably return the Slack thread
            # to the existing Executive ledger, not just post a parent.
            assert ExecutiveSlackReviewThreads(runtime=runtime).parent_thread(
                decision=decision(), job_id=job.job_id,
            ) == "1792699000.000001"
            before = len(requests)
            status, response = await deliver(
                signature="sha256=" + "0" * 64
            )
            assert (status, response["status"]) == (401, "SIGNATURE_INVALID")
            assert len(requests) == before
            assert len(runtime.jobs.list_jobs()) == 1

            # A real terminal Runtime Job/Attempt, rather than a synthetic
            # webhook verdict, drives the same exact-head GitHub review and
            # the originally captured Slack thread. This is still hermetic.
            runtime.workers.register_worker(
                "reviewer-01", provider="codex", account_label="reviewer",
                worker_type="mock", capabilities=["code"],
                quota_classes={"codex-native": ["code"]},
            )
            runtime.jobs.assign_job(job.job_id, "reviewer-01")
            runtime.jobs.complete_job(job.job_id, JobPayload(
                summary="Review found blocking changes; advisory only.",
                verdict="reject",
            ))
            replies = []
            async def post_reply(*, channel_id, thread_ts, text):
                replies.append((channel_id, thread_ts, text))
                return SlackMessage(
                    ts="1792699001.000002",
                    author_user_id="U0BT71H4FQE",
                    text=text, thread_ts=thread_ts,
                )
            relay.post_reply = post_reply
            github, history = git_api()
            return_owner = GitHubReviewReturn.for_authorized_source(
                runtime=runtime, github=github,
                publication_guard=lambda: None,
                source_mode=ReviewReturnSourceMode.EXTERNAL_GITHUB_ADVISORY,
                slack=SlackReviewResultNotifier(
                    client=relay,
                    threads=ExecutiveSlackReviewThreads(runtime=runtime),
                ),
            )
            first = await asyncio.to_thread(
                return_owner.deliver, decision=decision(), job_id=job.job_id,
            )
            assert first.publication.state is PublishState.PUBLISHED
            assert first.publication.review_id == "789"
            assert first.slack_receipt == "POSTED"
            assert len(history["posts"]) == len(replies) == 1
            assert history["posts"][0]["event"] == "COMMENT"
            assert "not attested" in history["posts"][0]["body"].lower()
            assert replies[0][0:2] == ("C0CAUK8P8S3", "1792699000.000001")
            assert "789" in replies[0][2] and REPO not in replies[0][2]
            second = await asyncio.to_thread(
                return_owner.deliver, decision=decision(), job_id=job.job_id,
            )
            assert second.publication.state is PublishState.ALREADY_PUBLISHED
            assert len(history["posts"]) == len(replies) == 1
        finally:
            server.close()
            await server.wait_closed()

    asyncio.run(exercise())
