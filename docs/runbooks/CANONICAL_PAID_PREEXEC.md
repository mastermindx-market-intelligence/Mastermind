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

`mastermind.paid_initializer_commitment/v1` has exactly these fields:

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
