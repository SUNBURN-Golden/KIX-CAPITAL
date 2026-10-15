const {test, expect} = require('@playwright/test');
const {spawn} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer';
const NOTE = path.join(root, 'docs', 'decisions', 'CAPITAL_FINANCIAL_TERMS.md');

function hasNumber(value) {
  if (typeof value === 'boolean') return false;
  if (typeof value === 'number') return true;
  if (Array.isArray(value)) return value.some(hasNumber);
  if (value && typeof value === 'object') return Object.values(value).some(hasNumber);
  return false;
}

function startServer(port, extra) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-portfolio-'));
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

async function drawOffer(page, amount) {
  await page.locator('#fixture').selectOption('sim-committed');
  await page.locator('#amount').fill(amount);
  const offered = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op === 'offer');
  await page.getByRole('button', {name: '모의 제안 생성'}).click();
  const offer = await (await offered).json();
  expect(offer.outcome).toBe('ACCEPTED');
  for (const name of ['모의 승인', '정산 근거 연결', '모의 노출 기록']) {
    const pending = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op);
    await page.getByRole('button', {name, exact: true}).click();
    expect((await (await pending).json()).outcome).toBe('ACCEPTED');
  }
  return offer.result.credit.advance_id;
}

test('portfolio rollup panel renders beside the terms card without POSTs', async ({page}) => {
  const port = 8893;
  const started = startServer(port, []);
  try {
    const state = await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/`);
    const order = await page.evaluate(() => {
      const ids = [...document.querySelectorAll('section.panel')].map(node => node.id);
      return {terms: ids.indexOf('terms'), portfolio: ids.indexOf('terms-portfolio')};
    });
    expect(order.terms).toBeGreaterThanOrEqual(0);
    expect(order.portfolio).toBe(order.terms + 1);
    await expect(page.locator('#terms-portfolio-label')).toContainText(LABEL);
    await expect(page.locator('#terms-portfolio-label')).toContainText('BOUND');
    await expect(page.locator('#terms-portfolio-cap')).toContainText('all_in_cost_cap_bps_annual');
    await expect(page.locator('#terms-portfolio-cap')).toContainText('ZERO_FEE_INTEREST_ONLY');
    await expect(page.locator('#terms-portfolio-totals')).toContainText('평가 0/0');
    await expect(page.locator('#terms-portfolio-totals')).toContainText('NOT_APPLICABLE');
    await drawOffer(page, '60000');
    const live = await getJson(port, '/api/state');
    const rollup = await getJson(port, `/api/terms/portfolio?instance_id=${encodeURIComponent(live.body.instance_id)}&draw_day=0&as_of_day=80`);
    expect(rollup.status).toBe(200);
    expect(rollup.body.mode).toBe('SIMULATED_OVERLAY');
    expect(rollup.body.funds_executed).toBe(false);
    expect(rollup.body.workspace_mutated).toBe(false);
    const row = rollup.body.rows[0];
    expect(row.status).toBe('BOUND');
    expect(row.draw_day_source).toBe('QUERY_PARAMETER');
    expect(row.cap_check).toBe('PASS');
    let posts = 0;
    page.on('request', request => { if (request.method() === 'POST') posts += 1; });
    const refreshed = page.waitForResponse(response => response.url().includes('/api/terms/portfolio') && response.url().includes('as_of_day=80') && response.request().method() === 'GET');
    await page.locator('#terms-as-of-day').fill('80');
    await page.locator('#terms-as-of-day').blur();
    const response = await (await refreshed).json();
    expect(response.rows[0].days_past_maturity).toBe(row.days_past_maturity);
    expect(posts).toBe(0);
    await expect(page.locator('#terms-portfolio-rows')).toContainText(row.contract_exact);
    await expect(page.locator('#terms-portfolio-rows')).toContainText(row.default_exact);
    await expect(page.locator('#terms-portfolio-rows')).toContainText('T1');
    await expect(page.locator('#terms-portfolio-rows')).toContainText(row.annualized_all_in_bps);
    await expect(page.locator('#terms-portfolio-totals')).toContainText('평가 1/1');
    await expect(page.locator('#terms-portfolio-totals')).toContainText(`(${rollup.body.totals.exact})`);
    await expect(page.locator('#terms-portfolio-totals')).toContainText(`cap_check ${rollup.body.totals.cap_check}`);
    const after = await getJson(port, '/api/state');
    expect(after.body.operation_count).toBe(live.body.operation_count);
    expect(after.body.state_digest).toBe(live.body.state_digest);
    const seen = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
    await page.locator('#role').selectOption('observer');
    expect((await seen).ok()).toBeTruthy();
    await expect(page.locator('#terms-portfolio-error')).toContainText('observer');
    await expect(page.locator('#terms-portfolio-error')).toContainText('projection:read');
    await expect(page.locator('#terms-portfolio-rows')).toHaveText('');
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('unbound note renders no numbers in the rollup panel', async ({page}) => {
  const port = 8894;
  const note = path.join(os.tmpdir(), `kix-capital-portfolio-missing-${process.pid}.md`);
  const started = startServer(port, ['--terms-note', note]);
  try {
    await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/`);
    await expect(page.locator('#terms-portfolio-label')).toContainText('terms not bound');
    const rollup = await getJson(port, '/api/terms/portfolio?as_of_day=1&instance_id=any');
    expect(rollup.status).toBe(409);
    const state = await getJson(port, '/api/state');
    const body = await getJson(port, `/api/terms/portfolio?instance_id=${encodeURIComponent(state.body.instance_id)}&as_of_day=1`);
    expect(body.body.status).toBe('NOT_BOUND');
    expect(body.body.reason).toBe('terms not bound');
    expect(hasNumber(body.body)).toBe(false);
    expect('rows' in body.body).toBe(false);
    await expect(page.locator('#terms-portfolio-rows')).toHaveText('');
    await expect(page.locator('#terms-portfolio-totals')).toHaveText('');
    await drawOffer(page, '1000');
    await expect(page.locator('#terms-portfolio-label')).toContainText('terms not bound');
    await expect(page.locator('#terms-portfolio-rows')).toHaveText('');
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('a lowered synthetic note fails the cap while the committed note is untouched', async ({page}) => {
  const port = 8895;
  const committed = fs.readFileSync(NOTE, 'utf8');
  const cap = JSON.parse(/```capital-decision-v1\s*\n([\s\S]*?)```/.exec(committed)[1])
    .entries.interest_rate.value.all_in_cost_cap_bps_annual;
  const low_cap = cap - 1100;
  const lowered = committed.replace(
    `"all_in_cost_cap_bps_annual": ${cap}`, `"all_in_cost_cap_bps_annual": ${low_cap}`);
  const note = path.join(os.tmpdir(), `kix-capital-portfolio-lowcap-${process.pid}.md`);
  fs.writeFileSync(note, lowered, 'utf8');
  const started = startServer(port, ['--terms-note', note]);
  try {
    await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/`);
    await drawOffer(page, '60000');
    const live = await getJson(port, '/api/state');
    const rollup = await getJson(port, `/api/terms/portfolio?instance_id=${encodeURIComponent(live.body.instance_id)}&as_of_day=1`);
    expect(rollup.body.cap.all_in_cost_cap_bps_annual).toBe(low_cap);
    expect(rollup.body.rows[0].tier).toBe('T1');
    expect(rollup.body.rows[0].cap_check).toBe('FAIL');
    expect(rollup.body.totals.cap_check).toBe('FAIL');
    await expect(page.locator('#terms-portfolio-rows')).toContainText('FAIL');
    await expect(page.locator('#terms-portfolio-cap')).toContainText(String(low_cap));
    expect(fs.readFileSync(NOTE, 'utf8')).toBe(committed);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
    fs.rmSync(note, {force: true});
  }
});
