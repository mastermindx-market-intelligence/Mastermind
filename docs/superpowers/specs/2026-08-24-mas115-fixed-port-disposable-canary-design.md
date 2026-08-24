# MAS-115 Fixed-Port Disposable Multilogin Canary Repair

**Date:** 2026-08-24

**Status:** Architecture approved in chat; committed written spec awaiting Chairman review; `SPEC_ONLY`

**Carrier:** `codex/mas115-fixed-port-20260824-9ju4rk`

**Protected Mastermind base:** `7136b30a63ac47bdfc0a44e4d5080e0cd345de42`

**Pinned Macro CI dependency:** `256c757b3c4f0ec759571c29a30a71387d0a18f8`

**Owning program:** `WS:CHAIRMAN-CONTROL-ROOM`, MAS-115 P0B non-seat canary

## 1. Decision

Repair the existing MAS-115 Multilogin disposable-profile canary by assigning
one program-owned loopback port, `65535`, to the canary origin and by adding one
narrow, idempotent configuration operation for the already-provisioned stopped
disposable profile.

The operation may preserve the profile's existing core auto-update preference
and change only the API representation of port-scan protection:

```text
{
  "profile_id": "<the provisioned disposable profile id>",
  "auto_update_core": <the exact current boolean read from Profile Metas>,
  "parameters": {
    "flags": {
      "ports_masking": "mask"
    },
    "fingerprint": {
      "ports": [65535]
    }
  }
}
```

This is Multilogin API encoding, not UI terminology. The Multilogin UI calls
the resulting behavior **Custom**: supported local ports remain masked except
for the explicitly whitelisted port. The current API documentation accepts
`mask` or `natural` for `ports_masking`; its current profile-create example
combines `"ports_masking": "mask"` with `"ports": [65535]` to represent the
whitelist. No caller may supply a port or add any arbitrary field.

The configured value persists on this dedicated disposable profile so future
canary runs are unattended. The canary remains loopback-only. It does not gain
a public origin, a tunnel, arbitrary navigation, profile-content access, or a
general Multilogin profile-update capability.

## 2. Outcome and completion boundary

The observable mission is: a fresh operator process can prove the full MAS-115
C0-C10 disposable-browser matrix through the real Multilogin cloud, launcher,
Mimic, WebDriver, and local-origin path, then stop only the profile it started,
without Chairman interaction and without changing any Chairman seat.

This specification does not claim that outcome. The current state is:

| Capability | State | Current evidence |
|---|---|---|
| Keychain credential handoff | `PROVEN_LIVE` | Secret-owning helper authenticated without exposing the token. |
| Complete bounded profile search | `PROVEN_LIVE` | Exact stopped disposable was found through the cloud census. |
| Exact-profile start and WebDriver session | `PROVEN_LIVE` | The provisioned Mimic profile started and accepted a WebDriver session. |
| Page membership and exact-profile cleanup | `PROVEN_LIVE` | Navigation returned membership evidence; cleanup stopped the disposable profile and preserved the other profile-process count. |
| Browser request observed by local origin | `BROKEN` | The browser reported navigation but the loopback server observed no request. |
| Full C0-C10 receipt | `BUILT_NOT_PROVEN` | The matrix has not passed through the real production path. |
| Chairman foreground-seat proof | `NOT_RUN` | This repair is non-seat only and must not touch a Chairman seat. |

The repair becomes `PROVEN_LIVE` only after the exact merged release produces a
full live C0-C10 receipt, cleanup passes, the disposable profile is stopped,
and before/after Chairman-seat and other-profile evidence is unchanged. A
green test, commit, pull request, merge, launch, Slack message, or `QUEUED`
runtime state is not equivalent to that proof.

## 3. Current diagnosis

The canary already crossed every boundary up to page navigation. The local
origin independently served a direct self-test and a separate-process request.
The same Multilogin browser failure reproduced with:

- `127.0.0.1`, `localhost`, and IPv6 loopback;
- the Chromium proxy-bypass flag;
- three-second and forty-five-second observation windows;
- macOS firewall block-all disabled and no relevant Chromium sandbox or
  network-denial evidence;
- the exact disposable profile started, a valid WebDriver session created,
  navigation accepted, and cleanup successful.

Multilogin documents that port-scan protection defaults to Masked, that Custom
masks all supported ports except an explicit whitelist, and that Real exposes
the host's port results. The existing canary chooses a random ephemeral port,
so a persistent profile whitelist cannot know which port to expose. The most
coherent current explanation is therefore that Mimic masks the randomly chosen
local service port.

That explanation is a falsifiable inference, not permission to mutate. A
secret-safe read-only Profile Metas preflight must positively classify the
exact disposable profile before the update surface is armed. If the profile is
already `natural`, returns an unknown mode, has a non-empty unexpected port
list, or cannot be classified exactly, the hypothesis is false or unproven and
the operation refuses without an update.

A read-only live Profile Summary call on 2026-08-24 returned an empty port list
and no explicit override in `masking_options`, consistent with the documented
default-masked state. That reduced observation is diagnostic evidence, not the
modification gate. The modification gate uses Profile Metas because the
official response exposes the exact `parameters.flags.ports_masking`,
`parameters.fingerprint`, folder/profile identity, current ownership, and
`is_auto_update` boolean in one bounded profile record.

The access token expired before a second read-only preference query. No update
was attempted. Credential freshness remains a normal admission gate.

## 4. Canonical ownership and no-rebuild boundary

- Executive Runtime remains the sole Job/Attempt/Worker/Event lifecycle and
  CEO-intent admission authority.
- Agent OS remains the durable organizational record for workstreams,
  decisions, discoveries, and handoffs. It does not become a browser queue.
- GitHub remains implementation and evidence truth.
- The existing `integrations.chairman_surfaces.nonseat_canary` flow remains the
  only canary lifecycle. This work extends it; it does not create another
  launcher, browser controller, identity registry, retry plane, or receipt
  store.
- The existing MAS-115 provision remains the only disposable-profile address.
  Its schema advances from v2 to v3 so it carries the exact vendor, folder,
  profile, browser type, disposable acknowledgement, and a fixed origin-policy
  identifier rather than a caller-shaped origin or port.
- The existing macOS Keychain helper remains the only live token source. The
  token never enters argv, environment, a repository file, a temporary file,
  a receipt, or model-visible output.
- The one configuration operation and the subsequent live canary stay bound
  to this single carrier until the outcome is canonically reconciled.

## 5. Dedicated loopback origin

### 5.1 Fixed address

The canary owns `http://127.0.0.1:65535` and no other origin. Port `65535` was
successfully bound on the Chairman host during the 2026-08-24 design check and
is the port used by Multilogin's current official profile-create example.

The port is a source constant. It is not a CLI argument, environment variable,
provision field, configuration-file value, fallback list, or dynamically
allocated socket. The origin binds IPv4 loopback only; it never binds
`0.0.0.0`, a LAN address, IPv6 wildcard, or an external interface.

Provision schema v3 removes `benign_origin` and replaces it with the literal
`"origin_policy": "mas115_fixed_loopback_v1"`. The existing private v2
provision may be migrated atomically without prompting only when it passes all
current v2 safety checks and its legacy origin equals the one historical setup
value, `http://127.0.0.1:7777`. The migration preserves the exact vendor,
folder, profile, browser type, and acknowledgement, removes the legacy origin,
adds the literal policy identifier, writes with mode `0600`, reloads through
the v3 validator, and occurs before Keychain or vendor access. Any other legacy
origin or field drift refuses without a rewrite. The migrated policy derives
`127.0.0.1:65535` only inside the program.

### 5.2 Refusal ordering

Every setup and canary invocation attempts an exclusive bind to
`127.0.0.1:65535` before reading Keychain or calling any vendor endpoint. If
the bind is unavailable, unsupported, redirected, or reports a different
address, the operation returns a fixed `CANARY_PORT_UNAVAILABLE` refusal. It
does not choose a random port or retry another port.

The loopback server still exposes only the existing five bounded canary paths:
`/a`, `/b`, `/state/set`, `/state/check`, and `/auth`. It does not serve files,
accept request bodies, execute scripts, proxy traffic, or reveal private data.

## 6. Read-only configuration preflight

The setup command is named `configure-canary-port`. It is available only from
the existing secret-owning vendor helper and has no generic URL, method, body,
profile ID, port, or field parameters.

Before Keychain access, it must prove:

1. the provision file is schema-valid v3 (or was just safely migrated from the
   one accepted v2 shape), current, private, acknowledged as disposable, and
   names Multilogin Mimic;
2. all three current Chairman seat bindings are present, fresh, unambiguous,
   and none collides with the disposable profile;
3. the exact dedicated loopback port is available;
4. the local reduced environment census identifies the exact disposable
   profile and says it is stopped.

After Keychain access, it performs only documented bounded reads:

1. a complete `/profile/search` census for exact folder/profile membership and
   current cloud ownership/lock state;
2. launcher `/api/v1/profile/status/p/{profile_id}` for exact stopped state;
3. `POST /profile/metas` with exactly `{"ids":["<profile_id>"]}`.

Profile Metas must return exactly one profile record whose profile ID and
folder ID match the provision, whose `in_use_by` is empty, whose browser type
is Mimic, and whose `is_auto_update` is a real boolean. The helper reduces the
private response internally. It may emit only fixed classifications, booleans,
counts, and stable digests; it never emits the profile ID, name, notes, proxy,
fingerprint payload, credential, or response body.

Accepted port states are closed:

- `DEFAULT_MASKED`: `ports_masking == "mask"` and `fingerprint.ports` is absent
  or an empty list. This is the only state that permits the one-time update.
- `EXACT_CONFIGURED`: `ports_masking == "mask"` and
  `fingerprint.ports == [65535]`. This is idempotent success and sends no
  update.
- every other state is `UNSUPPORTED_PORT_STATE` and sends no update.

The helper computes a private canonical digest of all returned profile metadata
except the two target port fields and expected vendor audit fields
(`last_update_at` and `last_updated_by`). This preservation digest is compared
after the update; private material used to compute it is never logged.

## 7. One-time modification protocol

### 7.1 One-shot modification authority

Chairman approval of this exact committed written specification authorizes one
Profile Partial Update on this carrier after the implemented preflight reports
`READY_TO_CONFIGURE`. It does not authorize a different profile, port, body,
endpoint, carrier, retry, or profile state. No additional confirmation prompt
is required when every frozen gate remains exact; this removes the Chairman
from the routine loop. If the profile is not `DEFAULT_MASKED`, any safety input
drifts, the effect becomes ambiguous, or the carrier changes, this authority is
spent or inapplicable and the operation stops for reconciliation rather than
assuming broader permission. Once exact configuration is proven, ordinary
canary runs require no Chairman action.

### 7.2 Exact request

The helper sends one `POST https://api.multilogin.com/profile/partial_update`
request with:

- the exact provisioned `profile_id`;
- `auto_update_core` copied without transformation from the Profile Metas
  `is_auto_update` boolean, preventing Multilogin's documented reset-to-true
  behavior from changing a second setting;
- `parameters.flags.ports_masking` fixed to `"mask"`;
- `parameters.fingerprint.ports` fixed to `[65535]`.

A structural allowlist constructs and validates the final serialized JSON. A
request containing any other top-level key, flag, fingerprint member, port,
profile, folder, proxy value, startup behavior, core version, name, note,
storage value, URL, tag, cookie, or command parameter is impossible through
the public command and is rejected internally before transport.

The previous blanket falsifier that forbids every profile update is superseded
only for this exact operation. The stronger replacement law is: one stopped,
non-Chairman disposable profile may receive only the exact port whitelist plus
the unchanged auto-update preservation value; every other profile mutation
surface remains forbidden.

### 7.3 Result classification and reconciliation

Definitive success requires HTTP 200 and the exact documented envelope:

```json
{
  "status": {
    "error_code": "",
    "http_code": 200,
    "message": "Profile successfully updated"
  },
  "data": null
}
```

Even that response is not final proof. The helper immediately re-runs exact
Profile Metas and requires `EXACT_CONFIGURED`, the unchanged
`auto_update_core` value, and an unchanged private preservation digest. It then
re-runs exact cloud ownership and launcher stopped-state reads.

An explicit 401 or 403 is `AUTH_EXPIRED_NO_PROOF`; an explicit schema-valid
vendor rejection is `REJECTED_NO_PROOF`. A timeout, connection loss,
oversized/malformed response, unexpected status, mismatched response envelope,
or process interruption after request dispatch is `EFFECT_UNKNOWN`.

`EFFECT_UNKNOWN` is never retried. The same carrier must reconcile by running
the read-only preflight:

- `EXACT_CONFIGURED` plus the preservation checks proves the intended effect;
- `DEFAULT_MASKED` proves no intended effect but does not authorize an
  automatic retry; a new exact Chairman instruction is required;
- any other result remains blocked for Chairman review.

The configuration command never starts or stops a profile. Cleanup ownership
continues to belong only to the canary launch boundary.

## 8. Unattended canary flow after configuration

After `EXACT_CONFIGURED` is proven, each canary invocation follows this order:

1. validate the current provision and fresh three-seat non-collision census;
2. bind `127.0.0.1:65535`, verify the exact server address, and run the local
   direct self-test;
3. open the fixed Keychain pipe and obtain a current credential inside the
   secret-owning process;
4. perform the complete cloud profile census and exact stopped/ownership
   preflight;
5. read Profile Metas and require `EXACT_CONFIGURED`; normal canary execution
   has no profile-update surface;
6. mint the exact-profile cleanup lease immediately before the single launch
   request;
7. start the exact profile, create the bounded WebDriver session, and execute
   the existing C0-C10 matrix against the five loopback paths;
8. stop only the exact profile covered by the cleanup lease;
9. prove the exact disposable profile is stopped, other profile-process count
   is unchanged, Chairman seats are unchanged, and the port-settings
   classification remains `EXACT_CONFIGURED`;
10. emit only the existing redacted receipt vocabulary and fixed new
    configuration classifications.

Credential expiration refuses before lifecycle modification. A lost or
ambiguous launch response retains the exact-profile cleanup lease and follows
the existing contained-cleanup behavior. The configuration endpoint is not
reachable from ordinary matrix execution.

## 9. Test and falsifier matrix

Implementation is test-driven. Tests must fail before the production change
and cover at least these cases:

### Dedicated port

- the loopback server binds exactly `127.0.0.1:65535`;
- a busy port refuses before Keychain, cloud, launcher, or browser access;
- there is no caller-selected port, fallback port, public bind, or tunnel;
- the provision and navigation contracts reject any competing origin.

### Read-only preflight

- incomplete, stale, conflicting, or colliding Chairman census refuses before
  Keychain;
- missing, malformed, running, owned, locked, wrong-folder, wrong-browser, or
  ambiguous disposable state refuses;
- truncated or changing paginated census is uncertainty, not absence;
- Profile Metas must contain exactly one matching record and a boolean
  `is_auto_update`;
- `DEFAULT_MASKED` is the only mutable pre-state;
- `EXACT_CONFIGURED` is idempotent and sends zero updates;
- `natural`, an unknown mode, unexpected port order, duplicates, extra ports,
  non-integer ports, or response-shape drift refuses without mutation.

### Mutation boundary

- the serialized request equals the exact allowlisted body byte-for-byte after
  canonical JSON normalization;
- the preservation boolean must equal the read value; callers cannot select
  it;
- an extra key at any nesting level refuses before transport;
- a different profile, folder, port, or endpoint is structurally unreachable;
- the update client exposes no generic request method;
- the credential cannot appear in argv, environment, stdout, stderr, receipts,
  exceptions, or fixtures;
- explicit rejection sends no retry;
- ambiguous effect emits `EFFECT_UNKNOWN`, sends no retry, and permits only the
  read-only reconciliation path;
- post-read mismatch in target state, auto-update value, preservation digest,
  ownership, or stopped state prevents success.

### Existing lifecycle and privacy law

- every existing C0-C10 hostile, mutation, cleanup, wrong-identity, and
  bounded-response test remains green after its narrow policy update;
- no WebDriver pointer, keyboard, form, script-evaluation, cookie-read,
  storage-read, download, arbitrary-command, or private-page-content surface is
  added;
- Chairman seat lifecycle is never called;
- cleanup targets only the exact leased disposable profile;
- raw process arguments, private URLs, IDs, response bodies, and profile
  contents remain outside receipts.

## 10. Live acceptance matrix

The live operation is accepted only when all of the following are captured
from the exact merged release:

1. protected-master SHA, merged SHA, changed files, and green authoritative CI;
2. preflight `EXACT_CONFIGURED`, dedicated port available, exact disposable
   stopped, and current three-seat non-collision proof;
3. complete C0-C10 PASS through the real Multilogin/Mimic/WebDriver/loopback
   path, including `benign_origin_observed=true`;
4. cleanup PASS, exact disposable stopped, no leaked exact-profile process, and
   the other-profile process count unchanged;
5. postflight `EXACT_CONFIGURED`, unchanged auto-update value, unchanged
   preservation digest, and unchanged Chairman seat census;
6. no profile update during the matrix itself;
7. no token, private identifier, URL, profile content, cookie, session,
   fingerprint payload, proxy credential, or raw argv in any evidence;
8. deployment and health proof are reported separately from CI and merge;
9. MAS-115 remains P0B until the independently governed Chairman foreground
   proof is completed.

## 11. Rejected alternatives

### Manual Multilogin UI configuration

Rejected as the durable workflow because it leaves the Chairman in the loop,
cannot enforce an exact payload, and does not provide machine-verifiable
idempotence or ambiguous-result reconciliation. The UI remains a human audit
surface, not the control plane.

### Public origin or tunnel

Rejected because the canary is specifically meant to prove local disposable
browser control. A tunnel adds egress, another availability dependency, a
larger attack surface, and a second route whose success would not prove the
intended local path.

### Random ephemeral port

Rejected because a persistent profile whitelist cannot anticipate a random
port. Silent fallback would make receipts incomparable and would recreate the
current failure.

### Real port-scan mode

Rejected because it exposes more host state than the canary needs. The single
port whitelist is the least-authority solution.

### Quick profile

Rejected because it is deleted on stop and cannot provide durable,
independently re-readable configuration and C4 persistence evidence.

### Generic profile-update adapter

Rejected because it would create an authority surface capable of mutating
Chairman seats or unrelated fingerprint, proxy, storage, navigation, or core
settings. This design permits one literal endpoint and one literal effect.

## 12. Durable-record reconciliation

Current Agent OS records still describe the older bearer/search failure and a
do-not-rerun blocker. Those records are stale relative to the now-proven
credential, cloud search, launcher, WebDriver, and cleanup path, but they remain
historical evidence rather than authority.

After implementation and live proof, the normal Macro Agent OS carrier must
record:

- a discovery that the old credential/search blockers were repaired;
- this port-masking root-cause ruling and the exact fixed-port safety boundary;
- the current capability ledger and live C0-C10 result;
- any remaining Chairman foreground or host-install/OAuth gate;
- the exact next action so a fresh session does not depend on this chat.

No new durable lifecycle or queue is created for this repair.

## 13. Primary sources

- [Multilogin browser fingerprint settings](https://multilogin.com/help/en_US/profile-settings-fingerprint-section)
  — Masked, Custom whitelist, and Real port-scan behavior.
- [Multilogin profile create guide](https://multilogin.com/help/en_US/creating-a-profile-with-postman)
  — current `ports_masking` and `fingerprint.ports` example using port `65535`.
- [Multilogin profile update guide](https://multilogin.com/help/en_US/updating-a-profile-with-postman)
  — partial-update behavior and success semantics.
- [Multilogin public API collection](https://documenter.getpostman.com/view/28533318/2s946h9Cv9)
  — `POST /profile/metas`, `GET /profile/summary`,
  `POST /profile/partial_update`, exact response envelope, field vocabulary,
  and the auto-update preservation warning.

## 14. Review gate

This design freezes the architecture only. Implementation planning begins only
after the Chairman reviews and approves this written specification. That
approval also supplies the one-shot authority described in section 7.1; it
does not bypass any implemented read-only or credential gate.
