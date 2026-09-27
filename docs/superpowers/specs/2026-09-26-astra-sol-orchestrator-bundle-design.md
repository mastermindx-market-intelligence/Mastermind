# Astra/Sol orchestrator delivery: bounded first slice

Operation: `astra-sol-orchestrator-bundle-20260926-sol-001`.
Parent: Mastermind #981 at `aaa7b350fb379d1aa54dcc016dc6d75634d65468`, stacked on #633.
Protected procedure: `4c6b206d3fb7fbc6d077faf61ae361bedf259925`, Skillpack v1.0.1.
Authority: current Chairman request to make Astra/Sol orchestration real and implement it.
Status: source candidate; production activation and recursive worker dispatch remain held.

## User outcome

An Astra principal can delegate a bounded coordination responsibility to Sol or Astra;
that coordinator ultimately leads separately admitted workers and returns compact evidence.
Routine implementation must not consume the principal by default. Model, organizational
responsibility, host, permission, and provider conversation remain separate identities.

## Reconciled baseline

#981 already implements one nonrecursive native Sol coordinator. Its exact-head independent
review request is outstanding. #633 already implements substantial client source and has an
unresolved historical DCR effect. #1000 is a separate no-login bootstrap. None is missing
merely because it is not on master. Preserve their source, review and effect carriers.
The installed attended profile still disables agents. The protected native-helper adapter
and COO policy enforce depth one; a native Codex recursion feature is not permission to
weaken those gates. Existing external pool capacity counts do not prove Executive admission.

## Approach and rejected alternatives

Extend #981 with an optional, complete client bundle and an Astra coordinator counterpart.
A single native coordinator slot remains the initial ceiling. Native descendants remain off
inside both coordinator roles. Actual worker Jobs must use existing Executive admission,
Capacity, custody, budget, review and exact-parent return. This first slice installs no
new lifecycle, scheduler, permission store, worker-spawn endpoint, or credential route.

Rejected: globally enabling agents and increasing thread/depth limits, because that would
outrun the current adapter. Rejected: a second local supervisor/queue, because Executive
already owns that concern. Rejected: reusing an inherited MCP token as proof the native
child has a separate Executive responsibility. It does not.

## First implementation contract

1. Add optional `mastermind-orchestrators.config.toml`: Astra/high; read-only parent;
   one native coordinator slot; named Sol and Astra roles; explicit principal duties.
2. Reuse #981's Sol role bytes unchanged. Add an Astra role with the same nonrecursive
   capability boundary and concentrated-judgment responsibility.
3. Add a standard-library bundle inspector/installer. The concrete consumers are Codex's
   named-profile loader and standalone `$CODEX_HOME/agents` discovery.
4. Inspection is default and performs no writes, subprocess, login, credential access,
   server call, or provider turn. Installation requires explicit `--install` and the
   inspected bundle digest, preventing a different source bundle being installed silently.
5. All source files are captured once as immutable bytes before inspection or installation.
   Refuse symlinked/nonregular files, missing roles, malformed TOML, wrong model/role,
   recursive role configuration, a non-read-only parent, and conflicting destination bytes.
6. Preserve `config.toml`, `mastermind-astra.config.toml`, unrelated roles and all auth state.
   Install role files first and the optional profile last. Never overwrite or delete an
   existing target; use atomic no-clobber publication. A partial failure preserves exact
   completed writes and yields a typed partial-install error; inspect before any new action.
7. A successful file readback proves only installation. It does not prove role selection,
   child capability enforcement, served model, RuntimeBinding, worker dispatch or acceptance.
   No installer path launches a model or authorizes production.

## Effective configuration precedence

The installed 0.154.0 parser proved that trusted project `.codex/config.toml` can
override named-profile settings: this profile alone yielded four active slots
including the parent, not the intended two. The bundle therefore provides
`configuration_overrides(codex_home, expected_bundle_digest=...)` and a read-only
`--configuration-overrides` CLI. They require exact complete installed/source
readback and emit explicit command-line configuration values for all parent
settings and absolute role paths. The native regression proves two slots under
both empty and trusted-project conditions. This output is not a launcher or an
admission receipt. The existing launch owner must apply it and revalidate at the
actual execution boundary. Generic native roles are not proven inaccessible;
role selection and descendant authority remain R2 proof obligations.

## Permission caveat

A role's read-only TOML is not an absolute security boundary: native Codex reapplies live
parent permission overrides to spawned children. Therefore the optional parent is also
read-only, and operational qualification must observe the actual parent/child permission
state. Do not launch with a broader permission override and claim the role is confined.
MCP permissions are independent of the filesystem sandbox. Explicit child admission and
trusted child identity are still required before a coordinator may submit worker work.

## Ordered remaining slices

R1: this complete two-role bundle, deterministic install/readback and native parse proof.
R2: current-owner proof of exact child role/model/permissions and child-specific Executive
identity; consume #1000 without bypassing #633's unresolved DCR operation.
R3: one admitted Sol coordinator to two read-only worker Jobs; independent review and
compact return consumed by the exact Astra parent. Count review/repair reservations.
R4: qualified Astra coordinator counterpart and multi-coordinator scheduling under the
existing budget/depth/Capacity owner. Expand native recursion only with an explicit
reviewed grant and native enforcement proof; a prompt prohibition is insufficient.

## Completion and durability

R1 source tests and a credentialless native parser probe are necessary, not production
acceptance. Keep the source Draft and production off pending current-base CI/review and
the separate R2/R3 receipts. Preserve #981's sole reviewer; do not spawn a second reviewer
for its frozen candidate. This child owns only its new bundle files.

## R2A: compose the existing attended launcher

Consume #1000 exact f0ab0bec981a12e58069c98404289d4402face96 by a source merge
into this same #1013 carrier; neither dependency branch nor its reviewer is changed.
This is candidate integration, not release acceptance. No second launcher is created.
The merged baseline fails 12 bootstrap cases: #981 enables the named Sol role while
#1000 only understands the older disabled profile. The default bootstrap must remain
native-disabled; it can consume either reviewed profile shape and explicitly project
agents.enabled=false. Unknown shapes, integer booleans and extra role entries refuse.
The optional coordinator mode uses one --orchestrator-bundle-digest argument. Its
source is the existing bundle compiler, and its destination is the actual effective
CODEX_HOME (or standard user default), never a separately chosen credential home.
Require complete installed bytes, exact digest and both role files before census.
Use explicit compiler settings plus the existing required five-tool MCP settings.
Unsupported auth remains a prepared-but-held result. Preflight invokes only existing
local list/get census, never an installer, auth helper or model. It reports role/model,
child permissions and worker authority as unproven; config is not runtime admission.
Immediately before any explicit attended exec, revalidate source/helper digests,
compiled settings and exact effective home. Changed/missing/rebound inputs refuse
without exec, login or retry. Preserve the existing enrollment and DCR effect gates.
Two-layer native configuration proof remains credentialless and does not qualify
role selection, children, permission enforcement or served-model identity.

R2A native findings: current 0.154.0 metadata reports unknown for the credentialless
fixture, so both unknown and unsupported produce the existing held preparation.
No new authenticated state or enrollment is inferred. Native prompt rendering also
initializes enabled MCPs; the real helper must not be used for configuration proof.
Tests pin required-server refusal with an inert helper, then parent-only rendering
with the fixture MCP disabled. Exact parent/child execution proof remains held.
Filesystem identity of the effective native home joins the local launch plan: path
and identical role bytes alone do not detect replacement of its credential directory.
These observations are transient launch inputs, not another session/auth registry.

## R2B native falsifier and corrected enforcement claim

The declared nonrecursive role setting is a request, not observed enforcement.
The installed 0.154.0 native runner selects both named coordinator roles and their
requested models correctly, and its read-only sandbox denies a real attempted child
project write. However, child spawn_agent remains exposed with role-local
agents.enabled=false. With one global child slot, the native runner refuses a
grandchild for capacity; with two isolated test slots, it creates a grandchild even
when agents.max_depth=1. This supersedes any interpretation above that the role flag
alone confines recursion. The candidate keeps its single-child limit unchanged.

Use the existing OHF client and a test-only scripted loopback response stream to
reproduce those observations without accounts or real model inference. Native child
completion reaches the exact parent's next request. This is harness qualification,
not a new worker authority or a production served-model receipt. Broader concurrency
needs an existing-owner capability solution that demonstrably bounds the full tree;
it cannot be obtained by simply editing these TOML limits. Worker admission and
child-specific Executive identity remain outstanding.
