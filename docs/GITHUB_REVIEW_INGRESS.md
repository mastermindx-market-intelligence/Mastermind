# GitHub independent-review ingress — decision core and adapter interfaces

Status: **DRAFT source slice.** Ships the decision core and the adapter
interfaces only. No transport, credential, webhook route, or reviewer identity
is bound here. This document is the operator contract for what a human admin
must do before any delivery can be admitted.

## What this slice is

| Module | Role |
| --- | --- |
| `control_plane/github_review_intent.py` | Pure decision core. HMAC verification, allowlist, intent channels, actor authority, fork refusal, untrusted-text fencing, admission identity, head freeze. No I/O, clock, network, subprocess, or filesystem. |
| `control_plane/github_review_intent_ingress.py` | Composition walk plus the adapter `Protocol`s and the concrete `ReconcilingReviewPublication` adapter. No HTTP client, queue, table, lifecycle, or credential. |
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
  model in `control_plane/executive_runtime.py` remains the only one. The
  publication adapter takes its `PublishedCommandIndex` by injection and creates
  no store.
- **No second verdict vocabulary.** The verdict set is borrowed verbatim from
  `plugins/mastermind-sol/skills/review-pull-request/SKILL.md`.
- **No second retry plane.** `PublicationEffectUnknown` is reconciled by reading
  GitHub, not by a queue, a scheduler, a backoff, or a persisted attempt log.

## Idempotency is the existing ledger's

There is no run registry, cache, or lock in this slice. The admission identity
is minted deterministically from `(repository, pull number, frozen head SHA)` —
and **not** from the intent channel — and shaped to be the existing
`events.command_id` UNIQUE index key
(`executive_runtime._COMMAND_ID_RE`, `^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`).

Consequences a host adapter inherits for free:

- an identical redelivery re-mints the same command id, so the UNIQUE index
  admits **exactly one** run;
- a moved head mints a **different** command id, so a stale review can never be
  mistaken for a current one;
- a reviewer requested, the label applied, and `/independent-review` commented
  in the same minute all collapse onto the same command id, so one exact head
  earns **one** review run rather than three separately billed Fabric reviews.
  One human intent expressed twice is not two independent reviews.

The identity namespace is domain-separated (`mastermind.github_review_intent.*`)
so it can never collide with the existing MCP / Slack / automated CEO-intent
families in `control_plane/ceo_request.py`.

### Explicitly authorized reruns

A distinct second review of the same head is reachable only through
`rerun_review_intent_id`, which requires an out-of-band authorization reference
(`rerun-<32..64 hex>`) **and** `policy.allow_explicit_rerun=True`. Reruns are off
by default and a requested rerun without policy authorization is refused
(`RERUN_NOT_AUTHORIZED`) rather than silently downgraded. Ordinary deliveries
have no route to this function at all.

## The pull request is the signed payload's

`admit_review_intent` takes **no pull-request number**. There is deliberately no
caller-supplied value to cross-bind against the signed one, so no route, tenant
id, database id, or operator input can aim a genuine delivery at the wrong pull
request.

The number is derived from the signature-verified body itself:

- `pull_request` — `number` must agree with `pull_request.number`, and the
  embedded pull request's `base.repo.full_name` must be the delivery's own
  repository.
- `issue_comment` — `issue.pull_request` must exist and its canonical GitHub API
  pull URL must name the same repository *and* the same number as `issue.number`.
  A slash command on a plain issue is refused with
  `PULL_REQUEST_IDENTITY_UNBOUND` before any read, ledger write, or
  reviewer-visible line.

The authoritative installation-scoped re-read must then match both the signed
repository and the signed number (`PULL_NUMBER_MISMATCH` otherwise). A correct
HMAC proves who signed the bytes; it never proves which pull request a wrong
caller route selected.

## The three intent channels

All three require an **allowlisted login**. Authority beyond the allowlist comes
from exactly one of two places, and from nothing else.

| Channel | Delivery | GitHub's own enforcement | Fresh read required? |
| --- | --- | --- | --- |
| Configured reviewer requested | `pull_request` / `review_requested` | Refused unless the actor holds triage/write at delivery time | No, unless `require_current_permission_for_all_channels` |
| Intent label | `pull_request` / `labeled` | Same | Same |
| Slash command comment | `issue_comment` / `created` | **None** — writable by anyone | **Yes** |

`issue_comment` is the open channel: GitHub's reported `author_association`
travels in the payload and is a **claim**, not authority. With no externally
reverified current permission the channel is refused with
`ACTOR_PERMISSION_NOT_REVERIFIED`. Bind `ActorPermissionPort` to a collaborator
permission read; a current permission of `none` (revoked) or below
`minimum_permission` (default `triage`) is refused with
`ACTOR_PERMISSION_INSUFFICIENT`.

Two relaxations exist, both explicit and both off by default:
`allow_static_actor_authority` falls back to the association ceiling when no read
is bound, and `require_current_permission_for_all_channels` extends the strict
posture to the two channels GitHub polices itself. The module never claims a
fresh permission check it did not perform.

The command matches the **first non-empty comment line exactly**. A comment that
merely mentions `/independent-review` never triggers a run.

## Fail-closed refusals

Every non-admitted decision names exactly one closed-vocabulary value. The
notable ones:

`SIGNATURE_INVALID`, `BODY_TOO_LARGE`, `EVENT_NOT_SUPPORTED`,
`ACTION_NOT_SUPPORTED`, `REPOSITORY_NOT_ALLOWLISTED`,
`INSTALLATION_NOT_ALLOWLISTED`, `REVIEW_REQUEST_FOR_OTHER_REVIEWER`,
`COMMAND_NOT_PRESENT`, `LABEL_NOT_PRESENT`, `ACTOR_NOT_AUTHORIZED`,
`ACTOR_ASSOCIATION_INSUFFICIENT`, `ACTOR_PERMISSION_NOT_REVERIFIED`,
`ACTOR_PERMISSION_INSUFFICIENT`, `PULL_REQUEST_IDENTITY_UNBOUND`,
`PULL_NUMBER_MISMATCH`, `PULL_REQUEST_NOT_OPEN`, `PULL_REQUEST_DRAFT`,
`HEAD_REPOSITORY_MISMATCH`, `HEAD_SHA_MALFORMED`,
`UNTRUSTED_CONTENT_DETECTED`, `ALREADY_ADMITTED`, `RERUN_NOT_AUTHORIZED`,
`HEAD_MOVED`.

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

**Freshness at the effect.** `publish_verified_review` performs its own
installation-scoped read of the pull request immediately before the review POST.
It takes no caller snapshot, because the whole question is what the head is
*now*: a snapshot cannot answer that, and a snapshot that happens to be current
is a coincidence. A moved head is refused with `HEAD_MOVED`; a read that answers
about a different pull request is refused with `PULL_NUMBER_MISMATCH`.

**An uncertain POST is reconciled, never retried blind.** When an adapter cannot
observe its own review POST it raises `PublicationEffectUnknown`.
`ReconcilingReviewPublication` then reconciles by reading the reviews already
present at the exact commit, verb, and byte-identical body. A positive match
returns the real review id; an unmatched effect is re-raised and reported as
`PUBLICATION_EFFECT_UNKNOWN`. No path turns an unknown effect into a second
formal review.

**No unfenced auto-approval.** `PASS` maps to a GitHub `COMMENT`, never
`APPROVE`. This slice mints no approval verb and no merge path at all, and
`ReconcilingReviewPublication` refuses any verb outside
`ALLOWED_REVIEW_EVENTS` before it can reach a socket.

**Separate worker.** Publication refuses a result whose reviewer is the builder
(`REVIEW_NOT_INDEPENDENT`) or whose reviewer identity is unknown
(`REVIEWER_IDENTITY_UNKNOWN`). The reviewer must come from the Fabric's own
worker identities, resolved by `Runtime.validated_role_completion` and
`control_plane/fabric_result_projection`.

**Publish retry.** Publication carries its own deterministic command id bound to
job and frozen head, so a retry reconciles to `ALREADY_PUBLISHED` instead of
posting a second formal review.

**Visibility is non-gating and opaque.** A Slack failure is recorded on the
outcome, never raised, and never causes a second admission. It collapses to the
single fixed code `VISIBILITY_TRANSPORT_UNAVAILABLE`: transport exception text
routinely embeds the workspace id, channel id, message id, API URL, and
occasionally a token fragment, and `ReviewIngressOutcome` structurally refuses to
construct with any other value.

## Adapter interfaces to bind

| Port | Binds to |
| --- | --- |
| `PullRequestReadPort` | A GitHub App installation token minted from the configured app, then `GET /repos/{repo}/pulls/{n}` |
| `ActorPermissionPort` | The authenticated collaborator permission read; GitHub's own vocabulary (`none`/`read`/`triage`/`write`/`maintain`/`admin`) or `None` |
| `FabricJobAdmissionPort` | `executive_runtime` Job registry — `create_job(..., command_id=decision.command_id)`; `admitted_command_ids()` reads the same index back |
| `VisibilityPort` | The existing Slack Web API client in `integrations/slack_agent_dialogue/slack_web_api.py` |
| `ReviewResultPort` | `Runtime.validated_role_completion` + `fabric_result_projection.project_fabric_role_result`, returning a result only when the projected receipt state is `SAME` |
| `ReviewPublicationPort` | `ReconcilingReviewPublication`, bound to a `ReviewTransportPort` (`POST`/`GET /repos/{repo}/pulls/{n}/reviews`) and a `PublishedCommandIndex` |
| `PublishedCommandIndex` | The host's existing durable record of published command ids — injected, never created here |

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
may request a review; anyone else is refused with `ACTOR_NOT_AUTHORIZED`, and
that check is static, so an un-allowlisted login never reaches an authenticated
read. Leave `allow_static_actor_authority` and `allow_explicit_rerun` at their
default `False`.

**Slack**

6. Grant the existing Slack app `chat:write` for the target channel. Reuse the
   existing dialogue client and its token; do not mint a second Slack
   credential.

**Runtime arming**

7. Bind the ports in the host that already owns the credentials. Until that
   happens an unbound port is a typed refusal — and an unbound
   `ActorPermissionPort` refuses the open comment channel by name rather than
   admitting it on a payload claim.
8. Decide the ingress route's exposure and rate limit. This slice ships no HTTP
   route, so there is nothing to expose yet.

## Verification performed

- `python3 -m pytest tests/test_github_review_intent.py tests/test_github_review_intent_ingress.py`
  — 155 tests, all passing.
- Incumbent guard files re-run unchanged and passing (866 tests):
  `test_github_pr_lifecycle`, `test_github_release_assessment`,
  `test_github_exact_edit`, `test_github_estate_governance`,
  `test_ci_pytest_policy`, `test_mastermind_plugin_packages`,
  `test_sol_capability_fabric_gh0`, `test_sol_capability_status`,
  `test_ceo_intent`, `test_executive_wake_fabric`,
  `test_executive_runtime_events`, `test_fabric_job_view`.
- Adversarial coverage: bad signature, tampered body, duplicate delivery,
  changed head, actor without permission, revoked/downgraded actor, fork prompt
  injection, stale review, publish retry, lost review POST.

### What these tests do *not* prove

Every port above is exercised through a fake. There is still no concrete
webhook HTTP listener, authenticated GitHub client, Executive/Fabric job
adapter, result bridge, Slack producer, host secret/route binding, or live
review readback. **The integration has not been called live or end to end, and
a green fixture run is not live acceptance.** Qualifying the host, the App
installation, the webhook secret, and the Slack permission remains the separate
human-admin ceremony above.

## Known gaps, unrelated to this change

The `mcp` dev dependency is not installed here, so `tests/workbench_*` and
`tests/*/test_*.py` that import it fail at collection.