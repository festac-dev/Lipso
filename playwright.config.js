import { defineConfig } from '@playwright/test';
import { existsSync } from 'node:fs';

const cached = '/root/.cache/ms-playwright/chromium-1254/chrome-linux-arm64/chrome';
export default defineConfig({
  testDir: './tests/browser',
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: 'http://127.0.0.1:3091',
    headless: true,
    viewport: { width: 1440, height: 1000 },
    launchOptions: { executablePath: process.env.CHROMIUM_PATH || (existsSync(cached) ? cached : undefined), args: ['--no-sandbox'] },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python3 tests/browser_server.py',
    url: 'http://127.0.0.1:3091',
    reuseExistingServer: false,
    timeout: 15000,
  },
});
