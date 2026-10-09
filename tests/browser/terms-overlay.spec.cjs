const {test, expect} = require('@playwright/test');
const {spawn} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer';

function hasNumber(value) {
  if (typeof value === 'boolean') return false;
  if (typeof value === 'number') return true;
  if (Array.isArray(value)) return value.some(hasNumber);
  if (value && typeof value === 'object') return Object.values(value).some(hasNumber);
  return false;
}

function startServer(port, extra) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-terms-'));
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

test('bound overlay shows the label and API values and does not POST', async ({page}) => {
  const port = 8891;
  const started = startServer(port, []);
  try {
    const state = await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/`);
    await expect(page.locator('#terms-label')).toHaveText(LABEL);
    await expect(page.locator('#terms-status')).toContainText('BOUND');
    await expect(page.locator('#terms-version')).toHaveText(state.terms.terms_version);
    const policy = await getJson(port, '/api/terms');
    expect(policy.body.label).toBe(LABEL);
    expect(policy.body.mode).toBe('SIMULATED_OVERLAY');
    expect(policy.body.funds_executed).toBe(false);
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
    const overlay = await getJson(port, `/api/terms/${encodeURIComponent(advanceId)}?instance_id=${encodeURIComponent(live.body.instance_id)}&draw_day=0&as_of_day=0`);
    expect(overlay.status).toBe(200);
    expect(overlay.body.label).toBe(LABEL);
    await expect(page.locator('#case-terms-label')).toHaveText(LABEL);
    await expect(page.locator('#case-terms-facts')).toContainText(overlay.body.accrual.exact);
    await expect(page.locator('#case-terms-facts')).toContainText(String(overlay.body.accrual.interest_krw));
    await expect(page.locator('#case-terms-facts')).toContainText(String(overlay.body.schedule.term_days));
    await expect(page.locator('#case-terms-facts')).toContainText(overlay.body.collateral.rung);
    await expect(page.locator('#case-terms-facts')).toContainText(String(overlay.body.reserve_provision.provision_bps));
    let posts = 0;
    page.on('request', request => { if (request.method() === 'POST') posts += 1; });
    const refreshed = page.waitForResponse(response => response.url().includes('/api/terms/') && response.request().method() === 'GET');
    await page.locator('#terms-as-of-day').fill('1');
    await page.locator('#terms-as-of-day').blur();
    await refreshed;
    expect(posts).toBe(0);
    const next = await getJson(port, `/api/terms/${encodeURIComponent(advanceId)}?instance_id=${encodeURIComponent(live.body.instance_id)}&draw_day=0&as_of_day=1`);
    await expect(page.locator('#case-terms-facts')).toContainText(next.body.accrual.exact);
    const after = await getJson(port, '/api/state');
    expect(after.body.operation_count).toBe(live.body.operation_count);
    expect(after.body.state_digest).toBe(live.body.state_digest);
    await page.setViewportSize({width: 375, height: 667});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const seen = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
    await page.locator('#role').selectOption('observer');
    expect((await seen).ok()).toBeTruthy();
    await expect(page.locator('#terms-error')).toContainText('observer');
    await expect(page.locator('#terms-error')).toContainText('projection:read');
    await expect(page.locator('#case-terms-error')).toContainText('projection:read');
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('unbound note shows terms not bound', async ({page}) => {
  const port = 8892;
  const note = path.join(os.tmpdir(), `kix-capital-missing-terms-${process.pid}.md`);
  const started = startServer(port, ['--terms-note', note]);
  try {
    await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/`);
    await expect(page.locator('#terms-label')).toHaveText(LABEL);
    await expect(page.locator('#terms-status')).toContainText('terms not bound');
    const policy = await getJson(port, '/api/terms');
    expect(policy.body.status).toBe('NOT_BOUND');
    expect(policy.body.reason).toBe('terms not bound');
    expect(hasNumber(policy.body)).toBe(false);
    await page.locator('#amount').fill('1000');
    const offered = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op === 'offer');
    await page.getByRole('button', {name: '모의 제안 생성'}).click();
    const offer = await (await offered).json();
    expect(offer.outcome).toBe('ACCEPTED');
    const live = await getJson(port, '/api/state');
    const overlay = await getJson(port, `/api/terms/${encodeURIComponent(offer.result.credit.advance_id)}?instance_id=${encodeURIComponent(live.body.instance_id)}&draw_day=0&as_of_day=0`);
    expect(overlay.body.reason).toBe('terms not bound');
    expect(hasNumber(overlay.body)).toBe(false);
    await expect(page.locator('#case-terms-facts')).toContainText('terms not bound');
    const facts = await page.locator('#case-terms-facts').innerText();
    expect(/\d/.test(facts)).toBe(false);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});
