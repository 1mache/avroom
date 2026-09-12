import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // Tests live next to what they cover, as *.test.ts(x).
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
  },
});
