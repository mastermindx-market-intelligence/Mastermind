# Worker harness parity: census and architecture decision

**Assessment date:** 11 October 2026 UTC

**Commission:** `worker-harness-parity-research-20261011-astra-001`

**Initial protected source:** `326c8469a21d7f50fc9ecb1848196bf1c6e66685`

**Final protected-source refresh:** `e67d9d2566de73ccc0ec7a5c6f86da79f7780c94` at 02:02 UTC

**Parent integration carrier:** [PR #600](https://github.com/mastermindx-market-intelligence/Mastermind/pull/600)

**Disposition:** Research and implementation design complete. Rich-worker deployment and integrated acceptance remain implementation work.

## 1. Decision

Upgrade the existing fabric into **one common, rich worker operating environment, with orchestrator-selectable role, capability, bootstrap and context profiles**.

Every ordinary worker should receive substantial working capability automatically: source and knowledge discovery, full work inside its assigned filesystems, shell and development tools, web research, applicable data access, a usable browser lane, appropriate skills, continuity, and the ability to investigate, implement, test, repair and return independently. Operators additionally need the existing commission, progress, decision and result interfaces, with admitted child delegation.

The orchestrator should choose different environments per assignment. It should be able to select a researcher, engineer, data scientist, designer, browser operator, system operator, independent reviewer, or coordinating operator; select additional domain skills and data; and choose the required browser/computer lane. It should also be able to request a deliberately smaller environment for a short task. Small environments should be an optimization, not the default ceiling.

Implement this through the existing Executive/HF1 contracts and resource owners. The design combines:

- Source-pinned role, skill and bootstrap packages.
- Canonical knowledge and memory references, plus derived task context.
- Real tool exposure, authentication and resource grants.
- Provider-specific configuration materialization.
- Observed initialization and meaningful task execution.
- Root-wide lineage, capacity, continuity and return acceptance.

This grants workers the operating capability needed for their work. It does not assume that a plugin name, permission flag, long prompt or shared model makes their environment equivalent to a CEO's.

## 2. Evidence basis and interpretation

The census combined protected repository source; current PR heads, comments and CI; installed M2 CEO and pool files; the installed host registry and a read-only lease database snapshot; Executive read projections; live discovery on both fabric MCP routes; and current official OpenAI, Anthropic, MCP and Playwright documentation. Three independent research agents covered fabric source, capability/bootstrap design and vendor harness behavior, then reviewed the proposed architecture.

The detailed hashes, observations, exact PR heads and timestamps are in [EVIDENCE.json](EVIDENCE.json). Installed observations are snapshots rather than claims about every remote host or every running session.

Before publication, protected master advanced through merged #1145 (`7ac70e15f13b33d9e44067113e75c656fe6fafa9`) and two UI fixes to `e67d9d2566de73ccc0ec7a5c6f86da79f7780c94`. The remote-transport delta was reviewed and incorporated below. It changes neither the capability registry nor the rich-profile restrictions. Installed observations retain their original timestamps; source merge does not update the installed runtime. [S10]

Use the following distinctions throughout implementation:

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| Protected source | Reviewed repository behavior at an exact commit | Installed generation, enabled admission or provider execution |
| Candidate PR | Proposed behavior and candidate validation | Merged or deployed behavior |
| Configuration | Intended flags, manifests and service wiring | Effective runtime inheritance or actual tool consumption |
| MCP catalog | Tool definitions exposed by that exact route | Authentication for every resource or successful use |
| Canary | A particular operation on a particular tuple | Every provider, host, role, resume path or production task |
| Accepted mission | Useful work consumed by its parent with evidence | Universal parity outside the tested contract |

No new external provider worker was launched for this census. The only live fabric interaction was protocol initialization and tool discovery, followed by session closure. No gateway policy, production arm, pool ceiling, browser permission or fleet installation was changed. Documentation was prepared in an acquired managed workspace.

## 3. How the current fabric actually works

### 3.1 There are three related execution paths

**Native provider subagents** are children of an attended Codex or Claude session. Their available tools and permissions depend on the actual parent process and provider implementation. They are distinct from workers launched through the external pool.

**The attended pool fabric** uses the installed `pool` launcher and the handoff kit under M2. `pool run` reaches `sub.sh`; `pool remote` reaches `remote_sub.sh`. The richer `fabric_task.py` facade adds task identity, classification, packet, parent/root references, model preference, complexity, result inspection and acceptance projection. It delegates execution to the incumbent launch/broker chain.

**Executive-governed Operators/workers** use Job/Attempt lineage, capability profiles, workspace identities, admission, dispatch, provider adapters, initialization attestation and return acceptance. These contracts are much richer than the currently admitted capability combinations. They are the appropriate home for the upgrade. [S1][S2][S3]

The native pool launch chain observed on M2 is:

1. `fabric_task.py` receives the task and resolves pool/launch policy.
2. `remote_sub.sh` obtains existing broker/account/host admission and builds a versioned support bundle.
3. `remote_sub_exec.py` owns the remote process under the existing lease.
4. Provider wrappers construct an isolated client environment and invoke the provider.
5. Existing result, inspection, cleanup and effect-uncertainty paths return evidence.

The installed facade does **not** yet expose a general role-profile, bootstrap-profile, capability-manifest, knowledge-context or memory-binding input. The remote metadata allowlist likewise does not propagate such a contract. Updating only an Executive dataclass or installing a skill would leave this launch chain incomplete. Installed file hashes are recorded in the evidence manifest.

### 3.2 Rich CEO configuration is deliberately suppressed on worker paths

M2's Codex configuration includes a broad sandbox setting and plugins or MCP bindings for documents, spreadsheets, presentations, browser-related tools, Figma, Paper, company tools and other domain resources. M2's Claude configuration includes design, Figma, Paper, Executive and workforce plugins, hooks and broad permission mode. These are installed configuration observations, not proof that every item is loaded or callable in every CEO session.

The pool worker paths deliberately construct different environments:

| Worker path | Observed launch behavior | Consequence for parity |
|---|---|---|
| Native Codex | Ignores user configuration, uses an ephemeral context, disables multi-agent, uses workspace-write and explicitly projects Studio MCP | CEO plugins, global skills and general MCP entries do not arrive automatically |
| Native Claude | Empty setting sources, strict projected MCP, Agent/Task disallowed | Installed CEO plugin and hook state is not a reliable worker bootstrap |
| OpenCode | Isolated XDG configuration with task delegation disabled | Its own adapter must materialize the role and tools |
| GLM through Codex wrapper | Has an explicit developer-instruction injection seam and exact packet preservation | Useful demonstrated mechanism for trusted bootstrap injection |
| MiniMax wrapper | Dedicated scratch CODEX_HOME and explicit MCP projection; supports continuation | A disposable home alone does not supply company knowledge or role skills |
| Other provider adapters | Provider-specific configuration, launch and session handling | Capability equivalence must be verified per adapter |

Some pool scripts describe “mechanical” work, but their actual classification and turn handling also cover more involved C2/C3 work. The accurate finding is missing consistent environment composition, rather than that all workers are inherently restricted to trivial tasks.

The existing workforce plugin on M2 is a skills-only candidate, `0.1.0-candidate.g61e97693f4bb.skills-only`. Plugin discovery is useful evidence; it does not show fresh worker consumption or grant operational tools.

### 3.3 The live Studio projection is much narrower than CEO access

The census made fresh MCP connections to the **actual routes emitted by the installed worker projection** on M2 at 01:48:58 UTC. Both negotiated MCP `2025-03-26` and reported gateway `0.1.9`.

| Route selected by task class | Exact exposed tools |
|---|---|
| Ordinary/read | `studio_ping`, `studio_fleet_status`, `paper_inspect`, `paper_catalog`, `paper_read` |
| Design | The five above, plus `paper_prepare` and `paper_edit` |

Both catalogs were complete with no next cursor; both sessions closed with HTTP 200. No Paper operation was invoked.

The underlying configuration enables a general Desktop Commander backend, Paper and git-publish components. However, installed `tailnet-gateway.mjs` injects the fixed profile-owned allowlists above. The absence of a toolAllowlist in the JSON file therefore does **not** mean broad access. Its observed SHA256 is recorded in EVIDENCE.json.

These routes expose no general filesystem, shell, browser, data-query or native computer-use tools. Workers may separately have local native file/shell tools. That local access must not be confused with remote M2 filesystem access through Studio.

The ChatGPT4 Studio connection used by this research session separately reported `0.1.10`. That newer connection does not prove the fabric routes have the same version or catalog.

### 3.4 Executive is present, but the rich compositions are not admitted

Executive's 01:40:25 UTC read projection reported server `1.5.0`, installed Mastermind source equal to the protected base, and Macro source `88804ed7079700c598bb8e04aa64307d1335402d`. Its snapshot had 17 Jobs, 21 Attempts, no running Job/Attempt, and one available worker. The separate fabric projection reported `ceo_submit_armed=false`. These observations are not a rich-worker canary.

The protected `mastermind.executive_agent_capabilities/v3` policy has:

- `production_armed=false`.
- An empty `plugins` map.
- Eleven profiles, all with empty `skills`.
- Enabled narrow App Server/read-only or sealed no-extension combinations.
- A narrow browser.local-review composition.
- A disabled browser.isolated profile.
- One specifically constrained read-only native-helper profile.

The registry and supervisor explicitly reject several compositions required by this mission, including company skills with write-capable or certain sealed/browser profiles, installed plugins, and write-capable native helpers. Claude's existing Operator projection is confined to Read/Glob/Grep. These are implementation constraints to change through new reviewed rich profiles. They should not become the permanent product specification. [S3][S4]

### 3.5 Capacity and native helper settings are separate dimensions

The installed host registry contains 14 registered hosts. Ubuntu lane ceilings remain 2, 2, 5 and 2, totaling 11 nominal external lanes. The read-only broker snapshot contained 5,266 historical rows, no waiter rows and two held MiniMax rows. These numbers are time-sensitive and do not establish free capacity, current process absence or accepted provider readiness.

The initial M2 read found global Codex agents disabled with a maximum of one; its separately installed `native12` profile enables twelve with depth one. The initial Claude read found ordinary concurrency two/depth one and an opt-in twelve/depth-two profile.

A later update to parent comment 6104204541 reports ordinary Claude concurrency raised to twelve on M2/Ubuntu1/Ubuntu2 with depth held at one; Ubuntu3 remains two. It also reports actual Codex prompt rendering of thirteen total slots on M2/Ubuntu0/Ubuntu3. These are stronger configuration/prompt observations, not successful child missions: the Claude model canary encountered expired OAuth and the Codex canary produced no child event. Earlier denied path writes, verification and interrupt operations were not replayed by this research session. The update is owner-reported evidence, distinct from the initial direct configuration hashes. [P600]

The upgrade must account for native children, external workers, resumes, reviews and repairs in one existing root work graph. An opt-in native limit of twelve is not evidence of eleven times twelve usable external workers.

Observed M2 command versions were Codex CLI `0.159.3`, Claude Code `2.1.296`, and OpenCode `1.18.31`. Remote-host CLI versions and model-to-tool behavior remain qualification inputs.

## 4. What already exists and should be reused

### 4.1 Contracts and lifecycle

`operator_harness_contract.py` already defines workspace identity, required/ambient/forbidden capabilities, requested profiles, skill/tool/MCP identities and initialization attestation. `operator_harness_orchestrator.py` validates, seals, commits dispatch, starts, binds and compares observed initialization before work. The remote adapter delegates to the incumbent remote owner. Candidate execution is distinct from Job completion. [S1][S2]

This is the correct foundation for requested, resolved and observed child environments. The implementation must extend registry validation, supervisors, provider materialization and launch propagation together.

Merged #1145 now supplies an Attempt-bound remote worker composition through a trusted endpoint-binding source. It pins the endpoint/UID and adapter identity, refuses uncertain remote binding without local fallback, and supports status-only proof recovery for an exact LOST/requeued Attempt. Rich materialization should consume this merged seam. It does not prove installed activation or change profile admission. [S10]

### 4.2 Packages and skills

`CapabilityPackageGeneration` already represents immutable package files, effective skill grants, app references, source identity, closure digests and revocation-related checks. The convergence index establishes the intended names:

- Root `capability_packages`.
- Raw profile `skill_capabilities`.
- Resolved runtime `profile.skills`.
- `plugins` remains reserved and empty until a separately supported meaning is implemented.

Keep package generations focused on source-pinned assets. Browser sessions, mutable memory, filesystem roots and data authority remain resource bindings and canonical-owner references compiled into the existing capability manifest. [S5][S6]

The current operator package contains four bound-operation workflows: receive commission, return progress, escalate decision and finish operation. The broader Sol plugin has twelve workflows. They represent different role procedures; distributing the Sol directory alone would not reproduce CEO runtime access.

The Codex skill canary provides exact skills-list and closure checks. Its disposable projection script is explicitly Codex-specific. General provider-neutral materialization belongs to HF1, not an expanded test harness. [S7]

### 4.3 Knowledge, memory and data

Repository procedure identifies **Agent OS in Macro as canonical organizational knowledge**. `ceo_boot_packet.py` is a bounded one-way reader using the existing brief interface. Context Fabric proposes derived context packs, Project Atlas and workspace overlays, marked non-authoritative and bound to source evidence. [S8][P1216]

Workers need broad retrieval of the same relevant company, project, architecture, ownership and domain knowledge available to CEOs. The initial bootstrap should provide enough to begin competently; the full corpus remains discoverable on demand. Progressive loading addresses context size and freshness. It must not become a reason to deny access.

Agent scratch notes, context caches and vendor conversation state must remain distinguishable from accepted organizational memory. Useful worker discoveries should return attributable proposals to the existing memory owner. Data access should resolve the existing Data OS/catalog and commissioned datasets, including mounted external storage where appropriate. No new “worker memory database” or duplicate dataset should be introduced.

### 4.4 Browser and computer resources

Existing Browser contracts and the merged recovery work bind the exact Attempt, workspace, resource reservation and live process/materialization identity. They are valuable even when broader modes are introduced. The current reviewed browser contract rejects shared-CDP/extension/unrestricted-file compositions; the shared-tab design must explicitly extend that contract where required. [S9][P1259]

The new computer-use pilot already has a signed local adapter, a remote consumer facet and a reported M2 screenshot/AX/Calculator journey. It is still a draft pilot; remote exposure and actual Claude client consumption are unproven. Its intended gateway integration belongs to #1217. [P1302]

The target should support all useful lanes: web research; an isolated automation context; an authenticated task profile; authorized attachment to existing tabs; and native desktop interaction where the host and model support it. Each lane needs explicit resource identity and actual callable tools.

## 5. Current implementation carriers and integration gaps

The following is a source snapshot, not a transfer of ownership. Exact heads are in the evidence manifest.

| Carrier | Existing responsibility | Evidence and next integration gate |
|---|---|---|
| [#600][P600] | Parent fabric/orchestration integration | Preserve existing parent, source/runtime roles and P0–P5 acceptance sequence |
| [#1272][P1272] | Worker operating environment and bootstrap | Exact-head CI succeeds, but bounded Agent OS subprocess and installer-closure repair is explicitly unapplied; independent review remains owed |
| [#1267][P1267] | Operator-first role methods | Candidate CI fails with `package_file_size_mismatch`; installer/session loading is unproven |
| [#1216][P1216] | Context Fabric / Atlas / workspace overlay | Candidate CI fails on duplicate test-module collection; narrow rename is proposed, not applied; deployed consumption remains separate |
| [#1217][P1217] | Studio/Paper gateway and provider projection | Owns broadening the actual fabric catalog and connecting existing facets |
| [#1259][P1259] | Dual-lane Browser and shared-tab architecture | Separate Browser catalog/plugin; use existing resource/effect owner; source/live qualification still required |
| [#1302][P1302] | Codex Computer Use local pilot | Local M2 actions reported; remote facet integration, client trust and fleet host qualification remain open |
| [#1145](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1145), #1144, #1143 | Remote endpoint, Linux and two-provider parent acceptance | #1145 merged at `7ac70e15f13b33d9e44067113e75c656fe6fafa9`; consume its protected remote transport. Installed admission and original-parent acceptance remain with #1144/#1143 |
| [#1271](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1271), [#1126](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1126) | Sealed COO/native-Claude lanes | Preserve compatibility; neither establishes the rich worker environment |
| [#1247](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1247), [#1248](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1248), [#1254](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1254) | Capacity/task-fit/model-selection work | Consume capability compatibility before placement and preserve the incumbent routing authority |
| Merged #703, #1071, #1113 | Job-bound login, browser recovery, hard model overrides | Reuse them; optional model override remains hard narrowing with zero Attempts if unavailable |

#1272's candidate already distinguishes preparation from admission, uses bounded packet forms, records tool observations and preserves native-skill attestation as a separate claim. Its current prepare/verify/augment/pool-entry seams are useful. The outstanding repair must land through the current owner; green CI does not erase an explicitly unapplied correctness fix.

#1267's five role references—meta-CEO, program CEO, operator, worker and reviewer—are role procedure, not runtime grants. Its installer patch belongs with the existing installer owner.

#1216's five proposed context tools—resolve, expand, diff, atlas search and workspace overlay—provide a natural task-context interface. They should supply evidence and invalidation, while authorization remains with their existing authenticated service and deployment bindings.

## 6. Vendor research: consequences for this design

Vendor behavior was checked against official documentation on the assessment date. Actual adapter behavior must be pinned to the installed version.

| Surface | Finding that changes the design |
|---|---|
| Codex native children | Parent runtime permissions and tools can be inherited; custom role configuration is not an independent authority boundary. Capture effective parent and child state. [V1] |
| Codex skills | Skill discovery uses progressive loading and a listing budget. A directory containing many skills is not proof that every required skill is visible and applied. [V2] |
| Codex MCP/App Server | Explicit server/tool configuration and runtime skills/catalog observations are available. Generate and test against the installed App Server protocol rather than assuming all documented fields exist. [V3][V4] |
| Claude native children | Plugin-agent configuration has ignored fields; parent modes can dominate child modes; persistent memory can add tools; resumed children retain their tool set. Represent these effects explicitly. [V5] |
| Claude SDK children | Fresh children need the mission and required context supplied explicitly; their context is not the parent's complete working knowledge. [V6] |
| Claude SDK permissions | `allowedTools` is pre-approval, not an exposure allowlist; an approval callback can be skipped by earlier approval. Enforce mandatory boundaries through the appropriate broker/server and deny-capable mechanisms. [V7] |
| Claude plugins/MCP | A missing plugin or unavailable authentication can coexist with process startup. Required capability admission needs loaded and callable evidence. [V8][V9] |
| Browser | Playwright persistent-profile sharing causes conflicts; distinct browser contexts do not serialize edits to the same remote account record. Claude's native Chrome path has its own client/account prerequisites. [V10][V11] |
| MCP versions | The 2026-07-28 specification changes protocol-session and initialization behavior, while the observed fabric negotiates 2025-03-26. Pin and qualify protocol combinations; preserve application-level ownership and effect reconciliation. [V12] |

No vendor research supports the shortcut “copy CEO settings and the worker has the same harness.” Equally, it does not justify keeping all workers in tiny read-only environments. The supported solution is an explicit, observed rich composition using the capabilities each adapter actually implements.

## 7. Alternatives considered

| Option | Benefits | Failure mode | Decision |
|---|---|---|---|
| Copy CEO homes, plugins and environment wholesale | Fast apparent parity | Ambient secrets, ignored settings, shared state, wrong role and unobserved inheritance; no reliable per-child control | Reject as the general mechanism |
| Add only a large bootstrap prompt or skills plugin | Improves procedure and orientation | Cannot supply missing browser/filesystem/authentication or change supervisor admission | Use as one component |
| Extend existing HF1/Executive contracts with rich selectable compositions | Reuses lifecycle, packages, resource owners, capacity and return evidence; supports providers honestly | Requires coordinated implementation and real-path acceptance | **Recommended** |
| Replace the fabric with a new provider SDK/API platform | Potential future managed capabilities | Duplicates current owners, changes operational assumptions, adds migration before solving known gaps | Keep as a future adapter evaluation |
| Give every worker the same maximal visible catalog | Simple naming | Tool clutter, unsupported host/model combinations and shared-resource collisions | Use broad defaults plus role-focused loading and selectable resources |

## 8. Remaining uncertainty and how implementation resolves it

The decisive design questions are resolved. The remaining uncertainties concern installed acceptance:

1. Which exact remote host/provider/profile tuples can consume the complete role and tool contract?
2. Which browser and native-computer lanes are callable under the intended principal?
3. Can one real Operator complete a build/test/repair mission, delegate, resume and deliver a result consumed by its original parent?
4. Does knowledge retrieval stay current without creating a competing memory source?
5. Do shared capacity and exclusive resources remain accounted for under parallel children and recovery?
6. Does the richer environment measurably reduce CEO intervention and capability-related failures?

The master plan specifies the source changes, owners, artifacts and acceptance journeys that answer these questions. They should be treated as implementation gates, not filled with optimistic configuration claims.

## Source index

Internal source links are pinned to the census base; PR links identify active carriers.

[S1]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/control_plane/operator_harness_contract.py
[S2]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/control_plane/operator_harness_orchestrator.py
[S3]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/control_plane/executive_agent_capabilities.py
[S4]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/control_plane/executive_operator_supervisor.py
[S5]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/control_plane/executive_capability_packages.py
[S6]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/docs/superpowers/plans/2026-09-01-sol-capability-fabric-package-generation-convergence-index.md
[S7]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/scripts/ohf/capability_skill_projection.py
[S8]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/AGENTS.md
[S9]: https://github.com/mastermindx-market-intelligence/Mastermind/blob/326c8469a21d7f50fc9ecb1848196bf1c6e66685/control_plane/browser_resource_contract.py
[S10]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1145
[P600]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/600
[P1272]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1272
[P1267]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1267
[P1216]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1216
[P1217]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1217
[P1259]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1259
[P1302]: https://github.com/mastermindx-market-intelligence/Mastermind/pull/1302
[V1]: https://learn.chatgpt.com/docs/agent-configuration/subagents
[V2]: https://learn.chatgpt.com/docs/build-skills
[V3]: https://learn.chatgpt.com/docs/extend/mcp?surface=cli
[V4]: https://learn.chatgpt.com/docs/app-server
[V5]: https://code.claude.com/docs/en/sub-agents
[V6]: https://code.claude.com/docs/en/agent-sdk/subagents
[V7]: https://code.claude.com/docs/en/agent-sdk/permissions
[V8]: https://code.claude.com/docs/en/agent-sdk/plugins
[V9]: https://code.claude.com/docs/en/agent-sdk/mcp
[V10]: https://github.com/microsoft/playwright-mcp
[V11]: https://code.claude.com/docs/en/chrome
[V12]: https://modelcontextprotocol.io/specification/2026-07-28/changelog
