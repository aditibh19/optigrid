import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  esbuild: { jsx: "automatic" },                       // tsconfig says "preserve" for Next; tests need real JSX output
  resolve: { alias: { "@": fileURLToPath(new URL("./", import.meta.url)) } },
  test: { environment: "node", include: ["tests/**/*.test.{ts,tsx}"] },
});
