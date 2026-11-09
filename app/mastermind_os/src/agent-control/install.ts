import { APP_CONTROL_SCHEMA, createAppControl, type ControlContext } from "./control";
import tools from "./tools.json";
import type { MissionHost } from "../host";

export type AppToolName = typeof tools[number]["name"];
export interface AppControlApi {
  readonly schema: typeof APP_CONTROL_SCHEMA;
  tools(): typeof tools;
  call(name: string, input?: unknown, options?: { signal?: AbortSignal }): Promise<unknown>;
  transport(): "REGISTERING" | "WEBMCP" | "BRIDGE_ONLY" | "REGISTRATION_FAILED" | "DISPOSED";
}
declare global { interface Window { MastermindAppControl?: AppControlApi; } }

/** Narrow structural adapter, not a replacement WebMCP implementation/polyfill. */
interface RegistrationContext {
  registerTool(tool: { name: string; description: string; inputSchema: object; annotations: object;
    execute(input: unknown, options?: { signal?: AbortSignal }): Promise<unknown> }, options: { signal: AbortSignal }): Promise<unknown> | void;
}

export function appControlContext(host: MissionHost | undefined): ControlContext {
  const state = host?.auth?.getState();
  const generation = host?.invalidationGeneration?.();
  return { owner: host ?? null, generation, auth: state?.status ?? "unknown",
    content: state?.content === true, acquisition: state?.acquisition === true };
}

/** Mount once at the existing app root. The app's host retains all authentication. */
export function installAppControl(root: HTMLElement, readContext = () => appControlContext(window.MastermindMissionHost)) {
  const window = root.ownerDocument.defaultView!;
  if (window.MastermindAppControl) throw new Error("APP_CONTROL_ALREADY_INSTALLED");
  const control = createAppControl(root, readContext);
  const registration = new AbortController();
  let transport: ReturnType<AppControlApi["transport"]> = "BRIDGE_ONLY";
  let disposed = false;
  const refused = (code: string) => ({ schema: APP_CONTROL_SCHEMA, status: "REFUSED", code });
  const api: AppControlApi = Object.freeze({
    schema: APP_CONTROL_SCHEMA,
    tools: () => structuredClone(tools),
    transport: () => transport,
    async call(name: string, input: unknown = {}, options?: { signal?: AbortSignal }) {
      if (transport === "DISPOSED") return refused("APP_UNAVAILABLE");
      if (options?.signal?.aborted) return refused("CANCELLED_BEFORE_DISPATCH");
      // Validation and currentness checks remain inside the shared control implementation.
      if (name === "mastermind_os_inspect") return control.inspect(input);
      if (name === "mastermind_os_check") return control.check(input);
      if (name === "mastermind_os_act") return control.act(input);
      if (name === "mastermind_os_navigate") return control.navigate(input);
      return refused("TOOL_UNAVAILABLE");
    },
  });
  Object.defineProperty(window, "MastermindAppControl", { value: api, configurable: true, writable: false });
  const modelContext = (root.ownerDocument as Document & { modelContext?: RegistrationContext }).modelContext;
  const ready = (async () => {
    if (typeof modelContext?.registerTool !== "function") return;
    transport = "REGISTERING";
    try {
      for (const tool of tools) {
        if (registration.signal.aborted) return;
        await modelContext.registerTool({ ...tool, execute: (input, options) => api.call(tool.name, input, options) }, { signal: registration.signal });
      }
      if (!registration.signal.aborted) transport = "WEBMCP";
    } catch {
      // Retire only our registrations. Never clear another producer's context.
      registration.abort();
      if (!disposed) transport = "REGISTRATION_FAILED";
    }
  })();
  return { api, ready, dispose() {
    disposed = true; transport = "DISPOSED"; registration.abort(); control.dispose();
    if (window.MastermindAppControl === api) delete window.MastermindAppControl;
  } };
}
