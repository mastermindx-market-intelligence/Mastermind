# OpenAI Secure MCP Tunnel credential capability — P1 feasibility receipt

Status: **GROUNDED_INTERFACE / SPEC_ONLY / PRODUCTION_INERT**  
Parent architecture: `research/CROSS_HOST_CREDENTIAL_CAPABILITY_ARCHITECTURE_2026-09-14.md`  
P0 census: `research/CROSS_HOST_CREDENTIAL_CENSUS_P0_2026-09-14.md`  
Protected base: `bffe2ca8506346ea278c8ee469bf1ac30a4de008`  
Date: 2026-09-14

## Mission

Ground the first independently useful credential capability against the actual OpenAI tunnel client installed on Mac Studio, without reading an admin key, listing/creating/updating/deleting any tunnel, changing a workspace association, or assuming undocumented command semantics.

This receipt answers one key uncertainty from the architecture pass: there **is** an installed native administrative surface for Secure MCP Tunnel metadata/CRUD, so P1 does not need to reverse-engineer a browser request or invent a generic OpenAI HTTP client.

## Installed client evidence

Observed on the actual Studio host:

```text
PATH launcher: /opt/homebrew/bin/tunnel-client
version: 0.0.14+0f870e50a973fa820d4c409000059e181e8d242b
Cellar launcher: /opt/homebrew/Cellar/tunnel-client/0.0.14/bin/tunnel-client
launcher sha256: 1f46f04ff45caa052903c63f6f652f549d4182ce9bfa3dcc2577c8098e3117d6
native executable: /opt/homebrew/Cellar/tunnel-client/0.0.14/libexec/tunnel-client
native executable sha256: 309fd85da5a8c2ca8dae920deea8ac10a4d7934ed18ac46e7df0c200139cc9c5
native executable: Mach-O arm64
```

The Homebrew `bin/tunnel-client` is an 88-byte fixed shell launcher that `exec`s the libexec binary with the same arguments. A production adapter should pin the exact installed release/native executable rather than trust ambient PATH.

No credential was supplied to obtain this evidence; only `--version`, `--help`, file metadata and hashes were read.

## Native tunnel administration contract observed

`tunnel-client admin tunnels --help` declares these subcommands:

```text
get
list
create
update
delete
```

The installed help states:

- `get <tunnel_id>` is read-only metadata lookup and may use either a runtime control-plane key or an admin key;
- `list`, `create`, `update`, `delete` require a real admin key from `OPENAI_ADMIN_KEY` or `--admin-key`;
- admin CRUD uses explicit organization/workspace/tenant scope where applicable;
- default control-plane base URL is `https://api.openai.com`;
- caller can request JSON output.

This is stronger evidence than the earlier assumption that an admin key might be usable: the exact currently installed OpenAI client advertises the needed capability surface.

## Exact command semantics relevant to P1

### List

`admin tunnels list` requires a real admin API key and **exactly one explicit scope filter**. Supported filters include organization ID(s), workspace ID(s), or tenant ID.

Implication: the agent must never guess which Business/Astra workspace is intended. The owner-selected scope becomes part of the prepared action/binding.

### Get

`admin tunnels get <tunnel_id>` is read-only. Its help explicitly recommends using JSON metadata from the known tunnel to recover live `organization_ids` / `workspace_ids` rather than guessing those values for later admin CRUD.

Implication: reconciliation should prefer exact known tunnel metadata when a tunnel identity already exists.

### Create

`admin tunnels create` requires:

- real admin key;
- name;
- description;
- at least one organization or workspace ID.

The installed help says to allow approximately 25–30 seconds after successful creation before expecting the tunnel to be active/ready.

Implication: `CREATE_APPLIED` and `TUNNEL_READY` are separate observations. P1 must not call creation failure merely because readiness is not immediate.

### Update

`admin tunnels update <tunnel_id>` has PUT-like replacement semantics for organization/workspace lists when those flags are provided; omission keeps existing edges.

Implication: P1 must never construct an update by supplying only the one desired workspace while assuming other associations survive. A modifying update must start from a fresh exact metadata preimage and make replacement intent explicit.

### Delete

`admin tunnels delete <tunnel_id>` requires a real admin key and an explicit `--confirm` flag.

P1 does not need delete for the motivating autonomy capability. Keep deletion out of the initial Web-facing contract.

## Admin-key authority does not equal Mastermind authority

OpenAI's public Admin API documentation separately confirms that Admin API keys are elevated organization-owner credentials used for programmatic organization administration and should be handled carefully.

The existence of an `OPENAI_ADMIN_KEY` therefore proves only that the native client *could* make an administrative request. It does not authorize a Mastermind agent to create/update a tunnel.

P1 remains:

```text
current Chairman/Executive authority
 -> exact admitted capability/action
 -> exact host/runtime binding
 -> fixed secret custody
 -> pinned tunnel-client executable
 -> exact owner-selected org/workspace/tunnel coordinates
 -> native OpenAI effect
 -> existing effect/reconciliation owner
```

No raw-key getter is added.

## Hardened P1 tool surface

The initial Web/worker capability should be narrower than the native CLI:

```text
openai_tunnel.capability_status        read-only
openai_tunnel.get_known                read-only
openai_tunnel.list_bound_scope         read-only
openai_tunnel.prepare_create           read-only
openai_tunnel.commit_create            modifying
openai_tunnel.reconcile_create         read-only
```

A later separately reviewed wave may add `prepare_update` / `commit_update` / `reconcile_update` if workspace reassociation is genuinely required.

Do **not** initially expose:

```text
delete
arbitrary tunnel_id lookup
caller-selected org/workspace IDs
caller-selected control-plane base URL
caller-selected CA bundle
caller-selected executable
--admin-key
```

The model may choose business-level intent such as “create the Astra Business Workbench tunnel” only within a host-owned prebound descriptor. It does not construct low-level authority coordinates.

## Credential custody for P1

P1 should enroll one fixed **Studio-local custody binding** for the OpenAI admin credential under a dedicated service/account coordinate, distinct from MAS-115, Slack fixtures, Executive OAuth and provider worker credentials.

The key must be consumed by a secret-owning helper. Preferred injection order for this native client:

1. the helper resolves the fixed Keychain item into memory;
2. it forks/execs the **pinned libexec tunnel-client** with a closed environment;
3. it supplies `OPENAI_ADMIN_KEY` only in that exact child's environment because the native client explicitly supports that variable;
4. the coordinator/model never receives the environment or secret;
5. stdout JSON is bounded, parsed and sanitized by the helper before returning semantic fields;
6. stderr is bounded/sanitized and never blindly surfaced;
7. no shell interpolation is used.

`--admin-key` must not be used because command-line arguments are observable in process listings and receipts. The one-child environment is a compatibility boundary for the fixed OpenAI executable, not a generic environment export.

P1 should disable core dumps for the credentialized child and ensure crash/debug collection cannot capture its environment.

## Destination and binary binding

The installed client exposes configurable `--control-plane.base-url` and `--ca-bundle`. Those are useful administrator features but dangerous on an agent-controlled credential path.

The P1 adapter must refuse caller/environment override of:

- control-plane base URL;
- control-plane URL path;
- CA bundle;
- proxy variables unless explicitly reviewed;
- executable path;
- dynamic library/runtime substitution paths.

The intended destination is the exact OpenAI control plane (`https://api.openai.com`) as declared by the installed client's default, with ordinary system trust. The adapter should set a closed environment rather than inherit proxy/TLS override variables from the caller.

The native executable hash above is observation evidence, not a permanent magic constant in architecture. Installation/release ownership must decide the accepted hash/release and update it through reviewed deployment rather than allowing a model to supply a hash.

## Create effect safety

Tunnel creation is externally effectful and cannot be blindly retried after timeout/client loss.

P1 should follow the existing Mastermind prepare/commit/reconcile pattern:

### Prepare

Bind a short-lived action reference to:

- stable operation key / Executive Attempt or Workbench authority;
- exact Studio `host_id` and executor generation;
- exact accepted tunnel-client release/hash;
- fixed credential ref + generation;
- exact organization/workspace scope supplied by the owner binding;
- exact tunnel name/description policy;
- fresh pre-effect tunnel census digest/metadata;
- expiry.

Prepare acquires no secret and causes no OpenAI effect.

### Commit

Immediately revalidate host, authority, executable, credential generation and pre-effect census; only then acquire the secret and issue one native `create`.

Persist a pre-effect marker **before** the external request. A lost response after dispatch is `EFFECT_UNKNOWN`, never “not created.”

### Reconcile

Use the original action reference and the same bound scope to inspect current tunnels through the native list/get path. Resolve to `APPLIED` only with a uniquely matching qualified tunnel identity/metadata consistent with the prepared action. Resolve to `NOT_APPLIED` only when evidence is strong enough to prove absence under the same authoritative scope. Ambiguity remains `EFFECT_UNKNOWN` and blocks another create.

Read-only reconciliation never creates or modifies a tunnel.

## Readiness is a second phase

After `APPLIED`, the newly created tunnel is not immediately called production-ready.

Wait/poll through the current reviewed tunnel status/doctor mechanism according to the installed client's documented activation delay, with a bounded deadline. Report separately:

```text
CREATE_EFFECT = APPLIED
TUNNEL_READINESS = READY | PENDING | FAILED | UNKNOWN
```

Failure to become ready does not authorize another create. Repair/reconcile the created tunnel.

## Exact motivating-account boundary

The current Web failure says the Business/Astra account lacks an identifiable dedicated Workbench Secure MCP tunnel and that the existing `chatgpt3` route is associated with two ChatGPT workspace IDs.

P1 must not infer which existing tunnel/workspace is the intended Astra Business association. Before the first modifying canary, an owner/admin observation must supply the exact current:

- OpenAI Platform organization;
- Business/Astra ChatGPT workspace;
- any existing tunnel candidate(s) and their metadata;
- desired dedicated tunnel policy/name.

This is an identity/reconciliation gate, not a need for the Chairman to paste a secret.

Once exact association is grounded, the native `get/list` path should preserve it durably so future sessions do not rediscover it by guesswork.

## Cross-host consequence

P1 should **not** copy the OpenAI admin key to Admin Mini.

The first cross-host proof should be:

```text
Web CEO or local caller on a non-Studio surface
 -> existing Executive/Workbench/Capacity route selects Studio
 -> Studio credential capability executes there
 -> semantic result returns
```

This demonstrates the important distinction between “credential is available to the fleet” and “secret bytes are installed on every fleet member.”

Only a later HA wave should replicate custody, with one logical credential generation and a separately enrolled Admin Mini binding.

## Acceptance contract

P1 cannot be called `PROVEN_LIVE` until all are proven on the exact accepted release:

1. dedicated Studio custody enrolled without exposing the admin key to a model/log/argv/repo;
2. read-only capability status succeeds after service restart;
3. native list/get through the pinned client succeeds for the exact Business/Astra scope;
4. one prepared create is executed exactly once from the actual Web/Workbench path;
5. response-loss or simulated client-loss reconciliation resolves the original action without a second create;
6. resulting tunnel reaches the intended readiness state;
7. exact Business/Astra workspace can use the Workbench MCP through that tunnel;
8. wrong host, wrong workspace/scope, stale credential generation, changed executable, proxy/base-URL override and expired action all refuse before external effect;
9. logs/process artifacts/receipts contain no admin key;
10. a caller on another fleet host can use the capability without possessing the secret;
11. no new Executive lifecycle/queue/host registry/provider selector is created;
12. Chairman no longer needs to retrieve/paste the admin key for this operation.

## Exact next implementation action

Implement a **read-only P1-A capability** first: fixed Studio custody descriptor + pinned `tunnel-client` wrapper + secret-free `capability_status` and bound-scope `list/get`, with all destination/executable/environment refusals and leak tests.

Do not issue create/update/delete in P1-A. Once P1-A is installed and proves the exact Business/Astra org/workspace/tunnel state, use that fresh metadata to freeze the one create/reconcile P1-B action. This ordering avoids using a modifying canary to discover identity.

The current #633 `DCR_EFFECT_UNKNOWN` operation remains untouched and is not a reason to retry or fail over that enrollment.
