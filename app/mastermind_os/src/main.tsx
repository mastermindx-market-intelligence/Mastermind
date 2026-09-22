import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { isTauri, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { App } from "./App";
import { bindMissionHost, createNativeClient } from "./host";
import { createWebAuth, handleWebAuthCallback } from "./web-auth";
import "./styles.css";

async function mount() {
  // The exact callback completes and cleans up before the product can mount.
  if (!isTauri() && handleWebAuthCallback()) return;
  try {
    const client = isTauri()
      ? await createNativeClient(invoke, listen)
      : createWebAuth();
    window.MastermindMissionHost = bindMissionHost(client);
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
