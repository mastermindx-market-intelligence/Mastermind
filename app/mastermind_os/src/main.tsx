import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { isTauri, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { App } from "./App";
import { createNativeClient } from "./host";
import { composeMissionHost } from "./compose-mission-host";
import { createWebAuth, handleWebAuthCallback } from "./web-auth";
import "./styles.css";

async function mount() {
  // The exact callback completes and cleans up before the product can mount.
  if (!isTauri() && handleWebAuthCallback()) return;
  try {
    const client = isTauri()
      ? await createNativeClient(invoke, listen)
      : createWebAuth();
    const composition = composeMissionHost(client);
    window.MastermindMissionHost = composition.host;
    void composition.ready.catch(() => {});
    const onPageHide = (event: PageTransitionEvent) => { if (!event.persisted) composition.dispose(); };
    window.addEventListener("pagehide", onPageHide);
    import.meta.hot?.dispose(() => {
      window.removeEventListener("pagehide", onPageHide);
      composition.dispose();
    });
  } catch {
    // The existing unavailable surface truthfully reports an absent host.
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
void mount();
