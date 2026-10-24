/** Isolated SOURCE FIXTURE artifact. Never used by the normal production build. */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: "dist-conversation-proof/os",
    emptyOutDir: true,
    rollupOptions: { input: ["conversation-reading-proof.html", "conversation-app-proof.html"] },
  },
});
