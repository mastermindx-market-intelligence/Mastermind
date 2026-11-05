import { useEffect, useRef, useState } from "react";
import type { MissionHost } from "../host";
import type { ResourceCapacityReadSelection } from "./resource-capacity-read";
import { validResourceCapacitySelection } from "./resource-capacity-read";
import type { RetainedProviderCapacityState } from "./retained-provider-capacity";
import { RetainedProviderCapacityPanel } from "./RetainedProviderCapacityPanel";
import "./resources.css";

/** Explicit read of an exact caller-qualified current work/Attempt. No discovery,
 * worker placement, acknowledgement or refresh of original observation time. */
export function ResourceCapacityRead({ host, selection, locale = "en" }: {
  host?: MissionHost; selection?: ResourceCapacityReadSelection | null; locale?: "en" | "zh-CN";
}) {
  const zh = locale === "zh-CN";
  const selected = selection && validResourceCapacitySelection(selection) ? selection : null;
  const key = selected ? JSON.stringify([selected.work_ref, selected.root_job_id, selected.job_id, selected.attempt_id]) : null;
  const reader = host?.readResourceCapacity;
  const epoch = host?.invalidationGeneration?.();
  const auth = host?.auth?.getState();
  const permitted = !!host && !!reader && !!selected && Number.isSafeInteger(epoch) && auth?.status === "signed_in" && auth.acquisition;
  const [value, setValue] = useState<{ host: MissionHost; reader: typeof reader; key: string; epoch: number; state: RetainedProviderCapacityState } | null>(null);
  const abort = useRef<AbortController | null>(null);
  const current = useRef({ host, reader, key });
  current.current = { host, reader, key };
  useEffect(() => {
    abort.current?.abort();
    setValue(null);
    const stop = host?.auth?.subscribe(() => { abort.current?.abort(); setValue(null); });
    return () => { abort.current?.abort(); stop?.(); };
  }, [host, reader, key]);
  const visible = permitted && value?.host === host && value.reader === reader && value.key === key && value.epoch === epoch ? value.state : null;
  const load = async () => {
    if (!host || !reader || !selected || !permitted || !key || epoch === undefined) return;
    abort.current?.abort();
    const controller = new AbortController(); abort.current = controller;
    const owned = { host, reader, key, epoch };
    const stillOwned = () => {
      const state = host.auth?.getState();
      return !controller.signal.aborted && current.current.host === host && current.current.reader === reader && current.current.key === key &&
        host.invalidationGeneration?.() === epoch && state?.status === "signed_in" && state.acquisition;
    };
    setValue({ ...owned, state: { state: "PENDING" } });
    try {
      const result = await reader({ ...selected, signal: controller.signal });
      if (stillOwned()) setValue({ ...owned, state: result });
    } catch {
      if (stillOwned()) setValue({ ...owned, state: { state: "UNAVAILABLE" } });
    }
  };
  return <section className="resources-workspace" aria-label={zh ? "读取所选工作的原始容量证据" : "Read original capacity evidence for selected work"}>
    <p className="muted">{selected
      ? zh ? "查看此工作尝试的原始供应商观测。读取不会安排或启动工作。" : "Inspect the original provider observation for this work attempt. Reading does not place or start work."
      : zh ? "打开具体工作项，查看其原始供应商凭据。" : "Open a work item to inspect its original provider receipt."}</p>
    <button type="button" onClick={() => void load()} disabled={!permitted || visible?.state === "PENDING"}>
      {visible?.state === "PENDING" ? zh ? "正在读取…" : "Reading…" : zh ? "读取原始认领" : "Read original claim"}
    </button>
    {selected && <RetainedProviderCapacityPanel state={visible ?? { state: "UNAVAILABLE" }} locale={locale} />}
  </section>;
}
