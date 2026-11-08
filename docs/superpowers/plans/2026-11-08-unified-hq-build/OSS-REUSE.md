# OSS reuse decisions and exact inspected interfaces

Primary source inspection: 2026-11-08. The commits below are the inspected repository heads, not claims about latest published npm releases. No donor implementation code or assets are copied by this package.

## Decision table

| Build | Preferred reuse | Scope and reason |
|---|---|---|
| A Company HQ | Selected Paperclip source patterns | Adapt project/company navigation, reporting tree and details to Mastermind callbacks; do not import the Paperclip application |
| B Living HQ | @xyflow/react | Supported React graph rendering/interaction; keep canonical data and layout projection outside the library |
| C Observatory | Selected AgentPrism UI source and compatible types/data helpers when needed | Useful trace tree/timeline/inspector, but source-copy UI and alpha API require an explicit adaptation boundary |
| D adapters | Mastermind's existing qualifiers/owner DTOs | Donor telemetry schemas do not create real traces, placement or enrollment |
| I integration | Existing Mastermind app shell, auth, readers and release | Reconcile exact dependency closure once; never copy donor manifests wholesale |

## Paperclip

Repository pin: [paperclipai/paperclip@a4dbde6181bcc2bd4c3ad0443dc00eb4e040356d](https://github.com/paperclipai/paperclip/tree/a4dbde6181bcc2bd4c3ad0443dc00eb4e040356d).

[LICENSE](https://github.com/paperclipai/paperclip/blob/a4dbde6181bcc2bd4c3ad0443dc00eb4e040356d/LICENSE) is MIT. Preserve copyright and permission notices for substantial copied source; inspect the exact assets/dependency closure actually adopted.

Do not treat @paperclipai/ui as a public component SDK. The [UI package](https://github.com/paperclipai/paperclip/blob/a4dbde6181bcc2bd4c3ad0443dc00eb4e040356d/ui/package.json) is described as prebuilt board UI assets; its generated publication is not a stable exported component API.

Useful inspected source: ui/src/pages/Org.tsx and OrgChart.tsx, plus CompanySwitcher, AgentIdentity, AgentLifecycleStatus, AgentAvatar, AgentCapsule and ActivityFeed/List/Row components. Org is coupled to useCompany, useBreadcrumbs, TanStack Query, agentsApi.org, queryKeys, routing helpers and @paperclipai/shared. Replace those dependencies with existing Mastermind projections and callbacks. Never import agentsApi.org as a new data owner.

The donor manifest uses React 19.2, Router 7, TanStack Query 5, panels 4, Tailwind 4 tooling and many adapter/editor/terminal packages. Mastermind's app is much smaller. Copying the manifest would introduce a second application dependency stack.

## XYFlow / React Flow

Repository pin: [xyflow/xyflow@1bc405cd113618c17fd181b931a9fe573bec9fee](https://github.com/xyflow/xyflow/tree/1bc405cd113618c17fd181b931a9fe573bec9fee).

[LICENSE](https://github.com/xyflow/xyflow/blob/1bc405cd113618c17fd181b931a9fe573bec9fee/LICENSE) is MIT. The inspected [packages/react/package.json](https://github.com/xyflow/xyflow/blob/1bc405cd113618c17fd181b931a9fe573bec9fee/packages/react/package.json) is @xyflow/react 12.12.1, with React/React DOM and types peers >=17. This is manifest compatibility evidence for React 19.3.0, not a tested Mastermind installation or npm availability claim.

Verified reusable exports include ReactFlow, ReactFlowProvider, Handle, Panel, Background, Controls, MiniMap, BaseEdge, EdgeLabelRenderer, NodeToolbar, NodeResizer, useReactFlow, useNodesState, useEdgesState, applyNodeChanges, applyEdgeChanges, getNodesBounds and getViewportForBounds. CSS exports include dist/style.css and dist/base.css. Avoid experimental middleware exports in this first build.

The package depends on @xyflow/system, classcat and Zustand. B should pin an actually available compatible published version and return one exact root-dependency proposal to I, with peer/build proof. Graph components must not leak the library's Node/Edge types into the shared domain contract.

## AgentPrism

Repository pin: [evilmartians/agent-prism@4fd371b5e4f25acd04278e94a0d4b21e543eb42c](https://github.com/evilmartians/agent-prism/tree/4fd371b5e4f25acd04278e94a0d4b21e543eb42c).

[LICENSE](https://github.com/evilmartians/agent-prism/blob/4fd371b5e4f25acd04278e94a0d4b21e543eb42c/LICENSE) is MIT. Its [README](https://github.com/evilmartians/agent-prism/blob/4fd371b5e4f25acd04278e94a0d4b21e543eb42c/readme.md) labels it alpha and documents source-copy installation for UI.

@evilmartians/agent-prism-ui is [private](https://github.com/evilmartians/agent-prism/blob/4fd371b5e4f25acd04278e94a0d4b21e543eb42c/packages/ui/package.json); do not instruct npm installation of that package. The documented published package names are @evilmartians/agent-prism-data and @evilmartians/agent-prism-types. The source manifest versions inspected by the researcher are 1.0.0, not a registry-release guarantee.

TraceViewer takes data entries containing traceRecord and spans. Other components include TraceList, TreeView and DetailsView; types include TraceRecord and TraceSpan. Data adapters include openTelemetrySpanAdapter and langfuseSpanAdapter. The documented conversion includes convertRawDocumentsToSpans; reviveTraceSpan restores Dates after JSON loading.

Use a thin presentation mapping only when real owner data supplies the needed semantics. Do not manufacture OpenTelemetry spans from chat prose or synthesize costs/time to satisfy a donor type. A smaller adapted tree/inspector is preferable to fake instrumentation.

Dependency issue: AgentPrism expects React 19+, Tailwind 3, panels 3, Radix Collapsible/Tabs, classnames, lucide-react 0.534 and react-json-pretty. Paperclip uses Tailwind 4 and panels 4. Adapt selected UI to Mastermind tokens/components; do not bulk-install conflicting donor stacks.

## cdesktop — candidate inspected, intended identity unconfirmed

Candidate: [cdesktop-ai/cdesktop@75bd015e88f9797d785c9fabcfca03c7151fd5cc](https://github.com/cdesktop-ai/cdesktop/tree/75bd015e88f9797d785c9fabcfca03c7151fd5cc). Its [README](https://github.com/cdesktop-ai/cdesktop/blob/75bd015e88f9797d785c9fabcfca03c7151fd5cc/README.md) explicitly describes Hermes among supported CLI agents and a session/transcript UI.

The supplied project handoff gives no cdesktop repository URL, so this cannot be asserted as the intended donor. Inspection is still useful: it is a React/TypeScript plus Rust/Tauri/SQLite application, not an established reusable trace SDK. Do not import its agent spawning, transcript store, provider catalog or orchestration backend.

Its [NOTICE](https://github.com/cdesktop-ai/cdesktop/blob/75bd015e88f9797d785c9fabcfca03c7151fd5cc/NOTICE) states Apache-2.0 and identifies modified BloopAI/vibe-kanban source and MIT cc-switch preset data. Any later copying must verify the exact LICENSE and retain applicable NOTICE/modification attribution. For this package, use only the observed UI concept reference and defer code extraction; the ambiguity does not block C or D.

## Integration and acceptance implications

Inspect actual package availability and peers at implementation; repository manifests are not installed dependency proof. I serializes root manifests and lockfiles. Preserve library notices for copied material. Test canonical identity/selection retention, stale generations, orphan/cyclic graphs, null timestamps, authorized sanitized content, reduced motion and accessible alternatives. Imported donor quality is not proof of the Mastermind consumer or live telemetry.

