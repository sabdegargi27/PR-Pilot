import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker Compose, API_PROXY_TARGET is set to http://api:8000 so the Vite
// dev server can reach the backend container by service name.
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": apiTarget,
      "/webhook": apiTarget,
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: "./src/test/setup.ts",
  },
});
