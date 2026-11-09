# Fixed Workspace OAuth source qualification

This is one exact MIT-licensed derivation of
[NousResearch/hermes-agent at 1c0cd667746d3395fe9e1b6c74f8f85952486f18](https://github.com/NousResearch/hermes-agent/tree/1c0cd667746d3395fe9e1b6c74f8f85952486f18),
qualified by the existing Executive release/inventory owner. `manifest.json`
pins every preimage/postimage and the complete patch. `UPSTREAM_LICENSE`
preserves attribution. No installed or credential authority comes from these
files.

The nine changes retain the original manager, storage, refresh, CLI-login,
server-park and HTTP client owners. The accepted `agent_init.py` and
`memory_caller_scope.py` privacy postimages remain exact. The fixed companion is
only the Mastermind Workspace READ resource paired with the original COO
connection; this is not a configurable multi-resource credential proxy.

## Reproduce source and engine checks

Use `python -m integrations.hermes_qualification.workspace_oauth_privacy.qualify
--donor-root /path/to/pristine/hermes` to check the original source without
changing it. Installation still needs the original root-owned frozen Git tree,
independently selected complete dependency inventory and verified receipt.

In a separate disposable Linux Python 3.12 environment:

```sh
python -m pip install -r integrations/hermes_qualification/workspace_oauth_privacy/requirements.txt
python -m pytest -o addopts= -q integrations/hermes_qualification/workspace_oauth_privacy/engine_cases.py
```

The ordinary PR workflow performs this explicit invocation. The filename is
intentional: the general receiver suite uses MCP 1.28.1; it must not collect the
2.3 engine suite accidentally. The package list records the tested qualification
environment, not a production dependency inventory.

`engine_cases.py` verifies seven actual source blobs from MCP/types 2.3.0 and
HTTPX2 2.15.1 before executing the upstream Hermes bodies. The upstream archive
provenance records SHA-256, Git blob and length for every original fixture.
Source archives are test data and are never used by the installed runtime loader.

`current-context-fixture.json` is a recorded result from the actual signed App /
current-compiler test on receiver MCP 1.28.1. It retains the producer-source
hashes, publication and exact result/bundle digest. The engine test delivers it
through real 2.3 Streamable HTTP/ClientSession into the original native decoder
and capture guard. The receiver's ordinary tests independently generate fresh
results and prove new compiler acquisition on each native admission. This
record is not a current production observation or a grant.

## Evidence boundaries

The engine suite executes the actual OAuth generator, PKCE, original token and
metadata files, atomic writer, file refresh fence, selected original CLI/park
definitions, transport methods, HTTP client, body cap and SDK session. It covers
two consents, independent and cold refresh, scope/endpoint checks, exact
identity, token/config/profile/selection races, cancellation ownership, redirect
refusal, event-stream preservation, complete diagnostic redaction, readiness,
SDK attribute compatibility and legacy single-resource behavior.

HTTP responses and callback/consent UI are inert fixture boundaries. The proxy,
live-endpoint lookup, connection registry and serving-loop lifecycle are
explicit test edges. No socket or real account is contacted. Browser login,
host installation, OAuth issuer interoperability, provider/model execution and
production endurance remain separate acceptance work.

The fixed deployment requires an explicit initial token scope. Valid issuers
that omit it will be refused; unchanged refresh scope is preserved by the
original refresh owner. The current native profile stays disabled until the
installed original path and both resource authorizations are proven.

Eight upstream numeric literals have exact source/site classifications in the
existing `tests/executive_fabric_release_identity_review.py` table: six HTTP
statuses, the `Path.mkdir` permission default, and the HTTPS default port.
The tests prove that full-file/path/site drift and an added identity remain
visible. Neither original source bytes nor scanner rules are modified.
