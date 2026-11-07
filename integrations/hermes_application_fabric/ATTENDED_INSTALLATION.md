# Attended Fabric installation through existing owners

This is the installation contract for ordinary Darwin Hermes at native
`2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19` plus the reviewed 20-file
`hermes_core/hermes-2bd378ed-host-bound.patch`. Final delivery remains original
Mastermind #2175 and paired Macro #10740. The #2225 contribution supplies these
joins; source qualification does not select an installed release or enroll a
service.

## Source and package ownership

The native PM installs the complete adapter root as
`mastermind-hermes-application-fabric`, providing the canonical import
`integrations.hermes_application_fabric`. The general plugin's native alias
delegates to this same package, preserving client classes and ContextVars.
The separate early `model_provider` entry registers the keyless provider through
the existing native discovery lifecycle. General plugin discovery deliberately
does not register model-provider entries.

| Native entry | Repository subdirectory | Manifest name |
| --- | --- | --- |
| General plugin and buildable shared package | integrations/hermes_application_fabric | mastermind-fabric-gateway |
| Early model provider | integrations/hermes_application_fabric/model_provider | mastermind-fabric |

Use the complete root for new installations. The old `gateway_plugin_entry`
directory remains a compatibility wrapper; installing that wrapper alone does
not install the shared Python package.

For each authorized profile, the existing plugin installer accepts these source
identifiers with `--ref "$HERMES_FABRIC_RELEASE_SHA"`, where the variable is the
actual protected, accepted 40-character Mastermind release commit. Stage disabled
until the existing owner can enable the complete installation:

```sh
hermes plugins install "mastermindx-market-intelligence/Mastermind#integrations/hermes_application_fabric" --ref "$HERMES_FABRIC_RELEASE_SHA" --no-enable --yes-deps
hermes plugins install "mastermindx-market-intelligence/Mastermind#integrations/hermes_application_fabric/model_provider" --ref "$HERMES_FABRIC_RELEASE_SHA" --no-enable --yes-deps
```

The commands are an installation recipe, not a record that they ran. Use the
actual profile and native PM launcher under its current installation/reload
custody. Preserve native install metadata outside the plugin tree; never create
a substitute metadata receipt. The existing enabled-plugin configuration must
eventually include both manifest names.

The native PM change snapshots every selected profile member. Identical,
self-contained builds of the same canonical distribution share one workspace
build while each home retains its own selected identity and immutable source
snapshot. Different build inputs, unsafe links, or external backend/source paths
refuse before lock publication. Removing one selected home leaves the other.
Source type, mode and content changes invalidate the existing member stamp.

## Installed Macro source closure

The original attended factory now comes from a fixed projection inside the
selected, sealed Executive release, rather than an ambient developer checkout.
The existing `capacity_host_artifacts.py` builds a deterministic data archive of
only the exact Macro commit's `config`, `engine` and `lib` trees. It reads Git
objects and ignores uncommitted workspace bytes.

Current Macro source is
`fff0025e10de394c6a297c7878518513f1dbe633`, tree
`66c2808c1424c1be13a8c93fad2cd046d1255598`. The reviewed
`macro-source.json` binds the repository, commit/tree, projection, material
manifest, archive size and SHA256. Reproduce the artifact using the reviewed
builder:

```sh
python3 ops/executive_os/capacity_host_artifacts.py build-hermes-attended-source --source-repository "$MACRO_SOURCE_REPOSITORY" --commit fff0025e10de394c6a297c7878518513f1dbe633 --output "$HERMES_ATTENDED_SOURCE_ARCHIVE"
```

The original Executive installer accepts the absolute archive path through
`--hermes-attended-source`. It validates the committed archive identity before
maintenance. Inside its existing exclusive release staging, it materializes data
only, writes the exact inventory and source receipt, then seals and verifies the
complete release before the original atomic publication. It executes no projected
Macro code or Git in this privileged materialization. A same-SHA release lacking
this projection refuses; the installer never grafts files into a sealed release.

The three projection roots live under
`native-dependencies/hermes-attended-macro/` in that release. They are not a
partial repository in the existing full `macro-sources/<sha>` namespace.
The release also contains the inventory and receipt. The existing Control observation remains the only selector; daemon,
credential and admission ownership remain unchanged.

## Current enrollment to installed consumer configuration

The committed Macro projection intentionally ships with no application
enrollment. The existing native Go service-enrollment owner now exports a
bounded public eligibility observation through
`ops/native_fabric/quota_continuity/rollout/export_application_consumer.py`.
The exporter reads the completed v9 attended role, checks its original private
binding/intent/receipt, and reuses the original Broker's current grant matcher.
Revoked, expired, ambiguous, mismatched or absent grants refuse. The export
contains references and current route eligibility, never a credential, a grant
issuance, a capacity reservation or a claim that a provider is ready.

Use the original completed ingress bundle and existing source/host authority:

```sh
python3 -B ops/native_fabric/quota_continuity/rollout/export_application_consumer.py --go-ingress-bundle "$COMPLETED_GO_INGRESS_BUNDLE" --service-profile hermes-attended > "$HERMES_ATTENDED_OBSERVATION"
python3 -B ops/executive_os/capacity_host_artifacts.py build-hermes-attended-configuration --observation "$HERMES_ATTENDED_OBSERVATION" --observation-sha256 "$HERMES_ATTENDED_OBSERVATION_SHA256" --archive "$HERMES_ATTENDED_SOURCE_ARCHIVE" --commitment integrations/hermes_application_fabric/macro-source.json --output "$HERMES_ATTENDED_CONFIGURATION"
```

The observation digest identifies the original source-linked return; it is not
authentication or installation authority. The existing release owner accepts
that concrete observation under the existing installation authority.

The data-only builder reads the exact Macro owner's literal transport and
service declarations without executing projected Python. It derives the
attended production-mode record, preserves the original workload-policy bytes,
and creates one consumer-local capability view. AUTO preserves the original
enrollment's pool restriction. Fixed mode requires its actual source-owned model
in the current grants. Qualification expires at the earliest represented grant
expiry. Other application's source/configuration remains under its own owner.

Supply these additional inputs to the **existing full Executive installer**:

```text
--hermes-attended-source <exact-source-archive>
--hermes-attended-configuration <exact-configuration-capsule>
--hermes-attended-configuration-sha256 <builder-returned-capsule-digest>
--control-config <preserved-complete-current-Control-input>
```

The installer validates the capsule before maintenance, rederives its contents
from the installed measured source, and atomically stages immutable data under
`/Library/Application Support/MastermindExecutive/config/hermes-attended/<digest>`.
An occupied digest slot must be identical. The existing Control writer selects
only that digest, and its existing observation publisher emits the closed v2
observation. With no selected capsule it preserves the exact legacy v1 form.
Neither capsule publication nor a digest grants provider permission.

A full same-SHA reinstall can renew selection without modifying the sealed
release. Preserve the complete current Control input during renewal. Revocation
uses a preserved Control input with the optional
`hermes_attended_configuration_sha256` field removed. Do not invoke the
observation publisher separately or bypass the existing maintenance interval.

The running plugin retains one canonical Macro code context. Each catalog
request or turn acquires its own current configuration lease. After renewal,
a new operation sees the new capsule without recreating factory classes; the
prior operation retains its original capsule for cleanup and cannot silently
reauthorize under the replacement. The actual native Broker still checks current
grants and route/account admission on every real operation.

## Runtime discovery and lifetime

`source_context.py` uses the existing fixed Darwin public control observation and
Control launchd plist to identify the selected release. It checks agreement,
root ownership, modes, ACLs, the release manifest and all relevant commitments.
It does not read private Control configuration contents. Only after checking the
sealed existing native source verifier's bytes does it use that verifier to hold
the complete three-root closure.

The importer executes measured source bytes for `engine` and `lib`. It rejects
ambient modules, missing owned modules, changed source, foreign loader identity,
and reload/re-execution. It neither falls through to another checkout nor relies
on cached bytecode. Retained descriptors and original closure checks fence source
changes. Import execution does not hold a context state lock while Python runs
arbitrary module code.

Native plugin references and active operations share that held context. Catalog
inspection and a complete admitted turn retain their own operation leases.
Unloading a plugin revokes its ability to authorize another request while the
original turn can still close its original owner. A changed retained context
refuses new work; it is never silently replaced under an active turn.

The general plugin attaches a catalog callback only to the actual home-bound
provider already registered at startup. Reconstructing an agent validates that
profile rather than replacing it. Callback ownership, current home and source
currentness are checked on use; native unload restores only the callback slot
still owned by that instance.

## Picker and selection

The ordinary inventory presents a managed-access provider without pretending
that an API key exists. Only the current authoritative callback supplies its
models. Disabled/excluded providers, an empty or failed callback, source drift
and retired homes do not fall back to a saved or static eligible model list.

The native TUI accepts eligible managed models without an API-key prompt and
does not expose disconnect for a host-managed credential. A held provider with
no eligible models remains unavailable. Select through the native picker, or
the session command accepted by that picker:

```text
/model mastermind-fabric/auto --provider mastermind-fabric --tui-session
```

The original Capacity Fabric router and APPLICATION broker own AUTO ranking,
pool/account eligibility, capacity admission and serving observations. The
factory supplies the trusted consumer identity and its route restriction. An exact model under an enrolled AUTO scope
narrows the existing owner before inspection freezes. One admitted turn,
including tools and reconstructed agents, retains one route and original effect;
a later newly admitted turn may select a different eligible route.

## Source identities and acceptance

| Closure | Current identity |
| --- | --- |
| Native 20-file patch | SHA256 631d202a736dc511b359b518dc74ab9b9b84566b05d74bafb2bab7763ed94541; previous 15 postimages unchanged |
| Attended 17-file runtime list | SHA256 7307c43984fe15297706af9b289c0d5aed7c665f3cfee12cbff33f29a0c68376 |
| Original role 11-file publication | SHA256 c801409819ce3cbc2e95414d685ccc7663753bd992e81158448488fd4ac06be2 |
| Macro source archive | SHA256 9380af04320616d210b45eb26168c20dee6967ce267153c6de521d70d2b0b99b; 75,612,290 bytes |

The attended runtime list and existing role publication are different contracts;
one digest never substitutes for the other. PM build configuration is retained
by the existing PM snapshot and release commitment.

The current package proof uses the actual patched native PM with two disposable
homes and its real environment builder. An isolated Python process imports the
installed canonical package without the developer checkout on its path, confirms
shared class identity, exact Macro commitment, JSON Schema 4.26.0 and PyYAML 6.0.3.
This proves ordinary packaging, not installation into a live selected Hermes
environment.

Source support is enabled for the fixed and automatic attended descriptors.
The shipped application mode map remains empty and runtime capability/service
enrollment remains absent. Real acceptance still requires the original approved
generation and service enrollment, eligible physical account/headroom, actual
model/account/usage attribution, native tools, settlement and denial/recovery
proof. Preserve the original H4 gateway/profile writer, original J collection
and settlement recovery, account-authentication refusals and existing release holds.
J has terminal execution-success evidence; its controller collection and root
acceptance are still unresolved, so no replay or re-homing is authorized. They cannot
be replaced by a fixture credential, a new request identity or a second runner.
