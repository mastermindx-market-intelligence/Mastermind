# Seatless Hermes GitHub App — host enrollment and proof

**State:** GitHub-native source implementation and mock GitHub API qualification only. NOT installed in Hermes; NOT proof of an organization-owned app; NOT permission to disable or remove GitHub accounts. Parent outcome and phases: [SHARED_GITHUB_APP_IMPLEMENTATION.md](SHARED_GITHUB_APP_IMPLEMENTATION.md).

## Supported design

GitHub identifies every installation-token action as the App's bot, not as a
separately licensed machine user. Many **separately authenticated Hermes
sessions** can use one GitHub App installation, with per-repository short-lived
tokens minted by the existing host credential custodian. Mastermind retains the
real role, operation, session digest and exact branch in GitHub commit
messages, PR bodies and comments. The original role/session/operation identity
is host-derived, not model-selected.

The implementation reuses `integrations.github_review_app_token` and its
bounded response decoder. Existing reviewers' `contents:read` /
`pull_requests:write` token profile is the unchanged default; **authoring**
selects the separately enrolled `AUTHORING_PERMISSIONS` constant. Do **not**
reuse a review installation as an authoring App merely because both share this
issuer code. `HermesGitHubApp` makes only fixed GitHub REST calls:
status, create exact bound branch, write one allowlisted file through
Git-data/fast-forward source CAS, create an original branch PR, and comment
on host-granted issues or that PR. Model tool args contain no repo/remote,
credential, GitHub identity, installation, role, or principal.

## One administrator-only enrollment

1. Confirm existing organization installation `152874959`'s App identity,
   permissions, current consumer and purpose; it was **not** verified to be a
   Hermes authoring installation.
2. In the `mastermindx-market-intelligence` organization, create a
   **private organization-owned GitHub App** named e.g.
   `mastermind-hermes-author` (unless an existing separately approved
   authoring App already satisfies these exact grants).
3. Request repository permissions **Contents: Read and write**, **Pull
   requests: Read and write**, **Issues: Read and write** and GitHub's
   mandatory Metadata read. No Organization administration, Actions write,
   checks write, workflow bypass, contents delete-a-repository, or user
   authentication scopes. No webhook events are required for the outbound-only
   authoring adapter.
4. Install on **Only select repositories**. Start with the Mastermind canary
   repository and expand only to each verified required repo after a canary.
   Keep reviewer App scope and human-review enforcement separate.
5. Place the App private key solely in the existing approved sealed **host
   credential custodian**, not in `SOUL.md`, `AGENTS.md`, a commit, model
   prompt, GitHub Actions logs, Slack, a long-lived PAT or interactive bot shell.
   Bind the numeric App ID, actual installation ID and one fixed repository to
   its existing trusted host composition. No GitHub App or key is generated or
   installed by merely merging this source.
6. Keep token lifetime under GitHub's one-hour expiration; the issuer already
   caches a repository-scoped token for at most 30 minutes and verifies the
   exact response grants and one repository before returning it to the private
   HTTP client. The model never receives token bytes.

The organization admin performs these settings under its authenticated GitHub
UI. The installed GitHub connector in ChatGPT is not that App by implication.

## Native Hermes host composition

The existing host/profile/session owner creates and retains **one**
`HostGitHubSession` per authorized original operation. No separate session
registry, login manager, queue, credential store, or source lease is installed.

```python
from integrations.github_review_app_token import (
    AUTHORING_PERMISSIONS, GitHubAppInstallationTokens,
)
from integrations.hermes_github_app import HostGitHubSession, HermesGitHubApp
from integrations.hermes_github_native import (
    HostHermesGitHubBinding, register_native_tool,
)

# These values and callables MUST be supplied by the installed incumbent
# host/source/secret owners. They are deliberately not environment discovery.
issuer = GitHubAppInstallationTokens(
    app_id=installed_app_id,
    installation_id=installed_installation_id,
    repository=existing_source_grant.repository,
    private_key_source=existing_secret_custodian.read_private_key_bytes,
    permissions=AUTHORING_PERMISSIONS,
)

def resolve_existing_session(session_id):
    grant = existing_native_owner.current_github_source_grant(session_id)
    if grant is None or not grant.is_current():
        return None
    # Existing native session owns retained_client and exact-custody binding.
    # Do not re-create the client on each lookup or accept model-supplied fields.
    return grant.retained_client

binding = HostHermesGitHubBinding(
    profile_id=actual_native_profile,
    resolve_client=resolve_existing_session,
    currentness_guard=existing_native_owner.profile_grant_current,
)
lease = register_native_tool(
    actual_native_plugin_context, binding, profile_id=actual_native_profile,
)
# The original Hermes native plugin owner retains lease and calls dispose()
# on qualified unload. Register once; collisions/uncertain registration stop.
```

`grant.retained_client` above is the host-retained
`HermesGitHubApp(HostGitHubSession(...))`. Its `HostGitHubSession` fields are
source-bound: exact original `profile_id`, `role`, `session_id`,
`operation_id`, repository, new `hermes/<operation>` branch, accepted
`master`/ `main` base SHA, numeric installation, allowed path prefixes,
allowed issue numbers and currentness guard. Nonexistent
`existing_native_owner` names in this example are an explicit **integration
point** to the original installed owner, not a claim of a new production API.

### Native tool requests

The installed `mmx_github` tool has a closed surface:

- `{"action":"status"}` reads the exact bound branch state.
- `{"action":"branch_create"}` creates `hermes/<operation>` only at the
  exact source-bound base SHA, or reports existing exact-base branch.
- `{"action":"file_commit","expected_head":"<40-hex>","path":"allowed/file.py","content":"...","message":"..."}` creates a one-file commit with a server-checked expected head, non-force fast-forward and GitHub-visible audit trailer.
- `{"action":"pr_create","expected_head":"<40-hex>","title":"...","body":"..."}` opens or finds the bound branch PR and adds the server-originated audit marker.
- `{"action":"comment_create","issue_number":123,"request_id":"stable-original-action","body":"..."}` posts to an explicitly host-authorized issue or a matching PR from the operation, with an exact source-linked comment marker. `comment_find` queries the original issue and marker without posting.

Never blindly repeat an `EFFECT_UNKNOWN` write. Use the original GitHub
branch/PR/comment readback; if evidence cannot settle the effect, keep it held
on its original operation and carrier. An empty `comment_find` under a
bounded read is **not** permission to replay an uncertain POST without
existing source/effect owner reconciliation. Concurrent same-request sends
across hosts require the existing Executive/source custody and single-writer
fence, not a new GitHub bot registry.

### First installed canary (after administrator enrollment)

1. In one authorized Hermes engineering session, read `status` and verify
   profile, repo, branch and selected source grant.
2. Create the bound branch from exact fresh base; then commit a harmless file
   under a dedicated authorized documentation test prefix.
3. Create a Ready PR on `master`; verify GitHub reports the author's actual
   `<app-slug>[bot]` identity, the original `Hermes-Role`/operation
   provenance, and matching branch/head. Confirm PR release requirements
   remain enforced.
4. Post one uniquely keyed source-linked PR comment. Read it back by comment
   ID, compare exact marker, confirm no duplicate.
5. Independently exercise rejected path traversal, wrong session, stale head,
   unauthorized repo/issue, revoked grant and interrupted POST with no blind
   replay. Verify real token expiry/re-mint and non-disclosure on failure.
6. Repeat with another *different* authorized Hermes profile using the same
   App installation but distinct original session/operation; verify two
   audit identities and the same App bot identity on GitHub.
7. Verify rollback (native lease dispose, token/key revocation and existing
   user credentials retained). Only then inventory organization billing and
   human/machine accounts. Remove an actual paid machine seat **only** after
   its observed GitHub use has been migrated, its outstanding operations have
   been reconciled, and an owner authorizes removal. Never delete human
   collaborators or a still-used automation identity.

## Source acceptance vs production acceptance

Tests: `tests/test_github_review_app_token.py` (legacy issuer) and
`tests/test_hermes_github_app.py` (host-authenticated API fixture, source
head fencing, duplicate comment, revocation and native session mismatch).
The tests use synthetic tokens/mock HTTP, not a registered App or real bot.
Production remains **BUILT_NOT_PROVEN** until a real installed Hermes native
session returns the GitHub App-authored branch/commit/PR/comment canary and
retains original Executive/source identity. Protected PR merge, separate
App administrator enrollment and host deployment require their actual
existing owners and receipts.

Official GitHub behavior:
- https://docs.github.com/en/apps/creating-github-apps/about-creating-github-apps/deciding-when-to-build-a-github-app
- https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-an-installation-access-token-for-a-github-app
