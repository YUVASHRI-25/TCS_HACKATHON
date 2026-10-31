import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": new URL("./src", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1") } },
  server: {
    port: 5173,
    proxy: { "/api": process.env.API_URL ?? "http://127.0.0.1:8000" },
  },
});
