// playwright.config.js
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './playwright_tests', // Directory where .spec.js files will be
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html', // Generates an HTML report
  use: {
    baseURL: 'http://localhost:5173', // Vite's default dev server port for frontend
    trace: 'on-first-retry', // Record trace on first retry of a failed test
    headless: true, // Run tests headless by default
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    // { name: 'webkit', use: { ...devices['Desktop Safari'] } },
  ],
  // Optional: Web server configuration to auto-start frontend dev server
  // This assumes your frontend is in 'swisper/frontend' and has 'npm run dev'
  webServer: {
    command: 'cd frontend && npm run dev', // Command to start the frontend dev server
    url: 'http://localhost:5173',     // URL to poll to ensure server is up
    reuseExistingServer: !process.env.CI, // Reuse server if already running locally
    timeout: 120 * 1000,                // Timeout for server to start
    // cwd: './frontend', // Not usually needed if command includes cd
  },
});
