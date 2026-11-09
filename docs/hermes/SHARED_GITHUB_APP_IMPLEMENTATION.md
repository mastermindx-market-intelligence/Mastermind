# Hermes GitHub App — seatless shared authoring integration

**Operation:** `hermes-github-app-20261108-sol-01`. **Base:** `master@1f55ea59961842f2600be9bf28777b7bea69b678`. **State:** source implementation in progress; not a live App enrollment or permission grant.

## User outcome and original DONE_WHEN

Every authorized Hermes bot can read its allowed repository, create source branches/commits/PRs, and comment on original issues or PRs as an organization-owned GitHub App bot, without paying for a separate GitHub machine-user seat per bot. The existing canonical GitHub/source, Executive, Agent OS and native Hermes session owners remain authoritative. The shared App actor must not erase actual role/session/operation provenance or manufacture independent author approvals.

**DONE_WHEN:** one installed, least-privileged app per appropriate authoring trust domain; existing Hermes role sessions authenticated through host-owned short-lived installation tokens; authorized exact bot performs branch -> source commit -> PR -> comment in a controlled repository with server-side role/operation and GitHub actor receipts; unauthorized role/repository/path/branch, stale SHA, duplicate action and uncertain response refused/reconciled; no separate paid machine-user seats needed for the migrated automation; legacy auth and relevant holds remain intact until real-path proof.

## Scope, lanes, dependencies

- **P1 source** — adapt existing review-App issuer without broadening its old defaults, or add a safely isolated authoring binding; keep credentials in existing host custodian and never send them to a model or GitHub comments.
- **P2 producer/consumer** — bounded GitHub App REST authoring adapter and single native Hermes tool registered through incumbent profile/session owner. Binds repo, branch, principal, operation and grant on the host; never accept model-selected installation ID, repository, token, remote URL or account.
- **P3 automated proof** — mock installation JWT/API tests for scope, provenance, optimistic head/file checks, response bounds, unknown POST effect, collisions, revocation, no replay and legacy reviewer regression. Hosted PR CI on immutable head.
- **P4 owner installation** — GitHub organization administrator confirms whether installation `152874959` is a separate connector/reviewer App; enrolls the intended authoring App (Contents read/write, PR read/write, Issues read/write, Metadata read; no Admin permission), select repositories only, host-side sealed key/installation binding, native plugin registration under already-authenticated roles.
- **P5 live consumer** — distinct Hermes sessions author and comment via the App and record GitHub readback, negative tests and audit attribution. Then audit/revoke only redundant *machine* memberships, with human seats untouched.

## Held boundaries

No direct protected-master writes, review self-approval, bypass of CODEOWNERS/CI/merge queue, new token vault, GitHub polling daemon, separate lifecycle or role registry, unknown-effect replay, administrative installation through unqualified credentials, or paid seat removal without provenance. Existing independent-review App path and its read-only Contents grant remain unchanged by default.

## Current source observations

- `integrations/github_review_app_token.py` already creates per-repository installation tokens from host-injected private key, but hardcodes `contents:read` / `pull_requests:write`.
- `integrations/hermes_leadership/native.py` demonstrates existing native registration scope and revocation, and `integrations/hermes_harness/native_tool_registration.py` controls selected-child registration.
- Organization installation `152874959` exists; its actual App ownership, available authoring permission and operational Hermes use were *not* established. Do not reinterpret the ChatGPT connector installation as the Hermes authoring App.
- The M2 Studio route preflight refused the previous read-only exact-host probe; no host-side auth/installed plugin claim is available from that route. GitHub-native isolated branch is an independently authorized source carrier, not a host-access fallback.

## Recovery

Primary source: `mastermindx-market-intelligence/Mastermind` PR on branch `sol/hermes-github-app-20261108-sol-01`. Preserve any effects and head SHA before continued source work; inspect current PR/files and GitHub app installation before operator enrollment. Next: implement narrowly scoped host-bound native/API code and tests; publish Ready only after complete source self-check; obey protected release workflow. This document is an editorial plan, not an Executive Job, an App installation or completed consumer proof.
