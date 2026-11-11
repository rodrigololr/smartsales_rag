import { defineConfig, devices } from "@playwright/test";

/**
 * Suíte E2E do pacote F05 (EAP 5.2). Roda contra a pilha real, já no ar:
 *   docker compose up --build        (vitrine em :3000, gateway em :8000)
 *   pnpm -C frontend exec playwright install chromium
 *   pnpm -C frontend run test:e2e
 * E2E_BASE_URL aponta para outra vitrine; E2E_API_URL, para outro gateway.
 */
export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium-desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
  ],
});
