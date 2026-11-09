import { useEffect, useRef, useState, type ReactNode } from "react";
import type { NativeHermesPort } from "../hermes-native/contract";
import { nativeHermesPort } from "../hermes-native/native-port";
import { TeamWorkspace } from "./TeamWorkspace";
import type { TeamRosterRead } from "./team-roster";
import type { DelegatedTask } from "./delegated-task";

/** Closed error vocabulary of the existing native port (the same set
 * HermesNativePanel treats as knownErrors). Anything else is reported as
 * NATIVE_CLIENT_UNAVAILABLE; a code is never paraphrased into health. */
const knownErrors = new Set([
  "REQUEST_INVALID",
  "NATIVE_BUSY",
  "NATIVE_INSTALL_UNAVAILABLE",
  "NATIVE_PLATFORM_UNAVAILABLE",
  "NATIVE_CLIENT_NOT_STARTED",
  "NATIVE_AUTH_NOT_DISPATCHED",
  "NATIVE_RECOVERY_UNAVAILABLE",
  "AUTHENTICATION_CHANGED",
  "NATIVE_IDENTITY_CHANGED",
  "NATIVE_RECOVERY_REQUIRED",
  "NATIVE_RESPONSE_INVALID",
  "NATIVE_CLIENT_UNAVAILABLE",
]);

/** One bounded read of the team roster through the EXISTING native port, in
 * the same shape HermesNativePanel uses: one `status` to bind the runtime
 * scope (the port requires it before any scoped operation), then the
 * read-only `team_roster` dispatch. The closed echo check and the fail-closed
 * roster parse live inside the port/parseNativeView — this container adds no
 * transport, provider key, polling loop or retry, and issues the read exactly
 * once per component lifetime (StrictMode-safe via the started ref). When the
 * native host is absent (web/dev) the view is UNAVAILABLE with
 * NATIVE_PLATFORM_UNAVAILABLE, never an empty company. */
export function TeamRoute({
  locale = "en",
  port = nativeHermesPort,
  conversationPanel,
  delegatedTask,
  onOpenConversations,
  onOpenCode,
  previewAuthority = true,
}: {
  locale?: "en" | "zh-CN";
  port?: NativeHermesPort;
  /** The EXISTING conversation surface node (App-owned). Never a second transport. */
  conversationPanel?: ReactNode;
  delegatedTask?: DelegatedTask | null;
  onOpenConversations?: () => void;
  onOpenCode?: () => void;
  /** True while this surface can only observe (PREVIEW chips stay honest). */
  previewAuthority?: boolean;
}) {
  const [roster, setRoster] = useState<TeamRosterRead>(() =>
    port.available()
      ? { kind: "PENDING" }
      : { kind: "UNAVAILABLE", reason: "NATIVE_PLATFORM_UNAVAILABLE" },
  );
  const started = useRef(false);
  useEffect(() => {
    if (!port.available() || started.current) return;
    started.current = true;
    void (async () => {
      try {
        // The port requires one successful status to bind the runtime scope
        // before any other operation (native-port.ts and its roster tests).
        await port.request({ operation: "status" });
        const result = await port.request({ operation: "team_roster" });
        setRoster(
          result.roster
            ? { kind: "AVAILABLE", roster: result.roster }
            : {
                kind: "UNAVAILABLE",
                reason: result.code ?? "NATIVE_RESPONSE_INVALID",
              },
        );
      } catch (error) {
        const raw =
          typeof error === "string"
            ? error
            : error instanceof Error
              ? error.message
              : "";
        setRoster({
          kind: "UNAVAILABLE",
          reason: knownErrors.has(raw) ? raw : "NATIVE_CLIENT_UNAVAILABLE",
        });
      }
    })();
  }, [port]);
  return (
    <TeamWorkspace
      locale={locale}
      roster={roster}
      conversationPanel={conversationPanel}
      delegatedTask={delegatedTask}
      onOpenConversations={onOpenConversations}
      onOpenCode={onOpenCode}
      previewAuthority={previewAuthority}
    />
  );
}
