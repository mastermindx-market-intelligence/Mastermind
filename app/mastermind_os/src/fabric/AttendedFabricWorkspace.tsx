import { useState } from "react";
import type { MissionHost } from "../host";
import { AttendedFabricInspector } from "./AttendedFabricInspector";
import { FabricRunCatalog } from "./FabricRunCatalog";

/** A catalog click fills the existing inspector; it never starts a read or worker. */
export function AttendedFabricWorkspace({ host, locale = "en" }: { host?: MissionHost; locale?: "en" | "zh-CN" }) {
  const [selection, setSelection] = useState<{
    rootId: string; runId: string; sourceEpoch: number; sourceHost: MissionHost;
  } | null>(null);
  const epoch = host?.invalidationGeneration?.();
  const visible = selection?.sourceHost === host && selection?.sourceEpoch === epoch ? selection : null;
  return <>
    <FabricRunCatalog host={host} locale={locale} onInspect={tuple => {
      const generation = host?.invalidationGeneration?.();
      const state = host?.auth?.getState();
      if (host && Number.isSafeInteger(generation) && generation !== undefined && state?.status === "signed_in" && state.acquisition)
        setSelection({ ...tuple, sourceEpoch: generation, sourceHost: host });
    }} />
    <AttendedFabricInspector key={epoch} host={host} locale={locale} selection={visible} />
  </>;
}
