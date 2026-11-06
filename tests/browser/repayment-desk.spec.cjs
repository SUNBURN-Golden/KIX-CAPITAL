const {test, expect} = require('@playwright/test');
const {spawn, spawnSync} = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const root = path.resolve(__dirname, '../..');
const pendingKey = 'kix-capital-pending-v1';
const won = value => new Intl.NumberFormat('ko-KR').format(value);

async function withServer(port, run, day = 60) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-repayment-desk-'));
  const workspace = path.join(directory, 'workspace');
  const seeded = spawnSync('python3', ['-c', `
import sys
from capital.service import CapitalService
from capital.store import FileWorkspace
from tests.test_overlay import draw_book, tick
with FileWorkspace.open(sys.argv[1]) as storage:
    service = CapitalService(storage)
    draw_book(service)
    draw_book(service, advance='sim-b', amount=1000, prefix='b')
    day = int(sys.argv[2])
    if day:
        tick(service, 'seed-clock', 0, day)
`, workspace, String(day)], {cwd: root, encoding: 'utf8'});
  expect(seeded.status, seeded.stderr).toBe(0);
  const log = fs.openSync(path.join(directory, 'server.log'), 'a');
  const child = spawn('python3', ['-m', 'capital.server', '--port', String(port), '--workspace', workspace], {cwd: root, stdio: ['ignore', log, log]});
  fs.closeSync(log);
  const base = `http://127.0.0.1:${port}`;
  try {
    let ready = false;
    for (let attempt = 0; attempt < 150; attempt++) {
      try { const response = await fetch(`${base}/api/state`); ready = response.ok; } catch {}
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve, 40));
    }
    expect(ready, fs.readFileSync(path.join(directory, 'server.log'), 'utf8')).toBe(true);
    return await run(base);
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      await new Promise(resolve => { child.once('exit', resolve); child.kill('SIGKILL'); });
    }
    fs.rmSync(directory, {recursive: true, force: true});
  }
}
async function json(request, base, route) { const response = await request.get(base + route); expect(response.ok()).toBe(true); return response.json(); }
async function open(page, base) {
  await page.goto(`${base}/?case=sim-a#desk`);
  await expect(page.locator('#desk-payment-amount')).toBeVisible();
  await expect(page.locator('#desk-refresh')).toBeEnabled();
  await expect(page.locator('#desk-payment-amount')).toBeEnabled();
}
function watch(page) {
  const seen = {posts: [], errors: []};
  page.on('request', request => { if (request.method() === 'POST' && request.url().endsWith('/api/overlay/commands')) seen.posts.push(request.postDataJSON()); });
  page.on('pageerror', error => seen.errors.push(String(error)));
  return seen;
}
async function preview(page, amount, evidence = '') {
  await page.locator('#desk-payment-amount').fill(String(amount));
  await page.locator('#desk-payment-evidence').fill(evidence);
  await page.locator('#desk-payment-preview').click();
  await expect(page.locator('#desk-payment-post')).toBeEnabled();
}
async function finishDelayedPreview(page, release) {
  const finished = page.waitForEvent('requestfinished', {predicate: request => request.url().includes('/api/terms/sim-a/allocation?')});
  release();await finished;
  await page.unroute('**/api/terms/sim-a/allocation?*');
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(resolve)));
}
async function post(page) {
  const response = page.waitForResponse(r => r.url().endsWith('/api/overlay/commands'));
  await page.locator('#desk-payment-post').click();
  const receipt = await (await response).json();
  await expect(page.locator('#desk-payment-receipt-note')).toContainText(`entry_no=${receipt.entry_no}`);
  await expect(page.locator('#desk-refresh')).toBeEnabled();
  return receipt;
}
async function receiptMatches(page, receipt) {
  const cells = await page.locator('#desk-payment-records tr').last().locator('td').allTextContents();
  expect(cells.slice(1, 5)).toEqual([receipt.amount_krw, receipt.allocation.default_interest_krw, receipt.allocation.interest_krw, receipt.allocation.principal_krw].map(String));
  expect(cells[5]).toContain(`${receipt.unapplied_before_krw} → ${receipt.unapplied_after_krw}`);
  await expect(page.locator('#desk-payment-receipt-note')).toContainText(`close_gate=${receipt.close_gate.status}`);
  expect(JSON.parse(await page.locator('#desk-payment-receipt').textContent())).toEqual(receipt);
}

test('interest-only, later quote divergence, partial principal, and excess show server records', async ({page, request}) => {
  await withServer(8950, async base => {
    const seen = watch(page);
    await open(page, base);
    const before = await json(request, base, '/api/state');
    const overlay = await json(request, base, '/api/overlay');
    const row = overlay.advances[0];
    await preview(page, row.interest_due_krw, 'sim-repayment-001');
    expect(seen.posts).toEqual([]);
    await expect(page.locator('#desk-payment-quote-rows td').nth(1)).toHaveText(won(row.interest_due_krw));
    const interest = await post(page);
    expect(interest.f04).toBeNull();
    expect((await json(request, base, '/api/state')).state_digest).toBe(before.state_digest);
    await receiptMatches(page, interest);
    await expect(page.locator('#desk-timeline-rows')).toContainText(interest.operation_id);
    // The unchanged hypothetical API quotes interest again. The ledger does not.
    await preview(page, 4000);
    await expect(page.locator('#desk-payment-quote-rows td').nth(1)).toHaveText(won(row.interest_due_krw));
    const partial = await post(page);
    expect(partial.allocation.interest_krw).toBe(0);
    expect(partial.allocation.principal_krw).toBe(4000);
    expect(partial.f04).not.toBeNull();
    await receiptMatches(page, partial);
    await preview(page, row.principal_outstanding_krw);
    const excess = await post(page);
    expect(excess.unapplied_after_krw).toBeGreaterThan(0);
    expect(excess.close_gate.status).toBe('UNAPPLIED_HELD');
    await receiptMatches(page, excess);
    await expect(page.locator('#desk-payment-records')).toContainText('SIM_UNAPPLIED_MEMO');
    expect((await json(request, base, '/api/state')).cases[0].phase).toBe('DRAWN');
    expect(seen.posts).toHaveLength(3);
    expect(Object.keys(seen.posts[0]).sort()).toEqual(['advance_ref','amount_krw','at_sim_day','evidence_ref','instance_id','op','operation_id'].sort());
    expect(seen.errors).toEqual([]);
  });
});

test('default interest, keyboard submission, mobile layout and auditor records', async ({page, request}) => {
  await withServer(8951, async base => {
    const seen = watch(page);
    await page.setViewportSize({width: 1280, height: 900});
    await open(page, base);
    const row = (await json(request, base, '/api/overlay')).advances[0];
    expect(row.default_interest_due_krw).toBeGreaterThan(0);
    await preview(page, row.default_interest_due_krw, 'sim:default');
    await expect(page.locator('#desk-payment-quote-rows td').first()).toHaveText(won(row.default_interest_due_krw));
    await page.locator('#desk-payment-post').focus();
    const response = page.waitForResponse(r => r.url().endsWith('/api/overlay/commands'));
    await page.keyboard.press('Enter');
    const receipt = await (await response).json();
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    await receiptMatches(page, receipt);
    expect(receipt.allocation.default_interest_krw).toBe(row.default_interest_due_krw);
    expect(receipt.close_gate.status).toBe('INTEREST_DUE');
    fs.mkdirSync(path.join(root, 'test-results/repayment-desk'), {recursive: true});
    await page.screenshot({path: path.join(root, 'test-results/repayment-desk/desktop.png'), fullPage: true});
    await page.setViewportSize({width: 375, height: 800});
    await page.locator('#desk-payment-records').scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path: path.join(root, 'test-results/repayment-desk/mobile.png'), fullPage: true});
    await page.locator('#role').selectOption('auditor');
    await expect(page.locator('#role-status')).toContainText('auditor');
    await expect(page.locator('#desk-payment-controls')).toBeHidden();
    await expect(page.locator('#desk-payment-records')).toContainText('sim:default');
    expect(seen.posts).toHaveLength(1);
    expect(seen.errors).toEqual([]);
  }, 75);
});

for (const delivered of [false, true]) test(`lost repayment response, delivered=${delivered}: identity survives reload; explicit lookup never retries`, async ({page, request}) => {
  await withServer(delivered ? 8952 : 8953, async base => {
    const seen = watch(page);
    await open(page, base);
    await preview(page, 5000, 'sim:lost');
    await page.route('**/api/overlay/commands', async route => { if (delivered) await route.fetch(); await route.abort('failed'); });
    await page.locator('#desk-payment-post').click();
    await expect(page.locator('#notice')).toContainText('UNKNOWN');
    const original = await page.evaluate(key => JSON.parse(localStorage.getItem(key)), pendingKey);
    expect(original).toEqual(seen.posts[0]);
    await page.reload();
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    await expect(page.locator('#desk-payment-post')).toBeDisabled();
    await expect(page.locator('#desk-advance')).toBeDisabled();
    await page.locator('#desk-refresh').click();
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)), pendingKey)).toEqual(original);
    await page.locator('#recover').click();
    if (delivered) {
      await expect(page.locator('#recovery')).toBeHidden();
      await expect(page.locator('#desk-payment-receipt-note')).toContainText('entry_no=');
      const lookup = await json(request, base, `/api/overlay?operation_id=${original.operation_id}`);
      expect(JSON.parse(await page.locator('#desk-payment-receipt').textContent())).toEqual(lookup.operation);
    } else {
      await expect(page.locator('#notice')).toContainText('UNKNOWN');
      await expect(page.locator('#recovery')).toBeVisible();
      expect(await page.evaluate(key => JSON.parse(localStorage.getItem(key)), pendingKey)).toEqual(original);
    }
    expect(seen.posts).toHaveLength(1);
  });
});

test('invalid lookup identity or recorded data retains UNKNOWN until valid explicit lookup', async ({page}) => {
  await withServer(8954, async base => {
    const seen = watch(page);
    await open(page, base);await preview(page, 5000);
    await page.route('**/api/overlay/commands', async route => { await route.fetch(); await route.abort(); });
    await page.locator('#desk-payment-post').click();
    await expect(page.locator('#notice')).toContainText('UNKNOWN');
    for (const mutate of [b => {b.instance_id='other';}, b => {b.operation.amount_krw++;}, b => {b.operation.evidence_ref='other';}, b => {b.operation.allocation.principal_krw='bad';}]) {
      await page.route('**/api/overlay?operation_id=*', async route => { const response = await route.fetch(); const body = await response.json();mutate(body);await route.fulfill({response,json:body}); });
      await page.locator('#recover').click();
      await expect(page.locator('#recover')).toBeEnabled();
      await expect(page.locator('#recovery')).toBeVisible();
      await page.unroute('**/api/overlay?operation_id=*');
    }
    await page.locator('#recover').click();await expect(page.locator('#recovery')).toBeHidden();
    expect(seen.posts).toHaveLength(1);
  });
});

for (const code of ['SIM_CLOCK_STALE', 'SESSION_CHANGED']) test(`${code} requires refresh and a new explicit preview`, async ({page}) => {
  await withServer(code === 'SIM_CLOCK_STALE' ? 8955 : 8956, async base => {
    const seen = watch(page);
    await open(page, base);await preview(page, 5000, 'sim:stale');
    await page.route('**/api/overlay/commands', route => route.fulfill({status:409,json:{error:code}}));
    await page.locator('#desk-payment-post').click();
    await expect(page.locator('#notice')).toContainText(code === 'SESSION_CHANGED' ? code : 'sim_day');
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    await expect(page.locator('#desk-payment-post')).toBeDisabled();
    await expect(page.locator('#desk-payment-amount')).toHaveValue('5000');
    await expect(page.locator('#desk-payment-evidence')).toHaveValue('sim:stale');
    expect(await page.evaluate(key => localStorage.getItem(key), pendingKey)).toBeNull();
    await page.unroute('**/api/overlay/commands');
    await page.locator('#desk-payment-preview').click();
    await expect(page.locator('#desk-payment-post')).toBeEnabled();
    await post(page);expect(seen.posts).toHaveLength(2);
  });
});

test('invalid, NOT_BOUND and delayed previews never authorize changed drafts; unrelated hypothetical days are ignored', async ({page}) => {
  await withServer(8957, async base => {
    await open(page, base);
    await page.locator('#desk-payment-amount').fill('5000');
    await page.locator('#desk-payment-evidence').fill('<img onerror=x>');
    await expect(page.locator('#desk-payment-preview')).toBeDisabled();
    await page.locator('#desk-payment-evidence').fill('sim:valid');
    for (const mutate of [b => {b.status='NOT_BOUND';}, b => {b.allocation.to_principal='5000';}, b => {b.observed_state_digest='wrong';}, b => {b.funds_executed=true;}]) {
      await page.route('**/api/terms/sim-a/allocation?*', async route => {const response=await route.fetch();const body=await response.json();mutate(body);await route.fulfill({response,json:body});});
      await page.locator('#desk-payment-preview').click();
      await expect(page.locator('#desk-payment-status')).toContainText('응답을 확인하지');
      await expect(page.locator('#desk-payment-post')).toBeDisabled();
      await page.unroute('**/api/terms/sim-a/allocation?*');
    }
    let release;const gate=new Promise(resolve=>{release=resolve;});
    await page.route('**/api/terms/sim-a/allocation?*', async route=>{await gate;await route.continue();});
    await page.locator('#desk-payment-preview').click();
    await page.locator('#desk-payment-amount').fill('6000');
    await finishDelayedPreview(page, release);
    await expect(page.locator('#desk-payment-post')).toBeDisabled();
    await page.locator('#terms-draw-day').evaluate(el=>{el.value='999';});
    const response=page.waitForResponse(r=>r.url().includes('/api/terms/sim-a/allocation?'));
    await page.locator('#desk-payment-preview').click();
    const url=new URL((await response).url());
    expect(url.searchParams.get('draw_day')).toBe('0');expect(url.searchParams.get('as_of_day')).toBe('60');
    await expect(page.locator('#desk-payment-post')).toBeEnabled();
    await page.locator('#desk-refresh').click();await expect(page.locator('#desk-refresh')).toBeEnabled();
    await expect(page.locator('#desk-payment-post')).toBeDisabled();
    await expect(page.locator('#desk-payment-amount')).toHaveValue('6000');
  });
});

test('first clock binding prerequisite is explained without automatically advancing', async ({page}) => {
  await withServer(8958, async base => {
    const seen=watch(page);await open(page,base);
    await page.locator('#desk-payment-amount').fill('5000');
    await expect(page.locator('#desk-payment-status')).toContainText('REPAYMENT_TERMS_NOT_BOUND');
    await expect(page.locator('#desk-payment-preview')).toBeDisabled();expect(seen.posts).toEqual([]);
    await page.locator('#desk-advance').click();await expect(page.locator('#desk-refresh')).toBeEnabled();
    await page.locator('#desk-payment-preview').click();await expect(page.locator('#desk-payment-post')).toBeEnabled();
  },0);
});

test('shared writer lock, double activation, and storage events prevent competing submissions', async ({page, context}) => {
  await withServer(8959, async base => {
    const seen=watch(page);await open(page,base);await preview(page,5000);
    const other=await context.newPage();await open(other,base);await preview(other,6000);
    let release;const gate=new Promise(resolve=>{release=resolve;});
    await page.route('**/api/overlay/commands',async route=>{await gate;await route.continue();});
    await page.locator('#desk-payment-post').evaluate(el=>{el.click();el.click();});
    await expect(page.locator('#desk-payment-post')).toBeDisabled();
    await expect(other.locator('#desk-payment-post')).toBeDisabled();
    await expect(other.locator('#desk-advance')).toBeDisabled();
    release();await expect(page.locator('#desk-refresh')).toBeEnabled();
    expect(seen.posts).toHaveLength(1);
    // Hold the same lock without a pending record: another tab must still be excluded.
    await other.locator('#desk-refresh').click();await expect(other.locator('#desk-refresh')).toBeEnabled();
    await preview(other,6000);
    await page.evaluate(()=>{window.testLock=navigator.locks.request('kix-capital-writer',()=>new Promise(resolve=>{window.releaseTestLock=resolve;}));});
    await other.locator('#desk-payment-post').click();
    await expect(other.locator('#notice')).toContainText('다른 탭');
    await page.evaluate(()=>window.releaseTestLock());await other.close();
  });
});

test('observer makes no repayment reads and observer/auditor/agent tokens cannot post', async ({page, request}) => {
  await withServer(8960, async base => {
    await page.addInitScript(()=>sessionStorage.setItem('kix-capital-role','observer'));
    const seen=watch(page),reads=[];page.on('request',r=>{if(r.method()==='GET')reads.push(new URL(r.url()).pathname);});
    await page.goto(`${base}/?case=sim-a#desk`);await expect(page.locator('#desk-forbidden')).toBeVisible();
    expect(reads).not.toContain('/api/overlay');expect(reads).not.toContain('/api/terms/sim-a/allocation');
    await expect(page.locator('#desk-payment-controls')).toBeHidden();
    const state=await json(request,base,'/api/state');
    for(const role of ['observer','auditor','agent']){
      const session=await request.post(base+'/api/session',{headers:{'X-Capital-Token':state.local_token},data:{role}});expect(session.ok()).toBe(true);
      const token=(await session.json()).local_token;
      const response=await request.post(base+'/api/overlay/commands',{headers:{'X-Capital-Token':token},data:{instance_id:state.instance_id,operation_id:'denied-'+role,op:'post_repayment',advance_ref:'sim-a',at_sim_day:60,amount_krw:5000}});
      expect(response.status()).toBe(403);expect((await response.json()).error).toBe('ROLE_FORBIDDEN');
    }
    expect(seen.posts).toEqual([]);expect(seen.errors).toEqual([]);
  });
});

test('hostile recorded evidence renders literally as text', async ({page}) => {
  await withServer(8961, async base => {
    const hostile='<img src=x onerror="window.hostileExecuted=true">';
    await page.route('**/api/export/manifest',async route=>{
      const response=await route.fetch(),body=await response.json();
      body.sections.overlay.body.journal.push({overlay_id:'hostile-record',kind:'repayment',sim_day:60,after_journal_index:4,payload:{advance_ref:'sim-a',amount_krw:1,unapplied_before_krw:0,allocation:{default_interest_krw:0,interest_krw:1,principal_krw:0,unapplied_after_krw:0},evidence_ref:hostile}});
      await route.fulfill({response,json:body});
    });
    await open(page,base);await expect(page.locator('#desk-payment-records')).toContainText(hostile);
    expect(await page.locator('#desk-payment-records img').count()).toBe(0);
    expect(await page.evaluate(()=>window.hostileExecuted)).toBeUndefined();
  });
});

test('malformed POST receipt retains command; valid lookup resolves it without a second POST', async ({page}) => {
  await withServer(8962, async base => {
    const seen=watch(page);await open(page,base);await preview(page,5000,'sim:malformed');
    await page.route('**/api/overlay/commands',async route=>{const response=await route.fetch(),body=await response.json();body.allocation.interest_krw='invalid';await route.fulfill({response,json:body});});
    await page.locator('#desk-payment-post').click();await expect(page.locator('#notice')).toContainText('UNKNOWN');
    const original=await page.evaluate(key=>JSON.parse(localStorage.getItem(key)),pendingKey);
    expect(original).toEqual(seen.posts[0]);await expect(page.locator('#desk-payment-post')).toBeDisabled();
    await page.locator('#recover').click();await expect(page.locator('#recovery')).toBeHidden();expect(seen.posts).toHaveLength(1);
  });
});

test('stale rejection with failed refresh stays blocked until successful refresh and preview', async ({page}) => {
  await withServer(8963,async base=>{
    await open(page,base);await preview(page,5000);
    await page.route('**/api/overlay/commands',route=>route.fulfill({status:409,json:{error:'SIM_CLOCK_STALE'}}));
    await page.route('**/api/state',route=>route.abort('failed'));
    await page.locator('#desk-payment-post').click();await expect(page.locator('#notice')).toContainText('현재 상태를 조회하지');
    await expect(page.locator('#desk-payment-post')).toBeDisabled();await expect(page.locator('#desk-payment-preview')).toBeDisabled();
    await page.unroute('**/api/state');await page.locator('#desk-refresh').click();await expect(page.locator('#desk-refresh')).toBeEnabled();
    await expect(page.locator('#desk-payment-post')).toBeDisabled();await page.locator('#desk-payment-preview').click();await expect(page.locator('#desk-payment-post')).toBeEnabled();
  });
});

test('a delayed preview cannot cross cases or role changes', async ({page}) => {
  await withServer(8964,async base=>{
    await open(page,base);let release;const gate=new Promise(resolve=>{release=resolve;});
    await page.route('**/api/terms/sim-a/allocation?*',async route=>{await gate;await route.continue();});
    await page.locator('#desk-payment-amount').fill('5000');await page.locator('#desk-payment-preview').click();
    await page.locator('#desk-case').selectOption('sim-b');
    await expect(page.locator('#desk-payment-amount')).toHaveValue('');
    await page.locator('#desk-case').selectOption('sim-a');
    await expect(page.locator('#desk-payment-amount')).toHaveValue('5000');
    await page.locator('#role').selectOption('auditor');await expect(page.locator('#role-status')).toContainText('auditor');
    await finishDelayedPreview(page, release);
    await expect(page.locator('#desk-payment-controls')).toBeHidden();await expect(page.locator('#desk-payment-quote')).toBeHidden();
    await page.locator('#role').selectOption('organizer');await expect(page.locator('#desk-payment-amount')).toBeEnabled();
    await expect(page.locator('#desk-payment-amount')).toHaveValue('5000');await expect(page.locator('#desk-payment-post')).toBeDisabled();
  });
});
