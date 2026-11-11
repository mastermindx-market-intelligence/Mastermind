"""Review-channel Slack publication is optional visibility, never execution."""
from control_plane.github_review_intent import (
    IntentSource, ReviewIntentDecision, review_command_id, review_intent_id,
)
from control_plane.executive_runtime import Runtime
from integrations.github_review_slack_thread import ExecutiveSlackReviewThreads
from integrations.slack_agent_dialogue.engine import SlackMessage
from integrations.github_review_slack_visibility import (
    REVIEW_CHANNEL_ID, SlackReviewVisibility,
)
from integrations.slack_agent_dialogue.slack_web_api import SlackWebApiDialogueClient


def client():
    return SlackWebApiDialogueClient(
        token="unit-test-non-secret-token",
        workspace_id="T0BRD2AQXQV",
        channel_id=REVIEW_CHANNEL_ID,
        bot_user_id="U0BT71H4FQE",
    )


def decision():
    intent = review_intent_id(
        repository="example/private", pull_number=42, head_sha="a" * 40
    )
    return ReviewIntentDecision(
        admitted=True, refusal=None, intent_source=IntentSource.INTENT_LABEL,
        intent_id=intent, command_id=review_command_id(intent),
        delivery_command_id="gh-review-delivery:" + "a" * 32,
        repository="example/private", pull_number=42,
        frozen_head_sha="a" * 40, actor="alice",
    )


def test_public_channel_never_discloses_private_repository_or_pr_body(tmp_path):
    instance = client()
    sent = []
    async def fake_post_parent(*, channel_id, text):
        sent.append((channel_id, text))
        return SlackMessage(ts="1792699000.000001", author_user_id="U0BT71H4FQE", text=text)
    instance.post_parent = fake_post_parent
    threads = ExecutiveSlackReviewThreads(runtime=Runtime.at(tmp_path))
    notice = SlackReviewVisibility(client=instance, threads=threads)
    notice.notify_review_admitted(summary="private secret title", decision=decision(), job_id="JOB-042")
    assert sent[0][0] == REVIEW_CHANNEL_ID
    assert "JOB-042" in sent[0][1]
    assert "QUEUED" in sent[0][1]
    assert "example/private" not in sent[0][1]
    assert "private secret title" not in sent[0][1]
    assert "alice" not in sent[0][1]


def test_exact_explicit_public_repo_opt_in(tmp_path):
    instance = client()
    sent = []
    async def fake_post_parent(*, channel_id, text):
        sent.append(text)
        return SlackMessage(ts="1792699000.000001", author_user_id="U0BT71H4FQE", text=text)
    instance.post_parent = fake_post_parent
    threads = ExecutiveSlackReviewThreads(runtime=Runtime.at(tmp_path))
    notice = SlackReviewVisibility(
        client=instance, threads=threads, public_repository_names_authorized=True
    )
    notice.notify_review_admitted(summary="", decision=decision(), job_id="JOB-042")
    assert "example/private#42" in sent[0]


def test_refusal_does_not_post_any_message():
    instance = client()
    async def reject_post(*, channel_id, text):
        raise AssertionError("refusal may not reach Slack")
    instance.post_parent = reject_post
    notice = SlackReviewVisibility(client=instance)
    notice.notify_review_refused(summary="untrusted", decision=decision())
