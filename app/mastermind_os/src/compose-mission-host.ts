import { bindMissionHost, type RawClient } from "./host";
import { readLaunchBindingConfig } from "./launch-config";
import type { LaunchBindingConfig } from "./orchestration/executive-launch-command-port";
import { createIndexedDbPendingPointerStore } from "./orchestration/indexeddb-pending-pointer-store";
import { createOsExecutiveHost } from "./orchestration/os-executive-host";

/** One app instance composes the existing read/auth owner with the fixed launch adapter. */
export function composeMissionHost(
  client: RawClient,
  config: LaunchBindingConfig | null = readLaunchBindingConfig(),
  indexedDB: IDBFactory | undefined = globalThis.indexedDB,
) {
  // Mount while signed out: the existing auth owner later qualifies this binding.
  const executive = config && client.executive
    ? createOsExecutiveHost(config, client.executive, createIndexedDbPendingPointerStore(indexedDB))
    : null;
  return {
    host: bindMissionHost(client, executive?.binding),
    ready: executive?.ready ?? Promise.resolve(),
    dispose: () => executive?.dispose(),
  };
}
