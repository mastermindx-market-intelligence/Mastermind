import type { MissionDiagnosticSnapshot } from "./diagnostic-state";
import type { NativeExecutiveObservation } from "./native-executive-observation";

/** Presentation of existing observations only. Never grants access or infers
 * live tokens, backend readiness, a provider cause or permission to retry. */
export function workConnectionPresentation(
  snapshot: MissionDiagnosticSnapshot | null,
  observation: NativeExecutiveObservation | undefined,
  locale: string,
): { title: string; description: string } | null {
  if (snapshot?.hostKind !== "native" || snapshot.acquisitionAvailable !== true ||
      snapshot.contentAvailable !== true) return null;
  const zh = locale === "zh-CN";
  const text = (en: string, cn: string) => zh ? cn : en;
  // Current transport readiness wins over an older explicit local observation.
  if (snapshot.executiveAvailable === true && snapshot.executiveContextPhase === "ready") return null;
  if (observation?.wire === "v1" && !observation.available) {
    switch (observation.reason) {
      case "AUTHORIZATION_REFUSED": return {
        title: text("Work authorization was not granted", "工作授权未获批准"),
        description: text("The latest local observation reports that work authorization was not granted.", "最近的本地观察显示工作授权未获批准。"),
      };
      case "EXPIRED": return {
        title: text("Work authorization expired", "工作授权已过期"),
        description: text("The latest local observation reports expired work authorization.", "最近的本地观察显示工作授权已过期。"),
      };
      case "AUTHORIZING": case "EXCHANGING": return {
        title: text("Work authorization is in progress", "工作授权正在进行中"),
        description: text("The latest local observation reports an authorization still in progress. Work access is not confirmed.", "最近的本地观察显示授权仍在进行中；工作访问尚未确认。"),
      };
      case "AUTH_TRANSACTION_EXPIRED": return {
        title: text("Work authorization timed out", "工作授权已超时"),
        description: text("The latest local observation reports that work authorization timed out.", "最近的本地观察显示工作授权已超时。"),
      };
    }
  }
  if (observation?.available !== true && snapshot.executiveAvailable === false &&
      (snapshot.executiveTransportPhase === "auth_unavailable" || snapshot.executiveContextPhase === "auth_unavailable")) return {
    title: text("Work connection unavailable", "工作连接不可用"),
    description: text("Work authorization is unavailable. Open connection details to inspect local status.", "工作授权当前不可用。展开连接详情可查看本地状态。"),
  };
  return {
    title: text("Work connection not confirmed", "工作连接尚未确认"),
    description: text("Starting work is unavailable here. Connection details show the reported status; they do not sign you in or refresh projects.", "此处暂时无法开始工作。连接详情仅显示已报告的状态，不会登录或刷新项目。"),
  };
}
