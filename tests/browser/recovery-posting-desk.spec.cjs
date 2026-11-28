const {test, expect} = require('@playwright/test');
const {spawn} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const storageKey = 'kix-capital-pending-v1';
const port = 8951;
const base = `http://127.0.0.1:${port}`;

function getState() {
  return new Promise((resolve, reject) => {
    const req = http.get(`${base}/api/state`, {timeout: 500}, response => {
      let body = '';
      response.on('data', chunk => body += chunk);
      response.on('end', () => {try {resolve(JSON.parse(body));} catch (error) {reject(error);}});
    });
    req.on('error', reject);
    req.on('timeout', () => req.destroy(Error('timeout')));
  });
}

async function withServer(scenario, run) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-recovery-desk-'));
  const log = fs.openSync(path.join(directory, 'server.log'), 'a');
  const child = spawn('python3', ['tests/browser/support/recovery_server.py', '--port', String(port), '--scenario', scenario], {cwd: root, stdio: ['ignore', log, log]});
  fs.closeSync(log);
  try {
    await expect.poll(async () => {
      if (child.exitCode !== null) throw Error(fs.readFileSync(path.join(directory, 'server.log'), 'utf8'));
      try {return !!(await getState()).instance_id;} catch {return false;}
    }, {timeout: 8000}).toBe(true);
    await run();
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      const exited = new Promise(resolve => child.once('exit', resolve));
      child.kill('SIGTERM');
      await exited;
    }
    fs.rmSync(directory, {recursive: true, force: true});
  }
}

const overlay = async request => (await (await request.get(`${base}/api/overlay`)).json());
const manifest = async request => (await (await request.get(`${base}/api/export/manifest`)).json());
const pending = page => page.evaluate(key => localStorage.getItem(key), storageKey);
const recoveryRow = view => view.recovery.advances.find(row => row.advance_id === 'sim-recovery');
const sourceQuote = (view, claim='sim-committed') => recoveryRow(view).quotes.find(q => q.source_ref.claim_id === claim);
function watch(page) {
  const seen = {posts: [], gets: [], errors: []};
  page.on('request', request => {
    const url = new URL(request.url());
    if (request.method() === 'POST' && url.pathname !== '/api/session') seen.posts.push(request.postDataJSON());
    if (request.method() === 'GET') seen.gets.push(url.pathname + url.search);
  });
  page.on('pageerror', error => seen.errors.push(String(error)));
  return seen;
}
async function open(page) {
  await page.goto(`${base}/?case=sim-recovery#desk`);
  await expect(page.locator('#desk-recovery')).toBeVisible();
  await expect(page.locator('#desk-refresh')).toBeEnabled();
}
async function role(page, name) {
  await page.locator('#role').selectOption(name);
  await expect(page.locator('#role-status')).toContainText(name);
  await expect(page.locator('#role')).toBeEnabled();
}
async function fillRecovery(page, view, amount='1000', claim='sim-committed') {
  await page.locator('#desk-recovery-source').selectOption(sourceQuote(view, claim).quote_ref);
  await page.locator('#desk-recovery-amount').fill(amount);
}
async function submit(page, op) {
  const response = page.waitForResponse(r => r.url().endsWith('/api/overlay/commands') && r.request().method() === 'POST');
  await page.locator(op === 'post_recovery' ? '#desk-recovery-post' : '#desk-recovery-writeoff').click();
  const result = await response;
  const body = await result.json();
  await expect(page.locator('#desk-refresh')).toBeEnabled();
  return {status: result.status(), body};
}
async function raw(request, body) {
  const state = await getState();
  return request.post(`${base}/api/overlay/commands`, {headers: {'X-Capital-Token': state.local_token}, data: {instance_id: state.instance_id, ...body}});
}
async function compareFacts(page, view) {
  const row = recoveryRow(view);
  for (const key of ['default_day_status', 'default_sim_day', 'writeoff_sim_day', 'writeoff_eligible', 'principal_krw', 'interest_krw', 'default_interest_krw', 'claim_krw', 'outstanding_loss_krw', 'residual_claim_krw']) {
    await expect(page.locator(`#desk-recovery-facts [data-field="${key}"]`)).toHaveText(row[key] === null ? '— (unavailable)' : String(row[key]));
  }
  await expect(page.locator('#desk-recovery-quotes tr')).toHaveCount(row.quotes.length);
  for (const q of row.quotes) {
    const cells = await page.locator('#desk-recovery-quotes tr').filter({hasText: q.quote_ref}).locator('td').allTextContents();
    expect(cells).toEqual([JSON.stringify(q.source_ref), q.quote_ref, String(q.available_krw), String(q.amount_krw), q.waterfall_step]);
  }
}

for (const width of [1280, 375]) test(`recovery, explicit write-off, then late recovery use server values at ${width}px`, async ({page, request}) => {
  await withServer('normal', async () => {
    const seen = watch(page);
    await page.setViewportSize({width, height: 900});
    await open(page);
    const original = await manifest(request);
    let view = await overlay(request);
    await compareFacts(page, view);
    await expect(page.locator('#desk-recovery-status')).toContainText('reserve_binding=NOT_BOUND');
    await expect(page.locator('#desk-recovery-source')).toHaveValue('');
    await expect(page.locator('#desk-recovery-approval-a')).not.toBeChecked();
    await fillRecovery(page, view);
    // Keyboard order remains ordinary DOM order, including explicit simulation controls.
    await page.locator('#desk-recovery-source').focus();
    for (const id of ['desk-recovery-amount', 'desk-recovery-approval-a', 'desk-recovery-approval-b', 'desk-recovery-decline', 'desk-recovery-post', 'desk-recovery-writeoff']) {
      await page.keyboard.press('Tab');
      await expect(page.locator(`#${id}`)).toBeFocused();
    }
    await page.locator('#desk-recovery-approval-a').check();
    const first = await submit(page, 'post_recovery');
    expect(first.status).toBe(200);
    expect(seen.posts[0]).toEqual({instance_id: view.instance_id, operation_id: first.body.operation_id, op: 'post_recovery', advance_ref: 'sim-recovery', at_sim_day: view.sim_day, amount_krw: 1000, source_ref: sourceQuote(view).source_ref, quote_ref: sourceQuote(view).quote_ref, approvals: [{approver_label: 'sim-approver-a'}]});
    view = await overlay(request);
    await compareFacts(page, view);
    expect(view.recovery.entries[0].allocation).toEqual(first.body.entry.allocation);
    await expect(page.locator('#desk-recovery-entries')).toContainText(JSON.stringify(first.body.entry.allocation, null, 2).split('\n')[1].trim());
    await expect(page.locator('#desk-recovery-amount')).toHaveValue('');
    await expect(page.locator('#desk-recovery-approval-a')).not.toBeChecked();
    await page.locator('#desk-days').fill('90');
    await page.locator('#desk-advance').click();
    await expect(page.locator('#desk-clock')).toContainText('sim_day 100');
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    await page.locator('#desk-recovery-decline').fill('SIMULATED_DECLINED');
    const wo = await submit(page, 'post_writeoff');
    expect(wo.status).toBe(200);
    expect(seen.posts[2]).toEqual({instance_id: view.instance_id, operation_id: wo.body.operation_id, op: 'post_writeoff', advance_ref: 'sim-recovery', at_sim_day: 100, approvals: [], setoff_declined_reason: 'SIMULATED_DECLINED'});
    await expect(page.locator('#desk-recovery-facts')).toContainText('recorded WRITEOFFtrue');
    await expect(page.locator('#desk-recovery-entries')).toContainText('"waterfall_trace"');
    await expect(page.locator('#desk-recovery-entries')).toContainText('UNBUILT_V1');
    view = await overlay(request);
    await compareFacts(page, view);
    await fillRecovery(page, view, '100');
    const late = await submit(page, 'post_recovery');
    expect(late.status).toBe(200);
    expect(late.body.entry.phase).toBe('POST_WRITEOFF');
    view = await overlay(request);
    await compareFacts(page, view);
    expect(recoveryRow(view).residual_claim_krw).toBe(late.body.entry.residual_claim_krw);
    const final = await manifest(request);
    expect(final.sections.journal).toEqual(original.sections.journal);
    expect((await getState()).state_digest).toBe(view.observed_state_digest);
    expect((await getState()).cases[0].phase).toBe('DEFAULTED');
    await expect(page.locator('#desk-recovery-controls')).toBeVisible();
    expect(await pending(page)).toBeNull();
    const dimensions = await page.evaluate(() => ({scroll: document.documentElement.scrollWidth, width: innerWidth}));
    expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.width);
    fs.mkdirSync(path.join(root, 'test-results/recovery-posting-desk'), {recursive: true});
    await page.screenshot({path: path.join(root, `test-results/recovery-posting-desk/lifecycle-${width}.png`), fullPage: true});
    expect(seen.errors).toEqual([]);
  });
});

for (const [scenario, op, error, decline] of [
  ['normal', 'post_writeoff', 'WRITEOFF_NOT_ELIGIBLE', ''],
  ['eligible', 'post_writeoff', 'WRITEOFF_SETOFF_AVAILABLE', ''],
  ['high', 'post_writeoff', 'TWO_PERSON_REQUIRED', 'SIMULATED_DECLINED'],
  ['high', 'post_recovery', 'TWO_PERSON_REQUIRED', ''],
  ['policy-race', 'post_writeoff', 'NOT_BOUND', 'SIMULATED_DECLINED'],
  ['normal', 'post_recovery', 'RECOVERY_WATERFALL_ORDER', ''],
]) test(`server refusal ${error} for ${op} is shown once without resubmission`, async ({page, request}) => {
  await withServer(scenario, async () => {
    const seen = watch(page);
    await open(page);
    const before = await overlay(request);
    if (op === 'post_recovery') await fillRecovery(page, before, scenario === 'high' ? '50000001' : '1', scenario === 'high' ? 'demo-alpha-arena' : 'sim-pending');
    if (decline) await page.locator('#desk-recovery-decline').fill(decline);
    const result = await submit(page, op);
    expect(result.status).toBeGreaterThanOrEqual(400);
    expect(result.body.error).toBe(error);
    await expect(page.locator('#notice')).toContainText(error);
    expect((await overlay(request)).recovery.entries).toEqual(before.recovery.entries);
    expect(await pending(page)).toBeNull();
    await page.reload();
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    expect(seen.posts).toHaveLength(1);
    expect(seen.posts[0].approvals).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

test('two selected synthetic labels satisfy the existing server threshold, without implying identity', async ({page, request}) => {
  await withServer('high', async () => {
    const seen = watch(page);
    await open(page);
    await expect(page.locator('#desk-recovery-approvals legend')).toContainText('not authenticated second-person approval');
    await fillRecovery(page, await overlay(request), '50000001', 'demo-alpha-arena');
    await page.locator('#desk-recovery-approval-b').check();
    await page.locator('#desk-recovery-approval-a').check();
    expect((await submit(page, 'post_recovery')).status).toBe(200);
    expect(seen.posts[0].approvals).toEqual([{approver_label: 'sim-approver-a'}, {approver_label: 'sim-approver-b'}]);
    expect(await pending(page)).toBeNull();
  });
});

test('stale quote refusal retains original source and quote and never retries', async ({page, request}) => {
  await withServer('normal', async () => {
    const seen = watch(page);
    await open(page);
    const old = await overlay(request), q = sourceQuote(old);
    await fillRecovery(page, old, '100');
    const other = await raw(request, {operation_id: 'other-tab-recovery', op: 'post_recovery', advance_ref: 'sim-recovery', at_sim_day: old.sim_day, amount_krw: 1, source_ref: q.source_ref, quote_ref: q.quote_ref, approvals: []});
    expect(other.ok()).toBe(true);
    const result = await submit(page, 'post_recovery');
    expect(result.body.error).toBe('RECOVERY_QUOTE_STALE');
    await expect(page.locator('#notice')).toContainText('RECOVERY_QUOTE_STALE');
    expect(seen.posts).toHaveLength(1);
    expect(seen.posts[0].quote_ref).toBe(q.quote_ref);
    expect(seen.posts[0].source_ref).toEqual(q.source_ref);
    expect((await overlay(request)).recovery.entries).toHaveLength(1);
    await expect(page.locator('#desk-recovery-source')).toHaveValue('');
    await expect(page.locator('#desk-recovery-amount')).toHaveValue('');
  });
});

for (const op of ['post_recovery', 'post_writeoff']) for (const delivered of [false, true]) test(`${op} lost response delivered=${delivered} keeps original identity across reload and resolves only via lookup`, async ({page, request}) => {
  await withServer('eligible', async () => {
    const seen = watch(page);
    await open(page);
    const view = await overlay(request);
    if (op === 'post_recovery') await fillRecovery(page, view);
    else await page.locator('#desk-recovery-decline').fill('SIMULATED_DECLINED');
    await page.locator('#desk-recovery-approval-b').check();
    await page.route('**/api/overlay/commands', async route => {
      if (delivered) expect((await route.fetch()).ok()).toBe(true);
      await route.abort();
    });
    await page.locator(op === 'post_recovery' ? '#desk-recovery-post' : '#desk-recovery-writeoff').click();
    await expect(page.locator('#notice')).toContainText('UNKNOWN');
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    const saved = await pending(page), original = JSON.parse(saved);
    expect(original).toEqual(seen.posts[0]);
    await page.reload();
    await expect(page.locator('#recover')).toBeEnabled();
    expect(await pending(page)).toBe(saved);
    for (const id of ['desk-recovery-post', 'desk-recovery-writeoff', 'desk-recovery-source', 'desk-recovery-amount', 'desk-recovery-approval-a', 'desk-recovery-decline', 'desk-advance']) await expect(page.locator(`#${id}`)).toBeDisabled();
    await page.locator('#desk-refresh').click();
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    expect(await pending(page)).toBe(saved);
    await page.locator('#recover').click();
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    if (delivered) {
      await expect(page.locator('#recovery')).toBeHidden();
      expect(await pending(page)).toBeNull();
      expect((await overlay(request)).recovery.entries).toHaveLength(1);
    } else {
      await expect(page.locator('#notice')).toContainText('UNKNOWN');
      expect(await pending(page)).toBe(saved);
      await expect(page.locator('#desk-recovery-post')).toBeDisabled();
      expect((await overlay(request)).recovery.entries).toHaveLength(0);
    }
    expect(seen.posts).toHaveLength(1);
    expect(seen.gets).toContain(`/api/overlay?operation_id=${original.operation_id}`);
    expect(seen.gets.some(url => url.startsWith('/api/operations/'))).toBe(false);
    expect(seen.errors).toEqual([]);
  });
});

test('auditor reads recovery data; observer initial, switch and pending reload send no protected requests', async ({page, request}) => {
  await withServer('eligible', async () => {
    const seen = watch(page);
    await open(page);
    const view = await overlay(request), q = sourceQuote(view);
    const saved = JSON.stringify({instance_id: view.instance_id, operation_id: 'observer-pending', op: 'post_recovery', advance_ref: 'sim-recovery', at_sim_day: view.sim_day, amount_krw: 1, source_ref: q.source_ref, quote_ref: q.quote_ref, approvals: []});
    await role(page, 'auditor');
    await compareFacts(page, view);
    await expect(page.locator('#desk-recovery-controls')).toBeHidden();
    await expect(page.locator('#desk-audit')).toBeVisible();
    await page.evaluate(({key, saved}) => {
      localStorage.setItem(key, saved);
      window.dispatchEvent(new StorageEvent('storage', {key}));
    }, {key: storageKey, saved});
    seen.gets.length = 0;
    await role(page, 'observer');
    await expect(page.locator('#desk-forbidden')).toBeVisible();
    await expect(page.locator('#recover')).toBeDisabled();
    await page.locator('#recover').click({force: true});
    await page.reload();
    await expect(page.locator('#role-status')).toContainText('observer');
    await expect(page.locator('#role')).toBeEnabled();
    await expect(page.locator('#recover')).toBeDisabled();
    expect(await pending(page)).toBe(saved);
    const protectedGets = seen.gets.filter(url => url.startsWith('/api/') && !url.startsWith('/api/state') && !url.startsWith('/api/readiness') && !url.startsWith('/api/scenarios'));
    expect(protectedGets).toEqual([]);
    expect(seen.posts).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

for (const scenario of ['unavailable', 'unanchored', 'no-sources']) test(`${scenario} clears stale controls and preserves unavailable values`, async ({page}) => {
  await withServer(scenario, async () => {
    const seen = watch(page);
    await open(page);
    if (scenario === 'no-sources') {
      await expect(page.locator('#desk-recovery-empty')).toContainText('견적 없음');
      await expect(page.locator('#desk-recovery-post')).toBeDisabled();
      await expect(page.locator('#desk-recovery-writeoff')).toBeEnabled();
    } else {
      await expect(page.locator('#desk-recovery-controls')).toBeHidden();
      await expect(page.locator('#desk-recovery-status')).toContainText(scenario === 'unavailable' ? 'NOT_BOUND' : 'DEFAULT_DAY_UNKNOWN');
      await expect(page.locator('#desk-recovery-source option')).toHaveCount(0);
    }
    expect(seen.posts).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});

test('missing, malformed and incompatible recovery snapshots clear drafted source, amount and labels', async ({page}) => {
  await withServer('normal', async () => {
    await open(page);
    for (const change of ['missing', 'malformed', 'incompatible', 'malformed-entry']) {
      await page.unroute('**/api/overlay');
      await page.locator('#desk-refresh').click();
      await expect(page.locator('#desk-refresh')).toBeEnabled();
      await page.locator('#desk-recovery-source').selectOption({index: 1});
      await page.locator('#desk-recovery-amount').fill('123');
      await page.locator('#desk-recovery-approval-a').check();
      await page.route('**/api/overlay', async route => {
        const response = await route.fetch(), body = await response.json();
        if (change === 'missing') delete body.recovery;
        if (change === 'malformed') body.recovery.advances[0].claim_krw = null;
        if (change === 'incompatible') body.recovery.advances[0].quotes[0].state_digest = 'old-cut';
        if (change === 'malformed-entry') body.recovery.entries = [null];
        await route.fulfill({response, json: body});
      });
      await page.locator('#desk-refresh').click();
      await expect(page.locator('#desk-refresh')).toBeEnabled();
      await expect(page.locator('#desk-recovery-status')).toContainText('unavailable or incompatible');
      await expect(page.locator('#desk-recovery-controls')).toBeHidden();
      await expect(page.locator('#desk-recovery-source option')).toHaveCount(0);
      await expect(page.locator('#desk-recovery-amount')).toHaveValue('');
      await expect(page.locator('#desk-recovery-approval-a')).not.toBeChecked();
    }
  });
});

for (const op of ['post_recovery', 'post_writeoff']) test(`${op} rejects malformed POST and mismatched lookup receipts without clearing UNKNOWN`, async ({page, request}) => {
  await withServer('eligible', async () => {
    const seen = watch(page);
    await open(page);
    if (op === 'post_recovery') await fillRecovery(page, await overlay(request));
    else await page.locator('#desk-recovery-decline').fill('SIMULATED_DECLINED');
    await page.locator('#desk-recovery-approval-a').check();
    await page.route('**/api/overlay/commands', async route => {
      const response = await route.fetch(), body = await response.json();
      body.actor = 'AUTHENTICATED';
      await route.fulfill({response, json: body});
    });
    await submit(page, op);
    await expect(page.locator('#notice')).toContainText('UNKNOWN');
    const saved = await pending(page);
    const mutations = [
      view => {view.instance_id = 'old-instance';},
      view => {view.operation = null;},
      view => {view.operation.operation_id = 'different-operation';},
      view => {view.operation.op = 'advance_day';},
      view => {view.operation.sim_day = 101;},
      view => {view.operation.entry.advance_id = 'different-advance';},
      view => {view.operation.entry.entry_kind = 'acceleration_event';},
      view => {view.operation.entry.entry_id = 'other-id';},
      view => {view.operation.entry.command.at_sim_day = 101;},
      view => {view.operation.entry.command.approvals = [{approver_label: 'sim-approver-b'}];},
      view => {view.operation.f04_journal_written = true;},
    ];
    if (op === 'post_recovery') mutations.push(
      view => {view.operation.entry.command.quote_ref = 'other-quote';},
      view => {view.operation.entry.command.source_ref.source_cut = 'other-cut';},
      view => {view.operation.entry.amount_krw = 999;},
    );
    else mutations.push(view => {view.operation.entry.command.setoff_declined_reason = 'DIFFERENT_REASON';});
    for (const mutate of mutations) {
      await page.route('**/api/overlay?operation_id=*', async route => {
        const response = await route.fetch(), body = await response.json();
        mutate(body);
        await route.fulfill({response, json: body});
      });
      await page.locator('#recover').click();
      await expect(page.locator('#recover')).toBeEnabled();
      await expect(page.locator('#notice')).toContainText('UNKNOWN');
      expect(await pending(page)).toBe(saved);
      await expect(page.locator('#desk-recovery-writeoff')).toBeDisabled();
      await page.unroute('**/api/overlay?operation_id=*');
    }
    await page.locator('#recover').click();
    await expect(page.locator('#recovery')).toBeHidden();
    expect(await pending(page)).toBeNull();
    expect(seen.posts).toHaveLength(1);
    expect(seen.errors).toEqual([]);
  });
});

test('amount syntax and changed case clear drafts without inventing allocation or approvals', async ({page, request}) => {
  await withServer('normal', async () => {
    const seen = watch(page);
    await open(page);
    const view = await overlay(request);
    await fillRecovery(page, view);
    for (const value of ['', '0', '-1', '1.5', '1e3', '9007199254740992']) {
      await page.locator('#desk-recovery-amount').fill(value);
      await page.locator('#desk-recovery-post').click();
      await expect(page.locator('#notice')).toContainText('안전한 정수');
    }
    const state = await getState();
    expect((await request.post(`${base}/api/commands`, {headers: {'X-Capital-Token': state.local_token}, data: {instance_id: state.instance_id, operation_id: 'other-case-offer', op: 'offer', advance_id: 'sim-other', args: {fixture_id: 'sim-pending', amount: 1000}}})).ok()).toBe(true);
    await page.locator('#desk-refresh').click();
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    await fillRecovery(page, view, '123');
    await page.locator('#desk-recovery-approval-a').check();
    await page.locator('#desk-case').selectOption('sim-other');
    await expect(page.locator('#desk-recovery')).toBeHidden();
    await page.locator('#desk-case').selectOption('sim-recovery');
    await expect(page.locator('#desk-recovery-source')).toHaveValue('');
    await expect(page.locator('#desk-recovery-amount')).toHaveValue('');
    await expect(page.locator('#desk-recovery-approval-a')).not.toBeChecked();
    expect(seen.posts).toEqual([]);
    expect(seen.errors).toEqual([]);
  });
});
