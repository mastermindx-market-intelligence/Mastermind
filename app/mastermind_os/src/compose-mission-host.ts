import { bindMissionHost, type RawClient, type SessionHostAttachment } from "./host";
import { readLaunchBindingConfig } from "./launch-config";
import type { MissionSelection } from "./mission";
import type { LaunchBindingConfig } from "./orchestration/executive-launch-command-port";
import { createIndexedDbPendingPointerStore } from "./orchestration/indexeddb-pending-pointer-store";
import { createIndexedDbSessionPendingPointerStore } from "./orchestration/indexeddb-session-pending-pointer-store";
import { createOsExecutiveHost } from "./orchestration/os-executive-host";
import { createOsExecutiveSessionHost } from "./orchestration/os-executive-session-host";

/**
 * One app instance composes the existing read/auth owner with the fixed
 * launch adapter and — independently — the selected-session continuation
 * host. Session continuation may exist without a Launch catalog; absent
 * Executive configuration/auth keeps it unavailable and it sends no requests.
 * The session store is a separate durable namespace: Launch records are never
 * read, migrated or cleared by it.
 */
export function composeMissionHost(
  client: RawClient,
  config: LaunchBindingConfig | null = readLaunchBindingConfig(),
  indexedDB: IDBFactory | undefined = globalThis.indexedDB,
) {
  // Mount while signed out: the existing auth owner later qualifies this binding.
  const executive = config && client.executive
    ? createOsExecutiveHost(config, client.executive, createIndexedDbPendingPointerStore(indexedDB))
    : null;
  // Separate session capability/controller and lifecycle; no shared slot with
  // the launch binding and no multiplexing through whichever screen is current.
  const session = client.executiveSession
    ? createOsExecutiveSessionHost(
        client.executiveSession,
        createIndexedDbSessionPendingPointerStore(indexedDB),
      )
    : null;
  const sessionAttachment: SessionHostAttachment | undefined = session
    ? {
        binding: session.binding,
        refresh: (selection) => session.refresh(selection as MissionSelection | null),
        setStopCondition: (provider) => session.setStopCondition(provider),
      }
    : undefined;
  return {
    host: bindMissionHost(client, executive?.binding, sessionAttachment),
    ready: executive?.ready ?? Promise.resolve(),
    sessionReady: session?.ready ?? Promise.resolve(),
    dispose: () => {
      executive?.dispose();
      session?.dispose();
    },
  };
}
