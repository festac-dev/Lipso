import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';

// The existing browser fixture creates and removes a separate fictional database.
const server = spawn('python3', ['tests/browser_server.py'], { stdio: ['ignore', 'pipe', 'inherit'] });
let browser;
try {
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Screenshot workspace did not start')), 15000);
    server.once('exit', code => { clearTimeout(timeout); reject(new Error(`Workspace exited: ${code}`)); });
    server.stdout.on('data', data => {
      if (data.toString().includes('Browser test workspace ready')) { clearTimeout(timeout); resolve(); }
    });
  });
  const cached = '/root/.cache/ms-playwright/chromium-1254/chrome-linux-arm64/chrome';
  browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || (existsSync(cached) ? cached : undefined), args: ['--no-sandbox'] });
  mkdirSync('docs/screenshots', { recursive: true });
  const cases = [
    { name: 'desktop-overview-light', width: 1440, height: 1000, theme: 'light', view: 'overview' },
    { name: 'desktop-planning-dark', width: 1440, height: 1100, theme: 'dark', view: 'plans' },
    { name: 'mobile-overview-light', width: 390, height: 844, theme: 'light', view: 'overview' },
    { name: 'mobile-overview-dark', width: 390, height: 844, theme: 'dark', view: 'overview' },
  ];
  for (const shot of cases) {
    const context = await browser.newContext({ viewport: { width: shot.width, height: shot.height }, deviceScaleFactor: 1, colorScheme: shot.theme });
    const page = await context.newPage();
    await page.goto(`http://127.0.0.1:3091/#${shot.view}`);
    await page.getByRole('heading', { name: shot.view === 'plans' ? 'A range of tomorrows' : 'A clearer picture.' }).waitFor();
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: `docs/screenshots/${shot.name}.png`, animations: 'disabled' });
    await context.close();
    console.log(`Captured ${shot.name}`);
  }
} finally {
  if (browser) await browser.close();
  server.kill('SIGTERM');
}
