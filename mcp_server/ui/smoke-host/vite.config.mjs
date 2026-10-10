import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

// Local synthetic-data smoke testing only. The browser uses one origin; the
// backend does not need CORS changes, a public tunnel, or provider credentials.
export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  resolve: { preserveSymlinks: true },
  server: {
    host: "127.0.0.1",
    port: 18180,
    strictPort: true,
    cors: false,
    proxy: {
      "/mcp": { target: "http://127.0.0.1:18001", changeOrigin: true },
    },
  },
  build: { outDir: "build", emptyOutDir: true },
});
