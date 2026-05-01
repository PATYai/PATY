import { defineConfig } from "vite";

// Tauri-friendly Vite config: fixed dev port, no auto-clear, env passthrough.
export default defineConfig({
  clearScreen: false,
  server: {
    port: 1420,
    strictPort: true,
  },
  envPrefix: ["VITE_", "TAURI_"],
});
