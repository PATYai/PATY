import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "tests",
  timeout: 15_000,
  use: {
    headless: true,
  },
  projects: [
    {
      name: "chromium",
      use: { browserName: "chromium" },
    },
  ],
});
