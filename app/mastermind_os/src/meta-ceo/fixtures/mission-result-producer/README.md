# Associated Mission/Result producer export

`actual-pair.json` is one unchanged HTTP response body from
`GET /workspace/mission-result/current` on the mounted Executive path.
`build_executive_mcp_app` registers that literal route on the same
`WorkspaceApp`, wrapped by `AuditedWorkspaceApp`. The bytes are not a direct
`WorkspaceApp` client capture. Their sha256 and byte length are
`fixture-provenance.json` `http_body_sha256` and `http_body_bytes`. Nested
`mission` and `role_result` are fields of that body. They are not separate
raw HTTP responses.

The TypeScript content-fallback case mutates the decoded role result in
memory. It is consumer projection coverage. It is not a second captured HTTP
response, and the captured `role_result.availability` stays `AVAILABLE`.

The proof ceiling is `SOURCE_ASSOCIATED_READ_QUALIFIED`. This export uses a
test-owned Runtime, namespace, and signed bearer. It does not prove an
installed UID, an Auth0 registration, or a signed-in Office UI.

## Replay

An ordinary vitest run, with `MISSION_RESULT_FIXTURE_DIR` absent, reads this
directory and checks the pinned sha256 and runtime source identity.

## Fresh consumption

Set `MISSION_RESULT_FIXTURE_DIR` to a directory that contains its own
`actual-pair.json` and `fixture-provenance.json`. The suite hashes those
files, checks the provenance hash against that directory's pair, and derives
identities from the documents. It does not consult this committed export.

A present-but-empty variable, a missing directory, an empty file, or malformed
JSON fails the process. There is no fallback to the committed bytes.

Negative cleanup removes only a `/tmp/mission-result-producer-negative-…`
directory created by that test. It refuses a caller-supplied or shared path.
