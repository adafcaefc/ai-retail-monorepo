import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
    // The Retail boards each render six Recharts charts and a paged table into
    // jsdom, and a filter change re-renders all of it. One interaction can take
    // four seconds by itself, leaving no headroom under vitest's 5s default
    // once the files run in parallel — the symptom is a timeout in whichever
    // heavy test happened to be scheduled next to another, not a real failure.
    // Raised so a red suite means something is actually broken.
    testTimeout: 20000,
  },
});


