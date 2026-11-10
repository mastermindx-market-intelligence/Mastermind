import { useEffect, useState } from "react";
import { normalizeResultSelection, type ResultSelection } from "./result";
import { decodeExecutionReturnRead, type ExecutionReturnRead as ReadReturn,
  type ExecutionReturnReadDocument } from "./execution-return-read";
import { ResultReturnCard } from "./team/ResultReturnCard";

export function ExecutionReturnRead({ selection, read, authGeneration, hostGeneration, locale }: {
  selection: ResultSelection;
  read: ReadReturn;
  authGeneration: string | number;
  hostGeneration: string | number;
  locale: "en" | "zh-CN";
}) {
  const normalized = normalizeResultSelection(selection);
  const identity = JSON.stringify([normalized, authGeneration, hostGeneration]);
  const [state, setState] = useState<{ identity: string; read: ReadReturn;
    document: ExecutionReturnReadDocument | null; pending: boolean } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    setState({ identity, read, document: null, pending: true });
    if (!normalized) {
      setState({ identity, read, document: null, pending: false });
      return () => controller.abort();
    }
    void (async () => {
      try {
        const raw = await read({ ...normalized, signal: controller.signal });
        if (controller.signal.aborted) return;
        const document = await decodeExecutionReturnRead(raw, normalized);
        if (!controller.signal.aborted) setState({ identity, read, document, pending: false });
      } catch {
        if (!controller.signal.aborted) setState({ identity, read, document: null, pending: false });
      }
    })();
    return () => controller.abort();
  }, [identity, read]);
  const current = state?.identity === identity && state.read === read ? state : null;
  const zh = locale === "zh-CN";
  if (!current || current.pending) return <p className="muted" role="status">{zh ? "正在读取原始返回回执…" : "Reading the original return receipt…"}</p>;
  if (!current.document || current.document.availability !== "AVAILABLE") return <p className="muted" role="status">{zh ? "原始返回回执当前不可用。" : "The original return receipt is unavailable."}</p>;
  return <ResultReturnCard executionReturn={current.document.execution_return}
    deliveryReceipt={current.document.delivery_receipt} locale={locale} />;
}
