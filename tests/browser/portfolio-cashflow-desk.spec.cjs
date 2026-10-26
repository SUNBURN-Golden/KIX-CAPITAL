const {test, expect} = require('@playwright/test');
const {spawn, spawnSync} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

// Local SIMULATED fixture server, always stopped, never a provider connection.
async function withDesk(page, run) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'capital-cashflow-'));
  const workspace = path.join(directory, 'workspace');
  const seed = spawnSync('python3', ['scripts/seed_demo.py', '--workspace', workspace], {encoding:'utf8'});
  expect(seed.status, seed.stderr).toBe(0);
  const child = spawn('python3', ['-m', 'capital.server', '--port', '8955', '--workspace', workspace], {stdio:'ignore'});
  const base = 'http://127.0.0.1:8955';
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  try {
    await expect(async () => expect((await page.request.get(base+'/api/state')).ok()).toBeTruthy()).toPass({timeout:8000});
    await run(base);
    expect(errors).toEqual([]);
  } finally {
    if (child.exitCode === null && child.signalCode === null) {
      const stopped = new Promise(resolve => child.once('exit', resolve));
      child.kill('SIGTERM');
      await stopped;
    }
    fs.rmSync(directory, {recursive:true, force:true});
  }
}
const snapshot = async (page, base) => {
  const state = await (await page.request.get(base+'/api/state')).json();
  return (await page.request.get(base+'/api/portfolio/snapshot?instance_id='+state.instance_id)).json();
};
const gate = () => {let release;const waiting = new Promise((resolve,reject) => {const timer=setTimeout(()=>reject(Error('cashflow response gate timed out')),6000);release=()=>{clearTimeout(timer);resolve();};});return {waiting, release};};
async function clock(page, base, day) {
  const state = await (await page.request.get(base+'/api/state')).json();
  const overlay = await (await page.request.get(base+'/api/overlay')).json();
  const response = await page.request.post(base+'/api/overlay/commands', {
    headers:{'X-Capital-Token':state.local_token},data:{instance_id:state.instance_id,
      operation_id:'cashflow-browser-'+day,op:'advance_day',from_sim_day:overlay.sim_day,
      to_sim_day:day,reason:'SIMULATED browser clock'},
  });
  expect(response.ok()).toBeTruthy();
}

test('snapshot parity, separate exact streams, case navigation, keyboard and 375px', async ({page}) => {
  await withDesk(page, async base => {
    const gets = [];
    page.on('request', request => {if(request.method()==='GET')gets.push(new URL(request.url()).pathname);});
    await page.goto(base+'/?case=sim-unbound#desk');
    const body = await snapshot(page,base);
    await expect(page.locator('#desk-cash-cut')).toContainText(body.snapshot_digest);
    await expect(page.locator('#desk-cash-cut')).toContainText('sim_day '+body.cut.sim_day);
    await expect(page.locator('#desk-cash-assumptions')).toHaveText('snapshot assumptions='+JSON.stringify(body.assumptions)+' · forecast assumptions='+JSON.stringify(body.forecast.assumptions));
    await expect(page.locator('[data-bucket]')).toHaveCount(5);
    for (const advance of body.forecast.advances) {
      if (advance.status==='NOT_APPLICABLE') {
        await expect(page.locator('#desk-cash-inapplicable')).toContainText(advance.advance_id+' · '+advance.phase+' · NOT_APPLICABLE · '+advance.reason);
        continue;
      }
      for (const leg of advance.legs) {
        const region = leg.bucket===null ? '#desk-cash-unscheduled' : `[data-bucket="${leg.bucket}"]`;
        const row = page.locator(`${region} tr[data-advance="${advance.advance_id}"][data-stream="${leg.kind}"]`);
        await expect(row).toContainText(leg.exact+' KRW (exact fraction)');
        await expect(row).toContainText(leg.status);
        await expect(row).toContainText(leg.assumption);
      }
    }
    await expect(page.locator('#desk-cash-reserve')).toContainText('coverage=NOT_BOUND');
    expect(gets).toContain('/api/portfolio/snapshot');
    expect(gets).not.toContain('/api/risk');
    expect(gets).not.toContain('/api/risk/covenants');
    expect(gets).not.toContain('/api/terms/portfolio/forecast');
    const advance = body.forecast.advances.find(row=>row.status==='BOUND');
    const link = page.locator(`#desk-cash-buckets a`).filter({hasText:advance.advance_id}).first();
    await link.focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(new RegExp('case='+advance.advance_id+'#desk'));
    await expect(page.locator('#desk-cash-detail')).toBeFocused();
    await expect(page.locator('#desk-cash-detail-body')).toContainText(`tier=${advance.tier} · draw_day=${advance.draw_day} · maturity_day=${advance.maturity_day} · principal_krw=${advance.principal_krw}`);
    await clock(page,base,advance.maturity_day+1);
    await page.locator('#desk-refresh').click();
    const later = await snapshot(page,base);
    await expect(page.locator('#desk-cash-cut')).toContainText(later.snapshot_digest);
    const laterAdvance = later.forecast.advances.find(row=>row.advance_id===advance.advance_id);
    for(const leg of laterAdvance.legs.filter(leg=>leg.kind!=='SETTLEMENT_CASH_IN')) {
      expect(leg.bucket).toBe('0-7');
      await expect(page.locator(`[data-bucket="0-7"] tr[data-advance="${advance.advance_id}"][data-stream="${leg.kind}"]`)).toContainText(leg.exact+' KRW (exact fraction)');
    }
    const covenant = later.covenants.watch_list.find(row=>row.advance_id===advance.advance_id);
    expect(covenant.reasons.some(reason=>reason.code==='PAST_MATURITY')).toBe(true);
    await page.locator('#desk-cash-watch a').filter({hasText:advance.advance_id}).click();
    for(const reason of covenant.reasons) {
      await expect(page.locator('#desk-cash-detail-body')).toContainText(`${reason.code} · ${reason.severity} · ${reason.detail}`);
    }
    await page.setViewportSize({width:375,height:800});
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await expect(page.locator('#desk-cash-buckets')).toHaveAccessibleName('현금 사다리 버킷');
    await page.locator('#role').selectOption('auditor');
    await expect(page.locator('#role-status')).toContainText('auditor');
    await expect(page.locator('#desk-cash-cut')).toContainText(later.snapshot_digest);
    await expect(page.locator('#desk-commands')).toBeHidden();
    const count = gets.filter(url=>url==='/api/portfolio/snapshot').length;
    await page.locator('#role').selectOption('observer');
    await expect(page.locator('#desk-forbidden')).toBeVisible();
    expect(gets.filter(url=>url==='/api/portfolio/snapshot').length).toBe(count);
  });
});

test('incomplete, unbound, malformed and mismatched cuts clear all old forecast numbers', async ({page}) => {
  await withDesk(page, async base => {
    await page.goto(base+'/#desk');
    await expect(page.locator('#desk-cash-buckets tr[data-advance]').first()).toBeVisible();
    const valid = await snapshot(page,base);
    const variants = [
      body=>{body.complete=false;body.status='INCOMPLETE';body.forecast=null;body.completeness.reasons=['TERMS_NOT_BOUND'];body.completeness.sections.forecast='UNAVAILABLE';},
      body=>{body.forecast={status:'NOT_BOUND',reason:'TERMS_NOT_BOUND'};},
      body=>{body.forecast.advances.find(row=>row.status==='BOUND').legs[0].exact='invalid';},
      body=>{body.cut.state_digest='0'.repeat(64);},
      body=>{body.covenants.sim_day+=1;},
    ];
    for (const mutate of variants) {
      const body=JSON.parse(JSON.stringify(valid));mutate(body);
      await page.route('**/api/portfolio/snapshot?**', route=>route.fulfill({json:body}));
      await page.locator('#desk-refresh').click();
      await expect(page.locator('#desk-cash-status')).toContainText('INCOMPLETE');
      await expect(page.locator('#desk-cash-buckets tr[data-advance]')).toHaveCount(0);
      await expect(page.locator('#desk-cash-unscheduled tr')).toHaveCount(0);
      await expect(page.locator('#desk-cash-detail-body')).toBeEmpty();
      await expect(page.locator('#desk-tiles')).toBeEmpty();
      await expect(page.locator('#desk-overlay-rows')).toBeEmpty();
      await expect(page.locator('#desk-actions')).toBeEmpty();
      await page.unroute('**/api/portfolio/snapshot?**');
    }
    await page.locator('#desk-refresh').click();
    await expect(page.locator('#desk-cash-cut')).toContainText(valid.snapshot_digest);
    await expect(page.locator('#desk-cash-buckets tr[data-advance]').first()).toBeVisible();
    await page.route('**/api/overlay', async route=>{const response=await route.fetch();const body=await response.json();body.sim_day+=1;await route.fulfill({json:body});});
    await page.locator('#desk-refresh').click();
    await expect(page.locator('#desk-clock')).toContainText('overlay cut does not match');
    await expect(page.locator('#desk-overlay-rows')).toBeEmpty();
    await expect(page.locator('#desk-cash-cut')).toContainText(valid.snapshot_digest);
  });
});

for (const after of [false,true]) for (const fail of [false,true]) test(`older ${fail?'failed':'successful'} refresh released ${after?'after':'before'} newer cut cannot replace or unlock it`, async ({page}) => {
  await withDesk(page, async base => {
    await page.goto(base+'/#desk');
    await expect(page.locator('#desk-cash-status')).toBeVisible();
    await expect(page.locator('#desk-cash-status')).toHaveText('SIMULATED · COMPLETE · advisory only · enforced=false');
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    const old=gate(),newer=gate(),arrived=gate(),nextArrived=gate();let count=0;
    await page.route('**/api/portfolio/snapshot?**', async route=>{
      const response=await route.fetch();
      count++;
      if(count===1){arrived.release();await old.waiting;if(fail){await route.fulfill({status:503,json:{error:'DELAYED_FAILURE'}});return;}}
      else if(count===2){nextArrived.release();await newer.waiting;}
      await route.fulfill({response});
    });
    await page.evaluate(()=>{window.oldRefresh=document.querySelector('#desk-refresh').onclick();});await arrived.waiting;
    await clock(page,base,1);
    // Re-selecting the current role starts the existing session/refresh flow.
    await page.evaluate(()=>document.querySelector('#role').dispatchEvent(new Event('change')));
    await nextArrived.waiting;
    if(!after){
      old.release();await page.evaluate(()=>window.oldRefresh);
      await expect(page.locator('#desk-refresh')).toBeDisabled();
    }
    newer.release();
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    const current=await snapshot(page,base);
    await expect(page.locator('#desk-cash-cut')).toContainText(current.snapshot_digest);
    await expect(page.locator('#desk-cash-cut')).toContainText('sim_day 1');
    await expect(page.locator('#desk-cash-assumptions')).toContainText(JSON.stringify(current.forecast.assumptions));
    if(after){old.release();await page.evaluate(()=>window.oldRefresh);}
    await expect(page.locator('#desk-cash-cut')).toContainText(current.snapshot_digest);
    await expect(page.locator('#desk-cash-assumptions')).toContainText(JSON.stringify(current.forecast.assumptions));
    await expect(page.locator('#desk-cash-status')).not.toContainText('unavailable');
  });
});

for (const fail of [false,true]) test(`old session ${fail?'failure':'success'} and desk exit are discarded`, async ({page}) => {
  await withDesk(page, async base => {
    await page.goto(base+'/#desk');
    await expect(page.locator('#desk-cash-status')).toBeVisible();
    await expect(page.locator('#desk-cash-status')).toHaveText('SIMULATED · COMPLETE · advisory only · enforced=false');
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    const hold=gate(),arrived=gate();let first=true;
    await page.route('**/api/portfolio/snapshot?**', async route=>{
      const response=await route.fetch();
      if(first){first=false;arrived.release();await hold.waiting;if(fail){await route.fulfill({status:503,json:{error:'OLD_SESSION'}});return;}}
      await route.fulfill({response});
    });
    await page.evaluate(()=>{window.oldRefresh=document.querySelector('#desk-refresh').onclick();});await arrived.waiting;
    await page.evaluate(()=>{document.querySelector('#role').value='observer';document.querySelector('#role').dispatchEvent(new Event('change'));});
    await expect(page.locator('#desk-forbidden')).toBeVisible();
    hold.release();await page.evaluate(()=>window.oldRefresh);
    await expect(page.locator('#desk-forbidden')).toBeVisible();
    await expect(page.locator('#role-status')).toContainText('observer');
    await expect(page.locator('#role')).toHaveValue('observer');
    await page.locator('#role').selectOption('organizer');
    await expect(page.locator('#desk-cash-status')).toBeVisible();
    await expect(page.locator('#desk-cash-status')).toHaveText('SIMULATED · COMPLETE · advisory only · enforced=false');
    await expect(page.locator('#desk-refresh')).toBeEnabled();
    const exitHold=gate(),exitArrived=gate();
    await page.unroute('**/api/portfolio/snapshot?**');
    await page.route('**/api/portfolio/snapshot?**', async route=>{const response=await route.fetch();exitArrived.release();await exitHold.waiting;await route.fulfill({response});});
    await page.evaluate(()=>{window.exitRefresh=document.querySelector('#desk-refresh').onclick();});await exitArrived.waiting;
    await page.locator('nav a[href="#overview"]').click();
    exitHold.release();await page.evaluate(()=>window.exitRefresh);
    await expect(page.locator('#desk')).toBeHidden();
    await expect(page.locator('#notice')).not.toContainText('조회에 실패');
    await page.unroute('**/api/portfolio/snapshot?**');
    await page.locator('nav a[href="#desk"]').click();
    await expect(page.locator('#desk-cash-status')).toBeVisible();
    await expect(page.locator('#desk-cash-status')).toHaveText('SIMULATED · COMPLETE · advisory only · enforced=false');
    await expect(page.locator('#desk-refresh')).toBeEnabled();
  });
});
