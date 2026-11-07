import { test, expect } from '@playwright/test';

test('overview renders real counts, citations, and no runtime errors', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'A clearer picture.' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Two versions of monthly rent.' })).toBeVisible();
  await page.getByRole('button', { name: /USD 2,050.00/ }).click();
  await expect(page.locator('#document-dialog')).toBeVisible();
  await expect(page.locator('.source-line.target')).toContainText('USD 2,050.00');
  await page.keyboard.press('Escape');
  await page.screenshot({ path: 'test-results/overview-desktop.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('questions return conflicting evidence without selecting a winner', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('textbox', { name: 'Ask your workspace' }).fill('What is the rent?');
  await page.getByRole('button', { name: 'Find evidence' }).click();
  await expect(page.getByRole('heading', { name: 'The current sources say' })).toBeVisible();
  const results = page.getByRole('region', { name: 'Evidence results' });
  await expect(results).toContainText('USD 2,050.00');
  await expect(results).toContainText('USD 1,950.00');
  await expect(results).not.toContainText('USD 1,850.00');
});

test('import, review, persistence, and safe document rendering', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'Import document', exact: true }).click();
  await page.getByLabel('Document file').setInputFiles({ name: 'inspection.txt', mimeType: 'text/plain', buffer: Buffer.from('Invoice total: USD 73.00.\nPayment due 2027-03-15.\n<script>window.injected = true</script>') });
  await page.getByLabel('Collection', { exact: true }).fill('Browser test');
  await page.locator('#import-form').getByRole('button', { name: 'Import document' }).click();
  await expect(page.locator('#document-dialog')).toBeVisible();
  await expect(page.locator('.source-sheet')).toContainText('<script>window.injected = true</script>');
  expect(await page.evaluate(() => window.injected)).toBeUndefined();
  await page.getByRole('button', { name: 'Findings (2)' }).click();
  await page.getByRole('button', { name: 'Confirm extraction' }).first().click();
  await expect(page.locator('#document-content .label-pill').filter({ hasText: /^confirmed$/ })).toHaveCount(1);
  await page.keyboard.press('Escape');
  await page.reload();
  await page.getByRole('button', { name: 'Documents', exact: false }).first().click();
  await expect(page.locator('main')).toContainText('inspection');
});

test('commitment completion persists after reload', async ({ page }) => {
  await page.goto('/#commitments');
  const complete = page.locator('.check-button').first();
  await complete.click();
  await page.getByLabel('Filter commitments').selectOption('completed');
  await expect(page.locator('.timeline-item.completed')).toHaveCount(1);
  await page.reload();
  await page.getByLabel('Filter commitments').selectOption('completed');
  await expect(page.locator('.timeline-item.completed')).toHaveCount(1);
});

test('planning lab recalculates a scenario and saves an isolated branch', async ({ page }) => {
  await page.goto('/#plans');
  await expect(page.getByRole('heading', { name: 'A range of tomorrows' })).toBeVisible();
  await expect(page.locator('.warning-list')).toContainText('current sources disagree');
  const originalName = await page.locator('#plan-picker option:checked').textContent();
  await page.locator('#scenario-income_delay').fill('20');
  await page.getByRole('button', { name: 'Test this scenario' }).click();
  await expect(page.locator('.scenario-badge')).toContainText('WHAT IF');
  await page.screenshot({ path: 'test-results/planning-desktop.png', fullPage: true });
  await page.getByRole('button', { name: 'Save as a branch' }).click();
  await page.getByLabel('Branch name').fill('Late payment stress test');
  await page.getByRole('button', { name: 'Save branch', exact: true }).click();
  await expect(page.locator('#plan-picker option:checked')).toContainText('Late payment stress test');
  const names = await page.locator('#plan-picker option').allTextContents();
  expect(names.some(name => name === originalName)).toBeTruthy();
  await expect(page.getByRole('heading', { name: 'A range of tomorrows' })).toBeVisible();
});

test('new plan, task, cash flow, and source link are usable', async ({ page }) => {
  await page.goto('/#plans');
  await page.getByRole('button', { name: 'New plan' }).click();
  await page.getByLabel('Plan name', { exact: true }).fill('Browser-created plan');
  await page.getByLabel('Opening cash').fill('1000');
  await page.getByRole('button', { name: 'Save plan', exact: true }).click();
  await expect(page.locator('#plan-picker option:checked')).toHaveText('Browser-created plan');
  await expect(page.getByRole('heading', { name: 'A range of tomorrows' })).toBeVisible();
  await page.getByRole('button', { name: 'Add task', exact: true }).first().click();
  await page.getByLabel('Task title').fill('Prepare a proposal');
  await page.getByRole('button', { name: 'Save task' }).click();
  await expect(page.locator('main')).toContainText('Prepare a proposal');
  await page.getByRole('button', { name: 'Add cash flow', exact: true }).first().click();
  await page.getByLabel('Description', { exact: true }).fill('Proposal payment');
  await page.getByLabel('Direction', { exact: true }).selectOption('in');
  await page.getByLabel('Amount (USD)', { exact: true }).fill('500');
  await page.getByLabel('Cannot arrive before this work finishes').selectOption({ label: 'Prepare a proposal' });
  await page.getByRole('button', { name: 'Save cash flow' }).click();
  await expect(page.locator('main')).toContainText('Proposal payment');
  await expect(page.locator('main')).toContainText('linked to work');
});

test('mobile navigation, dialogs, and planning have no horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'A clearer picture.' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: 'test-results/overview-mobile.png', fullPage: true });
  await page.getByRole('button', { name: 'Toggle navigation' }).click();
  await page.getByRole('button', { name: 'Planning lab', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'A range of tomorrows' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.getByRole('button', { name: 'New plan' }).click();
  await expect(page.getByLabel('Plan name', { exact: true })).toBeVisible();
  await page.keyboard.press('Escape');
  await page.screenshot({ path: 'test-results/planning-mobile.png', fullPage: true });
});

test('integrity verification and downloads work', async ({ page }) => {
  await page.goto('/#activity');
  await page.getByRole('button', { name: 'Check integrity' }).click();
  await expect(page.getByRole('heading', { name: 'The records line up.' })).toBeVisible();
  await page.keyboard.press('Escape');
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export workspace' }).click();
  expect((await download).suggestedFilename()).toBe('lipso-workspace.zip');
});
