# Required MCP audit directories during normal publication

The normal `publish-os-gateway` owner prepares the audit directories selected by
its already-qualified MCP candidate. A configured `steward` block selects both
`content` and `steward`, including when all Content profiles are dormant. Base
policies require `read` and `submit`; configured Workspace and COO policies add
`workspace` and `coo`. Policy IDs must remain distinct.

The fixed parent is `/var/log/mastermind-executive/mcp-auth`, an existing direct
root:wheel `0755` directory with trusted, non-writable, ACL-free ancestry. The
normal macOS root-owned `/var` alias is the only permitted alias. This operation
does not create or repair that parent.

The existing gateway transaction records the selected leaves and their physical
preimages before effects. It preserves existing direct MCP-owned `458:458 0700`
directories without ACLs and creates only positively absent required leaves.
Unsafe existing custody, changed parent/leaf identity, and a changed absence
refuse. It does not chmod/chown an existing directory, acquire an audit sink,
open or create a log, take a log lock, operate a service, or alter policy grants.
The genuine gateway retains ownership of creating its own `0600` audit files
and acquiring their append locks during startup.

The resulting identities are retained in the same original transaction at
`AUDIT_DIRECTORY_READY`, before the grant, MCP config or plist is published.
The existing source, stopped/unarmed/Runtime predicates, target CAS and
single-marker ownership remain in force. No additional
CLI, registry, lifecycle or receipt schema is introduced.

An interrupted directory effect leaves the original operation unknown. Normal
reconciliation checks the retained postimages; it never creates a missing
directory, adopts a replacement inode, or replays preparation. Historical
markers retain their original read-only contract and are not relabeled as
having carried this new prerequisite.

The change prevents the observed startup failure in which a valid dormant
Content configuration reached `PolicyAuditSink` without its required audit
leaves. It does not claim that directory preparation proves successful App
composition, active providers, or product acceptance.
