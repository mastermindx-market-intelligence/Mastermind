# Go APPLICATION release join

This source adds a fixed Go entry and handler to the existing immutable native
release. It retains the original Go script path, Python process/PID, singleton,
state/profile owners, controller behavior and canonical Fabric lease database.

## Source and staging

The default builder retains a closed, reviewed 102-member base. The explicit
`build_review_stage.py --include-go-application --output <fresh-external-output>`
adds only `ext/native_go_entry.py` and `ext/go_application_handler.py`.
The existing external Go component captures the original handler preimage, the
B source and its three A dependencies. The output is still uninstalled.

The original B102 base manifest was SHA256
`b4be55f9096985d8292160bc00886e44bfbe0941c095b65973b85ba36998acb6`.
The earlier protected controller composition was `8062512b10fc5c62b030c3ceb398495e63e6abd35b2018c5008b658f40d2251c`.
Published `001d972fba87ed2876e50fa73d2e70664f3b968b` composes protected
`51e9dc043fd9c53bb5e2ed7f43b76de058d73eea` with the accepted application A3.
Its independently rebuilt 102-member manifest is
`395b1af90c815125a92c81c8b72ec61065002f4f9e66ad53618794ec790ce429`,
including protected `remote_sub.sh` SHA256
`a1e271170778f992cf07c780234620c22d17f6242581311c414e30dd428ade40`.

The current HTTP application extension updates only those three A dependencies
inside that base, yielding default102 manifest
`9f7227994f47adca008093b193fc317e183ef1a88740128e246f2695ae9a83a3`.
Builder and installer share one validator: compare the actual A3 with captured
reviewed source, substitute only the three explicit historical A3 hashes in a
copy, and require the exact395b base. Any fourth changed member, missing or
extra member refuses. The actual target retains current hashes; no historical
manifest or receipt is rewritten. The 104-member Go application stage needs
fresh publication, installation and enrollment proof through the same owners.
The ordinary generation publisher remains the sole publisher. Old descriptors
retain their three entrypoints and exact generation identities. Partial Go
closure is invalid.

### Optional sealed HTTP metadata

Add `--include-application-http` together with `--include-go-application` to
compose exactly three further members: `application_http_transports.py`,
`application_http_realm_projection.py` and `application_http_realms.v1.json`,
all flat under `ext/`. A partial group is invalid. No new entrypoint is added.

The compiler accepts three exact historical1fc byte strings. The old H source
is retained as `source/application_http_transports.py.preimage`, inert AST
evidence that is never installed or imported. Current H is sealed separately.
The builder executes and seals the same captured reader bytes, so a stale
same-path Python module cannot stand in for the compiler. The existing manifest
binds the resulting projection digest. Native startup validates that digest
and the complete fixed driver identity without repository imports, credential
reads, SQLite or network effects. Missing or malformed sealed metadata never
falls back to a mutable repository owner.

## Existing finite installer

After protected-source publication and the ordinary owner prerequisites, use
the existing `native_install.py prepare-go` with the retained completed
successor bundle, published target generation, captured external component and
a fresh external output directory. Preparation is a reviewable source plan;
it changes no installed ingress.

`apply-go --bundle <original-bundle>` uses the SAME finite successor transition
owner: publication lock, original intent, exact source/target checks, Studio
consumer pin check, launcher, pool/task/Go bridges, one selection CAS and
receipt. Remote remains legacy. No service process is started or stopped.

`reconcile-go --bundle <original-bundle>` may complete only an exact committed
missing receipt. It cannot replace bridges or select a generation. Precommit
partial state stays the original transaction. Foreign bytes, changed full
selection, altered source or a different valid plan do not authorize repair,
rollback, a new carrier or another apply.

Historical8bc/d044/43e launchers and historical95/102 manifests/receipts keep
their exact identities. Retained preimage files are inert source data,
used only for authentic lineage reconstruction and disposable historical tests.

## Original process and startup

The Go bridge verifies/captures its planned launcher bytes and runs it in
process. The launcher reads CURRENT once, verifies the complete selected
release, then executes captured entry bytes. It never rewrites argv, spoofs
__file__, execs a different Go filename, or starts another server.

The entry qualifies the complete native module namespace, the actual original
GLM lifecycle helper, and declared owner aliases. Import/inspection does not
read credentials, initialize the broker, refresh quota, admit work or listen.
The real B.main owns the singleton, Router and one HTTP server.

No service enrollment means the exact empty tuple and original B.main() with
no Broker argument. Application startup requires actual B binding objects plus
the trusted completed startup owner's native host and original approved account
path. Inherited account, endpoint, port, state or policy paths must agree with
that projection. The supported incumbent custom account path is preserved;
HOME is not evidence of application credential custody.

An admitted startup supplies explicit canonical Broker paths, refuses absent
or aliased owners before construction, and retains the existing defaults for
external/PID gates. Fresh A grant parsing/authorization remains inside its
transaction. The existing paid_yaml_runtime.held_yaml owns the exact packaged
YAML bytes for the serving lifetime; ambient YAML is not adopted.

## HTTP enrollment and original recovery

The existing finite service-enrollment owner also accepts its v2 HTTP
specification. It commits the source-derived recipe, original account list and
incumbent `bailian_keys._codex_key_value` profile identity through the same
publication/broker locks, one private credential, prepared target inodes,
ordered renames and original completion receipt. It creates no second key,
grant, retry, queue or publication owner. A changed source recipe is checked
before fresh enrollment and inside A's fresh admission transaction.

Completed enrollment authenticates its historical binding/intent/receipt and
recipe independently of the current catalogue. A removed model, expired grant
or rotated provider credential cannot relabel an original effect. Current H
binding uses the current verified projection digest. The original request
recovery occurs before current recipe lookup, credential loading or admission;
an absent request must satisfy current source and grant. Provider credentials
are loaded by the existing key owner only on the exact A-selected account,
before intent and again at send. HTTP effects, serving model and nullable usage
remain observations in the original A/B receipt; no Go quota or cost ledger is
used for a Bailian transport.

## Limits and next activation work

This source does not create an application secret, permission grant, service
binding registry, model qualification, queue, provider retry or usage owner.
Service enrollment and VPS transport remain separate finite owner actions.
In particular, the existing Bailian Token Plan has no qualified backend
application permission; this source must not activate it or relabel its
workload/endpoint to escape that restriction. The source-pinned Go endpoint is not permission
to activate an unqualified model. Actual provider canary, restart/drain proof
and authenticated consumer/browser acceptance are still required.
