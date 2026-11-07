import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Explicit qualification entrypoint. Normal frontend-only test runs do not
// require Python fixtures or the generated private temporary output path.
export default defineConfig({
  plugins: [react()],
  test: {
    include: ["qualification/paid-browser-produced.qualification.tsx"],
    environment: "jsdom",
    maxWorkers: 1,
  },
});
