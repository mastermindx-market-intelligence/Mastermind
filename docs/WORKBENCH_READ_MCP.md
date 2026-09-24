# First-party Workbench project-read components

Status: developer source candidate; not installed or production-qualified.
Source operation: workbench-read-source-20260907-websol2-001.

## Observable capability and composition

The inert app constructor reuses the existing Business MCP JwtAuthenticator and
MastermindTokenVerifier and the official Python MCP SDK. It advertises one
read-only read_project_file tool. The read port connects the authenticated caller
to the retained-directory-descriptor source observer without a new auth service,
project registry, executor, queue, lifecycle or permission database.

The deployment owner supplies the dedicated workbench.read resource policy,
current clock, existing audit sink, approved host/origin list, current project
binding resolver, bounded I/O executor and declared result schema. Construction
starts no listener and supplies no live root, credential or default grant.
Do not reuse an Executive audience as a filesystem grant.

A ProjectReadBinding is an internal owner projection, not proof that a caller
has authenticated. The resolver must authorize subject/client/resource/project
and keep the approved root descriptor alive. The I/O callback must enforce its
existing capacity and deadline contract. No inline or second-executor fallback
is supplied. Windows, network filesystems and hung kernel-read deadlines remain
unqualified. Observation cancellation does not prove a read was interrupted.

## Request and result behavior

Tool fields: project_ref, relative_path; optional line_start, line_count,
expected_sha256. The caller cannot supply an absolute root, principal, policy,
permission or source generation. Per-call immutable requests prevent accidental
retargeting across asynchronous callbacks. Exact project/hash identity is checked
before returning a successful result. Token and policy are verified again after
the port await. Scope is resolved before opening and after reading, and checked
again after the I/O await. Reads are withheld on observed revocation; there is no
per-chunk revocation check or guarantee that a kernel read is interrupted.
The returned observation must match the selected context, owner, generation,
explicit baseline, requested path/range and expected hash before project identity
is added. A conflicting project label is refused rather than overwritten.

The observer returns exact text, a full-file SHA-256, file-identity digest, range,
truncation and continuation position. The selected committed baseline is separate
from working bytes. index_status stays NOT_OBSERVED and atomic_workspace_snapshot
stays false; this component neither refreshes CodeIntel nor guarantees a write lock.
It refuses undeclared paths, symlink/hardlink/special files, identity/ancestry drift,
expired or changed scope, stale hashes and oversized/unrepresentable file content.

File cap: 1 MiB. Text cap: 32 KiB. App encoding cap: 256 KiB including both MCP
representations. These are not upstream HTTP-frame, aggregate memory or OS sandbox
limits. The node's existing transport/resource owner must qualify those separately.
The pinned low-level SDK call handler disables SDK input prevalidation only so
THIS handler's closed validation runs before verbose SDK errors can echo input.
Input validation is not disabled at the application boundary. Refusals use closed,
bounded codes and do not echo credentials, caller payloads or dependency errors.

## Reproducible component checks

From this checkout in an environment with the repository's existing auth/MCP
libraries, run:

    python -m unittest discover -s tests/workbench_read_mcp -v

The native qualification used Python3.11.10, Python MCP1.27.2, PyJWT2.13.0,
cryptography48.0.0 and the existing jsonschema/httpx stack, with no installation.
Component populations: 29 auth/ASGI tests, 42 descriptor-port tests, 47 filesystem
tests. Counts are separate from earlier runs and must be verified on this package.
All signed credentials and project maps in tests are ephemeral fixtures. No real
OAuth account, live project grant or publicly listening endpoint is implied.

## Remaining acceptance and no-rebuild boundaries

The separate full signed-auth-to-descriptor qualifier was platform-blocked and
NOT_RUN. Do not reinterpret component checks as that end-to-end result or retry
that blocked action through an alternate tool. Current full repository/security
checks, independent review, installation, real-account enrollment, actual selected
project reads, revocation/refresh and publication rollback remain release gates.
No shell/writes, provider session, desktop/browser, machine enrollment, shared
service change or Desktop Commander cutover is included. Those capabilities remain
in the broader Workbench outcome and are not implemented by this read component.
Keep Personal/E1, Steward, Runtime/Capacity, CodeIntel and research490 source owners
unchanged. This library is not authority to install or broaden another endpoint.
