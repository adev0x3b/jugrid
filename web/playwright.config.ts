import { defineConfig, devices } from "@playwright/test";

// Runs against the composed stack (docker compose up, then the e2e seed); see the README.
export default defineConfig({
  testDir: "e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.JUGRID_URL ?? "http://127.0.0.1:8096",
    trace: "retain-on-failure",
    // A Chromium already on the machine, if Playwright's own is not installed.
    launchOptions: process.env.CHROMIUM_PATH
      ? { executablePath: process.env.CHROMIUM_PATH }
      : undefined,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
});
