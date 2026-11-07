# Native OMH integration continuation

Operation: hermes-omh-native-20261107-c3; parent hermes-omh-adoption-20261106-c3 / PR2162 / masterplan PR2159. Current Chairman explicitly directs implementation through real integration. Core source dependency: 01a42ccc4c02c2e453e1d573f3b57efe0f8d2702. Protected procedure remains compatible at b0a280be474ae67e7681f68dc0dfe3af2aea1626; observed protected master650b81344a7cf5790cdf617dff6e1e2175742037 changes only the later deployment receipt command among relevant laws.

## Outcome and design

Keep the already-installed OMH4.0.6 and selected OMH memory provider on M2. Expose the canonical graph proposal and existing OMH skill/category/model/effort recommendations through ONE read-only native Hermes tool, mmx_omh. This tool never dispatches work, changes model/provider/account, admits a plan, writes memory or claims execution. The existing native tools/Executive/Fabric remain the only execution path.

Use OMH's actual installed routing code and configured chain overrides, not copied editorial defaults or provider entitlement inference. Strip upstream served/availability labels: candidates are recommendations, not evidence that a provider served or admitted them. Reject malformed overrides instead of silently replacing them. Read only the selected OMH routing document; do not read auth.json, provider keys or memory files.

A dependency-free Hermes plugin calls the existing bounded deterministic CLI using an operator-installed, exact-source descriptor and fixed argv, never arbitrary commands. This avoids changing Hermes' or OMH's Python dependency environments and avoids importing a competing Mastermind runtime. The descriptor binds the profile, source release, source hashes, interpreter and OMH routing home. No model parameter can replace these. The native PluginContext and registration lease own tools, scope and unload; collisions fail rather than override. Native serving activation uses the existing Hermes installer/adoption and enable controls, not a new service.

Alternatives rejected: full OMH reinstall conflicts with the incumbent; global pip/dependency environment changes risk active capacity/memory work; an additional execution proxy would duplicate admission and uncertain-effect handling.

## Task tree and proof

N1: add bounded recommendation preparation and CLI mode, using actual installed OMH parser/ranker. TDD: valid category/overrides, malformed/deep/duplicate JSON, unknown category, source errors, no credentials/network, no promoted served/eligible labels.
N2: dependency-free native plugin, exact operator descriptor, fixed subprocess, profile and registration checks, value-free errors, no retries. TDD: real native PluginContext/registry invocation, collision, wrong profile, source drift, malformed output, timeout, no config writes or provider calls.
N3: source qualification and protected release; install exact released files as immutable local artifact, use existing native plugin metadata/enable owner, preserve unrelated configs. Prove default and Secretary native discovery/invocation or report exact unproved serving layer. No service restart or override of active source writers.
N4: publish the executable candidate interface to active Capacity #2155 and Agent OS memory #2163 owners, with actual tested output and role scope. No duplicate source implementation in those trees. Their actual admission/provider/result receipts remain necessary for full system acceptance.

DONE_WHEN: original core is protected-merged; native bridge is source/release-qualified, installed through current native owner and invoked through real Hermes tool dispatch; real OMH model/skill proposals are returned without provider/permission claims; actual execution integration consumed by existing owners is distinguished from outstanding acceptance. Pure fixtures or a source PR alone do not complete the larger programme.

Direct retention: PRINCIPAL_JUDGMENT / UNIQUE_APPROVED_ACCESS for the exact installed-runtime composition. Original refused core worker is not retried. Scope: integrations/hermes_omh/**, tests/test_hermes_omh_native.py, tests/test_hermes_omh_recommendations.py, this doc and the existing OMH readme only.

## Source qualification

N1/N2 source is implemented. Exact local command: `python3 -m pytest -q -o addopts='' tests/test_hermes_omh_native.py tests/test_hermes_omh_recommendations.py tests/test_hermes_omh.py tests/test_executive_plan_schema_versions.py integrations/hermes_delegate/tests/test_delegate.py` -> **176 passed, 9 subtests passed**, exit0. The real installed-runtime canary remains pending at this source checkpoint.

Observed RED failures preceded recommendation and native plugin implementation. Two additional failure tests exposed missing post-call registration revalidation and unsanitized partial registration uncertainty; both were repaired. The preexisting repository fixtures create scratch directories, so the no-write test compares the before/after directory census rather than assuming an empty fixture.

The runtime descriptor binds exactly19 original source files, including the unchanged canonical parser and its dependencies. It is operator installation metadata, not an authentication token or permission grant. The native bridge inherits no provider credentials into its local deterministic subprocess and never changes the existing memory provider. Native plugin registry collisions refuse; source/profile/registration drift refuses before delivery; there is no same-call retry.

## Installed-runtime qualification

Exact implementation `58c2614b1a0413998555a72755599c2bdd09c46f` passed the actual installed Hermes loader and registry on `2bd378ed1b8d6bf2192cb26e0a55ff3091e6bd19`. `PluginManager.discover_and_load` registered `mmx_omh`; `ToolRegistry.dispatch` exercised status, canonical graph preparation and the actual installed OMH4.0.6 recommendations. The original three-step plan digest remained `6e83ce32433558c5a8ee9aa0d34929d6878116ea72ac6d8d51d8a3142d2447f5`. Cross-profile use was refused and the temporary profile config was unchanged.

The real current OMH override (not the earlier default-chain snapshot) was consumed. Upstream aliases and efforts were retained as recommendations; selected_model remained null, availability NOT_OBSERVED, and admission/dispatch false. No provider inference or production profile edit was performed. The native owner prepared dependencies for the isolated data root before the canary; the zero blocked-network count covers the guarded native canary process, not bootstrap or a whole-host traffic capture. Exact structured evidence: `integrations/hermes_omh/qualification/native_receipt.json`.

Current release dependency: original #2162 is in the native protected queue, entry MQE_lQDOTotz3c8AAAABNb4ODM4ABAiKzgPLphI, integrated head32507c658d528f85f676592b447f98d8cc6012de. Mastermind OS merge-group checks succeeded; CI run42319527418 was still running at this observation. This is not a merge receipt; do not recreate its request.

## Existing-conversation access

The installed Hermes activation contract intentionally defers newly registered Python tools until the next session to preserve its prompt cache. Rather than restarting or resetting live bots, the bridge also registers `/mmx-omh status` and `/mmx-omh <category> <task>` through Hermes' existing command owner. These native gateway commands activate immediately when the gateway loads the plugin. They reuse the same checked local tool handler, actual native session context, profile/source checks and no-execution result. Command collisions fail; unknown registration effects are not retried. No extra service, model call, memory store or lifecycle is introduced. Native qualification covers the original command dispatcher and actual activation summary, not merely a declared manifest.

The original core #2162 protected-merged as `5883574ac855f9b42f05668458426450b40677ff`. All six merge-group test shards and the required test aggregate succeeded on integrated32507c65; Mastermind OS native/frontend checks also succeeded. No original effect was retried. The expanded native-command suite now reports179 passed and9 subtests passed. `/mmx-omh` uses the original native command/session context and refuses command collision or stale registration.

## Integrated native command qualification

The source composition `7c8c5a988c8dd005f11c8a49f54afe499a73d4c4` has parents owned command source01d2c53b and the actual protected core merge5883574a. Two genuine add/add conflicts (README and JSON input) were resolved only after proving the protected variants equal the original core bytes; the owned native extensions were retained. Against protected5883 the diff is exactly11 native-owned paths, not the inherited core or unrelated protected changes.

The resulting full focused run passed179 tests and9 subtests. A fresh minimal25-file packaged canary passed actual native loader, ToolRegistry.dispatch, and invoke_plugin_command on both status and recommendation. Native activation summary confirms `/mmx-omh` in activated_now.gateway_commands and `mmx_omh` in deferred.tools. This is the documented existing-session/new-session distinction, not a service restart workaround. The fresh receipt replaces only the qualification record; source, credentials, running conversations and production profiles remained unchanged during this proof.
