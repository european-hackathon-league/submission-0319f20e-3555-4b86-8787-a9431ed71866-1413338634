import { build } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";
import { mkdir, readdir, readFile, rm } from "node:fs/promises";

// Independent builds avoid shared JS chunks that a single MCP HTML resource cannot load.
await rm("dist", { recursive: true, force: true });
await mkdir("dist", { recursive: true });
for (const entry of ["scoring-panel.html", "trace-explorer.html"]) {
  await build({
    configFile: false,
    plugins: [viteSingleFile()],
    build: {
      target: "es2022",
      outDir: "dist",
      emptyOutDir: false,
      rollupOptions: { input: entry },
    },
  });
  const html = await readFile(`dist/${entry}`, "utf8");
  if (/<script\b[^>]*\bsrc\s*=|<link\b[^>]*\brel\s*=\s*["'](?:stylesheet|modulepreload)/i.test(html)) {
    throw new Error(`${entry} is not a self-contained MCP resource`);
  }
}
const outputs = await readdir("dist");
if (outputs.length !== 2) throw new Error(`Unexpected build outputs: ${outputs.join(", ")}`);
