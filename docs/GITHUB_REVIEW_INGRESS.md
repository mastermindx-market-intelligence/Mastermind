# GitHub independent-review ingress — decision core and adapter interfaces

Status: **DRAFT source slice.** Ships the decision core and the adapter
interfaces only. No transport, credential, webhook route, or reviewer identity
is bound here. This document is the operator contract for what a human admin
must do before any delivery can be admitted.

## What this slice is

| Module | Role |
| --- | --- |
| `control_plane/github_review_intent.py` | Pure decision core. HMAC verification, allowlist, intent channels, actor authority, fork refusal, untrusted-text fencing, admission identity, head freeze. No I/O, clock, network, subprocess, or filesystem. |
| `control_plane/github_review_intent_ingress.py` | Composition walk plus the five adapter `Protocol`s. No transport, queue, table, lifecycle, or credential. |
| `tests/test_github_review_intent.py` | Guard file for the decision core. |
| `tests/test_github_review_intent_ingress.py` | Guard file for the ingress walk. |

## What this slice is not

It deliberately does **not** create a second instance of anything that already
has an owner:

- **No second review adjudicator.** `control_plane/github_release_assessment.py`
  owns review adjudication; this slice never judges review content.
- **No second PR disposition owner.** `control_plane/github_pr_lifecycle.py` owns
  disposition.
- **No second GitHub App / installation governance layer.**
  `scripts/github_estate_governance.py` owns installation pinning and the
  least-privilege permission projection.
- **No second live GitHub reader.** `scripts/source_continuity.py` is the
  bounded reader; a host adapter that needs `/pulls/{n}` must extend it rather
  than stand up a new client.
- **No second review registry and no second independent-review authority.** The
  Fabric's `review_required` / `reviews_job_id` / `orchestration_role='review'`
  model in `control_plane/executive_runtime.py` remains the only one.
- **No second verdict vocabulary.** The verdict set is borrowed verbatim from
  `plugins/mastermind-sol/skills/review-pull-request/SKILL.md`.

## Idempotency is the existing ledger's

There is no run registry, cache, or lock in this slice. The admission identity
is minted deterministically from
`(repository, pull number, frozen head SHA, intent channel)` and shaped to be
the existing `events.command_id` UNIQUE index key
(`executive_runtime._COMMAND_ID_RE`, `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`).

Consequences a host adapter inherits for free:

- an identical redelivery re-mints the same command id, so the UNIQUE index
  admits **exactly one** run;
- a moved head mints a **different** command id, so a stale review can never be
  mistaken for a current one;
- the intent channel is part of the identity, so a label and a review request
  never silently collapse into one run.

The identity namespace is domain-separated (`mastermind.github_review_intent.*`)
so it can never collide with the existing MCP / Slack / automated CEO-intent
families in `control_plane/ceo_request.py`.

## The three intent channels

All three require an **allowlisted actor**.

| Channel | Delivery | Actor basis |
| --- | --- | --- |
| Configured reviewer requested | `pull_request` / `review_requested` | GitHub itself enforces triage/write; the login must still be allowlisted |
| Slash command comment | `issue_comment` / `created` | Login allowlist **and** GitHub's reported `author_association` against the policy ceiling |
| Intent label | `pull_request` / `labeled` | GitHub itself enforces write; the login must still be allowlisted |

The command matches the **first non-empty comment line exactly**. A comment that
merely mentions `/independent-review` never triggers a run.

## Fail-closed refusals

Every non-admitted decision names exactly one closed-vocabulary value. The
notable ones:

`SIGNATURE_INVALID`, `BODY_TOO_LARGE`, `EVENT_NOT_SUPPORTED`,
`ACTION_NOT_SUPPORTED`, `REPOSITORY_NOT_ALLOWLISTED`,
`INSTALLATION_NOT_ALLOWLISTED`, `REVIEW_REQUEST_FOR_OTHER_REVIEWER`,
`COMMAND_NOT_PRESENT`, `LABEL_NOT_PRESENT`, `ACTOR_NOT_AUTHORIZED`,
`ACTOR_ASSOCIATION_INSUFFICIENT`, `PULL_REQUEST_NOT_OPEN`,
`PULL_REQUEST_DRAFT`, `HEAD_REPOSITORY_MISMATCH`, `HEAD_SHA_MALFORMED`,
`UNTRUSTED_CONTENT_DETECTED`, `ALREADY_ADMITTED`, `HEAD_MOVED`.

A refusal is evidence for a human or a separately authorized caller. It is
never authority to open, close, merge, approve, or publish anything.

## Security properties

**Signature.** HMAC-SHA256 over the exact raw body, `sha256=<64 lowercase hex>`,
constant-time `hmac.compare_digest` after an exact length and shape fence —
mirroring `integrations/workspace_agent_return.py`. A delivery that fails
verification raises before the PR read, before the ledger, and before any
visibility surface, so it is neither a run trigger nor a probe oracle.

**Untrusted PR text.** Pull-request title and body are retrieved data, never
instruction. They are refused outright when they carry a credential shape
(the same patterns as `control_plane/github_pr_lifecycle.py`) or the untrusted
fence terminator, and are otherwise carried only inside an explicit
`<<<UNTRUSTED_PULL_REQUEST_CONTENT … >>>` block. A PR author can neither escape
the fence nor smuggle an instruction into a command, argv, or authority field.

**Forks.** A PR whose head repository differs from its base repository is
refused with `HEAD_REPOSITORY_MISMATCH`. A fork is the canonical
prompt-injection carrier: its author is not a repository collaborator.

**Exact PR identity.** The head SHA, base SHA, and repositories used to freeze a
run come from an installation-scoped re-read
(`GET /repos/{repo}/pulls/{n}`), never from the webhook payload. The webhook only
says a PR *may* have changed.

**Head freeze.** A run is admitted against one exact head SHA. Publication
re-checks the head and fails closed with `HEAD_MOVED` rather than re-pointing a
stale review at a new commit.

**No unfenced auto-approval.** `PASS` maps to a GitHub `COMMENT`, never
`APPROVE`. This slice mints no approval verb and no merge path at all.

**Separate worker.** Publication refuses a result whose reviewer is the builder
(`REVIEW_NOT_INDEPENDENT`) or whose reviewer identity is unknown
(`REVIEWER_IDENTITY_UNKNOWN`). The reviewer must come from the Fabric's own
worker identities, resolved by `Runtime.validated_role_completion` and
`control_plane/fabric_result_projection`.

**Publish retry.** Publication carries its own deterministic command id bound to
job and frozen head, so a retry reconciles to `ALREADY_PUBLISHED` instead of
posting a second formal review.

**Visibility is non-gating.** A Slack failure is recorded on the outcome, never
raised, and never causes a second admission.

## Adapter interfaces to bind

| Port | Binds to |
| --- | --- |
| `PullRequestReadPort` | A GitHub App installation token minted from the configured app, then `GET /repos/{repo}/pulls/{n}` |
| `FabricJobAdmissionPort` | `executive_runtime` Job registry — `create_job(..., command_id=decision.command_id)`; `admitted_command_ids()` reads the same index back |
| `VisibilityPort` | The existing Slack Web API client in `integrations/slack_agent_dialogue/slack_web_api.py` |
| `ReviewResultPort` | `Runtime.validated_role_completion` + `fabric_result_projection.project_fabric_role_result`, returning a result only when the projected receipt state is `SAME` |
| `ReviewPublicationPort` | `POST /repos/{repo}/pulls/{n}/reviews` with the publication command id as its idempotency key |

A missing port raises `ReviewIngressUnavailable` / `ReviewVerificationRefused`.
There is no fallback to an unauthenticated client.

## Human-admin gates (not satisfied by this slice)

Nothing below is automated, and none of it is done by this PR.

**GitHub App**

1. Create or select the GitHub App. Do not reuse `macro-production-publisher`;
   that app's installation is governed by
   `scripts/github_estate_governance.py` and is a different publisher identity.
2. Subscribe to exactly these repository events: `Pull request` (review
   requested, labeled) and `Issue comment`.
3. Install it on `mastermindx-market-intelligence/Mastermind` only, and record
   the resulting **installation id** — the policy allowlist refuses every other
   installation.
4. Set the webhook URL and record the **webhook secret** in the host's secret
   store only. Never in the repository, a prompt, a doc, or a git remote.
5. Confirm the App can read pull requests and submit pull request reviews. It
   needs nothing else — and specifically not merge, push, or administration
   scopes.

**The allowlist policy** is host configuration, not code. Populate
`repositories`, `installation_ids`, `configured_reviewer`, and
`authorized_actors`. `authorized_actors` should be the small set of humans who
may request a review; anyone else is refused with `ACTOR_NOT_AUTHORIZED`.

**Slack**

6. Grant the existing Slack app `chat:write` for the target channel. Reuse the
   existing dialogue client and its token; do not mint a second Slack
   credential.

**Runtime arming**

7. Bind the five ports in the host that already owns the credentials. Until
   that happens an unbound port is a typed refusal.
8. Decide the ingress route's exposure and rate limit. This slice ships no HTTP
   route, so there is nothing to expose yet.

## Verification performed

- `python3 -m pytest tests/test_github_review_intent.py tests/test_github_review_intent_ingress.py`
  — 90 tests, all passing.
- Incumbent guard files re-run unchanged and passing:
  `test_github_pr_lifecycle`, `test_github_release_assessment`,
  `test_github_exact_edit`, `test_github_estate_governance`,
  `test_ci_pytest_policy`, `test_mastermind_plugin_packages`,
  `test_sol_capability_fabric_gh0`, `test_sol_capability_status`,
  `test_ceo_intent`, `test_executive_wake_fabric`,
  `test_executive_runtime_events`, `test_fabric_job_view`.
- Adversarial coverage: bad signature, duplicate delivery, changed head, actor
  without permission, fork prompt injection, stale review, publish retry.

Known environment gap, unrelated to this change: the `mcp` dev dependency is not
installed here, so `tests/workbench_*` and `tests/*/test_*.py` that import it
fail at collection.