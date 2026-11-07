const {test, expect} = require('@playwright/test');
const {spawn, spawnSync} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const won = value => new Intl.NumberFormat('ko-KR').format(value);

function startServer(port) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-diag-'));
  const workspace = path.join(directory, 'workspace');
  const seeded = spawnSync('python3', ['scripts/seed_demo.py', '--workspace', workspace], {cwd: root, encoding: 'utf8'});
  expect(seeded.status, seeded.stderr).toBe(0);
  const log = fs.openSync(path.join(directory, 'server.log'), 'a');
  const child = spawn('python3', ['-m', 'capital.server', '--port', String(port), '--workspace', workspace], {
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

function getJson(port, pathname, token) {
  return new Promise((resolve, reject) => {
    const headers = token ? {'X-Capital-Token': token} : {};
    const req = http.get({hostname: '127.0.0.1', port, path: pathname, headers, timeout: 2000}, response => {
      let data = '';
      response.on('data', chunk => { data += chunk; });
      response.on('end', () => {
        try { resolve({status: response.statusCode, body: JSON.parse(data), headers: response.headers}); }
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

async function withServer(port, run) {
  const started = startServer(port);
  try {
    await waitReady(port);
    return await run(`http://127.0.0.1:${port}`);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
}

function watch(page) {
  const seen = {errors: [], posts: [], gets: []};
  page.on('pageerror', error => seen.errors.push(String(error)));
  page.on('console', message => { if (message.type() === 'error') seen.errors.push(message.text()); });
  page.on('request', request => {
    if (request.method() === 'POST') seen.posts.push({url: new URL(request.url()).pathname, body: request.postData()});
    else seen.gets.push(new URL(request.url()).pathname);
  });
  return seen;
}

const commandPosts = seen => seen.posts.filter(post => post.url !== '/api/session');
const metricsGets = seen => seen.gets.filter(item => item === '/api/metrics');

test('organizer sees health, capacity and counters that match the APIs, refreshed only on demand', async ({page}) => {
  await withServer(8961, async base => {
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-diag')).toBeVisible();
    const health = (await getJson(8961, '/api/health')).body;
    const metrics = (await getJson(8961, '/api/metrics')).body;
    const state = (await getJson(8961, '/api/state')).body;
    const overlay = (await getJson(8961, '/api/overlay')).body;
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
    await expect(page.locator('#desk-diag-health')).toContainText('health_status');
    await expect(page.locator('#desk-diag-health')).toContainText(health.status);
    await expect(page.locator('#desk-diag-health')).toContainText(health.workspace_status);
    await expect(page.locator('#desk-diag-health')).toContainText('LOCAL_OBSERVABILITY');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText(`${won(state.operation_count)}/${won(state.operation_capacity)}`);
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY');
    expect(overlay.capacity && typeof overlay.capacity === 'object').toBe(true);
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText(`${won(overlay.capacity.entries.current)}/${won(overlay.capacity.entries.max)}`);
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText(won(overlay.capacity.max_step_days));
    const commands = metrics.counters.commands;
    for (const op of Object.keys(commands)) {
      const row = page.locator('#desk-diag-command-rows tr').filter({has: page.getByRole('cell', {name: op, exact: true})});
      await expect(row.locator('td').nth(1)).toHaveText(won(commands[op].ACCEPTED));
      await expect(row.locator('td').nth(2)).toHaveText(won(commands[op].REJECTED));
    }
    const log = metrics.counters.event_log;
    await expect(page.locator('#desk-diag-eventlog')).toContainText('event_log.written');
    await expect(page.locator('#desk-diag-eventlog')).toContainText(`event_log.errors${log.errors}`);
    await expect(page.locator('#desk-diag-eventlog')).toContainText(`event_log.dropped${log.dropped}`);
    await expect(page.locator('#desk-diag-eventlog')).toContainText(won(log.max_bytes));
    await expect(page.locator('#desk-diag-gaps')).toContainText('external_exporters · NOT_BOUND');
    await expect(page.locator('#desk-diag-note')).toContainText('재시작');
    // a manual refresh renders the new counters after a command receipt
    const posted = await page.request.post(`${base}/api/commands`, {
      headers: {'X-Capital-Token': state.local_token},
      data: {instance_id: state.instance_id, operation_id: 'diag-offer-1', op: 'offer', advance_id: 'sim-diag-offer', args: {fixture_id: 'sim-committed', amount: 1000}},
    });
    expect(posted.ok()).toBeTruthy();
    const before = metricsGets(seen).length;
    await expect(page.locator('#notice')).toContainText('합성 데이터로 시작하세요');
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 값을 다시 조회했습니다');
    const after = (await getJson(8961, '/api/metrics')).body;
    const offer = page.locator('#desk-diag-command-rows tr').filter({has: page.getByRole('cell', {name: 'offer', exact: true})});
    await expect(offer.locator('td').nth(1)).toHaveText(won(after.counters.commands.offer.ACCEPTED));
    expect(metricsGets(seen).length).toBe(before + 1);
    expect(commandPosts(seen)).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

test('auditor gets the same permitted diagnostics; observer gets health only with the server denial shown', async ({page}) => {
  await withServer(8962, async base => {
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-diag')).toBeVisible();
    const switched = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
    await page.locator('#role').selectOption('auditor');
    expect((await switched).ok()).toBeTruthy();
    await expect(page.locator('#role-status')).toContainText('auditor');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY');
    await expect(page.locator('#desk-diag-command-rows tr').first()).toBeVisible();
    await expect(page.locator('#desk-diag-eventlog')).toContainText('event_log.written');
    const mark = seen.gets.length;
    const observerSwitch = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
    await page.locator('#role').selectOption('observer');
    expect((await observerSwitch).ok()).toBeTruthy();
    await expect(page.locator('#role-status')).toContainText('observer');
    const health = (await getJson(8962, '/api/health')).body;
    await expect(page.locator('#desk-diag-health')).toContainText(health.workspace_status);
    await expect(page.locator('#desk-diag-health')).toContainText('LOCAL_OBSERVABILITY');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('metrics:read');
    await expect(page.locator('#desk-diag-command-rows')).toContainText('metrics:read');
    await expect(page.locator('#desk-diag-gaps li')).toHaveCount(0);
    const observerGets = seen.gets.slice(mark);
    expect(observerGets).toContain('/api/health');
    expect(observerGets).not.toContain('/api/metrics');
    expect(observerGets).not.toContain('/api/overlay');
    expect(commandPosts(seen)).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

test('a failed metrics read shows an unavailable state once, with no retry or repair controls', async ({page}) => {
  await withServer(8963, async base => {
    const seen = watch(page);
    let calls = 0;
    await page.route('**/api/metrics', route => { calls += 1; route.abort('failed'); });
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-diag')).toBeVisible();
    const health = (await getJson(8963, '/api/health')).body;
    await expect(page.locator('#desk-diag-health')).toContainText(health.workspace_status);
    await expect(page.locator('#desk-diag-command-rows')).toContainText('확인하지 못했습니다');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY');
    expect(calls).toBe(1);
    await expect(page.locator('#notice')).toContainText('합성 데이터로 시작하세요');
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 값을 다시 조회했습니다');
    await expect(page.locator('#desk-diag-command-rows')).toContainText('확인하지 못했습니다');
    expect(calls).toBe(2);
    await expect(page.locator('#desk-diag button')).toHaveCount(1);
    expect(commandPosts(seen)).toEqual([]);
  });
});

test('a restarted session clears stale diagnostic values back to the new process counters', async ({page}) => {
  await withServer(8964, async base => {
    const state = await waitReady(8964);
    const posted = await page.request.post(`${base}/api/commands`, {
      headers: {'X-Capital-Token': state.local_token},
      data: {instance_id: state.instance_id, operation_id: 'diag-stale-1', op: 'offer', advance_id: 'sim-diag-stale', args: {fixture_id: 'sim-committed', amount: 1000}},
    });
    expect(posted.ok()).toBeTruthy();
    await page.goto(`${base}/#desk`);
    const row = page.locator('#desk-diag-command-rows tr').filter({has: page.getByRole('cell', {name: 'offer', exact: true})});
    await expect(row.locator('td').nth(1)).toHaveText('1');
  });
  await withServer(8964, async base => {
    const seen = watch(page);
    await page.goto('about:blank');
    await page.goto(`${base}/#desk`);
    const row = page.locator('#desk-diag-command-rows tr').filter({has: page.getByRole('cell', {name: 'offer', exact: true})});
    await expect(row.locator('td').nth(1)).toHaveText('0');
    const health = (await getJson(8964, '/api/health')).body;
    await expect(page.locator('#desk-diag-health')).toContainText(health.workspace_status);
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
    expect(commandPosts(seen)).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

test('keyboard walkthrough reaches the diagnostics refresh and capacity labels stay readable', async ({page}) => {
  await withServer(8965, async base => {
    const seen = watch(page);
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-diag')).toBeVisible();
    const active = () => page.evaluate(() => document.activeElement && (document.activeElement.id || document.activeElement.tagName));
    let reached = false;
    for (let index = 0; index < 60 && !reached; index += 1) {
      await page.keyboard.press('Tab');
      reached = (await active()) === 'desk-diag-refresh';
    }
    expect(reached).toBe(true);
    await expect(page.locator('#notice')).toContainText('합성 데이터로 시작하세요');
    const before = metricsGets(seen).length;
    await page.keyboard.press('Enter');
    await expect(page.locator('#notice')).toContainText('진단 값을 다시 조회했습니다');
    await expect.poll(() => metricsGets(seen).length).toBe(before + 1);
    const cells = await page.locator('#desk-diag-capacity-rows td').allTextContents();
    expect(cells.join(' ')).toMatch(/\d+\/\d+/);
    expect(cells.join(' ')).toContain('DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY');
    expect(commandPosts(seen)).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});
