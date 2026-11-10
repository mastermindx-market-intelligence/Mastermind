import { bindMissionHost, type RawClient, type SessionHostAttachment } from "./host";
import { createProjectConversationHistoryReaderFactory } from "./conversations/project-conversation-history-owner";
import {createProjectConversationCatalogueReaderFactory} from './conversations/project-conversation-catalogue-factory';
import { readLaunchBindingConfig } from "./launch-config";
import type { ExecutiveSessionSelection } from "./orchestration/executive-session-command-port";
import type { LaunchConfiguration } from "./orchestration/executive-launch-command-port";
import { createIndexedDbPendingPointerStore } from "./orchestration/indexeddb-pending-pointer-store";
import { createIndexedDbSessionPendingPointerStore } from "./orchestration/indexeddb-session-pending-pointer-store";
import type { OsExecutiveTransport } from "./orchestration/os-executive-host";
import { createOsExecutiveHost } from "./orchestration/os-executive-host";
import { createOsExecutiveSessionHost } from "./orchestration/os-executive-session-host";
import { validateExecutiveResource } from "./public-config";
import { isDiagnosticReadReason } from "./diagnostic-state";
import type {
  DiagnosticHostKind,
  DiagnosticReadReason,
  DiagnosticPhase,
  MissionDiagnosticSnapshot,
} from "./diagnostic-state";

// Closed phase vocabulary from the frozen diagnostic contract. A value
// outside it degrades to "unknown" instead of being trusted.
const DIAGNOSTIC_PHASES: readonly DiagnosticPhase[] = [
  "unknown",
  "not_requested",
  "pending",
  "auth_unavailable",
  "transport_failure",
  "invalid_response",
  "expired",
  "ready",
];

function closedPhase(value: unknown): DiagnosticPhase {
  return DIAGNOSTIC_PHASES.includes(value as DiagnosticPhase)
    ? (value as DiagnosticPhase)
    : "unknown";
}

/** Transport-reported Executive availability; never inferred from auth state. */
function executiveObservation(transport: OsExecutiveTransport | undefined): {
  authAvailable: boolean | null; phase: DiagnosticPhase; readReason: DiagnosticReadReason;
} {
  try {
    const value = transport?.diagnostics?.();
    return { authAvailable: typeof value?.authAvailable === "boolean" ? value.authAvailable : null,
      phase: closedPhase(value?.phase),
      readReason: isDiagnosticReadReason(value?.contextReadReason) ? value.contextReadReason : "UNKNOWN" };
  } catch { return { authAvailable: null, phase: "unknown", readReason: "UNKNOWN" }; }
}

/**
 * One app instance composes the existing read/auth owner with the shared
 * Executive command owner and the independent selected-session continuation
 * host. A Launch catalog enables only legacy Launch choices; project work and
 * fresh conversations use the same command context and store without it.
 * Absent Executive configuration/auth keeps these owners unavailable.
 * The session store is a separate durable namespace: Launch records are never
 * read, migrated or cleared by it.
 */
export function composeMissionHost(
  client: RawClient,
  config: LaunchConfiguration | null = readLaunchBindingConfig(),
  indexedDB: IDBFactory | undefined = globalThis.indexedDB,
  hostKind: DiagnosticHostKind = "unknown",
) {
  // Mount while signed out: the existing auth owner later qualifies this binding.
  const executive = client.executive
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
  const projectHistoryReader = client.executiveSession
    ? createProjectConversationHistoryReaderFactory(client.executiveSession) : undefined;
  const projectCatalogueReader = client.executiveSession
    ? createProjectConversationCatalogueReaderFactory(client.executiveSession) : undefined;
  const sessionAttachment: SessionHostAttachment | undefined = session
    ? {
        binding: session.binding,
        ...(projectHistoryReader ? {createProjectHistoryReader: projectHistoryReader} : {}),
        ...(projectCatalogueReader ? {createProjectCatalogueReader: projectCatalogueReader} : {}),
        // The session selection carries the closed target kind; the generic
        // attachment keeps its opaque signature.
        refresh: (selection) =>
          session.refresh(selection as ExecutiveSessionSelection | null),
        setStopCondition: (provider) => session.setStopCondition(provider),
      }
    : undefined;
  // Observer-only composition snapshot. Reading it performs no request, no
  // subscription change and no context refresh: it only reports facts the
  // existing auth owner and transports already hold.
  const diagnostics = (): MissionDiagnosticSnapshot => {
    let contextPhase: DiagnosticPhase = "not_requested";
    if (executive) {
      try {
        contextPhase = closedPhase(executive.diagnostics().contextPhase);
      } catch {
        contextPhase = "unknown";
      }
    }
    const auth = client.getState();
    const executiveState = executiveObservation(client.executive);
    return {
      hostKind,
      launchConfigured: config !== null,
      frontendResourceConfigured:
        validateExecutiveResource(import.meta.env?.VITE_MM_EXECUTIVE_RESOURCE) !== null,
      // The current wire exposes no native resource configuration; it is
      // never inferred from grants, config objects or auth outcomes.
      nativeResourceConfigured: null,
      acquisitionAvailable: typeof auth.acquisition === "boolean" ? auth.acquisition : null,
      contentAvailable: typeof auth.content === "boolean" ? auth.content : null,
      executiveAvailable: executiveState.authAvailable,
      executiveTransportPhase: executiveState.phase,
      executiveReadReason: executiveState.readReason,
      executiveContextPhase: contextPhase,
    };
  };
  const host = bindMissionHost(client, executive?.binding, sessionAttachment);
  host.diagnostics = diagnostics;
  return {
    host,
    ready: executive?.ready ?? Promise.resolve(),
    sessionReady: session?.ready ?? Promise.resolve(),
    dispose: () => {
      executive?.dispose();
      session?.dispose();
    },
  };
}
