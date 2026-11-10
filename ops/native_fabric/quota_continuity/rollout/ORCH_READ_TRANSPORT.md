# Prospective fixed original-read transport evidence

P8.T1.S33.S5 repairs the demonstrated local information loss while preserving the
frozen9de recovery reader and PR2310's independent release. Original maintenance
and its first recovery read remain UNKNOWN; neither is retried by this source.

`fleet_remote_sweep.read_original_orch_result(registry_bytes, ssh_config_bytes,
expected_module_sha=..., expected_storage_sha=..., expected_reader_sha=...,
expected_driver_sha=...)` is an opt-in existing-owner entry. It accepts no command,
path, operation, root, host, deadline, environment or retry selector. The fixed
plan's original operation/root and enrolled Ubuntu4 target are unchanged. Root
still decides whether any actual call is permitted. Source pins compare source;
frames compare observations. Neither supplies runtime authority.

The literal `read-orch-repair-framed` plan additionally binds the local driver
source and requires its established SSH vector. It replaces that vector's ONE
ConnectTimeout=20 element with ConnectTimeout=10, rather than appending a second
option that SSH might ignore. Global SSH, generic run(), mutating repair and all
other predecessor driver/module behavior remain unchanged. The total transport
budget remains20 seconds. Ten seconds of connect allowance leaves room for the
fixed helper/result; it does not guarantee actual network or helper completion.
All source files remain below the unchanged32768-byte source-reader cap.

The SHA-bound embedded storage/policy/reader sources perform the fixed Linux
scope check, then flush a canonical READ_ENTERED frame, then run the existing
read and flush its closed result. A fixed-account mismatch may emit only a closed
SCOPE_REFUSED frame, without claiming entry. Each frame binds the exact original
operation/root, semantic enrolled-target digest, and four source hashes. There
is no callback, remote path or source-loader selector. Errors are limited to
existing closed public reasons; raw exception text, paths, stderr and credentials
never enter the returned observation.

The additive driver starts exactly one local SSH process with stdin/stderr to
DEVNULL and stdout to a bounded pipe. A selector reads at most4097 bytes under the
same20-second monotonic budget. More than4096 bytes rejects the whole observation.
On deadline/overflow it terminates and reaps only its own local read transport,
as ordinary subprocess timeout cleanup does; this is not a remote cancellation
or a claim that a remote process stopped. No loop launches another process.
Canonical exact-context frames alone survive; banners, duplicates, extra frames,
foreign bindings or malformed results produce OUTPUT_UNQUALIFIED. Partial final
frames at timeout are discarded. Raw bytes are neither returned nor persisted.

Transport facts and receipt facts stay distinct:

- TIMED_OUT/UNOBSERVED means no qualified helper-entry frame was retained. It
  proves neither connection failure nor no remote execution.
- TIMED_OUT/READ_ENTERED retains only the qualified fixed-scope entry frame.
  Receipt settlement remains unknown.
- TIMED_OUT/RESULT_RETAINED preserves a complete, already qualified result that
  arrived before timeout, while explicitly preserving unsuccessful transport
  settlement. Historical/current receipt semantics remain those of9de.
- LOCAL_PROCESS_UNAVAILABLE, OUTPUT_UNQUALIFIED and
  RETURN_WITHOUT_QUALIFIED_RESULT are closed local classifications, not remote
  policy, identity or permission diagnoses.

All observations keep replay:false, retry_authorized:false,
lifecycle_authority:false and stderr_retained:false. No phase permits replay,
maintenance, policy publication, dispatch, lease or selection. No actual repaired
read is authorized merely by this source implementation.

The focused inert proof uses genuine disposable original-mutator receipts and
exact framed sources, with explicit installed-Linux scope/ACL substitutions.
Popen/selector/clock substitutions exercise the real driver loop without creating
any process/socket/SSH activity. It proves timeout evidence handling, not actual
host delivery, transport authentication or recovered original runtime outcome.
