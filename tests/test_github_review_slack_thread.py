"""One reviewed Executive job tracks one Slack parent/reply without new store."""
import pytest

from control_plane.executive_runtime import Runtime
from integrations.github_review_slack_thread import (
    ExecutiveSlackReviewThreads, SlackReviewResultNotifier,
    SlackReviewThreadUnavailable, CHANNEL_ID,
)
from integrations.github_review_slack_visibility import SlackReviewVisibility
from integrations.slack_agent_dialogue.engine import SlackMessage
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient
from test_github_review_runtime_adapter import decision

ROOT = "1792699000.000001"


def client():
    return SlackWebApiDialogueClient(
        token="test-non-secret", workspace_id="T0BRD2AQXQV",
        channel_id=CHANNEL_ID, bot_user_id="U0BT71H4FQE",
    )


def parent_message(text):
    return SlackMessage(
        ts=ROOT, author_user_id="U0BT71H4FQE", text=text,
    )


def test_admission_parent_and_exact_thread_result_with_one_reply(tmp_path):
    runtime = Runtime.at(tmp_path)
    correlation = ExecutiveSlackReviewThreads(runtime=runtime)
    slack = client()
    notices = []
    async def fake_parent(*, channel_id, text):
        notices.append((channel_id, text))
        return parent_message(text)
    replies = []
    async def fake_reply(*, channel_id, thread_ts, text):
        replies.append((channel_id, thread_ts, text))
        return SlackMessage(
            ts="1792699001.000002", author_user_id="U0BT71H4FQE",
            text=text, thread_ts=thread_ts,
        )
    slack.post_parent = fake_parent
    slack.post_reply = fake_reply
    vis = SlackReviewVisibility(client=slack, threads=correlation)
    vis.notify_review_admitted(
        summary="private source", decision=decision(), job_id="JOB-777"
    )
    assert len(notices) == 1
    assert correlation.parent_thread(
        decision=decision(), job_id="JOB-777"
    ) == ROOT
    notifier = SlackReviewResultNotifier(client=slack, threads=correlation)
    assert notifier.notify_result(
        decision=decision(), job_id="JOB-777", review_id="879"
    )
    assert len(replies) == 1 and replies[0][1] == ROOT
    assert "879" in replies[0][2]
    assert "example/repo" not in replies[0][2]
    assert not notifier.notify_result(
        decision=decision(), job_id="JOB-777", review_id="879"
    )
    assert len(replies) == 1


def test_invalid_second_github_review_receipt_cannot_claim_same_thread(tmp_path):
    runtime = Runtime.at(tmp_path)
    correlation = ExecutiveSlackReviewThreads(runtime=runtime)
    assert correlation.reserve_parent_send(decision=decision(), job_id="JOB-777")
    correlation.record_parent(
        decision=decision(), job_id="JOB-777", message=parent_message("queued")
    )
    assert correlation.reserve_result_reply(
        decision=decision(), job_id="JOB-777", review_id="879"
    ) == ROOT
    with pytest.raises(SlackReviewThreadUnavailable, match="CONFLICT"):
        correlation.reserve_result_reply(
            decision=decision(), job_id="JOB-777", review_id="880"
        )


def test_unbound_slack_thread_cannot_fabricate_a_result_post(tmp_path):
    correlation = ExecutiveSlackReviewThreads(runtime=Runtime.at(tmp_path))
    slack = client()
    async def unexpected(*, channel_id, thread_ts, text):
        raise AssertionError("unbound thread cannot be used")
    slack.post_reply = unexpected
    notifier = SlackReviewResultNotifier(client=slack, threads=correlation)
    assert not notifier.notify_result(
        decision=decision(), job_id="JOB-777", review_id="879"
    )


def test_ambiguous_slack_post_is_never_retried(tmp_path):
    runtime = Runtime.at(tmp_path)
    correlation = ExecutiveSlackReviewThreads(runtime=runtime)
    assert correlation.reserve_parent_send(decision=decision(), job_id="JOB-777")
    correlation.record_parent(
        decision=decision(), job_id="JOB-777", message=parent_message("queued")
    )
    slack = client()
    count = []
    async def failing(*, channel_id, thread_ts, text):
        count.append(1)
        raise OSError("lost Slack ACK")
    slack.post_reply = failing
    notifier = SlackReviewResultNotifier(client=slack, threads=correlation)
    with pytest.raises(SlackReviewThreadUnavailable, match="EFFECT_UNKNOWN"):
        notifier.notify_result(
            decision=decision(), job_id="JOB-777", review_id="879"
        )
    assert not notifier.notify_result(
        decision=decision(), job_id="JOB-777", review_id="879"
    )
    assert len(count) == 1


def test_duplicate_parent_admission_reserves_one_send_before_slack_post(tmp_path):
    import concurrent.futures
    import threading

    runtime = Runtime.at(tmp_path)
    correlation = ExecutiveSlackReviewThreads(runtime=runtime)
    slack = client()
    posts = []
    lock = threading.Lock()

    async def fake_post_parent(*, channel_id, text):
        with lock:
            posts.append((channel_id, text))
        return parent_message(text)

    slack.post_parent = fake_post_parent
    visibility = SlackReviewVisibility(client=slack, threads=correlation)
    subject = decision()
    barrier = threading.Barrier(2)

    def deliver(_):
        barrier.wait(timeout=5)
        visibility.notify_review_admitted(
            summary="", decision=subject, job_id="JOB-777"
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(deliver, range(2)))
    assert len(posts) == 1
    assert correlation.parent_thread(decision=subject, job_id="JOB-777") == ROOT
    send_events = runtime.store.list_events(
        command_id_prefix="gh-review-slack-send:"
    )
    assert len(send_events) == 1
    assert send_events[0].event_type == "GITHUB_REVIEW_SLACK_PARENT_SEND_RESERVED"


def test_parent_post_lost_ack_consumes_one_reservation_without_repost(tmp_path):
    runtime = Runtime.at(tmp_path)
    correlation = ExecutiveSlackReviewThreads(runtime=runtime)
    relay = client()
    sent = []

    async def ambiguous_parent(*, channel_id, text):
        sent.append((channel_id, text))
        raise OSError("Slack acknowledged remotely but local ACK was lost")

    relay.post_parent = ambiguous_parent
    subject = decision()
    owner = SlackReviewVisibility(client=relay, threads=correlation)
    with pytest.raises(OSError):
        owner.notify_review_admitted(summary="", decision=subject, job_id="JOB-777")
    # The first request might have succeeded remotely. Do not issue a second.
    owner.notify_review_admitted(summary="", decision=subject, job_id="JOB-777")
    assert len(sent) == 1
    assert correlation.parent_thread(decision=subject, job_id="JOB-777") is None
    claims = runtime.store.list_events(command_id_prefix="gh-review-slack-send:")
    assert len(claims) == 1
