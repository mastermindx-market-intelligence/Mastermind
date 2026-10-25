# Canonical paid initializer qualification

This source path is part of the existing disabled canonical paid qualification.
It creates no Worker, Capacity row, service, credential, provider request or live
approval. Current unknown/refused hook inspections and operations remain held.

The Root `qualify-paid` action requires a bounded initializer commitment on stdin
and `--expected-initializer-sha256` for those exact input bytes. It still requires
the installed release/full seal, Control/definition preimages, disarmed state,
stopped/quiescent owners, actual bridge principal, registry and CONFIG_ROOT lock.
Missing input refuses before transport or reservation. No post-observation hash
is converted into approval, and no fixture/example supplies live values.

The action input must originate in the actual administrator's independent review
of the selected initializer bytes, permitted effects, SSH/bootstrap platform and
account/context. A hash or a correctly shaped document alone proves none of those
facts. In particular, the fixed unsourced bootstrap is a previously qualified
platform prerequisite; its later self-observed kernel hash does not authenticate
its own earlier startup. SSH server/user-shell startup belongs to that same
independently qualified platform premise. Paid qualification additionally forces
StrictHostKeyChecking=yes and UpdateHostKeys=no on the existing SSH transport;
it cannot enroll or update a host key. Ordinary telemetry policy is unchanged. Those facts are currently unproven by
this source change, and are not a new human-only gate or a request to inspect a
held remote operation.

For `paid-host-env-held-fd.v1`, `mastermind.paid_initializer_commitment/v1` has exactly these fields:

- `schema_version`, `host_ref`, `transport_alias`, `lane_root`;
- `account`: UID, GID, user and home;
- `bootstrap_python` and `launch_python`: absolute logical path, real path, SHA256;
- `host_env`: fixed lane `ext/HOST_ENV.sh` path, SHA256, size, UID, GID and permissions;
- `initialized_context`: exact HOME and GLM_CONFIG selectors, without credential data;
- `initialization_contract`: `paid-host-env-held-fd.v1`;
- `purpose`: `canonical-paid-qualification.v1`;
- `startup`: `cpython-3.12-linux-root-prefix.v1` plus exact prefix, exec_prefix,
  base_prefix and base_exec_prefix.

The transport selects only the committed absolute bootstrap, with `-I -S -B` and
no PATH fallback. The supported initial profile requires Root-owned, non-writable,
ACL-free launch selectors, interpreter image and startup distribution namespace.
The bounded startup-tree check excludes only site-packages/dist-packages, which
`-S` excludes from this execution. The actual `pyvenv.cfg` selectors must also
reside in the protected namespace. An account-owned lane virtualenv is unsupported;
no HOME, PATH, GLM_CONFIG, PYTHONHOME or VIRTUAL_ENV substitution makes it qualify.
Concurrent external Root modification remains outside the trusted platform
premise; the code does not invent exclusive custody or a global lock.

Before initializer evaluation, the bootstrap holds the actual launch ELF and
runs the actual isolated getpath observation through that FD, with the logical
argv0 as DATA. It compares the observed executable/prefix tuple to the commitment.
The later probe independently checks the kernel image, image hash and executable.
The CPython implementation derives startup paths separately from the kernel
image; Linux tests compare actual path-exec and FD-exec startup rather than
assuming argv0 is authentication. See [CPython 3.12.13 getpath](https://github.com/python/cpython/blob/v3.12.13/Modules/getpath.py)
and [Python execve FD support](https://docs.python.org/3.12/library/os.html#os.execve).

The approved hook bytes are copied into a Linux memfd and all WRITE/GROW/SHRINK/
SEAL seals are applied and read back before inheritance. Bash sources only that
immutable snapshot. The original hook FD/name and ancestors remain custody
checks, not a claim of byte immutability. Unsupported memfd sealing refuses.
The contract explicitly uses FD-source semantics; a hook depending on its old
BASH_SOURCE pathname is not silently treated equivalent. The actual initialized
Python/HOME/GLM_CONFIG selectors must match; they are not overwritten to pass.
Bash returns only bounded, NUL-framed UTF-8 environment DATA. Functions, traps
or options created by the hook never acquire final-launch or witness authority.
The pinned Python parent rejects duplicate/invalid environment keys, exported
functions, loader/Python startup overrides and context drift, then transfers the
validated environment to the held launch image with fixed observer code. Neither
Bash output nor an environment emitter is treated as observer evidence. The
parent alone constructs the final witness after that genuine child completes.

The fixed existing `.initial-qualification` staging sibling is reserved durably
before the sole remote child starts and is checked immediately before transport.
Its Root-only intent binds the current
release/source/registry/definition and expected initializer. Any failed or lost
transport after that reservation remains EFFECT_UNKNOWN with the same directory
retained. A later call refuses the occupied sibling. It never cleans up, retries,
relabels a missing result as no effect, or creates a parallel operation ledger.
Only successful source composition fills that same directory with the existing
four artifacts before the normal RENAME_SWAP publication.

New requests/observations are v2. Their closed pre-execution witness joins the
same commitment, immutable snapshot and original identity; old v1 observations
cannot qualify this path. Old retained source DATA remains readable through its
old closed shape, without being promoted to pre-execution proof. The generated
native closure includes the exact selected initializer implementation; no mutable
import search or controller callback supplies it.

Local source tests do not establish current host trust, actual approved hook
bytes/effects, credentials or availability. Linux memfd, FD-exec/venv and the full
inert initializer journey require the actual Linux CI results. The full inert
journey explicitly simulates the supported startup/account namespace metadata
(ownership, permissions and ACL absence) and a clean allowed launcher environment.
Actual FDs, sealed bytes, Bash/getpath and the child probe stay real. Injected ACL
and loader-environment negatives must still refuse before a hook marker. This is
not a production Root ownership/ACL/bootstrap receipt. Normal remote_sub/readiness and actual first paid START
remain separate held consumers until their own same-context prerequisites are
qualified. A protected source release alone does not authorize any of them.


The explicit nested DATA variant
-------------------------------

`paid-host-env-held-fd-token-data.v1` is a separate closed variant of that same
commitment schema. It adds only `nested_helper`: fixed path, expected SHA256,
size, UID, GID and permission mode 0600. The fixed path is
`account.home/lanes/ext/.host_glm_token.sh`; `lane_root` must be
`account.home/lanes`. This input still requires the actual independent approval
and custody facts. The current live helper bytes and their approval are UNKNOWN.
No example or correct digest supplies approval, and no helper is read remotely
merely to complete this source work.

The variant admits only the exact 587-byte outer source with SHA256
`c7fc8be292b3f231317c3cc9e5b64c990a34a495cf0fa095048a37df0379b2f6`.
Before any private helper bytes are read, the owner holds and revalidates its
named ancestry, descriptors, native ACL absence, account, exact size and 0600
mode. The helper parser accepts only the existing generated assignment grammar:
`export GLM_SHIM_TOKEN="<32 lowercase hexadecimal characters>"` and one newline.
Other retained formats refuse; this path does not rotate, mint or repair a token.

The reviewed DATA component seals the private bytes and transforms only that
outer source's sole final helper-source line into a no-op. The separately sealed
572-byte execution source has SHA256
`87198f3568e199c64a4deb2d41242a1c812dd65797f60ecc0db00fdf71b6e378`.
The old contract never selects this transformation. The original outer and
helper FD/name custody remain live checks; sealed snapshots supply immutable
bytes, not authority. Only the initial child environment receives the parsed
private value. Actual captured and final observer environments must retain that
exact value; loss or change refuses without reinjection. No secret is included
in evidence, errors, argv or the returned witness.

For this variant, `initialized_context.glm_config` binds existing effective
semantics: an existing nonempty GLM_CONFIG selector or HOME/.glm/config.json.
The owner does not export a missing selector or read the config contents. It
retains the incumbent lane-venv PATH prepend and checks the actual first
executable python3 against the separately committed logical launch path. It
never infers the launch selector from the bootstrap or overwrites a mismatch.
The protected image/startup/actual-kernel proof is unchanged.

The parent, token parser and nested-input module are exact hashed bytes in one
private package with an empty search path, preloaded in that order. Current
qualification binds eight fixed source files; the normal builder produces a
98-member closure. Historical 95-member fixtures remain byte-exact. Old retained
five-source DATA and old six-source pre-execution DATA remain readable under
their own closed shapes; new nested DATA requires all eight sources. No retained
DATA becomes a qualification grant.

The new closed pre-execution witness retains the six old fields and adds only
`nested_inputs` (the reviewed five-field transformation/helper fingerprint) and
`helper_origin_identity` (the actual nine-field private origin stat identity).
`context_identity.host_env_sha256` stays the original outer digest;
`pre_execution.snapshot_sha256` is the transformed digest. The ordinary Root
producer validates this join before publishing the existing four artifacts. Its
original pre-transport one-use reservation and all post-entry UNKNOWN/no-replay
semantics remain unchanged.

Linux joined tests use disposable credentialless inputs and explicitly simulate
protected platform metadata; they do not establish the current host's Root
namespace, private helper, approval, credentials or provider readiness. The new
case exercises the actual private-package loader, memfd snapshots, Bash capture,
held-image child, effective default config, observation codec, and helper
metadata/ACL-before-read and token-survival refusals. Darwin skips of that case
and the component's sealing cases must be replaced by actual Linux CI evidence
before protected delivery.

The inert tests prefer the existing fixed /usr/bin/python3 resolving to a
Root-owned CPython3.12 image only after the actual ACL/startup namespace meets
the finite profile. That branch leaves the fresh observer's checks unchanged.
The pytest/toolcache bootstrap premise remains explicitly simulated. If the
system layout is absent or unsupported, a fixed test-only ACL metadata model
is also installed in the fresh observer for only the declared distribution and
disposable private namespace. Its real read/identity/codec body stays intact;
outside paths and unrelated xattrs retain their errors. Completion notices name
which fixture profile ran. A simulated branch proves mechanics and refusal
composition, never current Linux platform custody or initializer approval.

Protected telemetry transport composition
----------------------------------------

The normal protected host-pull telemetry and existing inspections retain their
short SSH command, supervised stdin spool and cancellation behavior. Paid
qualification remains a separate fixed-bootstrap branch: it cannot adopt the
spool's ambient PATH-selected Python, SHELL or mutable script as new bootstrap
authority. Its actual final remote command, after shell quoting/framing, is
bounded to 100000 UTF-8 bytes including its terminating NUL before SSH. This
finite ceiling is below Linux's 131072-byte per-argument bound. Multibyte paths,
quote expansion and code growth are counted in that final representation; an
over-bound command refuses without falling back to another transport. The
strict/no-update SSH flags and EOF child stdin are retained. Inert tests join
the actual eight-source compiler to the shell's exact SSH argv and exercise
ASCII, multibyte, quoting and one-byte terminator boundaries without executing
a remote initializer or enrolling a host.

Linux failure discrimination
----------------------------

A denied write to a sealed memfd can still change its mtime/ctime. Immutable
content does not imply unchanged full custody metadata. The healthy private-env
case therefore remains separate from mutation attempts: those cases require
immutable bytes and require the existing full-identity fence to refuse any
metadata drift, including its context exit. The guard never re-baselines.

The existing shard2 job runs a fast three-case initializer preflight before its
full canonical suite. This is supplemental: there is no new workflow, runner,
permission, exclusion or green path that omits a full shard. Unexpected final
observer refusal emits only a closed test-owned function/line/errno/field-name
diagnostic as a structured error annotation. The real nonzero exit and owner
refusal remain. Environment, stderr, tokens, path values and exception repr are
not emitted; unknown diagnostic data becomes a fixed unavailable classification.
These diagnostic cases do not qualify an actual host namespace or approve an
initializer, and a passing fast preflight alone is not protected acceptance.

The hosted fallback fixture explicitly models only the enumerated image-selector directory ancestry in its fresh observer, matching its parent premise. Metadata for unmodeled/private sibling directories and regular files remains real and adverse checks use the actual observer walk guard. This is a finite test premise, not qualification of the hosted or deployed distribution.

### Explicit nested no-site startup profile

`cpython-3.12-linux-root-prefix-nosite.v1` is accepted only with
`paid-host-env-held-fd-token-data.v1`. The old startup profile and old initializer
contract retain their strict namespace/type checks. Selecting the new profile is
an explicit commitment, not discovery of platform trust or approval of an unknown
`sitecustomize.py` target.

The fixed compiler places the exact `NO_SITE_PREAMBLE` before standard-library or
qualified-package imports in the bootstrap, held-image getpath child and final
observer. It requires real CPython 3.12 `-I -S -B`, rejects any preloaded `site`,
`sitecustomize` or `usercustomize` key, and installs exactly those three normal-import
tombstones. `require_no_site_policy()` checks existing state without installing or
repairing it. Launch/return checks preserve that policy. Administrative packet
assembly must not execute this preamble in the administrator's interpreter; the
separate acquisition packet must place it before its own base64/wrapper imports.

Only an immediate `lib/python3.12/sitecustomize.py` symlink can be excluded from
executable startup closure. It still counts toward the unchanged 20,000-entry
bound. New-profile traversal uses no-follow `scandir` classification. The existing
Root-owned, nonwritable, ACL-qualified library directory and ancestors stay held;
`O_PATH|O_NOFOLLOW` pins the link node. A successful native no-follow
`listxattr` must return an actual empty list at
`/proc/self/fd/<held-library-directory>/sitecustomize.py`, never at the link
FD itself or its target. Full named/FD and parent identities bracket the query.
Every error, unsupported operation, non-list result or visible attribute name
refuses. This is a type-semantics/custody and empty-visible-metadata invariant:
Linux VFS excludes symlink inodes from POSIX ACL interpretation. An empty list
alone does not prove universal attribute absence because inaccessible names can
be omitted; it grants no LSM, target-code or sandbox assurance. Ordinary files
and directories retain their existing getxattr ACL guards. Changed node,
foreign owner, other symlink/type, writable namespace or excess count refuses.
All image, zip, `._pth`, pyvenv, getpath, immutable snapshot and source guards remain.


The same explicit new profile also supports exactly the immediate
`_sysconfigdata__linux_x86_64-linux-gnu.py` alias to the exact same-directory
ordinary file `_sysconfigdata__x86_64-linux-gnu.py`. This is a deliberately finite
supported policy, not a claim that the hosted or deployed alias target was
observed. The public Ubuntu 3.12.3-1ubuntu0.17 stdlib package declares this literal alias,
and its minimal package supplies the ordinary target. This public packaging
evidence is separate from hosted/deployed identity: the actual alias and target
must satisfy this policy in Linux CI and at action time.
[CPython `sysconfig._init_posix`](https://github.com/python/cpython/blob/v3.12.3/Lib/sysconfig.py#L495-L501)
can import this dependency, so it is qualified,
not ignored or tombstoned. No target code is executed by qualification.

The held library and its held Root ancestors retain their existing ACL and
namespace guards. The alias has no-follow O_PATH/full-nine-field custody and must
name only that literal target before any target bytes are read. The target opens
relative to the held library with O_NOFOLLOW, must be an ordinary Root-owned
nonwritable single-link file of at most 1 MiB, and retains its FD, ACL, full
metadata, named identity and content hash through bootstrap/handoffs/return.
Retargeting, absolute/escaping/other relative names, chains, writable/foreign
files, hard links, changed content or unsupported native proof refuse. Both names
still count toward the unchanged startup limit; all other links still refuse,
and the old strict profile remains unchanged.

These tombstones are normal-import controls under exact pinned code, not a Python
sandbox. An arbitrary alias/file loader could execute another file; no such loader
or caller-supplied Python is admitted. The canonical request still binds the fixed
probe hash and eight-source closure, and the new profile additionally checks the
probe bytes before initialization. Token/config/request data never becomes Python
code. No daemon, policy registry or new approval store is introduced.

Synthetic/local proofs do not establish the complete deployed distribution, unknown
symlink target, actual initializer approval, helper input, readiness or live H1.
Actual Linux no-follow custody and the real compiled nested journey require current
hosted execution. The Linux fixture distinguishes its old-profile finite ownership
premise from its added actual Root-system-image no-site segment; unsupported native
proof fails rather than qualifying a simulation. The final quoted UTF-8 paid command
including its NUL remains bounded at 100,000 bytes before SSH.


For a failed explicit CI system-fixture startup precondition, the original
failure remains primary. A separate best-effort structural inventory walks only
`/usr/lib/python3.12` with held/no-follow directory operations, excluding the
existing site-package roots. It opens no ordinary file or link target and runs
no getpath, import, initializer or provider operation after failure. The report
is not an ACL, complete platform, readiness or admission proof. It caps traversal
at 20,000 nodes/five seconds, records at 64 and encoded output at 16 KiB; any
limit, unavailable metadata, unsafe name, unqualified directory or namespace
change explicitly marks it incomplete. Only bounded canonical ASCII relative
names, kind/reason enums and optional lexical targets within `/usr/lib` appear.
Outside/unsafe targets remain OUTSIDE/UNKNOWN without raw values. The diagnostic
is preloaded before the test; diagnostic failure cannot replace or fix the
original assertion, and interrupts propagate.
