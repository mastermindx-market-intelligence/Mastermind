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
The independently rebuilt protected composition at
`cb390bfc5a4b85a59a1005bfd3824305a5a4bfee` is SHA256
`8062512b10fc5c62b030c3ceb398495e63e6abd35b2018c5008b658f40d2251c`.
Its only base-member change is `ext/remote_sub.sh`, from
`e24d6123ae1c303fe7a72b88c9ae6093979dcf35a9984d7ba16ccb9689700b05`
to `3fbad86bc76c65248302191e0ff2e27eecdb933097244c5b87a03863385452c2`,
retaining the protected BASH_COMPAT and bounded heredoc self-test fix.
The three accepted A dependencies and B handler remain unchanged.
The builder and installer continue requiring the exact rebuilt base digest;
the resulting 104-member application stage is a new generation and needs fresh
publication, installation and enrollment proof through the existing owners.
The ordinary generation publisher remains the sole publisher. Old descriptors
retain their three entrypoints and exact generation identities. Partial Go
closure is invalid.

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
their exact identities. The two retained preimage files are inert source data,
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

## Limits and next activation work

This source does not create an application secret, permission grant, service
binding registry, model qualification, queue, provider retry or usage owner.
Completed service enrollment/startup resolution and VPS transport remain
separate finite owner changes. The source-pinned Go endpoint is not permission
to activate an unqualified model. Actual provider canary, restart/drain proof
and authenticated consumer/browser acceptance are still required.
