import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { deepSeekAppConfig } from "../../integrations/deepseek_harness/company_plugin/src/protocol.ts";
export default defineConfig(({ mode }) => {
  const value = loadEnv(mode, process.cwd(), "VITE_MM_DSH_APP_URL").VITE_MM_DSH_APP_URL;
  const chat = value ? deepSeekAppConfig(value, "https://mcp.mastermind-x.com") : null;
  if (value && !chat) throw new Error("VITE_MM_DSH_APP_URL must be a separate company HTTPS application origin.");
  // The web release's existing sealed index is the one configuration source
  // for both the frame URL and its exact server Content-Security-Policy.
  if (chat && mode === "native") throw new Error("The full DeepSeek application requires the qualified web host.");
  return {
    base: mode === "native" ? "./" : "/os/",
    plugins: [react(), {
      name: "mastermind-deepseek-application",
      transformIndexHtml() {
        return chat ? [{tag: "meta", attrs: {name: "mastermind-dsh-app", content: chat.url}, injectTo: "head" as const}] : [];
      },
    }],
    test: {
      css: { include: [/\/src\/styles\.css\?raw$/] },
    },
  };
});
