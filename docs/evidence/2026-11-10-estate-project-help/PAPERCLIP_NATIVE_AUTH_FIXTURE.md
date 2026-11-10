# Finite native Hermes test configuration correction

This incremental test-only change follows the original, failed native test on
primary tree `762490642b3746e58763c817562d5c9976518a70`. It leaves the original
two-file candidate and all production code unchanged. The original run is
preserved; it is not replayed.

## Original outcome and cause

The original native client reached the existing HTTP MCP initialization owner,
which returned HTTP 401. Hermes then performed its own existing automatic
Streamable HTTP/SSE connection fallback and parked the server. No model-visible
tools were discovered. The second test case was not run.

At exact native source `ba4ddf9945a213ede9dda016602a86591ed634f9`,
the run configuration in `tools/mcp_tool_server_run.py` selects authentication from the
explicit `auth` configuration field. `tools/mcp_tool_transport.py::_build_oauth_auth`
returns no OAuth provider unless that field selects `oauth`. The disposable
fixture supplied `url`, `oauth`, and `trust`, but omitted `auth`. The retained
fixture token and metadata files existed; their mere presence does not select
the OAuth owner. The original bearer was therefore not configured for the
transport. No alternate credential or permission is required.

The failed test also invoked cleanup on the wrong native module. The actual
owner is `tools.mcp_tool_lifecycle.shutdown_mcp_servers`, whose existing timeout
and profile-scoped teardown behavior are retained.

Read-only original Runtime reconciliation found the selected work Job `JOB-003`
still `QUEUED`, with zero Attempts and no current Attempt. Its exact original
command `coo-cycle:JOB-001:dispatch:JOB-003:attempt:1` has no Event. There are zero
`COO_SELECTED_CHILD_RESULT_ACKNOWLEDGED` Events. The original 47 Events include
fixture planner and separate prerequisite evidence, not a selected work claim.

The first fixture did not save its passive HTTP header records before the
assertion failed. Its preserved client log proves the HTTP 401 response and
incumbent fallback; no missing wire record is reconstructed. The increment
saves passive request-header hashes, response status, and decoded tool/action
names before assertions, including when authentication rejects before body
consumption. Bearers and request bodies are not saved in this evidence.

## Exact delta

- Select the existing native OAuth owner with `auth: oauth` in the new disposable
  fixture configuration, and assert that the actual connected task selected it.
- Import cleanup from its actual native lifecycle owner.
- Pin those two additional imported source files.
- Retain original HTTP exchange evidence before assertions or cancellation.

The original native timeouts, middleware, hooks, token custody, model-visible
dispatcher, App authentication, grants, profile isolation, selected-child
admission, result validation, explicit acknowledgment, and response-loss
reconciliation remain unchanged. No live Paperclip issue or native-origin
authority is asserted.

Both changed Python files parse successfully and `git diff --check` is clean.
Actual native normal and response-loss cases remain pending on a new disposable
fixture after parent composition and exclusive host release. No test pass or
installed activation is claimed by this artifact.
