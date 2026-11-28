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
    let finishBind;
    const bindPending = new Promise(resolve => { finishBind = resolve; });
    await page.route('**/api/session', async route => {
      await bindPending;
      await route.continue();
    });
    await expect(page.locator('#role')).toBeEnabled();
    const mark = seen.gets.length;
    const observerSwitch = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
    try {
      await page.locator('#role').selectOption('observer');
      await expect(page.locator('#desk-diag-capacity-rows')).toContainText('unavailable');
      await expect(page.locator('#desk-diag-command-rows')).toContainText('unavailable');
      await expect(page.locator('#desk-diag-eventlog')).toContainText('unavailable');
    } finally {
      finishBind();
    }
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
    expect(observerGets).not.toContain('/api/overlay/slices');
    expect(commandPosts(seen)).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

test('a failed metrics read shows an unavailable state once, with no retry or repair controls', async ({page}) => {
  await withServer(8963, async base => {
    const seen = watch(page);
    let calls = 0;
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-diag')).toBeVisible();
    const health = (await getJson(8963, '/api/health')).body;
    await expect(page.locator('#desk-diag-health')).toContainText(health.workspace_status);
    await expect(page.locator('#desk-diag-eventlog')).toContainText('event_log.written');
    await expect(page.locator('#notice')).toContainText('합성 데이터로 시작하세요');
    await page.route('**/api/metrics', route => { calls += 1; route.abort('failed'); });
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 값을 다시 조회했습니다');
    await expect(page.locator('#desk-diag-command-rows')).toContainText('확인하지 못했습니다');
    await expect(page.locator('#desk-diag-eventlog')).toHaveText('event_logunavailable');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY');
    expect(calls).toBe(1);
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#desk-diag-refresh')).toBeEnabled();
    await expect(page.locator('#desk-diag-command-rows')).toContainText('확인하지 못했습니다');
    await expect(page.locator('#desk-diag-eventlog')).toHaveText('event_logunavailable');
    expect(calls).toBe(2);
    await page.unroute('**/api/metrics');
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#desk-diag-eventlog')).toContainText('event_log.written');
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

test('a failed state prerequisite during refresh clears loaded diagnostics in place', async ({page}) => {
  await withServer(8966, async base => {
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('event_log.written');
    const before = metricsGets(seen).length;
    // Keep the loaded page; fail only the state prerequisite of the refresh.
    await page.route('**/api/state', route => route.abort('failed'));
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 조회에 실패했습니다');
    await expect(page.locator('#desk-diag-label')).toContainText('사용할 수 없습니다');
    await expect(page.locator('#desk-diag-health')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-command-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-eventlog')).not.toContainText('event_log.written');
    await expect(page.locator('#desk-diag-capacity-rows')).not.toContainText('DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY');
    await expect(page.locator('#desk-diag-command-rows tr')).toHaveCount(1);
    // The failed prerequisite stops the refresh: no diagnostics re-read, no retry.
    expect(metricsGets(seen).length).toBe(before);
    await page.unroute('**/api/state');
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 값을 다시 조회했습니다');
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('event_log.written');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY');
    expect(commandPosts(seen)).toEqual([]);
  });
});

test('a failed evidence prerequisite during refresh clears loaded diagnostics in place', async ({page}) => {
  await withServer(8967, async base => {
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('event_log.written');
    const before = metricsGets(seen).length;
    // Keep the loaded page; state succeeds but the evidence prerequisite fails.
    await page.route('**/api/evidence', route => route.abort('failed'));
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 조회에 실패했습니다');
    await expect(page.locator('#desk-diag-label')).toContainText('사용할 수 없습니다');
    await expect(page.locator('#desk-diag-health')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-command-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-eventlog')).not.toContainText('event_log.written');
    await expect(page.locator('#desk-diag-capacity-rows')).not.toContainText('DEMO_BOUND_NOT_FINANCIAL_LIMIT_NOT_STAGE5_CAPACITY');
    expect(metricsGets(seen).length).toBe(before);
    await page.unroute('**/api/evidence');
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 값을 다시 조회했습니다');
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('event_log.written');
    expect(commandPosts(seen)).toEqual([]);
  });
});

test('an in-page server restart clears stale diagnostics without navigating away', async ({page}) => {
  let started = startServer(8968);
  try {
    const base = 'http://127.0.0.1:8968';
    const first = await waitReady(8968);
    const posted = await page.request.post(`${base}/api/commands`, {
      headers: {'X-Capital-Token': first.local_token},
      data: {instance_id: first.instance_id, operation_id: 'diag-inpage-1', op: 'offer', advance_id: 'sim-diag-inpage', args: {fixture_id: 'sim-committed', amount: 1000}},
    });
    expect(posted.ok()).toBeTruthy();
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/#desk`);
    const row = page.locator('#desk-diag-command-rows tr').filter({has: page.getByRole('cell', {name: 'offer', exact: true})});
    await expect(row.locator('td').nth(1)).toHaveText('1');
    // Restart on the same port while the page keeps its old token and DOM.
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
    started = startServer(8968);
    const second = await waitReady(8968);
    expect(second.instance_id).not.toBe(first.instance_id);
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 조회에 실패했습니다');
    await expect(page.locator('#desk-diag-label')).toContainText('사용할 수 없습니다');
    await expect(page.locator('#desk-diag-health')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-command-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-command-rows')).not.toContainText('offer');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('unavailable');
    expect(commandPosts(seen)).toEqual([]);
    // Killing the process under the live page produces transport-level console
    // noise (403 for the stale token, reset/empty response on reused idle
    // sockets); Chromium retries and the assertions above pin the outcome.
    // Uncaught page errors are not resource noise and remain fatal here.
    expect(seen.errors.filter(item => !item.startsWith('Failed to load resource:'))).toEqual([]);
    // Recovery is a fresh load against the new process: counters start at 0.
    await page.reload();
    const fresh = page.locator('#desk-diag-command-rows tr').filter({has: page.getByRole('cell', {name: 'offer', exact: true})});
    await expect(fresh.locator('td').nth(1)).toHaveText('0');
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('a changed instance with a failing evidence read clears the previous session diagnostics', async ({page}) => {
  let started = startServer(8969);
  try {
    const base = 'http://127.0.0.1:8969';
    const first = await waitReady(8969);
    const posted = await page.request.post(`${base}/api/commands`, {
      headers: {'X-Capital-Token': first.local_token},
      data: {instance_id: first.instance_id, operation_id: 'diag-restart-evidence-1', op: 'offer', advance_id: 'sim-diag-restart-evidence', args: {fixture_id: 'sim-committed', amount: 1000}},
    });
    expect(posted.ok()).toBeTruthy();
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/#desk`);
    const row = page.locator('#desk-diag-command-rows tr').filter({has: page.getByRole('cell', {name: 'offer', exact: true})});
    await expect(row.locator('td').nth(1)).toHaveText('1');
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
    started = startServer(8969);
    const second = await waitReady(8969);
    expect(second.instance_id).not.toBe(first.instance_id);
    // Controlled prerequisite failure: let /api/state return the restarted
    // process's real snapshot (the page's old token would otherwise 403),
    // then fail /api/evidence so the new state never reaches the commit.
    await page.route('**/api/state', async route => {
      const snapshot = await getJson(8969, '/api/state');
      await route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify(snapshot.body)});
    });
    let failEvidence;
    const evidenceFailure = new Promise(resolve => { failEvidence = resolve; });
    await page.route('**/api/evidence', async route => {
      await evidenceFailure;
      await route.abort('failed');
    });
    await page.locator('#desk-diag-refresh').click();
    // The new instance clears the old values while evidence is still pending,
    // before the failure catch or final state/deskData replacement can run.
    await expect(page.locator('#desk-diag-label')).toContainText('세션이 바뀌어');
    await expect(page.locator('#desk-diag-health')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-command-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-command-rows')).not.toContainText('offer');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('unavailable');
    failEvidence();
    await expect(page.locator('#notice')).toContainText('진단 조회에 실패했습니다');
    // The fulfilled state carried the new process token, so removing the
    // controlled failures lets a manual refresh recover without navigation.
    await page.unroute('**/api/state');
    await page.unroute('**/api/evidence');
    await page.locator('#desk-diag-refresh').click();
    await expect(page.locator('#notice')).toContainText('진단 값을 다시 조회했습니다');
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
    const fresh = page.locator('#desk-diag-command-rows tr').filter({has: page.getByRole('cell', {name: 'offer', exact: true})});
    await expect(fresh.locator('td').nth(1)).toHaveText('0');
    const health = (await getJson(8969, '/api/health')).body;
    await expect(page.locator('#desk-diag-health')).toContainText(health.workspace_status);
    expect(commandPosts(seen)).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
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
    // Keyboard-only failure path: a controlled prerequisite failure must clear
    // every loaded value, and Tab+Enter must restore them without a mouse.
    // The busy fence disables the focused button, so Tab back to it first.
    await page.route('**/api/state', route => route.abort('failed'));
    for (let index = 0; index < 60 && (await active()) !== 'desk-diag-refresh'; index += 1) await page.keyboard.press('Tab');
    expect(await active()).toBe('desk-diag-refresh');
    await page.keyboard.press('Enter');
    await expect(page.locator('#notice')).toContainText('진단 조회에 실패했습니다');
    await expect(page.locator('#desk-diag-label')).toContainText('사용할 수 없습니다');
    await expect(page.locator('#desk-diag-health')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-capacity-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-command-rows')).toContainText('unavailable');
    await expect(page.locator('#desk-diag-eventlog')).toContainText('unavailable');
    await page.unroute('**/api/state');
    for (let index = 0; index < 60 && (await active()) !== 'desk-diag-refresh'; index += 1) await page.keyboard.press('Tab');
    expect(await active()).toBe('desk-diag-refresh');
    await page.keyboard.press('Enter');
    await expect(page.locator('#notice')).toContainText('진단 값을 다시 조회했습니다');
    await expect(page.locator('#desk-diag-label')).toContainText('LOCAL_OBSERVABILITY');
    const restored = await page.locator('#desk-diag-capacity-rows td').allTextContents();
    expect(restored.join(' ')).toMatch(/\d+\/\d+/);
    expect(commandPosts(seen)).toEqual([]);
  });
});
