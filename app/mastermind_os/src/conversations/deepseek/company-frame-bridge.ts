import {
  COMPANY_SCHEMA, decodeChildMessage, decodeCompanyView,
  type CompanyView, type ParentMessage,
} from "../../../../../integrations/deepseek_harness/company_plugin/src/protocol";

interface FrameTarget { postMessage(message: ParentMessage, origin: string): void; }
export type CompanyBridgeState = "loading" | "connected" | "unavailable";

/** One iframe lifecycle; no credentials, commands, retries, or persistent state. */
export function createCompanyFrameBridge(options: {
  target: FrameTarget;
  origin: string;
  view: CompanyView;
  onOpenProject: (workRef: string) => boolean;
  onState: (state: CompanyBridgeState) => void;
}) {
  let current = decodeCompanyView(options.view);
  if (!current) throw new Error("Invalid company presentation");
  let view: CompanyView = current;
  let nonce = crypto.randomUUID();
  let paired = false;
  let disposed = false;
  const post = (message: ParentMessage) => {
    if (!disposed) options.target.postMessage(message, options.origin);
  };
  const publish = () => {
    if (paired) post({schema: COMPANY_SCHEMA, type: "context", nonce, view});
  };
  return {
    connect() {
      if (disposed) return;
      paired = false;
      nonce = crypto.randomUUID();
      options.onState("loading");
      post({schema: COMPANY_SCHEMA, type: "connect", nonce});
    },
    update(next: CompanyView) {
      const decoded = decodeCompanyView(next);
      if (disposed || !decoded || decoded.generation <= view.generation) return false;
      view = decoded;
      options.onState("loading");
      publish();
      return true;
    },
    receive(event: {source: unknown; origin: string; data: unknown}) {
      if (disposed || event.source !== options.target || event.origin !== options.origin) return;
      const message = decodeChildMessage(event.data);
      if (!message) return;
      if (message.type === "hello") {
        post({schema: COMPANY_SCHEMA, type: "connect", nonce});
        return;
      }
      if (message.nonce !== nonce) return;
      if (message.type === "ready") {
        paired = true;
        options.onState("loading");
        publish();
        return;
      }
      if (!paired) return;
      if (message.type === "ack") {
        if (message.generation === view.generation) options.onState("connected");
        return;
      }
      let ok = false;
      if (message.generation === view.generation && view.state === "CURRENT" &&
        view.projects.some(project => project.workRef === message.workRef)) {
        try { ok = options.onOpenProject(message.workRef) === true; } catch { /* A rejected view stays rejected. */ }
      }
      post({schema: COMPANY_SCHEMA, type: "navigation_result", nonce,
        generation: message.generation, workRef: message.workRef, ok});
    },
    dispose() {
      if (disposed) return;
      // Clear presentation in the original document before detaching it.
      if (paired) post({schema: COMPANY_SCHEMA, type: "context", nonce, view: {
        ...view, generation: view.generation + 1, state: "SIGNED_OUT", projects: [], selectedProject: null,
      }});
      disposed = true;
      paired = false;
    },
  };
}
