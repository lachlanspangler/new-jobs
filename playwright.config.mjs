// Browser tests for the static site (docs/). The server swaps in a fixture jobs.json: no network, deterministic.
import { defineConfig } from "@playwright/test";

const PORT = 8612;
export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, browserName: "chromium", viewport: { width: 1280, height: 900 } },
  webServer: { command: `python3 tests/e2e/serve.py ${PORT}`, url: `http://127.0.0.1:${PORT}/index.html`, reuseExistingServer: false },
});
