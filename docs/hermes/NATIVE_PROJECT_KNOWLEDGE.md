# Native Hermes project knowledge

## Supported behavior

The v5 native consumer can read current project knowledge, capture a project note,
change the project's communication preference, and recover the original operation
after a lost reply. It retains the incumbent discovery-source and correction tools.
Canonical notes remain Agent OS project files; the preference remains the existing
project preference record. This contribution does not establish personal memory or
automatic insertion of every note into every model prompt.

The connected source operation is `hermes-native-project-knowledge-20261108-c3`.
Its finite source grants are in the Hermes teammate masterplan sections 57–58,
published before the corresponding edits. The capability profile stays disabled
until the original installed admission and receiving-owner checks qualify it.

## Explicit version and owner selection

| Coordinate | v5 value |
| --- | --- |
| Consumer publication | `mastermind.hermes_native_executive_consumer/v5` |
| Catalogue | `coo.project_knowledge.v1` |
| Tool result | `mastermind.coo_project_knowledge_result.v1` |
| Profile | `principal.hermes-native.executive-coo.project-knowledge.v1` |
| MCP grant | `mastermind-executive-coo-project-knowledge-v1` |
| Complete tool-schema digest | `3464e86ed27db54b7e3caa0520da0c86482772563ba5aea8491c8a492df69ae3` |
| Context frame | `mastermind.ceo_ingress.coo_project_knowledge_context.v1` |
| Context result | `mastermind.coo_project_knowledge_context_result.v1` |

The same ExecutiveContextConsumerPublication type, ConsumerSlot, native MCP caller,
call lock, original future, uncertainty record, trust gate, reservation owner and
registration leases carry v5. There is no second memory, authentication, retry,
publication or runtime owner. Raw MCP tools remain excluded from native automatic
tool inclusion; the finite native registrations retain the existing checks.

The existing public COO catalogue gains the two knowledge descriptors after its
unchanged v4 descriptors. The native discovery registration owner exposes exactly
these four tools:

| Native tool | Selection and behavior |
| --- | --- |
| `executive_project_discovery_source` | Existing opaque discovery-source read |
| `executive_project_discovery_correction` | Existing original correction operation |
| `executive_project_knowledge` | `catalogue`, `memory`, or exact `source` read |
| `executive_project_knowledge_authoring` | `prepare`, `read`, `submit`, `reconcile` |

The original context owner separately acquires
`executive_agentos_current_context` with the explicit v5 frame/result. The existing
Executive ingress now selects the matching v3, v4 or v5 result validator. Historical
v2/v3/v4 catalogue digests and payload contracts stay unchanged; a v5 envelope cannot
be presented as a historical result.

The closed principal actions are `read_current_agentos_context`,
`read_project_discovery`, `correct_project_discovery`,
`read_project_knowledge`, `add_project_file` and
`set_project_communication_preference`. Project mutation authority remains with
the original Workspace source-operation grants. A read-capable native profile does
not manufacture a Workspace mutation grant.

## Connected note journey

1. Read the current catalogue for the assigned workstream. Retain its DATA commit,
   workstream content hash, opaque source references and blob revisions.
2. Build one immutable add-file request, with an original request identifier, the
   observed source commit and workstream preimage. Its file has a display name,
   supported media type and exact UTF-8 content.
3. Call authoring `prepare`. The forwarding owner reacquires the current
   authenticated catalogue, compares it to the original request and invokes the
   incumbent compiler/source-operation owner. A fresher read never rewrites the
   request's preimages.
4. Inspect the original two-postimage preview and retain its preview witness.
   Preparation records the original intent; it does not prove publication.
5. Submit using the complete retained seven-field lookup and that witness. The
   forwarding owner first reads the full original lookup. Only the original
   `INTENT` reaches the incumbent short submit carrier; an already progressed
   operation is observed without another submit.
6. Reconcile that same lookup through the original owner. A proposal is not a
   canonical source publication. After actual source integration, require the
   owner’s two-file source receipt and read the current catalogue/source again.

The public prepare envelope is exactly `{operation, request}`. The request's
closed schema determines its action; there is no redundant caller-controlled
top-level action. For example, the note request contains:

```python
{
    "schema": "mastermind.project_file_add_request.v1",
    "request_id": original_note_request_id,
    "work_ref": assigned_work_ref,
    "source_commit": catalogue["source"]["commit"],
    "base_revision": catalogue["source"]["workstream_sha256"],
    "file": {
        "display_name": "Research-notes.md",
        "media_type": "text/markdown",
        "content_utf8": exact_note_text,
    },
}
```

The request identifier uses `mmos-project-file-add-` followed by 40 lowercase hex
characters. Keep the same identifier and complete request throughout the original
operation; changing either does not recover an uncertain operation.

## Communication preference

Preference requests use schema `mastermind.project_preference_set_request.v1`
and identifier prefix `mmos-project-preference-set-`. Along with the same project,
source commit and workstream preimage, they contain `value` and
`expected_preference_revision`.

The expected preference revision is the existing preference's **content SHA-256**,
or null only when the actual current memory read is `EMPTY`. An unavailable read
is not an empty preference. Preparation compares the fresh catalogue and memory
CODE context, repository, default ref, canonical DATA commit and reader closure.
Independent observation timestamps may differ for the same immutable snapshot.

For an available preference, the original fixed decision path, source commit,
content preimage and catalogue-to-memory blob revision must all agree. This
prevents a stale preference update from silently replacing a newer value.

## Source coordinates and byte fidelity

| Coordinate | Meaning |
| --- | --- |
| `source.commit` | Canonical DATA commit |
| `code_context.executable_macro_commit` | Independently issued compiler CODE |
| Catalogue item `revision` | Exact Git blob SHA-1 |
| Source-read `expected_revision` | Expected Git blob SHA-1, not DATA commit |
| `source.content_sha256` | SHA-256 of exact content bytes |
| Preference `expected_preference_revision` | SHA-256 preimage of the preference record |

Available current reads require independently validated CODE context and canonical
DATA observation. Exact source reads retain the opaque source reference and check
both SHA-256 and the Git blob calculation against the returned UTF-8 bytes and
requested revision. Rehashing altered content with SHA-256 cannot make it satisfy
the original blob selection.

The original seven-field knowledge lookup is:

```text
action, request_id, work_ref, source_commit, base_revision,
request_sha256, expected_preference_revision
```

The lookup retains null as a value. Only the existing GET query adapter encodes
that known nullable field as the parser's literal `null`; POST JSON and retained
identity remain unchanged. Discovery recovery retains its different, eight-field
lookup and three-file publication proof.

Preparation checks exactly two postimages: the selected workstream and its
deterministically scoped note or preference. It verifies both preimages and the
original note-body hash. Body-free recovery cannot reconstruct a private note's
extension or content from a hash. Source readback therefore requires the original
owner/request-hash join, the selected workstream plus one permitted deterministic
note/preference path, and one publication commit.

## Authentication and original-effect handling

The original independently authenticated Executive and Workspace resources must
agree on issuer, subject and client. Their permissions, catalogue, receiving owner,
current authority and retained transport are rechecked around awaited work.
Neither a caller-provided identity nor an earlier successful read supplies a grant.

| Observation | Meaning and next action |
| --- | --- |
| `NOT_DISPATCHED` | The adapter has evidence it did not enter the mutation carrier |
| `EFFECT_UNKNOWN` | Preserve the original request/future and use its read/reconcile path |
| `OBSERVED` with `INTENT` | Original preparation exists; publication remains unproved |
| `OBSERVED` with `PROPOSAL_OBSERVED` | Original proposal exists; no source publication receipt |
| `OBSERVED` with `SOURCE_OBSERVED` | Original owner supplies the exact source receipt |
| `UNAVAILABLE` read | The read is unavailable; do not infer absence or empty memory |

Once a mutation POST has been attempted, a later rejected or malformed response
does not prove zero effect. The adapter preserves `EFFECT_UNKNOWN`, including a
Workspace permission rejection whose private implementation may know more than
the forwarding transport. There is no automatic retry or replacement request.

An outstanding original future blocks concurrent authoring and recovery calls.
A current knowledge read or another action cannot clear an uncertain note.
An original prepare can settle on the matching intent; an uncertain submit does
not settle merely because an intent remains visible. The same owner and lookup
must establish its actual outcome.

## Existing bounds and packaging

Notes are limited to 32,768 UTF-8 bytes. Display names are at most 128 UTF-8 bytes,
with Markdown or plain-text media matching a .md/.txt suffix. Preference values
are at most 2,000 UTF-8 bytes. Complete encoded HTTP requests retain the 64 KiB
ceiling; tool parameters reserve 1 KiB for original SDK framing. Escaping and
multibyte characters count toward the actual encoded limits. Oversize is refused,
never silently truncated. Existing result and private context ceilings remain in
force.

V5 release composition requires the existing `workspace_oauth_privacy` vendor
derivation, including deferred release validation. The diagnostic-only or
computer-environment derivations cannot substitute. No EVAL integration allowlist,
dependency, workflow, account, fleet or installed-runtime permission is expanded.

## Source qualification and installed acceptance

Qualification exercises the actual temporary Git/compiler/Event/source publisher,
signed HTTP/MCP resource pair, original client and Executive ingress handler over
an explicit in-memory duplex carrier, native SDK decoder, and pinned Hermes
PluginContext/ToolRegistry. Synthetic account, credential, host-seal and PR edges
are identified in the fixtures. No Unix listener, installed service or provider
inference is invoked.

The source cases cover exact note/preference publication and current readback,
immutable preconditions and byte identities, preview/status tampering, late
authority/owner changes, original-future recovery, four-tool registration and
collision behavior, version separation and release derivation. The configured
profile remains disabled.

Installation still requires the original runtime carrier, current release and
derivation, enrolled receiving owner, explicit grants, actual installed note and
preference journeys, revocation/restart recovery, and parent consumption. Source
tests, a merged PR, a queued release, API-key mechanism observation or a proposal
receipt do not establish those outcomes.
