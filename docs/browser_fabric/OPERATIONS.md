# Browser Fabric operational release

This runbook describes the implemented source path. It is not an installation
receipt. Actual host enrollment, installed Chrome/native registration, public
ingress, OAuth applications and multi-client acceptance require separate evidence.

## Ownership and persistent identity

The public Browser facade routes one local Browser Link owner and at most sixteen
fixed remote Workbench owners. Each host retains its existing action store,
resource/reconciliation receipts, owner lease and profile grants. No fleet cache,
second action store, automatic host failover or browser-action replay is introduced.

The host process runs as the actual Chrome user. Its fixed LaunchAgent label is
`com.mastermind.workbench-browser`; configuration, lifecycle journal and logs live
under `~/.local/share/mastermind-workbench-browser`. The installed configuration
is `config.json`, while a proposed configuration is `staged-config.json`.

The source generation is
`/Library/Application Support/MastermindExecutive/releases/<40-character-SHA>`.
A dedicated SDK lives under
`workbench-mcp-runtimes/<Chrome-UID>/<SHA>`, with its separate root-owned binding
under `config/workbench-browser-runtimes/<Chrome-UID>/<SHA>.json`.
It is never a Company runtime or a Studio account.

The Browser lock is `requirements/workbench-browser-macos-arm64-py312.lock`.
It retains the reviewed Workbench dependency closure and adds Pillow 12.3.0.
Provisioning uses the incumbent signed Python and immutable, hash-checked SDK
materializer. Temporary development environments are not production interpreters.

## Publish source through the incumbent exporter

Use a clean, owned checkout whose exact committed HEAD is the current protected
`origin/master`. The installer must come from that checkout. Required checks,
review and protected merge precede publication.

The typed option below invokes the existing Git archive, release manifest and
exclusive publication implementation. It does not select a release or alter
installed services, configuration, receipts or transactions.

```bash
sudo /absolute/qualified-checkout/ops/executive_os/install.sh \
  --source-repo /absolute/qualified-checkout \
  --expected-sha <qualified-protected-SHA> \
  --operator-user <qualified-operator-account> \
  --python-binary /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
  --python-runtime-root /Library/Frameworks/Python.framework/Versions/3.12 \
  --stage-workbench-browser-release-only
```

This mode retains the existing read-only Python, Codex, account, worker-auth,
source and filesystem admission checks. It excludes OS assets, ordinary OS-stage
mode, frozen/protected-ancestor selection, privileged arming and control-config
replacement. An unresolved deterministic `.stage.<SHA>` is retained and refused;
it is never adopted or deleted by another invocation.

A source-only generation is sealed. A later OS web installation cannot graft
assets into the same SHA. Browser mode can verify an existing qualified generation
that already contains assets; it cannot repair or reseal one.

## Provision and qualify the dedicated SDK

Use the exact base interpreter, isolated startup and sealed source bootstrap.
The variables below are operator inputs, not discovery or fallback selectors.

```bash
MMX_BROWSER_SHA='<qualified-protected-SHA>'
MMX_BROWSER_UID='<qualified-Chrome-user-UID>'
MMX_BROWSER_SOURCE="/Library/Application Support/MastermindExecutive/releases/$MMX_BROWSER_SHA"
MMX_BROWSER_PYTHON='/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12'
MMX_BROWSER_BOOTSTRAP='import sys;sys.path.insert(0,sys.argv.pop(1));from ops.executive_os.workbench_mcp_runtime import main;raise SystemExit(main())'

sudo "$MMX_BROWSER_PYTHON" -I -S -B -c "$MMX_BROWSER_BOOTSTRAP" \
  "$MMX_BROWSER_SOURCE" provision --release "$MMX_BROWSER_SHA" \
  --service-uid "$MMX_BROWSER_UID"
```

The real Chrome account must exist with the qualified home and UID at least 501.
A complete existing SDK is verified. An interrupted SDK retains its incomplete
marker and original bytes. The explicit `recover-incomplete` command archives
only an unpublished incomplete tree; it refuses a complete published binding.
It does not repair a generation in place or discard evidence.

## Stage, inspect, start and stop

Enrollment supplies the existing owner lease, action key, project/action/audit
directories, real Browser Link profile grants, policy and route documents. The
service owner does not issue its own lease or infer consent. Before stage, place
the candidate at the fixed private `staged-config.json` path as the Chrome user.

Run lifecycle commands as that user, using the same bootstrap. The launcher
verifies the selected SDK, then enters it with `-I -S -B` and explicitly adds
only its verified site-packages. It does not use user site-packages, PYTHONPATH,
site hooks or an arbitrary command/configuration path.

```bash
"$MMX_BROWSER_PYTHON" -I -S -B -c "$MMX_BROWSER_BOOTSTRAP" \
  "$MMX_BROWSER_SOURCE" lifecycle --release "$MMX_BROWSER_SHA" --operation preview

"$MMX_BROWSER_PYTHON" -I -S -B -c "$MMX_BROWSER_BOOTSTRAP" \
  "$MMX_BROWSER_SOURCE" lifecycle --release "$MMX_BROWSER_SHA" --operation stage \
  --expected-plan-sha256 <reviewed-preview-digest>

"$MMX_BROWSER_PYTHON" -I -S -B -c "$MMX_BROWSER_BOOTSTRAP" \
  "$MMX_BROWSER_SOURCE" lifecycle --release "$MMX_BROWSER_SHA" --operation start \
  --expected-install-sha256 <installed-digest>

"$MMX_BROWSER_PYTHON" -I -S -B -c "$MMX_BROWSER_BOOTSTRAP" \
  "$MMX_BROWSER_SOURCE" lifecycle --release "$MMX_BROWSER_SHA" --operation inspect

"$MMX_BROWSER_PYTHON" -I -S -B -c "$MMX_BROWSER_BOOTSTRAP" \
  "$MMX_BROWSER_SOURCE" lifecycle --release "$MMX_BROWSER_SHA" --operation stop \
  --expected-install-sha256 <installed-digest>
```

The preview pins source/runtime, configuration, authority documents, the original
key bytes and persistent directory identities. Stage verifies these and writes
its durable journal before changing files; the install manifest is published
last. Interrupted staging resumes only the exact original plan and permitted
preimages. Stage does not prove semantic profile consent or remote availability;
the actual service factories and admission owners still validate those inputs.

The LaunchAgent has `RunAtLoad=false` and `KeepAlive=false`. Start records one
bootstrap and one kickstart before issuing them. An ambiguous attempt is observed
without issuing either again. A clean service restart is an explicit lifecycle
operation. It preserves the original key and store, and the Browser resource owner
revisits deterministic original starts rather than replaying page actions.

Readiness requires a fresh nonce, HMAC, original process identity, host/boot,
configuration fingerprint and acquired-input digest. The digest comes from the
actual documents, retained key and open directory descriptors used during startup.
Completion precedes browser activation and credential maintenance. The probe has
a bounded loopback response and total coroutine deadline. Runtime readiness keeps
`fleet_observation=unobserved`; it does not claim that all remote hosts are online.

Stop records one SIGTERM, then waits for that original process and the matching
launchd generation. Exit 0 with qualified original absence permits one bootout.
Exit 3 retains physical-drain uncertainty; exit 4 retains cleanup uncertainty.
Exit 2, other codes/signals, replaced identities and unqualified observations also
hold. A hold survives reboot. A spontaneous qualified exit is classified by the
same original-generation evidence. Neither an offline fleet nor failed readiness
authorizes a fresh launch or forced unregistration.

## Optional outgoing credential maintenance

Service v1-v4 retain their behavior. Service v5 is the v4 Link/estate configuration
plus the required absolute `browser_fabric_credentials_file`. Its private 0600
enrollment document has this closed shape:

```json
{
  "schema": "mastermind.browser_workbench_credentials.v1",
  "credentials": [
    {
      "host_ref": "<existing-fixed-route>",
      "client_id": "<enrolled-M2M-client>",
      "client_secret_file": "/absolute/private/client-secret",
      "policy": "<the existing full ResourcePolicy object, not a string>"
    }
  ]
}
```

The illustration names the policy field; replace its placeholder with the actual
closed `mastermind.business_mcp_auth_policy.v1` object. The issuer must use the
supported HTTPS origin form, scopes must be exactly `workbench.action`, the
resource must equal that route's resource, and the sole allowed subject digest and
derived client reference must equal the route's broker identity. Auth0 API/client
grants must already authorize this client. No management application or grant is
created by startup.

The secret file contains one nonempty printable ASCII client secret, optionally
followed by one newline. It and the existing/absent output artifact must have
qualified private parents and safe same-user custody. The publisher never
creates or repairs those enrollment directories. Outputs, lock files, secrets and
the enrollment file cannot overlap. A managed subset of routes is allowed.

The publisher derives `/oauth/token` from the qualified issuer. It issues at most
one bounded POST per admitted attempt, disables redirects/proxies/retries, verifies
the signed token through the existing JWT/JWKS owner, and compares exact resource,
subject, client and scope. Artifact expiry comes from the signed JWT, never
`expires_in`. A sufficiently live verified artifact is reused without issuance.

A persistent per-output lock spans reread, issuance, verification and publication.
The final 0600 write/fsync/replace/directory-fsync transaction is synchronous under
that same lock. Admission, original parent/lock identity and expiry are checked
again before replacement. The service's current local owner lease controls
issuance; revocation or expiry does not renew authority.

One finite pass runs inside the existing profile-maintenance task: at most four
concurrent routes, five seconds per attempt, and a 22-second whole-pass budget.
Failures observe configured backoff. Status exposes only host reference and
`PUBLISHED`, `REUSED`, `BUSY`, `DEFERRED`, `INACTIVE`, `UNAVAILABLE` or
`UNCERTAIN`. A failure after replacement or during subsequent cleanup remains
`UNCERTAIN`; it does not roll back to an old token. The next independent pass can
verify and reuse the current complete artifact.

Secret contents and rotating token artifacts are excluded from the installed-plan
digest; the nonsecret enrollment document is pinned. Browser transport remains
unchanged and rereads its fixed credential artifact on each independent call.
A 401 or uncertain browser result never triggers refresh-and-replay.

## Installed acceptance

Source tests use synthetic Chrome peers and issuer responses. Production
acceptance must separately establish:

1. Exact current Chrome profile/process/extension identity and qualified native
   registration root, followed by the existing Web Sol overlay/native transaction.
2. Human tab consent and the actual connected native channel for each profile.
3. One-host and two-host discovery, exact selection, stale-reference refusal and
   concurrent writes to distinct tabs.
4. Creation of a new tab/window through an admitted shared anchor, with explicit
   child sharing policy and retained original action receipt.
5. Clean restart and original-action reconciliation without a duplicate effect;
   unresolved physical/cleanup states must remain held.
6. Private/public ingress, issuer/application enrollment and actual provider-client
   use. A generated client configuration or successful runtime readiness is not
   evidence of ChatGPT, Claude, Grok Bot, OpenClaw or Fabric connectivity.

Primary protocol/enrollment references:
https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging ;
https://auth0.com/docs/get-started/authentication-and-authorization-flow/client-credentials-flow/call-your-api-using-the-client-credentials-flow ;
https://docs.openclaw.ai/cli/mcp/transports ;
https://docs.x.ai/grok-bot/team-bots ;
https://developers.openai.com/plugins/build/auth ;
https://claude.com/docs/connectors/building .
