import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { isTauri, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { App } from "./App";
import { DisplayPreferences, DisplayPreferencesRoot } from "./preferences/DisplayPreferences";
import { createNativeClient } from "./host";
import { composeMissionHost } from "./compose-mission-host";
import { createWebAuth, handleWebAuthCallback } from "./web-auth";
import "./styles.css";
import { EVIDENCE_PATH, evidenceRoute } from "./research/evidence-contract";
import { ResearchEvidenceEntry } from "./research/ResearchEvidenceEntry";

async function mount() {
  // The exact callback completes and cleans up before the product can mount.
  if (!isTauri() && handleWebAuthCallback()) return;
  if (!isTauri() && location.pathname.startsWith(EVIDENCE_PATH)) {
    const itemId = evidenceRoute(location);
    const client = itemId ? createWebAuth() : null;
    createRoot(document.getElementById("root")!).render(
      <StrictMode><ResearchEvidenceEntry itemId={itemId} transport={client?.research} signOut={() => client?.signOut() ?? Promise.resolve()} /></StrictMode>,
    );
    return;
  }
  try {
    const client = isTauri()
      ? await createNativeClient(invoke, listen)
      : createWebAuth();
    if (!isTauri()) void client.restore?.().catch(() => {});
    // The reported host kind is the actual mount surface; it changes no
    // transport choice, request or subscription behavior.
    const composition = composeMissionHost(client, undefined, undefined, isTauri() ? "native" : "web");
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
      <DisplayPreferencesRoot>
        {({ theme, locale, control }) => <App theme={theme} locale={locale}
          preferencesControl={<DisplayPreferences control={control} />} />}
      </DisplayPreferencesRoot>
    </StrictMode>,
  );
}
void mount();
