const {test, expect} = require('@playwright/test');
const {spawn, spawnSync} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const SHOTS = path.join(root, 'test-results', 'operator-desk');
const CSP = "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'";
const won = value => new Intl.NumberFormat('ko-KR').format(value);

function startServer(port) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-desk-'));
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

function getJson(port, pathname) {
  return new Promise((resolve, reject) => {
    const req = http.get({hostname: '127.0.0.1', port, path: pathname, timeout: 2000}, response => {
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

async function overflow(page) {
  return page.evaluate(() => ({
    scroll: document.documentElement.scrollWidth, inner: window.innerWidth,
    panel: document.querySelector('#desk').getBoundingClientRect().right,
  }));
}

async function shot(page, name, viewport) {
  const directory = path.join(SHOTS, viewport);
  fs.mkdirSync(directory, {recursive: true});
  const file = path.join(directory, `${name}.png`);
  await page.screenshot({path: file, fullPage: true});
  const png = fs.readFileSync(file);
  expect(png.readUInt32BE(0)).toBe(0x89504e47);
  expect(png.length).toBeGreaterThan(12000);
  return file;
}

async function chooseRole(page, role) {
  const switched = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
  await page.locator('#role').selectOption(role);
  expect((await switched).ok()).toBeTruthy();
}

async function cellTexts(page, rows, advanceId) {
  const row = page.locator(`${rows} tr`).filter({has: page.getByRole('cell', {name: advanceId, exact: true})});
  return row.locator('td').allTextContents();
}

test('organizer advances sim_day by 1 and by 30 and interest_due matches GET /api/overlay', async ({page}) => {
  await withServer(8911, async base => {
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/?case=sim-unbound#desk`);
    await expect(page.locator('#desk')).toBeVisible();
    await expect(page.locator('#desk-clock')).toContainText('sim_day 0');
    const risk = (await getJson(8911, '/api/risk')).body;
    await expect(page.locator('[data-tile="outstanding"] strong')).toHaveText(won(risk.totals.outstanding_krw));
    await expect(page.locator('[data-tile="hhi"] strong')).toContainText(`${risk.concentration.hhi_permille}‰`);
    await expect(page.locator('[data-tile="reserve"] strong')).toHaveText(won(risk.reserve.requirement_krw));
    await expect(page.locator('#desk-tiles .tile')).toHaveCount(6);
    let prior = 0;
    for (const days of [1, 30]) {
      await page.locator('#desk-days').fill(String(days));
      const response = page.waitForResponse(item => item.url().endsWith('/api/overlay/commands') && item.request().method() === 'POST');
      await page.locator('#desk-advance').click();
      expect((await response).ok()).toBeTruthy();
      const overlay = (await getJson(8911, '/api/overlay')).body;
      expect(overlay.sim_day).toBe(prior + days);
      await expect(page.locator('#desk-clock')).toContainText(`sim_day ${overlay.sim_day}`);
      expect(overlay.advances.length).toBeGreaterThan(0);
      for (const row of overlay.advances) {
        await expect(async () => {
          const cells = await cellTexts(page, '#desk-overlay-rows', row.advance_id);
          expect(cells[2]).toBe(won(row.principal_outstanding_krw));
          expect(cells[3]).toBe(won(row.interest_due_krw));
          expect(cells[4]).toBe(won(row.default_interest_due_krw));
          expect(cells[5]).toBe(String(row.accrued_through_sim_day));
        }).toPass({timeout: 5000});
      }
      const body = JSON.parse(commandPosts(seen).at(-1).body);
      expect(body.op).toBe('advance_day');
      expect(body.from_sim_day).toBe(prior);
      expect(body.to_sim_day).toBe(prior + days);
      prior = overlay.sim_day;
      await expect(page.locator('#notice')).toContainText(`sim_day ${body.from_sim_day} → ${body.to_sim_day}`);
    }
    const final = (await getJson(8911, '/api/overlay')).body;
    expect(final.advances.some(row => row.interest_due_krw > 0)).toBe(true);
    expect(commandPosts(seen).map(post => post.url)).toEqual(['/api/overlay/commands', '/api/overlay/commands']);
    // the F04 journal is untouched by advance_day
    const timeline = page.locator('#desk-timeline-rows tr[data-source^="오버레이"]');
    await expect(timeline.first()).toBeVisible();
    await expect(page.locator('#desk-timeline-rows')).toContainText('posted_contract_krw=');
    expect(seen.errors).toEqual([]);
  });
});

test('disabled actions show a server reason and a click sends zero POSTs', async ({page, request}) => {
  await withServer(8912, async base => {
    const seen = watch(page);
    await page.goto(`${base}/?case=sim-unbound#desk`);
    const overlay = (await getJson(8912, '/api/overlay')).body;
    const row = overlay.advances.find(item => item.advance_id === 'sim-unbound');
    expect(row.close_ready).toBe(false);
    const close = page.locator('#desk-act-close');
    await expect(close).toHaveAttribute('aria-disabled', 'true');
    const reason = page.locator('#desk-reason-close');
    await expect(reason).toHaveText(`close_ready=false · principal_outstanding_krw=${row.principal_outstanding_krw} · interest_due_krw=${row.interest_due_krw} · default_interest_due_krw=${row.default_interest_due_krw}`);
    await expect(close).toHaveAccessibleDescription(await reason.textContent());
    await expect(page.locator('#desk-act-default')).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('#desk-reason-default')).toContainText(`margin.limit=${overlay.margin.limit}`);
    await expect(page.locator('#desk-reason-default')).toContainText(`margin.state=${row.margin.state}`);
    // Playwright treats aria-disabled as not enabled, so force the click the way a user would try it
    await close.click({force: true});
    await expect(page.locator('#notice')).toContainText('close_ready=false');
    await page.locator('#desk-act-default').click({force: true});
    await expect(page.locator('#notice')).toContainText('default_eligible 제안 없음');
    await page.waitForTimeout(300);
    expect(seen.posts).toEqual([]);

    await page.locator('#desk-case').selectOption('sim-pending-settlement');
    const preview = (await getJson(8912, `/api/preview/sim-pending-settlement?instance_id=${(await getJson(8912, '/api/state')).body.instance_id}`)).body;
    expect(preview.outcome).toBe('WOULD_REJECT');
    await expect(page.locator('#desk-act-draw')).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('#desk-reason-draw')).toHaveText(preview.reason);
    await page.locator('#desk-act-draw').click({force: true});
    await page.waitForTimeout(300);
    expect(seen.posts).toEqual([]);

    // an OFFERED case: approve stays enabled, the underwrite record is advisory text from the server
    const state = (await getJson(8912, '/api/state')).body;
    const offered = await request.post(`${base}/api/commands`, {
      headers: {'X-Capital-Token': state.local_token},
      data: {instance_id: state.instance_id, operation_id: 'desk-offer-1', op: 'offer', advance_id: 'sim-desk-offer', args: {fixture_id: 'sim-pending', amount: 10000}},
    });
    expect(offered.ok()).toBeTruthy();
    await page.goto(`${base}/?case=sim-desk-offer#desk`);
    const record = (await getJson(8912, `/api/underwrite/sim-desk-offer?instance_id=${state.instance_id}&sim_day=0`)).body;
    await expect(page.locator('#desk-act-approve')).not.toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('#desk-reason-approve')).toContainText(`proposal=${record.proposal}`);
    if (record.failed_check) await expect(page.locator('#desk-reason-approve')).toContainText(`failed_check=${record.failed_check}`);
    await expect(page.locator('#desk-reason-approve')).toContainText('막지 않음');
    expect(seen.errors).toEqual([]);
  });
});

test('auditor sees timeline and tiles with no command controls; observer sees a forbidden notice', async ({page}) => {
  await withServer(8913, async base => {
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-tiles .tile')).toHaveCount(6);
    await chooseRole(page, 'auditor');
    await expect(page.locator('#role-status')).toContainText('auditor');
    await expect(page.locator('#desk-tiles .tile')).toHaveCount(6);
    await expect(page.locator('#desk-timeline-rows tr').first()).toBeVisible();
    await expect(page.locator('#desk-overlay-rows tr').first()).toBeVisible();
    await expect(page.locator('#desk-commands')).toBeHidden();
    await expect(page.locator('#desk-advance')).toBeHidden();
    await expect(page.locator('#desk-days')).toBeHidden();
    await expect(page.locator('#desk-actions button')).toHaveCount(0);
    await expect(page.locator('#desk-commands-note')).toContainText('overlay:command');
    await shot(page, 'auditor', 'desktop');
    expect(commandPosts(seen)).toEqual([]);
    await chooseRole(page, 'observer');
    await expect(page.locator('#desk-forbidden')).toBeVisible();
    await expect(page.locator('#desk-forbidden')).toContainText('projection:read');
    await expect(page.locator('#desk-forbidden')).toContainText('observer');
    await expect(page.locator('#desk-body')).toBeHidden();
    await expect(page.locator('#desk-advance')).toBeHidden();
    await shot(page, 'observer', 'desktop');
    expect(commandPosts(seen)).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

test('observer from the first load has no desk fetches and no console errors', async ({page}) => {
  await withServer(8914, async base => {
    await page.addInitScript(() => sessionStorage.setItem('kix-capital-role', 'observer'));
    const seen = watch(page);
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#role-status')).toContainText('observer');
    await expect(page.locator('#desk-forbidden')).toBeVisible();
    expect(seen.gets).not.toContain('/api/overlay');
    expect(seen.gets).not.toContain('/api/export/manifest');
    expect(seen.gets).not.toContain('/api/risk');
    expect(commandPosts(seen)).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

test('keyboard-only path completes advance_day with a tested focus order', async ({page}) => {
  await withServer(8915, async base => {
    const seen = watch(page);
    await page.goto(`${base}/?case=sim-unbound#desk`);
    await expect(page.locator('#desk-clock')).toContainText('sim_day 0');
    await expect(page.locator('#desk-act-default')).toBeVisible();
    const active = () => page.evaluate(() => document.activeElement && (document.activeElement.id || document.activeElement.tagName));
    let reached = false;
    for (let index = 0; index < 40 && !reached; index += 1) {
      await page.keyboard.press('Tab');
      reached = (await active()) === 'desk-refresh';
    }
    expect(reached).toBe(true);
    const order = ['desk-refresh'];
    for (let index = 0; index < 7; index += 1) {
      await page.keyboard.press('Tab');
      order.push(await active());
    }
    expect(order).toEqual(['desk-refresh', 'desk-case', 'desk-days', 'desk-advance', 'desk-act-close', 'desk-act-default', 'desk-overlay-region', 'desk-timeline-region']);
    for (let index = 0; index < 5; index += 1) await page.keyboard.press('Shift+Tab');
    expect(await active()).toBe('desk-days');
    await page.keyboard.press('Control+A');
    await page.keyboard.type('2');
    await page.keyboard.press('Tab');
    expect(await active()).toBe('desk-advance');
    const first = page.waitForResponse(item => item.url().endsWith('/api/overlay/commands'));
    await page.keyboard.press('Enter');
    expect((await first).ok()).toBeTruthy();
    await expect(page.locator('#desk-clock')).toContainText('sim_day 2');
    await expect(page.locator('#desk-advance')).toBeEnabled();
    expect(await active()).toBe('desk-advance');
    await page.keyboard.press('Shift+Tab');
    await page.keyboard.press('Control+A');
    await page.keyboard.type('1');
    await page.keyboard.press('Tab');
    const second = page.waitForResponse(item => item.url().endsWith('/api/overlay/commands'));
    await page.keyboard.press('Space');
    expect((await second).ok()).toBeTruthy();
    await expect(page.locator('#desk-clock')).toContainText('sim_day 3');
    expect((await getJson(8915, '/api/overlay')).body.sim_day).toBe(3);
    expect(commandPosts(seen).length).toBe(2);
    expect(seen.errors).toEqual([]);
  });
});

test('375px has no horizontal overflow and screenshots are saved', async ({page}) => {
  await withServer(8916, async base => {
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await page.goto(`${base}/?case=sim-unbound#desk`);
    await expect(page.locator('#desk-tiles .tile')).toHaveCount(6);
    await expect(page.locator('#desk-timeline-rows tr').first()).toBeVisible();
    let metrics = await overflow(page);
    expect(metrics.scroll).toBeLessThanOrEqual(metrics.inner);
    const desktop = await shot(page, 'organizer', 'desktop');
    await page.setViewportSize({width: 375, height: 800});
    metrics = await overflow(page);
    expect(metrics.scroll).toBeLessThanOrEqual(metrics.inner);
    expect(metrics.panel).toBeLessThanOrEqual(metrics.inner);
    await page.locator('#desk-timeline-region').scrollIntoViewIfNeeded();
    metrics = await overflow(page);
    expect(metrics.scroll).toBeLessThanOrEqual(metrics.inner);
    await page.locator('#desk-advance').scrollIntoViewIfNeeded();
    const box = await page.locator('#desk-advance').boundingBox();
    expect(box.x + box.width).toBeLessThanOrEqual(375);
    const mobile = await shot(page, 'organizer', 'mobile');
    expect(fs.existsSync(desktop) && fs.existsSync(mobile)).toBe(true);
    await chooseRole(page, 'auditor');
    await expect(page.locator('#desk-commands')).toBeHidden();
    metrics = await overflow(page);
    expect(metrics.scroll).toBeLessThanOrEqual(metrics.inner);
    await shot(page, 'auditor', 'mobile');
    await chooseRole(page, 'observer');
    await expect(page.locator('#desk-forbidden')).toBeVisible();
    metrics = await overflow(page);
    expect(metrics.scroll).toBeLessThanOrEqual(metrics.inner);
    await shot(page, 'observer', 'mobile');
    expect(seen.errors).toEqual([]);
  });
});

test('CSP header is unchanged and the page keeps the desk hidden outside #desk', async ({page}) => {
  await withServer(8917, async base => {
    await page.goto(`${base}/`);
    await expect(page.locator('#desk')).toBeHidden();
    await expect(page.getByRole('button', {name: '데스크 새로고침'})).toHaveCount(0);
    const head = await page.request.get(`${base}/`);
    expect(head.headers()['content-security-policy']).toBe(CSP);
    const script = await page.request.get(`${base}/app.js`);
    const text = await script.text();
    expect(text).not.toContain('innerHTML');
    expect(text).not.toMatch(/\beval\s*\(/);
    await page.locator('nav a[href="#desk"]').click();
    await expect(page.locator('#desk')).toBeVisible();
    await expect(page.locator('#create')).toBeHidden();
    await page.locator('nav a[href="#overview"]').click();
    await expect(page.locator('#desk')).toBeHidden();
    await expect(page.locator('#create')).toBeVisible();
  });
});

test('a lost advance_day response stays UNKNOWN and recovery never re-POSTs', async ({page}) => {
  await withServer(8918, async base => {
    const seen = watch(page);
    await page.route('**/api/overlay/commands', route => route.abort('failed'));
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-clock')).toContainText('sim_day 0');
    await page.locator('#desk-advance').click();
    await expect(page.locator('#notice')).toContainText('UNKNOWN');
    await expect(page.locator('#recovery')).toBeVisible();
    await expect(page.locator('#desk-advance')).toBeDisabled();
    expect(await page.evaluate(() => JSON.parse(localStorage.getItem('kix-capital-pending-v1')).op)).toBe('advance_day');
    await page.locator('#recover').click();
    await expect(page.locator('#notice')).toContainText('UNKNOWN');
    await expect(page.locator('#recovery')).toBeVisible();
    expect(commandPosts(seen).length).toBe(1);
    expect((await getJson(8918, '/api/overlay')).body.sim_day).toBe(0);
    expect(seen.gets.filter(item => item === '/api/overlay').length).toBeGreaterThan(1);
  });
});

test('when the server applied the advance but the response was lost, recovery finds it by operation_id', async ({page}) => {
  await withServer(8919, async base => {
    const seen = watch(page);
    await page.route('**/api/overlay/commands', async route => { await route.fetch(); await route.abort('failed'); });
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-clock')).toContainText('sim_day 0');
    await page.locator('#desk-advance').click();
    await expect(page.locator('#notice')).toContainText('UNKNOWN');
    await expect(page.locator('#recovery')).toBeVisible();
    await page.locator('#recover').click();
    await expect(page.locator('#recovery')).toBeHidden();
    await expect(page.locator('#desk-clock')).toContainText('sim_day 1');
    expect(await page.evaluate(() => localStorage.getItem('kix-capital-pending-v1'))).toBeNull();
    expect(commandPosts(seen).length).toBe(1);
    expect((await getJson(8919, '/api/overlay')).body.sim_day).toBe(1);
    await expect(page.locator('#desk-advance')).toBeEnabled();
  });
});

test('busy fence: a second advance is blocked while the first is in flight', async ({page}) => {
  await withServer(8920, async base => {
    const seen = watch(page);
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/api/overlay/commands', async route => { await gate; await route.continue(); });
    await page.goto(`${base}/#desk`);
    await expect(page.locator('#desk-clock')).toContainText('sim_day 0');
    await page.locator('#desk-advance').click();
    await expect(page.locator('#desk-advance')).toBeDisabled();
    await expect(page.locator('#desk-days')).toBeDisabled();
    await expect(page.locator('#desk-refresh')).toBeDisabled();
    release();
    await expect(page.locator('#desk-clock')).toContainText('sim_day 1');
    await expect(page.locator('#desk-advance')).toBeEnabled();
    expect(commandPosts(seen).length).toBe(1);
  });
});

test('a stale preview response for a case the operator left is dropped', async ({page}) => {
  await withServer(8921, async base => {
    let release;
    const gate = new Promise(resolve => { release = resolve; });
    await page.route('**/api/preview/sim-pending-settlement**', async route => { await gate; await route.continue(); });
    await page.goto(`${base}/?case=sim-pending-settlement#desk`);
    await expect(page.locator('#desk-act-cancel')).toBeVisible();
    await expect(page.locator('#desk-reason-draw')).toContainText('불러오는 중');
    await page.locator('#desk-case').selectOption('sim-unbound');
    await expect(page.locator('#desk-act-close')).toBeVisible();
    release();
    await page.waitForTimeout(400);
    await expect(page.locator('#desk-act-draw')).toHaveCount(0);
    await expect(page.locator('#desk-act-close')).toBeVisible();
    await expect(page.locator('#desk-next-help')).toContainText('sim-unbound');
  });
});
