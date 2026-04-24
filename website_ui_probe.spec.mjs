import { test, expect } from '@playwright/test';
import fs from 'node:fs/promises';

const SITES = [
  {
    id: 'finance_emp',
    url: 'https://amazingbank-empathetic.web.app/',
    serviceQuestion: 'Tell me about card service',
  },
  {
    id: 'finance_non',
    url: 'https://amazingbank-non-empathetic.web.app/',
    serviceQuestion: 'Tell me about card service',
  },
  {
    id: 'spa_emp',
    url: 'https://wellbeing-spa-empathetic.web.app/',
    serviceQuestion: 'Tell me about massage services',
  },
  {
    id: 'spa_non',
    url: 'https://wellbeing-spa-non-empathetic.web.app/',
    serviceQuestion: 'Tell me about massage services',
  },
];

const BLOCKED_TEXT = /could not process|undefined|null/i;

test.use({
  headless: true,
  viewport: { width: 1366, height: 900 },
});

async function ensureScreenshotDir() {
  await fs.mkdir('qa_results/ui', { recursive: true });
}

async function sendMessage(page, message) {
  const before = await page.locator('.left-msg').count();
  await page.locator('.msger-input').fill(message);
  await page.locator('.msger-send-btn').click();
  await expect(page.locator('.loading-dots')).toHaveCount(0, { timeout: 35000 });
  await expect(page.locator('.left-msg')).toHaveCount(before + 1, { timeout: 35000 });
  const texts = await page.locator('.left-msg .msg-text').allTextContents();
  return texts.at(-1).trim();
}

for (const site of SITES) {
  test(`${site.id} website chat probe`, async ({ page }, testInfo) => {
    await ensureScreenshotDir();
    try {
      await page.addInitScript(() => localStorage.clear());
      await page.goto(site.url, { waitUntil: 'domcontentloaded', timeout: 45000 });

      await expect(page.locator('.msger')).toHaveClass(/active/, { timeout: 10000 });
      await expect(page.locator('#welcome-text')).toBeVisible({ timeout: 10000 });

      const immediateWelcome = (await page.locator('#welcome-text').innerText()).trim();
      expect(immediateWelcome).not.toMatch(BLOCKED_TEXT);

      await page.waitForTimeout(2500);
      const hydratedWelcome = (await page.locator('#welcome-text').innerText()).trim();
      expect(hydratedWelcome).not.toMatch(BLOCKED_TEXT);
      expect(hydratedWelcome.length).toBeGreaterThan(20);

      const greetingResponse = await sendMessage(page, 'Hello');
      expect(greetingResponse).not.toMatch(BLOCKED_TEXT);
      expect(greetingResponse.toLowerCase()).not.toContain('next step:');

      const serviceResponse = await sendMessage(page, site.serviceQuestion);
      expect(serviceResponse).not.toMatch(BLOCKED_TEXT);
      expect(serviceResponse.length).toBeGreaterThan(30);

      const closerResponse = await sendMessage(page, 'Ok thanks');
      expect(closerResponse).not.toMatch(BLOCKED_TEXT);
      expect(closerResponse.toLowerCase()).not.toContain('next step:');
    } catch (error) {
      const safeTitle = testInfo.title.replace(/[^a-z0-9_-]+/gi, '_').toLowerCase();
      await page.screenshot({ path: `qa_results/ui/${safeTitle}.png`, fullPage: true });
      throw error;
    }
  });
}
