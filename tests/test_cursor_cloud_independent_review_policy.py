"""Discriminating source-law tests for the manual GitHub-native Cursor review route.

The same contract validator runs against the actual policy and in-memory
adversarial mutations. No credentials, provider calls, PR edits or runtime effects.
"""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PATHS = {
    "review": "docs/sol_skills/REVIEW_RETURN.md",
    "worker": "docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md",
    "skill": "plugins/mastermind-sol/skills/review-pull-request/SKILL.md",
    "runbook": "docs/CURSOR_CLOUD_INDEPENDENT_REVIEW.md",
}
POLICY = {k: (ROOT / p).read_text() for k, p in PATHS.items()}


def normalized(text):
    return " ".join(text.split())


def scope(texts):
    """Validate each normative statement in its owning, identified section."""
    review = texts["review"].split("## Step 2B — ", 1)[-1].split("## Step 3 — ", 1)[0]
    skill = texts["skill"].split("## Independent review route: Cursor Cloud", 1)[-1].split("## Output", 1)[0]
    worker = texts["worker"].split("For independent PR source/security review", 1)[-1].split("### FABLE", 1)[0]
    runbook = texts["runbook"].split("## Historical real example", 1)[0]
    history = texts["runbook"].split("## Historical real example — Mastermind #1515", 1)[-1]
    return {k: normalized(v) for k, v in [
        ("review", review), ("skill", skill), ("worker", worker),
        ("runbook", runbook), ("history", history),
    ]}


# Match *whole signed, normative clauses*, not loose keywords, substrings like
# valid inside invalid, or the mere presence of "terminal" or "permission".
REQUIRED = {
    "review": [
        "is **not** an Executive OS model/provider alias, Job, Attempt, Fabric acceptance, automatic failover",
        "Never route around an explicit safety/permission/qualification denial, a refused Attempt with `retry_allowed=false`, an active reviewer, or `EFFECT_UNKNOWN`",
        "`Taking a look!` or an agent link alone proves at most a launch acknowledgement, **not** terminal review or acceptance",
        "In Mastermind #1515, GitHub issue-comment `user.login` was `cursor[bot]`, while the agent-reported authenticated GitHub/MCP principal was `chriswong6031-creator`",
        "an ordinary PR issue comment (bot- or author-posted) is never a submitted formal GitHub PR review",
        "**SOURCE-REVIEW-ONLY / NON_AUTHOR_APPROVAL_NOT_PROVEN**, never formal independent `APPROVED`",
        "A Cursor technical PASS cannot close GitHub→Executive/Fabric→formal-review→Slack acceptance",
        "A fresh operation name, GitHub comment or reviewer identity does not reconcile an original `EFFECT_UNKNOWN` review or waive its refusal.",
    ],
    "runbook": [
        "This is not an Executive OS provider, automated reviewer fallback, branch-protection exemption",
        "**No Cursor commission is authorized for the same PR/head/review scope** while an original Fabric Attempt is STARTED/RUNNING, has `EFFECT_UNKNOWN`, has unverified effects, or has not been reconciled.",
        "A new operation ID, distinct reviewer or new `@cursor` comment does not turn that unresolved review into an authorized separate scope.",
        "An explicit safety, permission or qualification denial (including `retry_allowed=false`) **cannot be bypassed** by switching to Cursor.",
        "Only a genuinely separate, independently authorized scope may be commissioned once all prior effects are terminally reconciled and no applicable denial or reviewer collision remains.",
    ],
    "history": [
        "| GitHub issue-comment posting account (GitHub `user.login`) | `cursor[bot]` |",
        "| Cursor Cloud Agent identity | `bc-03e22133-a364-4ec8-98c4-3db18becba0c` |",
        "| Agent-reported authenticated GitHub/MCP principal | `chriswong6031-creator` |",
        "| Formal non-author GitHub PR review from this Cursor source comment | `NOT_PROVEN` |",
        "An ordinary PR issue comment, whether posted by a bot or an author, is never a submitted GitHub pull-request review.",
        "The later `MastermindX1` submitted `APPROVED` review is a distinct GitHub event on a different head",
    ],
    "skill": [
        "is a **valid manual source-review route**",
        "A `Taking a look!` acknowledgement is never a completed review",
        "formal **non-author approval is NOT proven**",
        "Never use this avenue to circumvent an explicit permission/safety denial, `retry_allowed=false`, `EFFECT_UNKNOWN`",
    ],
    "worker": [
        "permissible attended external review surface",
        "It is not an Executive-provider alias, a new Fabric pool, or automatic fallback",
        "Only after Fabric unavailability is verified and the original reviewer effects are reconciled",
        "does not replace formal non-author GitHub approval or any mandatory Fabric START/acceptance proof",
    ],
}


def failed_contracts(texts):
    parts = scope(texts)
    return [
        f"{doc}: missing normative contract {clause!r}"
        for doc, clauses in REQUIRED.items()
        for clause in clauses
        if clause.replace("`", chr(96)) not in parts[doc]
    ]


def test_current_policy_fulfills_all_normative_contracts():
    assert not failed_contracts(POLICY), "\n".join(failed_contracts(POLICY))


@pytest.mark.parametrize("doc,old,new", [
    ("review", "is **not** an Executive OS model/provider alias", "is an Executive OS model/provider alias"),
    ("runbook", "This is not an Executive OS provider", "This is an Executive OS provider"),
    ("skill", "**valid manual source-review route**", "**invalid manual source-review route**"),
    ("review", "proves at most a launch acknowledgement, **not** terminal review or acceptance",
     "is terminal review and acceptance"),
    ("review", "never formal independent `APPROVED`",
     "and is formal independent `APPROVED`"),
    ("review", "Never route around an explicit safety/permission/qualification denial",
     "Always route around an explicit safety/permission/qualification denial"),
    ("runbook", "**No Cursor commission is authorized for the same PR/head/review scope**",
     "**A Cursor commission is authorized for the same PR/head/review scope**"),
    ("runbook", "**cannot be bypassed** by switching to Cursor",
     "**can be bypassed** by switching to Cursor"),
    ("runbook", "A new operation ID, distinct reviewer or new `@cursor` comment does not turn",
     "A new operation ID, distinct reviewer or new `@cursor` comment does turn"),
    ("skill", "Never use this avenue to circumvent an explicit permission/safety denial",
     "Always use this avenue to circumvent an explicit permission/safety denial"),
    ("worker", "It is not an Executive-provider alias, a new Fabric pool, or automatic fallback",
     "It is an Executive-provider alias, a new Fabric pool, and automatic fallback"),
    ("review", "GitHub issue-comment `user.login` was `cursor[bot]`",
     "GitHub issue-comment `user.login` was `chriswong6031-creator`"),
    ("review", "agent-reported authenticated GitHub/MCP principal was `chriswong6031-creator`",
     "agent-reported authenticated GitHub/MCP principal was `cursor[bot]`"),
    ("review", "an ordinary PR issue comment (bot- or author-posted) is never a submitted formal GitHub PR review",
     "an ordinary PR issue comment (bot- or author-posted) is a submitted formal GitHub PR review"),
    ("runbook", "| GitHub issue-comment posting account (GitHub `user.login`) | `cursor[bot]` |",
     "| GitHub issue-comment posting account (GitHub `user.login`) | `chriswong6031-creator` |"),
    ("runbook", "| Cursor Cloud Agent identity | `bc-03e22133-a364-4ec8-98c4-3db18becba0c` |",
     "| Cursor Cloud Agent identity | `chriswong6031-creator` |"),
    ("runbook", "| Agent-reported authenticated GitHub/MCP principal | `chriswong6031-creator` |",
     "| Agent-reported authenticated GitHub/MCP principal | `cursor[bot]` |"),
    ("runbook", "| Formal non-author GitHub PR review from this Cursor source comment | `NOT_PROVEN` |",
     "| Formal non-author GitHub PR review from this Cursor source comment | `APPROVED` |"),
    ("runbook", "The later `MastermindX1` submitted `APPROVED` review",
     "The later `cursor[bot]` submitted `APPROVED` review"),
], ids=[
    "alias-review", "alias-runbook", "invalid-is-not-valid", "ack-is-not-verdict",
    "author-account-is-not-approval", "denial-no-bypass", "unknown-effect-no-cursor",
    "retry-denial-no-bypass", "new-label-not-new-scope", "skill-denial-no-bypass",
    "no-autonomous-provider", "commenter-not-mcp-principal",
    "mcp-principal-not-bot", "issue-comment-not-formal-review",
    "history-commenter-not-author", "agent-id-not-mcp-principal",
    "history-mcp-not-commenter", "source-comment-not-approval",
    "later-formal-reviewer-not-commenter",
])
def test_adversarial_mutation_is_rejected_by_same_policy_validator(doc, old, new):
    old, new = old.replace("`", chr(96)), new.replace("`", chr(96))
    original = normalized(POLICY[doc])
    old, new = normalized(old), normalized(new)
    assert original.count(old) == 1, f"Mutation cannot anchor exactly once: {doc}: {old!r}"
    mutant = dict(POLICY)
    mutant[doc] = original.replace(old, new, 1)
    failures = failed_contracts(mutant)
    assert failures, f"Forbidden {doc} mutation incorrectly survived all normative contracts"


def test_historical_real_agent_is_source_evidence_not_formal_approval():
    runbook = POLICY["runbook"]
    assert "6389262119" in runbook and "6389332447" in runbook
    assert "bc-03e22133-a364-4ec8-98c4-3db18becba0c" in runbook
    assert "NON_AUTHOR_APPROVAL_NOT_PROVEN" in runbook
    assert "submitted review" in runbook


def test_historical_pr1515_does_not_falsely_attribute_comment_to_source_author():
    review, history = POLICY["review"], POLICY["runbook"]
    assert "posted through a PR-author account, as occurred in" not in review
    assert "The posting GitHub identity also authored PR code" not in history
    assert not failed_contracts(POLICY), "\n".join(failed_contracts(POLICY))
