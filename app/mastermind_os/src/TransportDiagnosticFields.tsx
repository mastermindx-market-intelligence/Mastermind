import { useEffect, useRef, useState } from "react";
import type { NativeExecutiveObservation } from "./native-executive-observation";
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
  refreshNativeDiagnostics?: (request: { signal: AbortSignal }) => Promise<NativeExecutiveObservation>;
}) {
  const zh = props.locale === "zh-CN";
  const [local, setLocal] = useState<{reader: typeof props.refreshNativeDiagnostics; phase: "pending" | "ready" | "unavailable"; value?: NativeExecutiveObservation} | null>(null);
  const active = useRef<AbortController | null>(null);
  const latest = useRef(props.refreshNativeDiagnostics);
  latest.current = props.refreshNativeDiagnostics;
  useEffect(() => () => { active.current?.abort(); }, [props.refreshNativeDiagnostics]);
  const observed = local?.reader === props.refreshNativeDiagnostics ? local : null;
  const refresh = async () => {
    const reader = props.refreshNativeDiagnostics;
    if (!reader || observed?.phase === "pending") return;
    active.current?.abort();
    const controller = new AbortController(); active.current = controller;
    setLocal({ reader, phase: "pending" });
    try {
      const value = await reader({ signal: controller.signal });
      if (!controller.signal.aborted && latest.current === reader && active.current === controller)
        setLocal({ reader, phase: "ready", value });
    } catch {
      if (!controller.signal.aborted && latest.current === reader && active.current === controller)
        setLocal({ reader, phase: "unavailable" });
    }
  };
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
  const native = observed?.phase === "ready" ? observed.value : undefined;
  const closed = (value: unknown, allowed: readonly string[]) => typeof value === "string" && allowed.includes(value) ? value : "UNKNOWN";
  if (native) rows.push(
    {term: zh ? "最近本地原生观察" : "Last local native observation", code: native.wire === "v1" ? "LAST_EXPLICIT_LOCAL_READ" : "LEGACY_METADATA"},
    {term: zh ? "本地 Executive 配置" : "Local Executive configured", code: booleanCode(typeof native.configured === "boolean" ? native.configured : null, zh)},
    {term: zh ? "本地 Executive 可用性" : "Local Executive availability", code: booleanCode(typeof native.available === "boolean" ? native.available : null, zh)},
    {term: zh ? "本地 Executive 原因" : "Local Executive reason", code: closed(native.reason, ["UNCONFIGURED","NOT_ESTABLISHED","AUTHORIZING","EXCHANGING","AVAILABLE","EXPIRED","AUTHORIZATION_REFUSED","TOKEN_EXCHANGE_FAILED","TOKEN_RESPONSE_INVALID","AUTH_BROWSER_UNAVAILABLE","AUTH_TRANSACTION_EXPIRED","GENERATION_EXHAUSTED"])},
    {term: zh ? "本地 Executive 代次" : "Local Executive generation", code: Number.isSafeInteger(native.generation) && native.generation >= 0 ? String(native.generation) : "UNKNOWN"},
    {term: zh ? "最近原生 Projects 读取" : "Last native Projects read", code: closed(native.programsRead?.phase, ["NOT_OBSERVED","PENDING","READY","AUTH_UNAVAILABLE","HTTP_FAILURE","NETWORK_FAILURE","TIMEOUT","BODY_FAILURE","INVALID_RESPONSE"])},
    {term: zh ? "最近 Projects HTTP 状态" : "Last Projects HTTP status", code: typeof native.programsRead?.httpStatus === "number" && Number.isInteger(native.programsRead.httpStatus) && native.programsRead.httpStatus >= 100 && native.programsRead.httpStatus <= 599 ? String(native.programsRead.httpStatus) : "UNKNOWN"},
  );
  return (<>
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
    {props.refreshNativeDiagnostics ? <div>
      <button type="button" disabled={observed?.phase === "pending"} onClick={() => { void refresh(); }}>
        {zh ? "刷新本地原生诊断" : "Refresh local native diagnostics"}
      </button>
      <p className="muted">{zh ? "仅查看本地状态；不会登录或刷新项目。" : "Reads local status only. It does not sign in or refresh projects."}</p>
      <p role="status">{observed?.phase === "pending" ? (zh ? "正在读取本地状态。" : "Reading local status.") : observed?.phase === "unavailable" ? (zh ? "无法读取本地诊断。" : "Local diagnostics unavailable.") : null}</p>
    </div> : null}
  </>);

}
