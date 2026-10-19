const {test, expect} = require('@playwright/test');
const {spawn, spawnSync} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const LABEL = 'SIMULATED portfolio risk analytics — read-only, not a credit decision, not an accounting policy';

function startServer(port, extra) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-risk-'));
  const log = fs.openSync(path.join(directory, 'server.log'), 'a');
  const child = spawn('python3', ['-m', 'capital.server', '--port', String(port), ...extra(directory)], {
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

const won = value => new Intl.NumberFormat('ko-KR').format(value);

function watch(page) {
  const seen = {errors: [], posts: 0};
  page.on('pageerror', error => seen.errors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') seen.errors.push(message.text()); });
  page.on('request', request => { if (request.method() === 'POST') seen.posts += 1; });
  return seen;
}

async function overflow(page) {
  return page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth, inner: window.innerWidth,
    panel: document.querySelector('#risk').getBoundingClientRect().right,
  }));
}

test('seeded demo shows the risk panel on desktop and 375px with no overflow and no console errors', async ({page}) => {
  const port = 8901;
  const started = startServer(port, directory => {
    const workspace = path.join(directory, 'workspace');
    const seeded = spawnSync('python3', ['scripts/seed_demo.py', '--workspace', workspace], {cwd: root, encoding: 'utf8'});
    expect(seeded.status, seeded.stderr).toBe(0);
    return ['--workspace', workspace];
  });
  try {
    await waitReady(port);
    const risk = (await getJson(port, '/api/risk')).body;
    expect(risk.mode).toBe('SIMULATED_RISK_ANALYTICS');
    expect(risk.status).toBe('BOUND');
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`http://127.0.0.1:${port}/`);
    await expect(page.locator('#risk-label')).toContainText(LABEL);
    await expect(page.locator('#risk-label')).toContainText('SYNTHETIC_UNADOPTED');
    await expect(page.locator('#risk-summary')).toContainText(`${won(risk.totals.outstanding_krw)} KRW`);
    await expect(page.locator('#risk-summary')).toContainText(risk.risk_digest);
    await expect(page.locator('#risk-reserve')).toContainText(`요구액 ${won(risk.reserve.requirement_krw)} KRW`);
    await expect(page.locator('#risk-reserve')).toContainText('not an accounting policy');
    await expect(page.locator('#risk-concentration')).toContainText(`HHI ${risk.concentration.hhi_permille}‰`);
    await expect(page.locator('#risk-tier-rows')).toContainText('T1');
    await expect(page.locator('#risk-tier-rows')).toContainText(won(risk.by_tier[0].outstanding_krw));
    await expect(page.locator('#risk-maturity-rows tr')).toHaveCount(4);
    await expect(page.locator('#risk-aging-rows tr')).toHaveCount(6);
    await expect(page.locator('#risk-cap-rows tr')).toHaveCount(3);
    await expect(page.locator('#risk-reserve-rows tr')).toHaveCount(risk.reserve.rows.length);
    await expect(page.locator('#risk-stress-rows tr')).toHaveCount(4);
    await expect(page.locator('#risk-stress')).toContainText('500/1000/2500/5000 bps');
    await expect(page.locator('#risk-reconciliation')).toContainText('일치');
    await expect(page.locator('#risk')).toBeVisible();
    let metrics = await overflow(page);
    expect(metrics.scroll).toBeLessThanOrEqual(metrics.inner);
    await page.setViewportSize({width: 375, height: 800});
    await page.locator('#risk').scrollIntoViewIfNeeded();
    await expect(page.locator('#risk-stress-rows')).toBeVisible();
    metrics = await overflow(page);
    expect(metrics.scroll).toBeLessThanOrEqual(metrics.inner);
    expect(metrics.panel).toBeLessThanOrEqual(metrics.inner);
    expect(seen.posts).toBe(0);
    expect(seen.errors).toEqual([]);
    const after = await getJson(port, '/api/state');
    expect(after.body.state_digest).toBe(risk.observed_state_digest);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('observer sees the permission reason and no numbers', async ({page}) => {
  const port = 8902;
  const started = startServer(port, () => []);
  try {
    await waitReady(port);
    const seen = watch(page);
    await page.goto(`http://127.0.0.1:${port}/`);
    await expect(page.locator('#risk-label')).toContainText(LABEL);
    const switched = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
    await page.locator('#role').selectOption('observer');
    expect((await switched).ok()).toBeTruthy();
    await expect(page.locator('#risk-error')).toContainText('observer');
    await expect(page.locator('#risk-error')).toContainText('projection:read');
    await expect(page.locator('#risk-tier-rows')).toHaveText('');
    await expect(page.locator('#risk-summary')).toHaveText('');
    expect(seen.errors.filter(text => !text.includes('403'))).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('unbound note renders NOT_BOUND and no numbers', async ({page}) => {
  const port = 8903;
  const note = path.join(os.tmpdir(), `kix-capital-risk-missing-${process.pid}.md`);
  const started = startServer(port, () => ['--terms-note', note]);
  try {
    await waitReady(port);
    const body = (await getJson(port, '/api/risk')).body;
    expect(body.status).toBe('NOT_BOUND');
    expect('totals' in body).toBe(false);
    const seen = watch(page);
    await page.goto(`http://127.0.0.1:${port}/`);
    await expect(page.locator('#risk-label')).toContainText('NOT_BOUND');
    await expect(page.locator('#risk-label')).toContainText('terms not bound');
    await expect(page.locator('#risk-tier-rows')).toHaveText('');
    await expect(page.locator('#risk-summary')).toHaveText('');
    expect(seen.errors).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});
