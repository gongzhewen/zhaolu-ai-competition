import playwright from '../../apps/web/node_modules/playwright-core/index.js';
import fs from 'node:fs';

const { chromium } = playwright;

const base = process.env.UI_BASE_URL || 'http://127.0.0.1:3000';
const edge = process.env.EDGE_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const report = {
  timestamp: new Date().toISOString(),
  base,
  steps: [],
  pageErrors: [],
  apiErrors: [],
};

const browser = await chromium.launch({
  executablePath: edge,
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
});

const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  acceptDownloads: true,
});
const page = await context.newPage();
page.on('pageerror', error => report.pageErrors.push(String(error)));
page.on('console', message => {
  if (
    message.type() === 'error' &&
    !message.text().includes('favicon') &&
    !message.text().includes('Failed to load resource')
  ) {
    report.pageErrors.push(`console:${message.text()}`);
  }
});
page.on('response', response => {
  if (response.url().includes('/api/') && response.status() >= 500) {
    report.apiErrors.push({ status: response.status(), url: response.url() });
  }
});

async function step(name, action, timeout = 30000) {
  const entry = { name, status: 'passed', elapsed_ms: 0, detail: '' };
  const started = performance.now();
  try {
    entry.detail = String((await action()) || '');
  } catch (error) {
    entry.status = 'failed';
    entry.detail = String(error?.stack || error);
  }
  entry.elapsed_ms = Math.round(performance.now() - started);
  report.steps.push(entry);
  return entry.status === 'passed';
}

async function login() {
  await page.goto(`${base}/login`, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(/\/dashboard$/, { timeout: 15000 });
}

async function openRoute(route, expectedText) {
  await page.goto(`${base}${route}`, { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(700);
  const body = await page.locator('body').innerText();
  if (!body.includes(expectedText)) {
    throw new Error(`页面 ${route} 未找到文本：${expectedText}`);
  }
  if (await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2)) {
    throw new Error(`页面 ${route} 出现横向溢出`);
  }
  return body.length;
}

async function closeModal() {
  const modal = page.locator('.ant-modal-content').last();
  await modal.waitFor({ state: 'visible', timeout: 10000 });
  await modal.locator('.ant-modal-footer button').first().click();
  await modal.waitFor({ state: 'hidden', timeout: 10000 });
}

async function selectInsightScope(label, expectedHeading) {
  const responsePromise = page.waitForResponse(
    response =>
      response.url().includes('/api/v1/ai/insights?scope=') &&
      response.status() === 200,
    { timeout: 60000 },
  );
  await page.locator('.ant-select-selector').first().click();
  await page.getByText(label, { exact: true }).last().click();
  await responsePromise;
  await page.getByText(expectedHeading, { exact: true }).first().waitFor({
    state: 'visible',
    timeout: 30000,
  });
  return expectedHeading;
}

try {
  await step('login_and_dashboard', async () => {
    await login();
    await page.getByText('招生工作台', { exact: true }).waitFor({
      state: 'visible',
      timeout: 15000,
    });
    const body = await page.locator('body').innerText();
    if (!body.includes('招生工作台')) {
      throw new Error('登录后未进入驾驶舱');
    }
    return '登录成功并进入驾驶舱';
  });

  await step('admissions_overview_loaded', () => openRoute('/admissions/overview', '招生驾驶舱'));
  await step('source_overview_loaded', () => openRoute('/source/overview', '生源分析'));

  await step('plan_create_modal_open_cancel', async () => {
    await page.goto(`${base}/admissions/plans`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: /新增招生计划/ }).click();
    const dialog = page.getByRole('dialog');
    await dialog.waitFor({ state: 'visible', timeout: 10000 });
    const text = await dialog.innerText();
    if (!text.includes('招生年度') || !text.includes('计划人数')) {
      throw new Error(`新增招生计划弹窗字段不完整：${text.slice(0, 300)}`);
    }
    await closeModal();
    return '弹窗打开、字段校验、取消关闭';
  });

  await step('major_alias_modal_open_cancel', async () => {
    await page.goto(`${base}/data/major-aliases`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: /新增名称映射/ }).click();
    const dialog = page.getByRole('dialog');
    await dialog.waitFor({ state: 'visible', timeout: 10000 });
    const text = await dialog.innerText();
    if (!text.includes('来源专业名称') || !text.includes('标准专业')) {
      throw new Error('新增名称映射弹窗字段不完整');
    }
    await closeModal();
    return '弹窗打开、字段校验、取消关闭';
  });

  await step('template_download', async () => {
    await page.goto(`${base}/data/import`, { waitUntil: 'domcontentloaded' });
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 20000 }),
      page.getByRole('button', { name: /下载标准模板/ }).click(),
    ]);
    const filename = download.suggestedFilename();
    if (!filename.endsWith('.csv')) {
      throw new Error(`模板下载文件名异常：${filename}`);
    }
    return filename;
  });

  await step('report_preview', async () => {
    const responsePromise = page.waitForResponse(
      response =>
        response.url().includes('/api/v1/reports/preview') &&
        response.status() === 200,
      { timeout: 60000 },
    );
    await page.goto(`${base}/reports`, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: '生成预览', exact: true }).click();
    await responsePromise;
    await page.getByText('核心结论', { exact: true }).waitFor({
      state: 'visible',
      timeout: 30000,
    });
    return '预览生成并展示核心结论';
  });

  await step('insights_candidate_switch', async () => {
    await page.goto(`${base}/ai/insights`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(1000);
    return selectInsightScope('考生画像', '性别结构');
  });

  await step('insights_subject_switch', () =>
    selectInsightScope('学科成绩', '逐科成绩分析'));

  await step('insights_major_switch', () =>
    selectInsightScope('专业志愿', '专业志愿热度与志愿率'));

  await step('ai_assistant_question_answer', async () => {
    await page.goto(`${base}/ai/assistant`, { waitUntil: 'domcontentloaded' });
    await page.getByText(
      '我是招录智策 AI 助手。可以查询招生计划、录取、专业、生源和渠道等统计数据。',
      { exact: true },
    ).waitFor({ state: 'visible', timeout: 15000 });
    const initialCount = await page.locator('.chat-message.assistant .chat-content').count();
    await page.getByPlaceholder(/例如：2025年各专业招生计划完成情况/).fill('2026年招生计划数是多少？');
    await page.getByRole('button', { name: /发\s*送/ }).click();
    await page.waitForFunction(
      count => document.querySelectorAll('.chat-message.assistant .chat-content').length > count,
      initialCount,
      { timeout: 90000 },
    );
    const latest = page.locator('.chat-message.assistant .chat-content').last();
    const answer = (await latest.innerText()).trim();
    if (
      !answer ||
      answer.includes('我是招录智策 AI 助手。可以查询招生计划、录取、专业、生源和渠道等统计数据。')
    ) {
      throw new Error('AI 未返回新的有效回答');
    }
    return answer.slice(0, 160);
  }, 100000);

  await step('anomaly_page_loaded', () => openRoute('/analytics/anomalies', 'AI 异常检测'));
  await step('forecast_page_loaded', () => openRoute('/forecast/overview', '预测'));
  await step('student_page_loaded', () => openRoute('/system/students', '学生'));
  await step('audit_page_loaded', () => openRoute('/system/audit', '审计'));
} finally {
  await context.close();
  await browser.close();
}

report.passed = report.steps.filter(item => item.status === 'passed').length;
report.failed = report.steps.filter(item => item.status === 'failed').length;
report.status = report.failed === 0 && report.pageErrors.length === 0 && report.apiErrors.length === 0
  ? 'passed'
  : 'failed';
fs.writeFileSync('ui_business_regression_20261110.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify({
  status: report.status,
  passed: report.passed,
  failed: report.failed,
  pageErrors: report.pageErrors,
  apiErrors: report.apiErrors,
  failedSteps: report.steps.filter(item => item.status === 'failed'),
}, null, 2));
if (report.status !== 'passed') process.exitCode = 1;
