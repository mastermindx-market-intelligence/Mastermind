import type {
  DiagnosticHostKind,
  DiagnosticPhase,
  DiagnosticReadReason,
  MissionDiagnosticSnapshot,
} from "./diagnostic-state";
import { decodeMissionDiagnostics, isDiagnosticReadReason } from "./diagnostic-state";

// Closed vocabularies from the frozen diagnostic contract. Anything outside
// them renders as the fixed unknown code; input is never stringified.
const HOST_KINDS: readonly DiagnosticHostKind[] = ["native", "web", "unknown"];
const PHASES: readonly DiagnosticPhase[] = [
  "unknown",
  "not_requested",
  "pending",
  "auth_unavailable",
  "transport_failure",
  "invalid_response",
  "expired",
  "ready",
];

function hostCode(value: DiagnosticHostKind): DiagnosticHostKind {
  return HOST_KINDS.includes(value) ? value : "unknown";
}

function phaseCode(value: DiagnosticPhase): DiagnosticPhase {
  return PHASES.includes(value) ? value : "unknown";
}

function booleanCode(value: boolean | null, zh: boolean): string {
  if (value === null) return zh ? "未知" : "Unknown";
  return value ? (zh ? "是" : "Yes") : (zh ? "否" : "No");
}

/**
 * Observer-only diagnostic fields appended to the existing fallback Technical
 * details disclosures. The snapshot is untrusted: decodeMissionDiagnostics
 * rejects every non-conforming shape, and a rejected or absent snapshot
 * renders the fixed unknown values — never raw exception text, URLs, tokens,
 * principals or account identifiers. This reports availability facts only;
 * it confers no authority and triggers nothing.
 */
export function TransportDiagnosticFields(props: {
  snapshot: unknown;
  programsPhase: DiagnosticPhase;
  programsReason?: DiagnosticReadReason;
  locale: string;
}) {
  const zh = props.locale === "zh-CN";
  const d: MissionDiagnosticSnapshot | null = decodeMissionDiagnostics(
    props.snapshot,
  );
  const rows: Array<{ term: string; code: string }> = [
    { term: zh ? "宿主" : "Host", code: d ? hostCode(d.hostKind) : "unknown" },
    {
      term: zh ? "Launch 配置" : "Launch configured",
      code: booleanCode(d ? d.launchConfigured : null, zh),
    },
    {
      term: zh ? "前端 Executive 资源" : "Frontend Executive resource",
      code: booleanCode(d ? d.frontendResourceConfigured : null, zh),
    },
    {
      term: zh ? "原生 Executive 资源" : "Native Executive resource",
      // The current wire exposes no native resource configuration; it stays
      // unknown instead of being inferred from any grant or auth outcome.
      code: booleanCode(d ? d.nativeResourceConfigured : null, zh),
    },
    {
      term: zh ? "Acquisition 可用性" : "Acquisition availability",
      code: booleanCode(d ? d.acquisitionAvailable : null, zh),
    },
    {
      term: zh ? "Content 可用性" : "Content availability",
      code: booleanCode(d ? d.contentAvailable : null, zh),
    },
    {
      term: zh ? "Executive 可用性" : "Executive availability",
      code: booleanCode(d ? d.executiveAvailable : null, zh),
    },
    {
      term: zh ? "Executive 授权状态阶段" : "Executive auth-status phase",
      code: d ? phaseCode(d.executiveTransportPhase ?? "unknown") : "unknown",
    },
    {
      term: zh ? "Executive 上下文阶段" : "Executive context phase",
      code: d ? phaseCode(d.executiveContextPhase) : "unknown",
    },
    {
      term: zh ? "Executive 最近读取原因" : "Executive read reason",
      code: d?.executiveReadReason ?? "UNKNOWN",
    },
    {
      term: zh ? "Projects 读取阶段" : "Projects read phase",
      code: phaseCode(props.programsPhase),
    },
    {
      term: zh ? "Projects 最近读取原因" : "Projects read reason",
      code: isDiagnosticReadReason(props.programsReason) ? props.programsReason : "UNKNOWN",
    },
  ];
  return (
    <dl className="muted">
      {rows.map((row) => (
        <div key={row.term}>
          <dt>{row.term}</dt>
          <dd>
            <code>{row.code}</code>
          </dd>
        </div>
      ))}
    </dl>
  );
}
