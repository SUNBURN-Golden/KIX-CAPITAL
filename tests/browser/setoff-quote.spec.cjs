const {test, expect} = require('@playwright/test');
const {spawn} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer';
const fmt = value => new Intl.NumberFormat('ko-KR').format(value);

function hasNumber(value) {
  if (typeof value === 'boolean') return false;
  if (typeof value === 'number') return true;
  if (Array.isArray(value)) return value.some(hasNumber);
  if (value && typeof value === 'object') return Object.values(value).some(hasNumber);
  return false;
}

function startServer(port, extra) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-setoff-'));
  const log = fs.openSync(path.join(directory, 'server.log'), 'a');
  const child = spawn('python3', ['-m', 'capital.server', '--port', String(port), ...extra], {
    cwd: root, stdio: ['ignore', log, log],
  });
  fs.closeSync(log);
  return {child, directory};
}

function stopServer(child) {
  return new Promise(resolve => {
    if (!child || child.exitCode !== null || child.signalCode !== null) return resolve();
    const timer = setTimeout(resolve, 3000);
    child.once('exit', () => { clearTimeout(timer); resolve(); });
    child.kill('SIGKILL');
  });
}

function getJson(port, pathname) {
  return new Promise((resolve, reject) => {
    const req = http.get({hostname: '127.0.0.1', port, path: pathname, timeout: 2000}, response => {
      let data = '';
      response.on('data', chunk => { data += chunk; });
      response.on('end', () => {
        try { resolve({status: response.statusCode, body: JSON.parse(data)}); }
        catch (error) { reject(error); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(Error('timeout')); });
  });
}

async function waitReady(port) {
  const deadline = Date.now() + 8000;
  let last;
  while (Date.now() < deadline) {
    try {
      last = await getJson(port, '/api/state');
      if (last.status === 200 && last.body.instance_id) return last.body;
    } catch (error) { last = String(error); }
    await new Promise(resolve => setTimeout(resolve, 40));
  }
  throw Error('SERVER_NOT_READY ' + JSON.stringify(last));
}

async function switchRole(page, role) {
  const seen = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
  await page.locator('#role').selectOption(role);
  expect((await seen).ok()).toBeTruthy();
  await expect(page.locator('#role-status')).toContainText(role);
}

test('bound setoff quote shows verbatim API values for organizer and auditor and never POSTs', async ({page}) => {
  const port = 8893;
  const started = startServer(port, []);
  try {
    await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/`);
    await page.locator('#fixture').selectOption('sim-committed');
    await page.locator('#amount').fill('60000');
    const offered = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op === 'offer');
    await page.getByRole('button', {name: '모의 제안 생성'}).click();
    const offer = await (await offered).json();
    expect(offer.outcome).toBe('ACCEPTED');
    const advanceId = offer.result.credit.advance_id;
    for (const [name, phase] of [['모의 승인', 'APPROVED'], ['정산 근거 연결', 'APPROVED'], ['모의 노출 기록', 'DRAWN']]) {
      const pending = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op);
      await page.getByRole('button', {name, exact: true}).click();
      expect((await (await pending).json()).outcome).toBe('ACCEPTED');
      await expect(page.locator('#phase')).toContainText(phase);
    }
    const live = await getJson(port, '/api/state');
    const quote = await getJson(port, `/api/terms/${encodeURIComponent(advanceId)}/setoff?instance_id=${encodeURIComponent(live.body.instance_id)}&draw_day=0&as_of_day=0`);
    expect(quote.status).toBe(200);
    expect(quote.body.label).toBe(LABEL);
    expect(quote.body.mode).toBe('SIMULATED_OVERLAY');
    expect(quote.body.proposal_only).toBe(true);
    expect(quote.body.applied).toBe(false);
    expect(quote.body.execution_authority).toMatch(/^HUMAN_OPERATOR/);
    expect(quote.body.setoff.status).toBe('BOUND');
    expect(quote.body.setoff.setoff_amount).toBe(0);
    expect(quote.body.setoff.base_reason).toBe('ALLOCATION_NOT_OBSERVED');
    expect(quote.body.fsm_repay).toBeNull();
    // The panel renders the route response verbatim; nothing is computed on the page.
    await expect(page.locator('#case-setoff-label')).toHaveText(LABEL);
    await expect(page.locator('#case-setoff-body')).toBeVisible();
    const summary = page.locator('#case-setoff-summary');
    await expect(summary).toContainText(`proposal_only ${quote.body.proposal_only}`);
    await expect(summary).toContainText(quote.body.execution_authority);
    await expect(summary).toContainText(`setoff_amount ${fmt(quote.body.setoff.setoff_amount)}`);
    await expect(summary).toContainText(`(${quote.body.setoff.capped_by})`);
    await expect(summary).toContainText(quote.body.setoff.base_reason);
    await expect(summary).toContainText(quote.body.setoff.route);
    const facts = page.locator('#case-setoff-facts');
    await expect(facts).toContainText(String(quote.body.setoff.outstanding_exposure));
    await expect(facts).toContainText(quote.body.setoff.base_reason);
    await expect(facts).toContainText(quote.body.setoff.route);
    await expect(facts).toContainText(quote.body.allocation.order.join(' → '));
    await expect(facts).toContainText('fsm_repay');
    await expect(facts).toContainText(quote.body.post_default);
    await expect(facts).toContainText(quote.body.collateral_execution.primary);
    await expect(facts).toContainText(quote.body.settlement_view.counterparty_class_id);
    const lines = page.locator('#case-setoff-lines tr');
    await expect(lines).toHaveCount(quote.body.settlement_view.lines.length);
    for (const line of quote.body.settlement_view.lines) {
      const row = page.locator('#case-setoff-lines tr', {hasText: line.payee});
      await expect(row).toContainText(`${line.class} ${line.class_id}`);
      await expect(row).toContainText(line.beneficiary_mapped ? '매핑' : '비매핑');
      await expect(row).toContainText(fmt(line.distributed));
      await expect(row).toContainText(fmt(line.eligible_krw));
      if (line.counted) await expect(row).toHaveClass(/counted/);
      else await expect(row).not.toHaveClass(/counted/);
    }
    let commandPosts = 0;
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().endsWith('/api/commands')) commandPosts += 1;
    });
    const refetched = page.waitForResponse(response => response.url().includes('/setoff?') && response.request().method() === 'GET');
    await page.locator('#terms-as-of-day').fill('1');
    await page.locator('#terms-as-of-day').blur();
    await refetched;
    expect(commandPosts).toBe(0);
    const after = await getJson(port, '/api/state');
    expect(after.body.operation_count).toBe(live.body.operation_count);
    expect(after.body.state_digest).toBe(live.body.state_digest);
    await switchRole(page, 'auditor');
    await expect(page.locator('#case-setoff-label')).toHaveText(LABEL);
    await expect(page.locator('#case-setoff-body')).toBeVisible();
    await expect(page.locator('#case-setoff-summary')).toContainText(quote.body.setoff.base_reason);
    await page.setViewportSize({width: 375, height: 667});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await switchRole(page, 'observer');
    await expect(page.locator('#case-setoff-error')).toContainText('observer');
    await expect(page.locator('#case-setoff-error')).toContainText('projection:read');
    await expect(page.locator('#case-setoff-body')).toBeHidden();
    expect(commandPosts).toBe(0); // role switches are /api/session only; the quote never commands
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('unbound terms note leaves the setoff panel without numbers', async ({page}) => {
  const port = 8894;
  const note = path.join(os.tmpdir(), `kix-capital-missing-setoff-${process.pid}.md`);
  const started = startServer(port, ['--terms-note', note]);
  try {
    await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/`);
    await page.locator('#fixture').selectOption('sim-committed');
    await page.locator('#amount').fill('1000');
    const offered = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op === 'offer');
    await page.getByRole('button', {name: '모의 제안 생성'}).click();
    const offer = await (await offered).json();
    expect(offer.outcome).toBe('ACCEPTED');
    const advanceId = offer.result.credit.advance_id;
    const live = await getJson(port, '/api/state');
    const quote = await getJson(port, `/api/terms/${encodeURIComponent(advanceId)}/setoff?instance_id=${encodeURIComponent(live.body.instance_id)}&draw_day=0&as_of_day=0`);
    expect(quote.status).toBe(200);
    expect(quote.body.status).toBe('NOT_BOUND');
    expect(quote.body.reason).toBe('terms not bound');
    expect(quote.body.proposal_only).toBe(true);
    expect(hasNumber(quote.body)).toBe(false);
    await expect(page.locator('#case-setoff-label')).toHaveText(LABEL);
    await expect(page.locator('#case-setoff-summary')).toContainText('terms not bound');
    const facts = await page.locator('#case-setoff-facts').innerText();
    expect(/\d/.test(facts)).toBe(false);
    await expect(page.locator('#case-setoff-lines tr')).toHaveCount(0);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});
