import playwright from '../../apps/web/node_modules/playwright-core/index.js';
import fs from 'node:fs';

const { chromium } = playwright;
const base = process.env.UI_BASE_URL || 'http://127.0.0.1:4173';
const outputFile = process.env.UI_REPORT_FILE || 'ui_browser_regression_20261109.json';
const edge = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const routes = [
  '/login', '/dashboard', '/admissions/overview', '/admissions/plans', '/source/overview',
  '/data/import', '/data/dbf', '/data/quality', '/data/major-aliases',
  '/ai/assistant', '/ai/insights', '/analytics/anomalies', '/analytics/simulation',
  '/reports', '/forecast/overview', '/system/users', '/system/roles',
  '/system/students', '/system/audit',
];

const report = { timestamp: new Date().toISOString(), routes: [], errors: [], desktop: {}, mobile: {} };
const browser = await chromium.launch({
  executablePath: edge,
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
});

async function login(context) {
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  await page.goto(`${base}/login`, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(/\/dashboard$/, { timeout: 15000 });
  await page.close();
  if (errors.length) report.errors.push(...errors);
}

async function scan(viewportName, viewport) {
  const context = await browser.newContext({ viewport });
  await login(context);
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(String(error)));
  page.on('console', msg => { if (msg.type() === 'error') pageErrors.push(`console:${msg.text()}`); });

  for (const route of routes) {
    const entry = { viewport: viewportName, route, status: 'passed', url: '', textLength: 0, overflow: false, errors: [] };
    try {
      await page.goto(`${base}${route}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
      await page.waitForTimeout(900);
      entry.url = page.url();
      entry.textLength = (await page.locator('body').innerText()).trim().length;
      if (!entry.textLength) entry.errors.push('empty body');
      if (entry.url.includes('/login') && route !== '/login') entry.errors.push('redirected to login');
      entry.overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    } catch (error) {
      entry.errors.push(String(error));
    }
    if (entry.errors.length) entry.status = 'failed';
    report.routes.push(entry);
  }

  report[viewportName] = {
    total: routes.length,
    passed: report.routes.filter(item => item.viewport === viewportName && item.status === 'passed').length,
    failed: report.routes.filter(item => item.viewport === viewportName && item.status === 'failed').length,
    pageErrors: [...new Set(pageErrors)],
  };
  await context.close();
}

try {
  await scan('desktop', { width: 1440, height: 900 });
  await scan('mobile', { width: 390, height: 844 });
} finally {
  await browser.close();
}

report.passed = report.routes.filter(item => item.status === 'passed').length;
report.failed = report.routes.filter(item => item.status === 'failed').length;
fs.writeFileSync(outputFile, JSON.stringify(report, null, 2));
console.log(JSON.stringify({ passed: report.passed, failed: report.failed, desktop: report.desktop, mobile: report.mobile }, null, 2));
if (report.failed) process.exitCode = 1;
