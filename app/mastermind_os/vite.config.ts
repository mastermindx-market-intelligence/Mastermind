import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig(({ mode }) => ({
  base: mode === "native" ? "./" : "/os/",
  plugins: [react()],
  test: {
    css: { include: [/\/src\/styles\.css\?raw$/] },
  },
}));
