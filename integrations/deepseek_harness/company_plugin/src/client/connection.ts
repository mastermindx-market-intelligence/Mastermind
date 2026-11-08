import {createSnapshotStore} from "@deepseek-ai/dsh-client-store";
import {COMPANY_SCHEMA, DONOR_SHA, decodeParentMessage, type CompanyView, type ChildMessage} from "../protocol";

export const PARENT_ORIGIN = "https://mcp.mastermind-x.com";
export interface CompanySnapshot {readonly view: CompanyView | null; readonly refused: boolean;}
/** The existing parent supplies a qualified view, never a token or execution grant. */
export function createCompanyConnection(win: Window, parentOrigin = PARENT_ORIGIN) {
  const state = createSnapshotStore<CompanySnapshot>({view: null, refused: false});
  let nonce: string | null = null;
  let generation = -1;
  let disposed = false;
  const post = (message: ChildMessage) => {
    if (!disposed && win.parent !== win) win.parent.postMessage(message, parentOrigin);
  };
  const receive = (event: MessageEvent) => {
    if (disposed || event.source !== win.parent || event.origin !== parentOrigin) return;
    const message = decodeParentMessage(event.data);
    if (!message) return;
    if (message.type === "connect") {
      if (nonce !== message.nonce) {
        nonce = message.nonce;
        generation = -1;
        state.set({view: null, refused: false});
      }
      post({schema: COMPANY_SCHEMA, type: "ready", nonce, donor: DONOR_SHA});
      return;
    }
    if (!nonce || message.nonce !== nonce) return;
    if (message.type === "context") {
      if (message.view.generation < generation) return;
      generation = message.view.generation;
      state.set({view: message.view, refused: false});
      post({schema: COMPANY_SCHEMA, type: "ack", nonce, generation});
      return;
    }
    if (message.generation === generation && !message.ok)
      state.set({...state.getSnapshot(), refused: true});
  };
  win.addEventListener("message", receive);
  post({schema: COMPANY_SCHEMA, type: "hello"});
  return {
    state,
    openProject(workRef: string) {
      const view = state.getSnapshot().view;
      if (!nonce || !view || view.state !== "CURRENT" || !view.projects.some(p => p.workRef === workRef)) return false;
      post({schema: COMPANY_SCHEMA, type: "open_project", nonce, generation, workRef});
      return true;
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      win.removeEventListener("message", receive);
      nonce = null;
      state.set({view: null, refused: false});
    },
  };
}
