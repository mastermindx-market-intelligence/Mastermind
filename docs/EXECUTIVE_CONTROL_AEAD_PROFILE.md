# Event-only AEAD closure for the existing Executive control host

The reply-event host requires `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
in the Runtime-owning control process. The existing PSF Python 3.12.10 launcher
uses `-I -S -B` and cannot import packages from the separate MCP network runtime.
This profile preserves that interpreter, those flags and the disabled incumbent
path. It adds only the hash-locked AEAD dependency closure when the existing sealed
control configuration explicitly enrolls reply events. It adds no account, key,
listener, Runtime, release actuator or second installer.

`requirements/executive-control-aead-macos-arm64-py312.lock` extracts the existing
reviewed production lock's exact cryptography 50.0.1, cffi 2.1.1 and pycparser 3.0
versions and hashes. Public bundle preparation uses the matching macOS arm64
CPython 3.12/native ABI wheels and contains exactly three original wheel archives.
A caller-built manifest cannot substitute for wheel provenance: preflight validates
original wheel SHA-256 against the committed lock, matches each internal WHEEL tag
to the allowed filename platform/version, validates
closed package paths, then derives the package manifest from those accepted bytes.
Startup hooks, arbitrary top-level modules, symlinks and traversal are refused.

The existing `install.sh` optionally consumes `--control-aead-bundle` before its
mutation/maintenance boundary. Its helper reads committed lock bytes from the exact
already-admitted source SHA, checks the operator-owned stable descriptor, and
performs no package import during preflight. After the original installer seals
and verifies the release, the same installer materializes the immutable profile at
its derived lock-digest address under the existing System root. It reuses the
existing descriptor-relative exclusive rename. A same-profile occupant must verify
exactly; it is never replaced or cleaned. Failure preserves partial staging for the
existing installing owner to reconcile. No separate service or installer owns it.
The installer's restrictive umask is preserved. Only a freshly created dependency
parent with verified ownership, descriptor identity and no ACL is widened to 0755;
an existing parent must already satisfy that mode. `--stage-release-only` exits
after release sealing and does not materialize or activate the dependency profile.

The profile retains its original wheel archives, exact derived manifest and extracted
files. Verification rechecks all original hashes, all file bodies, closed inventory,
root custody/modes/ACLs and sealed parents. The control wrapper uses the existing
`load_control_config` owner before selecting any dependency path. It adds only this
qualified package directory, refuses cached dependencies from another origin,
imports the actual AEAD implementation, and verifies a synthetic encryption/decryption
and authentication-failure self-test. It rechecks the same profile after import.
The disabled configuration performs no dependency I/O. No actual host storage key
is used in this dependency qualification.

Installed-peer control qualification verifies this optional closure's contents once
per connection. Both subsequent race checks freshly observe its descriptors, ACLs,
file identities, lock and manifest; no observation is reused across connections.
Reads, hashing and decompression obey the same original qualification budget.
Direct profile verification also caps the lock read at its 32 KiB contract limit.
Gateway/network qualification
remains separate; the event flag does not reinterpret a release-controller profile
or native worker grant. The new key reader also reuses the existing descriptor-bound
`control_plane.fs_security.has_macos_acl` observer for the open key and its parent
chain. An ACL or unavailable observation refuses custody before key use.

The next real owner sequence is: protected exact source and locked public bundle;
existing installer/maintenance admission and sealed interpreter/profile qualification;
explicit existing-custodian key provisioning and private access/ACL/backup proof;
mutually consistent sealed MCP and control release/peer configuration; existing
Company/native Runtime composition; then explicit event enrollment and the existing
service lifecycle owner. No source command provisions a key or grants enrollment.
An actual privilege/consent/install refusal remains on its original carrier.

Source tests exercise rejected locks, archive tamper, manifest ambiguity, startup
hooks, traversal, changed dependency origins, descriptor/ACL failures, conflicting
occupants, restart verification and default-off behavior. A separate disposable
public-wheel fixture runs the actual accepted code under the intended PSF interpreter
with `-I -S -B`, verifies module origins and AEAD behavior. Its root metadata is
explicitly simulated: that proves source/interpreter compatibility, not installed
root custody, enrollment or production callback acceptance. Those remain actual
release/install owner gates. Ordinary independently authorized Work subscription,
canonical native COMMIT, callback receipt, `session_reply_read` and original-parent
acceptance remain separate observations; the closed DotApp refusal is untouched.

Rollback belongs to the original release owner. De-selecting the event enrollment
keeps the existing Runtime subscription history, tombstones and unknown reservations;
it does not erase encrypted state or authorize callback replay. Keep the provisioned
storage key and its identity while any ciphertext depends on it. A reviewed source
rollback must use the original installer/source admission and the matching immutable
dependency profile. The helper never substitutes an arbitrary interpreter, network
runtime, older package cache or new key when an existing profile refuses. It never
cleans a partial profile, overwrites its digest address, or deletes a previous one;
reconciliation and eventual reclaim remain with the installing custodian.
