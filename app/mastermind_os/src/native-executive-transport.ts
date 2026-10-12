import type { OsExecutiveTransport } from "./orchestration/os-executive-host";

type Invoke = <T>(command: string, args?: Record<string, unknown>) => Promise<T>;
type Listen = (event: string, listener: (event: { payload: unknown }) => void) => Promise<() => void>;
function status(raw: unknown): { generation: number; available: boolean } | null {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const value = raw as Record<string, unknown>;
  return Object.keys(value).sort().join(",") === "available,generation" &&
    Number.isSafeInteger(value.generation) && Number(value.generation) >= 0 && typeof value.available === "boolean"
    ? { generation: Number(value.generation), available: value.available } : null;
}

/** Private native auth epoch; no token/claims enter the webview, no arbitrary native command. */
export async function createNativeExecutiveTransport(invoke: Invoke, listen: Listen) {
  let nativeGeneration = -1, epoch = 0, available = false;
  let generationAbort = new AbortController();
  const listeners = new Set<() => void>();
  const invalidate = (nextAvailable = false) => {
    epoch++; available = nextAvailable;
    const previous = generationAbort; generationAbort = new AbortController(); previous.abort();
    for (const listener of listeners) listener();
  };
  // A locally requested sign-in/out requires a later native auth generation.
  let minimumNativeGeneration = 0;
  const update = (raw: unknown) => {
    const next = status(raw);
    if (!next) { invalidate(); minimumNativeGeneration = nativeGeneration + 1; return; }
    if (next.generation < Math.max(nativeGeneration, minimumNativeGeneration)) return;
    if (next.generation === nativeGeneration && next.available === available) return;
    nativeGeneration = next.generation;
    invalidate(next.available);
  };
  let listening = false;
  try {
    await listen("mastermind-executive-auth-state", (event) => update(event.payload));
    listening = true;
  } catch { /* The read-only workspace remains usable without this optional capability. */ }
  const ready = (async () => {
    if (!listening) return;
    try {
      const started = epoch;
      const initial = await invoke("executive_auth_status");
      if (started === epoch) update(initial);
    } catch { /* Missing command remains unavailable. */ }
  })();

  function call(command: "executive_context" | "executive_submit" | "executive_status",
    signal: AbortSignal, args?: Record<string, unknown>): Promise<unknown> {
    const started = epoch, boundary = generationAbort.signal;
    if (!available || signal.aborted) return Promise.reject(new Error("EXECUTIVE_UNAVAILABLE"));
    return new Promise((resolve, reject) => {
      let settled = false;
      const finish = (failed: boolean, value: unknown) => {
        if (settled) return;
        settled = true; signal.removeEventListener("abort", abort); boundary.removeEventListener("abort", abort);
        failed ? reject(value) : resolve(value);
      };
      const abort = () => finish(true, new Error("EXECUTIVE_AUTH_CHANGED"));
      signal.addEventListener("abort", abort, { once: true }); boundary.addEventListener("abort", abort, { once: true });
      if (signal.aborted || boundary.aborted) { abort(); return; }
      try {
        Promise.resolve(invoke(command, args)).then((value) => {
          if (started !== epoch || !available || signal.aborted) abort(); else finish(false, value);
        }, () => { finish(true, new Error("EXECUTIVE_TRANSPORT_UNAVAILABLE")); });
      } catch { finish(true, new Error("EXECUTIVE_TRANSPORT_UNAVAILABLE")); }
    });
  }
  const transport: OsExecutiveTransport = {
    authGeneration: () => epoch, available: () => available,
    subscribe(listener) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    context: (signal) => call("executive_context", signal),
    submit: (arguments_, signal) => call("executive_submit", signal, { arguments: arguments_ }),
    status: (arguments_, signal) => call("executive_status", signal, { intentId: arguments_.intent_id }),
  };
  return { transport, ready, invalidate() { minimumNativeGeneration = nativeGeneration + 1; invalidate(); } };
}
