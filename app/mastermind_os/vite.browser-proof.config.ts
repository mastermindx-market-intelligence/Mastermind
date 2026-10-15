/**
 * SOURCE FIXTURE build config — test-only compiled-browser harness entry.
 *
 * Never used by the default build: `npm run build` runs `tsc -b && vite build`
 * with vite.config.ts, whose input remains index.html and whose outDir remains
 * dist/. This config builds only browser-proof.html into the separate
 * dist-browser-proof/ artifact directory, so the harness can never enter the
 * production bundle.
 *
 * Build command (run at the app root):
 *   npx vite build --config vite.browser-proof.config.ts
 */
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    outDir: "dist-browser-proof",
    emptyOutDir: true,
    rollupOptions: {
      input: "browser-proof.html",
    },
  },
});
