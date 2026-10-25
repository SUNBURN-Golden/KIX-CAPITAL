const {test, expect} = require('@playwright/test');
const {spawn, spawnSync} = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const root = path.resolve(__dirname, '../..');
let child, directory;
const base = 'http://127.0.0.1:8941';
test.beforeEach(async ({request}) => {
 directory = fs.mkdtempSync(path.join(os.tmpdir(), 'capital-audit-'));
 const workspace = path.join(directory, 'workspace');
 const seeded = spawnSync('python3', ['scripts/seed_demo.py', '--workspace', workspace], {cwd:root, encoding:'utf8'});
 expect(seeded.status, seeded.stderr).toBe(0);
 child = spawn('python3', ['-m','capital.server','--port','8941','--workspace',workspace], {cwd:root, stdio:'ignore'});
 await expect.poll(async () => {try{return (await request.get(base+'/api/state')).status();}catch{return 0;}}).toBe(200);
});
test.afterEach(async () => {
 if(child && child.exitCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGTERM');await exited;}
 fs.rmSync(directory,{recursive:true,force:true});
});
async function auditor(page){
 await page.addInitScript(()=>{if(!sessionStorage.getItem('kix-capital-role'))sessionStorage.setItem('kix-capital-role','auditor');});
 await page.goto(base+'/?case=sim-unbound#desk');
 await expect(page.locator('#desk-audit-content')).toBeVisible();
 await expect(page.locator('#role')).toBeEnabled();
}
for(const width of [1280,375])test(`auditor evidence associations and GET-only interactions at ${width}px`,async({page,request})=>{
 await page.setViewportSize({width,height:900});
 const errors=[];page.on('pageerror',error=>errors.push(String(error)));
 await auditor(page);
 const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(r.url());});
 const manifest=await (await page.request.get(base+'/api/export/manifest')).json();
 const report=await (await page.request.get(base+'/api/reconciliation')).json();
 const rows=await page.locator('#desk-audit-chain tr').allTextContents();
 const entries=manifest.sections.journal.body.entries;
 for(const [index,entry] of entries.entries())if(entry.advance_id==='sim-unbound'){
  expect(rows.some(row=>row.includes('#'+index)&&row.includes(entry.idempotency_key)&&row.includes(JSON.stringify(manifest.sections.receipts.body.receipts[entry.idempotency_key].receipt)))).toBe(true);
 }
 for(const [index,check] of report.checks.entries())await expect(page.locator('#desk-audit-checks tr').nth(index)).toHaveText(check.id+check.status+(check.detail??'—'));
 await expect(page.locator('#desk-audit-checks tr')).toHaveCount(report.checks.length);
 const journalKeys=new Set(entries.map(row=>row.idempotency_key));
 const unlinked=Object.entries(manifest.sections.receipts.body.receipts).filter(([key])=>!journalKeys.has(key));
 expect(unlinked.some(([,value])=>value.receipt.outcome==='REJECTED')).toBe(true);
 await expect(page.locator('#desk-audit-receipts li')).toHaveText(unlinked.map(([key,value])=>`${key} · no F04 journal row · ${JSON.stringify(value.receipt)}`));
 await expect(page.locator('#desk-audit-gaps')).toContainText('NOT_BOUND');
 await expect(page.locator('#desk-audit-unknown')).toContainText('UNKNOWN_UNRESOLVED');
 const summary=page.getByText('Settlement evidence · READ_ONLY_FIXTURE',{exact:true});
 await summary.focus();await page.keyboard.press('Enter');
 const state=await (await page.request.get(base+'/api/state')).json();
 const evidence=await (await page.request.get(base+'/api/evidence')).json();
 const selected=state.cases.find(row=>row.advance_id==='sim-unbound');
 await expect(page.locator('#desk-audit-fixture')).toHaveText(JSON.stringify(evidence.rows.filter(row=>row.claim_id===selected.claim_id||row.claim_id===selected.settlement_id),null,2));
 await page.getByText('Offline verification recipe · not executed here',{exact:true}).click();
 await expect(page.locator('#desk-audit')).toContainText('python3 -m capital.verify --workspace /path/to/local-workspace');
 await page.locator('#desk-case').selectOption('sim-pending-settlement');
 await page.locator('#desk-refresh').click();
 await expect(page.locator('#desk-refresh')).toBeEnabled();
 expect(posts).toEqual([]);expect(errors).toEqual([]);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:`test-results/auditor-evidence-${width}.png`,fullPage:true});
 await page.locator('#role').selectOption('observer');
 await expect(page.locator('#desk-forbidden')).toContainText('projection:read');
 await expect(page.locator('#role')).toBeEnabled();
 const gets=[];page.on('request',r=>gets.push(new URL(r.url()).pathname));
 await page.reload();await expect(page.locator('#desk-forbidden')).toBeVisible();
 for(const route of ['/api/evidence','/api/reconciliation','/api/overlay','/api/export/manifest'])expect(gets).not.toContain(route);
 await expect(page.locator('#desk-audit')).toBeHidden();
});
test('V3 overlay boundaries preserve server order and include the seventh check',async({page,request})=>{
 const state=await (await request.get(base+'/api/state')).json();
 const headers={'X-Capital-Token':state.local_token};
 for(const day of [1,2]){
  const response=await request.post(base+'/api/overlay/commands',{headers,data:{instance_id:state.instance_id,operation_id:'audit-clock-'+day,op:'advance_day',from_sim_day:day-1,to_sim_day:day,reason:'SIMULATED auditor test setup'}});
  expect(response.ok()).toBe(true);
 }
 await auditor(page);
 const manifest=await (await page.request.get(base+'/api/export/manifest')).json();
 expect(manifest.format).toBe('KIX_CAPITAL_EXPORT_MANIFEST_V3');
 await expect(page.locator('#desk-audit-checks tr')).toHaveCount(7);
 const expected=[];
 manifest.sections.journal.body.entries.forEach((entry,index)=>{if(entry.advance_id==='sim-unbound')expected.push({key:[index,1,index],boundary:'#'+index,event:entry.op});});
 manifest.sections.overlay.body.journal.forEach((entry,index)=>{if(entry.payload?.advance_id==='sim-unbound'||['clock','terms_binding'].includes(entry.kind))expected.push({key:[entry.after_journal_index,0,index],boundary:'@'+entry.after_journal_index,event:entry.kind});});
 expected.sort((a,b)=>a.key[0]-b.key[0]||a.key[1]-b.key[1]||a.key[2]-b.key[2]);
 const actual=await page.locator('#desk-audit-chain tr').evaluateAll(rows=>rows.map(row=>({boundary:row.cells[0].textContent,event:row.cells[3].textContent})));
 expect(actual).toEqual(expected.map(({boundary,event})=>({boundary,event})));
});
for(const fault of ['unknown-check','unreadable','failed-get'])test(`auditor withholds unavailable reconciliation: ${fault}`,async({page})=>{
 const errors=[];page.on('pageerror',error=>errors.push(String(error)));
 await page.route('**/api/reconciliation',async route=>{
  if(fault==='failed-get')return route.fulfill({status:503,json:{error:'SIMULATED_TEST_FAILURE'}});
  const response=await route.fetch();const body=await response.json();
  if(fault==='unknown-check')body.checks.push({id:'not-a-known-check',status:'MATCHED'});
  else{body.status='WORKSPACE_UNREADABLE';body.cut=null;body.checks=[];}
  await route.fulfill({json:body});
 });
 await page.addInitScript(()=>sessionStorage.setItem('kix-capital-role','auditor'));
 await page.goto(base+'/#desk');
 await expect(page.locator('#desk-audit-error')).not.toBeEmpty();
 await expect(page.locator('#desk-audit-content')).toBeHidden();
 await expect(page.locator('#desk-audit-checks tr')).toHaveCount(0);
 expect(errors).toEqual([]);
});
test('server reasons are literal text and incompatible snapshots are withheld',async({page})=>{
 const hostile='<img src=x onerror=alert(1)>';
 await page.route('**/api/reconciliation',async route=>{
  const response=await route.fetch();const body=await response.json();
  body.checks[0].detail=hostile;await route.fulfill({json:body});
 });
 await auditor(page);
 await expect(page.locator('#desk-audit-checks')).toContainText(hostile);
 await expect(page.locator('#desk-audit img')).toHaveCount(0);
 await page.route('**/api/export/manifest',async route=>{
  const response=await route.fetch();const body=await response.json();
  body.sections.reconciliation.body.cut='incompatible';await route.fulfill({json:body});
 });
 await page.locator('#desk-refresh').click();
 await expect(page.locator('#desk-audit-error')).toContainText('incompatible');
 await expect(page.locator('#desk-audit-content')).toBeHidden();
 await expect(page.locator('#desk-audit-chain tr')).toHaveCount(0);
});
