# Hermes vault fill through the original Workbench browser owner

## Status and consumer

This opt-in source slice connects one host-selected Hermes login item to the
existing authenticated Workbench browser service. It adds
`prepare_browser_credential_fill(browser_ref, grant_ref)` to service v3. The
returned action is executed and reconciled through the existing
`run_browser_action` and `reconcile_browser_action` tools and ActionArtifactStore.
Service v1/v2, fixed worker channels and ordinary browser grants do not acquire
credential authority automatically.

Source qualification, ordinary CI, installed runtime qualification, account
enrollment, field filling and successful authentication are distinct outcomes.
This source change alone proves none of the installed/account outcomes. The
original Ubuntu1 C26 administrator-connection refusal remains unretried. The
macOS/Homebrew B1 runtime is the currently supported installed closure; Linux CI
uses disposable engines and does not qualify a Linux fleet installation.

## Existing owners and sequence

1. The existing host-selected Workbench service config supplies a v3 credential
   narrowing. Its caller/project/operation/generation lease remains the authority
   owner. One runtime adopts one grant once. No account discovery or auto-enrollment
   occurs.
2. JWT authentication and the normal browser process/resource checks precede public
   preparation. Preparation freezes a SHA-256 of the complete secret-free selected
   grant, actual resource and scope binding, caps its deadline, and returns an
   existing signed action token. It does not read a key, ciphertext or password.
3. Original execution claims the existing durable action artifact and rechecks
   current runtime authority, the same relay identity and the complete selection
   digest. Reusing a grant label cannot redirect a prepared action to another
   account, item, origin or vault directory.
4. On the same relay RPC gate, the original owned Node child first qualifies a
   unique visible editable login form in its single held Page/main Document.
   The private prepare response contains only a fresh target nonce.
5. Only after that response does the original Python relay open the selected vault
   directory and files using descriptor-relative, no-follow, read-only operations.
   The directory must match enrolled device/inode, same UID and mode 0700; both
   files must be regular, single-link, same-UID 0600 files. Size, stable identity,
   metadata and the named entry are checked. No creation, unlock, chmod, backend
   fallback or decryption occurs in the relay.
6. The same private child receives the captured key/ciphertext outside the normal
   MCP tools/call path. It rechecks target and trusted expiry, invokes the pinned
   Fernet decoder, and selects exactly one item matching item ID, account and
   canonical HTTPS origin. It decrypts the donor's whole vault document privately;
   the donor format does not provide per-record encryption.
7. Before any input/change event, the child registers password and identifier
   representations in the exact shared upstream redaction map. It reclassifies
   the held fields before each write and verifies their native values through
   Playwright utility-world inputValue. It never presses the login button.
   Passwords containing NUL or line breaks refuse before writing: native password
   fields cannot preserve those values, and silently normalizing a credential
   would select a different secret.
8. A closed result returns through the original relay and durable action ledger.
   Transport loss leaves the original claim uncertain. Reconciliation never makes
   a second fill attempt.

There is no new vault writer, auth service, identity registry, effect ledger,
browser owner, queue, retry mechanism, daemon or provider route. Executive OS,
Agent OS, GitHub and the existing service retain their respective ownership.

## Private v3 selection

The normal v2 configuration fields remain required. V3 changes `schema` to
`mastermind.workbench_action_service.v3` and adds two closed objects:

```json
{
  "credential_grant": {
    "schema": "mastermind.workbench_browser_credential_grant.v1",
    "grant_ref": "credential:<32 lowercase hex characters>",
    "backend": "hermes-fernet-v1",
    "vault_directory": "<absolute selected existing directory>",
    "vault_device": "<observed integer>",
    "vault_inode": "<observed positive integer>",
    "item_ref": "vault_<12 lowercase hex characters>",
    "account_identifier": "<exact selected account>",
    "origin": "https://<exact canonical host and optional nondefault port>",
    "expires_at_ms": "<integer deadline within original service lease>"
  },
  "credential_runtime": {
    "runtime_root": "<absolute B1 installation container>/runtime",
    "manifest_sha256": "<owner-ratified install manifest SHA-256>"
  }
}
```

The example is a field guide, not a runnable grant: angle-bracket values must be
selected from the actual owner and integer fields must be JSON numbers. The
configuration contains no password, vault key or encrypted vault body. Account
metadata remains private to the selected service configuration. The public tool
accepts only the browser and credential references.

V3 refuses a source root or Python interpreter differing from the running service.
The credential narrowing is unavailable to persistent browser profiles. A caller,
scope, host, boot, process, generation or lease mismatch refuses dispatch. A
runtime revocation prevents future dispatch; it is not retroactive cancellation
of a fill already admitted into the original private child.

## Runtime and source custody

The B1 installer retains its existing closed installation manifest, complete
node_modules/Chromium closure and exact Node/library rules. It installs the selected
npm dependencies and copies one fixed first-party entry into
`node_modules/@mastermind/workbench-vault/child.cjs` before the same normalization
and manifest generation. The entry and dependencies must be qualified against
reviewed source pins. A new installation manifest requires explicit ratification
by its existing owner; it must never be learned as trusted merely because a file
currently exists on a host.

The original relay holds the installation container descriptor through its
existing Popen. A derived bootstrap verifies the held manifest, Node, unchanged
MCP CLI identity and fixed credential entry, then changes into the held container
and execs relative paths. A replacement at the old path cannot select another
runtime. The original v1 bootstrap bytes and CLI-only launch remain unchanged.
The selected Node loader constrains nonbuiltin module resolution to the attested
node_modules closure. The relay still owns the only child handle and the original
process group remains the final physical cleanup owner.

The private child creates one fresh Chromium BrowserContext, then supplies that
same context to Playwright MCP's context-getter API. `browser.isolated: false` at
that API adopts the explicitly created owned context; it does not attach a real
user profile or CDP session. Downloads are disabled/cancelled and service workers
are blocked. EOF, malformed input and output errors join the same idempotent close
owner. Startup and server-connect failures close any created browser.

## Secret and artifact behavior

Passwords are absent from the public tool schema, prepared action, action ledger,
model-facing request/result and normal MCP tools/call transcript. The private
relay captures encrypted material; only the owned child decrypts and fills it.
Python/JavaScript immutable strings and garbage collection do not provide a
locked-memory or cryptographic-erasure guarantee.

The selected upstream browser can persist text console/snapshot artifacts. This
implementation permits those **known-value-redacted text artifacts**; it does not
claim artifact absence. The shared map is logically monotonic for the child
lifetime and globally reordered longest-first without changing the map object,
so delayed writers and overlapping old/new values retain redaction. Raw,
JSON-escaped, YAML single-quoted, URL/form-encoded and common HTML representations
are covered and exercised in qualification. Capacity exhaustion refuses another
fill before writing rather than discarding prior secrets.

Binary/image/resource responses, screenshot/console/network tools, output filenames,
credential aliases and known secret representations in generic tool arguments are
refused in credential mode. Keyboard access is narrowed to navigation keys;
clipboard shortcuts, modified clicks and context-menu clicks are refused. Public
snapshot text is additionally scrubbed of private aliases. Fixed private protocol
constants are validated separately, so a password equal to `FILLED` does not
corrupt the original effect receipt.

An authorized destination website necessarily receives the submitted field
values. Deliberate arbitrary encoding or splitting by that website is outside
the known-value redaction guarantee. A general shell running as the vault-owning
UID could directly read the files; this slice does not silently enable such a
shell. Credential use must remain within the actual host/account grant and
capability owner when broader native tools are eventually admitted.

## Effect interpretation

| Result | Meaning |
| --- | --- |
| `APPLIED / FILLED` | Both native field values matched the selected credentials after the held-target checks. No login/submit or authenticated session is asserted. |
| `NOT_APPLIED / TARGET_REFUSED` | The child refused before a credential write because the target did not meet the fixed classifier. |
| `NOT_APPLIED / ITEM_REFUSED` | The selected encrypted record could not be qualified; no credential write was attempted. |
| Other closed `NOT_APPLIED` code | The identified permission, file, protocol or capacity boundary refused before writing. |
| `EFFECT_UNKNOWN / FILL_UNCERTAIN` | A write may have occurred, including a partial identifier write or failed native verification. |
| Original relay response lost | Original action remains `EFFECT_UNKNOWN`; no new action or automatic retry is created. |

A field replaced, hidden, moved to another form, switched to new-password, or
accompanied by another eligible password target no longer qualifies. Navigation
invalidates the held document. A change triggered by the first field's event can
therefore produce uncertainty while refusing the second write.

## Reused upstream engines and licenses

| Component | Exact source | Use and license |
| --- | --- | --- |
| Hermes `VaultStore` | NousResearch/hermes-agent `1c0cd667746d3395fe9e1b6c74f8f85952486f18`; `vault_store.py` blob `746fbf8a771a7834e1b06a01df96a74df75477ce` | Existing vault owner/format; full unmodified writer fixture and MIT license retained. Only environment/file helpers are supplied by the disposable fixture. |
| Playwright MCP | `@playwright/mcp@0.0.79` | Actual MCP server and context integration; Apache-2.0 package/license retained by installation. |
| Playwright/Core | `1.63.0-alpha-2026-08-05`, source `5f58876dc84d69008907e75d818baf55b0f78dc1` | Actual owned Chromium and DOM/utility-world verification; Apache-2.0. |
| Fernet | `fernet@0.3.3`, csquared/fernet.js `76936e1e70c9f8c98b18a71660f0e97260524c95` | Unchanged selected decoder; MIT. |
| Fernet dependencies | `crypto-js@4.2.0`, `urlsafe-base64@1.0.0` | Exact npm lock/integrities; MIT, with urlsafe-base64's license retained in its README. |

Primary source links: [Hermes writer](https://github.com/NousResearch/hermes-agent/blob/1c0cd667746d3395fe9e1b6c74f8f85952486f18/vault_store.py),
[Playwright source](https://github.com/microsoft/playwright/tree/5f58876dc84d69008907e75d818baf55b0f78dc1),
[Fernet source](https://github.com/csquared/fernet.js/tree/76936e1e70c9f8c98b18a71660f0e97260524c95).
No proprietary implementation, asset, branding or corpus is copied.

## Qualification and activation frontier

The focused source suite exercises the actual shared action ledger, runtime
credential projection, authenticated JWT/FastMCP entry, descriptor capture and
final anchored exec. Transport/host inspector fixtures are explicitly identified.
The Node source suite checks map lifetime/ordering, alias refusal, binary/file and
clipboard restrictions, private receipt integrity and uncertain-effect behavior.

The ordinary `Workbench credential engine` PR workflow installs the exact npm
lock and its selected disposable Chromium. Its real-engine tests:

- Write synthetic ciphertext with the full unmodified Hermes writer, then decode
  it with the actual unchanged Node Fernet dependency. Wrong key, tampering,
  truncation, wrong item/account/origin refuse.
- Exercise the real McpStdioSession, private relay handler, MCP server and owned
  browser. Verify native fields, actual persisted redaction, generic tool refusal
  and original child cleanup.
- Exercise actual held-DOM invalidation, partial write and overridden page getter/
  setter cases. Trusted Node expiry still refuses when page time is manipulated.
- Compare installed dependency bytes with the selected source pins.

The dedicated tests require their ordinary CI opt-in. Skips in a generic local
test run do not count as real-engine success. The fixture HTTPS route serves
synthetic responses; it is not a SaaS login, account grant, network policy proof,
installed macOS closure proof or live Executive admission.

Installed activation must use the original host connection and existing service
owner: reconcile original effects, qualify the intended immutable source/runtime,
enroll the exact existing vault item with a bounded lease, qualify the real
authenticated public prepare/run/reconcile path, then inspect original artifacts
and cleanup. Do not replay the C26 denial through another host, silently widen
worker/native tools, or describe field fill as successful login.
