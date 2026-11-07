import { invoke, isTauri } from "@tauri-apps/api/core";
import { parseNativeView, type NativeHermesPort } from "./contract";

/** No browser fetch, native URL, bearer, profile picker, or raw RPC escape hatch. */
export const nativeHermesPort: NativeHermesPort = {
  available: () => typeof window !== "undefined" && isTauri(),
  async request(request) {
    if (!this.available()) throw new Error("NATIVE_PLATFORM_UNAVAILABLE");
    return parseNativeView(await invoke("hermes_native", { request }));
  },
};
