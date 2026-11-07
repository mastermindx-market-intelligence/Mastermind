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
