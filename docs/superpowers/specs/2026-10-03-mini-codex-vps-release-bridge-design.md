# Mini Codex → bounded VPS release bridge

**Date:** 2026-10-03
**Status:** source candidate; production-inert until reviewed, merged, installed, and canary-proven.

## Outcome

Mini-hosted Codex sessions can request one exact current-`origin/master` Mastermind production
deployment without possessing the VPS root key and without this bridge granting an arbitrary shell
on the M2 release host. The existing GitHub release law and transactional VPS deploy script remain canonical.
Executive OS gains only one subordinate fixed-action actuator and its existing receipt/effect fence.
Technical availability of that actuator is not standing organizational permission to deploy: every
future invocation still requires the current release authority, exact-candidate review/CI gates and
effect reconciliation that would apply to the incumbent release executor.

This amendment is intentionally narrower than granting direct SSH. The production VPS credential
remains machine-local on M2 Studio. The bridge uses only a dedicated M2 relay identity whose
`authorized_keys` entry forces a closed relay command.

## Existing-owner map

- GitHub owns source, PR/CI/review evidence and the exact current `origin/master` commit.
- `scripts/deploy_code_to_vps.sh` remains the transactional deployment executor.
- The existing Executive privileged-action broker owns effect admission, in-flight markers,
  terminal receipts, replay refusal and `EFFECT_UNKNOWN`.
- SSH is transport only. It creates no Job, release, retry, queue or authority plane.
- The M2-local VPS key remains a host credential and never enters prompts, Git, Agent OS or minis.
## Closed effect

Add exactly one privileged action:

`executive.vps.deploy_mastermind {commit_sha: <40 lowercase hex>}`

The caller cannot select host, username, key, destination path, executable, service, health URL,
Git remote or branch. The privileged broker maps the request to the installed release's
`ops/executive_os/deploy-mastermind-vps.sh`.

The wrapper:

1. requires root broker identity and one exact commit argument;
2. fixes the Mastermind GitHub remote, `master` branch and M2 source-repository path;
3. performs GitHub authentication only under the attended M2 owner's existing Git credential context,
   with prompting disabled and hooks suppressed; no Git credential is exposed to the mini or caller;
4. requires the request SHA to equal current remote `master`, then refetches and rechecks it
   immediately before the production-effect boundary;
5. materializes a clean archive from that exact fetched commit in a private temporary directory;
6. requires the target archive's `scripts/deploy_code_to_vps.sh` to be byte-identical to the
   installed trusted Executive release copy before production effect;
7. uses the M2-local VPS key plus strict known-host verification;
8. invokes the existing deploy transaction with fixed production coordinates;
9. independently verifies the final production marker and health;
10. maps an unprovable final state to exit 75 so the privileged broker preserves `EFFECT_UNKNOWN`.

A changed deployment implementation therefore cannot bootstrap itself merely because it landed on
GitHub. The trusted Executive release must first be updated through its own existing release gates.
## Mini transport

Each mini receives a dedicated Ed25519 key named `~/.ssh/m2_release`. That key is not the existing
recovery identity and is not a VPS credential. On M2 its public key is installed with:

`restrict,command="'/Library/Application Support/MastermindExecutive/bin/mmx-vps-release-relay' miniN"`

The forced label is part of the server-side key grant. The relay accepts only:

- `preflight`
- `status <request-id>`
- `deploy <40-hex-sha> <request-id>`

Status and deploy request IDs must begin with the forced mini label (for example
`mini4-release-20261003-001`), preventing one mini key from querying or replaying another mini's
release receipts. It invokes the stable root-owned `mmx-admin` client, which in turn reaches the existing local
privileged broker socket. It never executes `SSH_ORIGINAL_COMMAND` as shell text.

The mini client derives and validates its local `miniN` label, requires request IDs with that
prefix, and uses `ssh -F /dev/null`, a fixed `chriswong@m2studio` target, the dedicated key,
`IdentitiesOnly=yes`, strict host-key checking, no TTY and all forwarding disabled. Ignoring the
user SSH config prevents a broad recovery identity from being offered accidentally. Activation
requires an already-pinned `m2studio` entry in that mini's owner-controlled `known_hosts`; the
client installer verifies that condition without fetching or trusting a host key itself.

## One-time key ceremony

Credential generation and authorization remain an explicit host ceremony, separate from source
merge. For each mini:

1. verify the attended owner-controlled `m2studio` host key is already pinned in
   `~/.ssh/known_hosts` on the mini;
2. generate a fresh Ed25519 key at `~/.ssh/m2_release` with mode 0600;
3. copy only its public key to the attended M2 operator;
4. inspect `scripts/render_mini_vps_release_authorized_key.py --public-key-file ... --label miniN`;
5. on attended M2, run
   `scripts/install_mini_vps_release_authorized_key.py --public-key-file ... --label miniN`;
   it appends only the exact rendered `restrict,command="'...' miniN"` entry and refuses label rebinding;
6. install the mini client with `scripts/install_mini_vps_release_client.py --require-key`;
7. run `mmx-vps-release preflight` and record the exact host/key/install identities.
No private key is copied between machines. Reusing `m2_recovery` as the release credential is
prohibited because an already-broad authorized-key entry would defeat the forced-command boundary.
The current mini fleet already has a broader historical M2 recovery identity for other workflows;
this bridge does not claim to revoke or sandbox that separate credential. Migrating/removing that
legacy authority is a separate operation and is required before claiming that mini-hosted Codex has
no arbitrary M2 shell path at all.

## Acceptance

Source tests must prove:

- request schema and argv are closed;
- deployment SHA is exact lowercase 40-hex and current remote master;
- broker trust covers both the wrapper and transactional deploy implementation;
- exit 75 preserves effect uncertainty and replay remains receipt-owned;
- the mini client ignores SSH config and disables forwarding;
- the forced relay cannot execute arbitrary commands;
- the authorized-key renderer always emits `restrict,command=...`;
- known-host pinning is supported by the existing transactional deploy script.

Production acceptance additionally requires a fresh installed Executive release on M2, one dedicated
mini relay key, a read-only preflight, then one already-authorized real deployment of the exact merged
current master SHA with broker receipt plus VPS health/commit readback. A merge, installer run,
preflight or broker receipt alone is not production acceptance.

## Rollback and revocation

Revoke one mini by removing only its dedicated public-key line from M2 `authorized_keys` and
deleting that mini's `~/.ssh/m2_release` key. This does not touch the VPS credential or another
mini. Disable the privileged action by installing an Executive release without the catalog entry or
by leaving the privileged broker unarmed; do not create a second kill switch.

If a deployment request becomes `EFFECT_UNKNOWN`, preserve its request id and reconcile with
`mmx-vps-release status --request-id ...`. Never send a new deploy request merely because the
client stream ended.
