# Bailian credential custody: bounded native-generation repair

## Review result

The active native helper and Qwen wrapper are repaired in this isolated draft.
Credential values no longer cross helper stdout, shell command substitution,
shell evaluation, or the wrapper's environment. The helper replaces its process
with the fixed `codex exec` executable and puts the exact selected credential
only in that child's environment. Account selection, broker ownership, key
slots, continuation, output framing and provider failure classification remain
with their incumbent owners.

Seventeen fixture-only subprocess tests passed in 3.045 seconds. `bash -n
qwen_exec.sh` passed. No real credential file, Codex provider, network, live
service, Git state, security setting or alert disposition was touched.

This is a reviewable candidate, not an integrated or deployed production proof.

## Exact finding and evidence

The reviewed CodeQL result is analysis **1974871800**, for PR1592 head
**9e4c0c6dafe70f76fad6d0a45f3e55e2df5e75b5**. Root retrieved the original SARIF
at `/tmp/fabric-quota-9e4-codeql.sarif` on M2 and flattened its source/sink flows
at `/tmp/fabric-quota-codeql-flow-review.json`. The original SARIF SHA256 is:

`5eca8fead3139b9e277474df05eadf274fa7680b5c5331a61730a3c6d67f4f8d`

The adjudication combines that exact trace, supplied by root, with independent
local static review and dummy-value subprocess experiments. This lane did not
independently download or rewrite the SARIF file.

| Head-9e4 alert IDs | Observed path | Adjudication |
| --- | --- | --- |
| 177, 178 | Existing research picker and account-pairing picker fixture print routing lines | Public account-name projection; no API-key value is selected by this flow. |
| 179 | Native source `cmd_pick`, line 781 | Prints the selected account alias. |
| 181 | Native source `cmd_status`, line 811 | Prints account aliases, capacity, usage and cooldown metadata. |
| 182, 183 | Native candidate/source picker `print(line)`, lines 2577/2570 | Routing field `KEY` contains an account alias, not the credential value. |
| 180 | Native source `cmd_env`, line 789 | Actual API-key value is written to stdout as a shell export. Requires a real custody repair. |

For the six metadata findings, the actual trace starts at
`tp.get("api_keys")` on source line 187, traverses `entry.get("name")` on line
188, the `name` entry in the projected dictionary, and `key_names()` on line
202. It then reaches `pick()`/`status_lines()` or the route formatter. The
analyzer marks the entire private-config collection sensitive and propagates
that taint through its public `name` field. The trace does not project the
`api_key` field at those six sinks. The configuration contract explicitly
distinguishes a public account alias from its private key value.

The actual credential-output trace additionally traverses `entry.get("api_key")`
on line 189 or the legacy key on line 195, `_key_value()`, and
`env_export_line()`. The former Qwen wrapper captures this export into `_exp`
before its late `set +x`; ordinary `bash -x` therefore logs the secret-bearing
assignment. A dummy-value reproduction confirmed this old-order leak. The
current tests establish both the retired interface and a direct child handoff
under `bash -x`, independently of the wrapper's early tracing disable.

CodeQL's official query documentation describes stdout as a sensitive logging
sink: <https://codeql.github.com/codeql-query-help/python/py-clear-text-logging-sensitive-data/>.
The precise field-flow evidence above, rather than a general claim about
scanner imprecision, is the basis for the six metadata adjudications.

## Implemented boundary

`bailian_keys.py check-key NAME` privately checks the exact selected account and
produces no stdout. The wrapper uses it in the existing wait/release path, so
failure before launch still releases its newly acquired slot and respects the
existing key-wait budget. This reads the incumbent credential store; it creates
no new metadata, readiness or lease authority.

`bailian_keys.py exec-codex NAME -- ARGS...` privately revalidates the account,
loads its key and calls:

```python
os.execvpe("codex", ["codex", "exec", *args], child_env)
```

Only the fixed Codex exec entry point is supported. No executable parameter,
shell evaluation, child fork, automatic retry or slot mutation is introduced.
For a leased child, the helper independently requires `NAME == POOL_ACCOUNT`
before reading a credential. Invalid account/mismatched lease returns 78;
missing, malformed, empty or NUL-bearing credentials return 75 before Codex
starts. Private-config/exec exception strings are not formatted into errors.

The wrapper disables inherited tracing and unsets an inherited
`BAILIAN_API_KEY` at entry. Projection, selection, cleanup and ledger helpers
therefore receive no parent credential. Both initial and resume launch branches
call the new helper. The wrapper carries only the account name; it never
captures a credential value.

The former `env NAME` command remains an explicit fail-closed compatibility
diagnostic: it returns 78 with `BAILIAN_ENV_EXPORT_RETIRED` without reading
config. `env_export_line()` is removed. This deliberately retires that old
internal interface in the new generation.

## Compatibility and proof limits

The tests verify exact initial and explicit-resume argv, stdin, caller prompt
preservation, completed response publication, leased automatic continuation,
unleased auth rotation on the same thread, and a leased quota failure without
account substitution. The Codex PID equals the helper PID; account slot files
remain owned by the wrapper PID and are removed on completion/failure.

Unknown worker failure remains its original nonzero status without retry;
unconfirmed framing remains 77; direct child termination remains the actual
signal and the Bash wrapper returns 143 for SIGTERM. Executable lookup and
permission failure retain shell-compatible 127 and 126. There is no positive
completion or replay after an uncertain worker failure.

A key disappearing after the silent preflight is rejected again at exec, with
75 and no worker launch. The secret is loaded afresh for each initial/resume
process. A credential owner replacing the value under the same account alias
between turns will consequently supply the new value on the next turn, rather
than retaining the old wrapper-cached secret. Account/lease identity is not
changed by this reload.

The installed Codex must be an executable resolved through PATH; exported shell
functions/aliases or shell fallback for an executable without a usable binary
format/shebang are not part of the new helper interface. Ordinary executable
and shebang-based Codex installations retain their existing argument/I/O
contract. Codex still receives its provider credential in its environment;
this repair does not claim to protect against a compromised Codex executable or
to redact credential text a worker deliberately emits.

Fixtures bind helper file paths directly after import and bind the wrapper's
single provider-home path in its test copy. They never repurpose `HOME` or
`CODEX_HOME`, and construct a small test environment without reading inherited
provider credentials. The fake Codex records only account-match booleans and
public invocation/PID data. Local validation ran on this Linux executor; M2
and integrated repository checks remain root's next validation step.

## Scoped disposition and immutable preimages

Recommend independently substantiated false-positive adjudication only for the
six named metadata alerts, after matching any final-head alerts to the same
source/field/sink flow. Do not disable the rule, change query heuristics,
introduce a sanitizer, obfuscate `api_keys`, or invent a public metadata store.
Alert 180 must close through the active custody repair; it is not a metadata
false positive. This lane has taken no alert-disposition action.

The eight incumbent functions `list_keys`, `key_names`, `_key_value`,
`usable_names`, `pick`, `status_lines`, `cmd_pick` and `cmd_status` have unchanged
ASTs. Public `pick`/`status` fixture outputs contain aliases and no configured
private values. Thus the metadata API was neither narrowed nor rewritten to
hide the analyzer's flow.

All original source preimages remain byte-identical in this lane. Root's
proposed integration may preserve the obsolete helper as explicitly
non-importable `source/bailian_keys.py.preimage`, provided the fixed builder
requires the active candidate, verifies the exact original SHA, and cannot
fall back to executing/publishing the retired helper. That is evidence
preservation after an actual runtime fix. It must not become a means to
publish the old secret-output implementation outside analysis.

The active helper's changed hash requires the normal host-readiness refresh
under the existing validator-hash contract. This draft does not refresh,
synthesize or reuse observations. Historical research and flat-install
wrappers/helpers remain outside this generation and are untouched.

## Files and integration

| File | SHA256 |
| --- | --- |
| Original `source/bailian_keys.py` | `435dad2bcde27384c4c47edaea5afdf7f248d10229558193414b105664a9759c` |
| Original `source/qwen_exec.sh` | `9173abf57c81e1b53cb555f92fc01a0942396b744ae10f3a652014e5b69306c1` |
| Candidate `bailian_keys.py` | `77052ba1b71f684ffe72962519773928b82cea39fa9d79cd974156d23aa627d2` |
| Candidate `qwen_exec.sh` | `34e5265f98c8fe5f413cda4775abaad43a76441ec59f4a4c10cb98aadf75bed1` |
| `test_credential_custody.py` | `fd4a99ba1464da18832a44a869d149b5917d97afd927f9fd8ca44447beb4a2bc` |

The adjacent `credential-custody.patch` is a review diff against the exact
source preimages; root should integrate the two candidate files as native
overlays and preserve original evidence separately. The test currently expects
the two candidate files beside itself. Root may bind that test source location
to `../candidate` when installing it into the repository test layout.

Reproduction in this isolated directory:

```sh
python3 -m unittest -v test_credential_custody.py
bash -n qwen_exec.sh
```

The required integrated checks, exact-head security adjudication, independent
review, immutable release build, host-readiness refresh and live production
proof remain with root. This lane is frozen at the hashes above.
