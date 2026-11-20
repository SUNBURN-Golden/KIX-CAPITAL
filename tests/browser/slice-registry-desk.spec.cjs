const {test,expect}=require('@playwright/test');
const {spawn}=require('child_process');
const path=require('path');
const root=path.resolve(__dirname,'../..');
const base='http://127.0.0.1:8951';
let child,serverLog,allCommandPosts;
async function startServer(request,empty=false,shadowNotBound=false){
 serverLog='';
 child=spawn('python3',['tests/browser/helpers/slice_registry_server.py','--port','8951',...(empty?['--empty']:[]),...(shadowNotBound?['--shadow-not-bound']:[])],{cwd:root,stdio:['ignore','pipe','pipe']});
 child.stdout.on('data',data=>serverLog+=data);child.stderr.on('data',data=>serverLog+=data);
 await expect.poll(async()=>{try{return (await request.get(base+'/api/state')).status();}catch{return 0;}},{message:'SIMULATED fixture server: '+serverLog}).toBe(200);
}
async function stopServer(){
 if(child&&child.exitCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGTERM');await exited;}
}
test.beforeEach(async({request,page})=>{allCommandPosts=[];page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname!=='/api/session')allCommandPosts.push(r.url());});await startServer(request);});
test.afterEach(async()=>{try{expect(allCommandPosts).toEqual([]);}finally{await stopServer();}});
async function open(page,role='organizer'){
 await page.addInitScript(role=>{if(!sessionStorage.getItem('kix-capital-role'))sessionStorage.setItem('kix-capital-role',role);},role);
 await page.goto(base+'/#desk');
 await expect(page.locator('#role')).toBeEnabled({timeout:15000});
 await expect(page.locator('#slices-status')).toContainText('CURRENT_READ');
}
async function inspect(page,claim='demo-alpha-arena',payee='organizer',days='60'){
 await page.locator('#slices-claim').selectOption(claim);
 await page.locator('#slices-payee').selectOption(payee);
 await page.locator('#slices-days').fill(days);
 const reply=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/overlay/slices'&&new URL(r.url()).searchParams.has('expected_days'));
 await page.locator('#slices-inspect').click();
 const response=await reply;
 await expect(page.locator('#slices-quote')).toBeVisible();
 return {body:await response.json(),url:new URL(response.url())};
}
function watch(page){
 const posts=[],errors=[],sliceGets=[];
 page.on('request',r=>{const url=new URL(r.url());if(r.method()==='POST'&&url.pathname!=='/api/session')posts.push(url.pathname);if(url.pathname==='/api/overlay/slices')sliceGets.push(url);});
 page.on('pageerror',e=>errors.push(String(e)));
 return {posts,errors,sliceGets};
}
async function cut(request){
 const state=await (await request.get(base+'/api/state')).json(),overlay=await (await request.get(base+'/api/overlay')).json();
 return {f04:state.state_digest,operations:state.operation_count,overlay:overlay.overlay_state_digest};
}
for(const [role,width] of [['organizer',1280],['auditor',1280],['auditor',375]])test(`${role} inspects five real SIMULATED states, evidence and quotes at ${width}px`,async({page,request})=>{
 const seen=watch(page),before=await cut(request);
 await page.setViewportSize({width,height:900});await open(page,role);
 const registry=await (await request.get(base+'/api/overlay/slices')).json();
 expect(new Set(registry.slices.map(r=>r.status))).toEqual(new Set(['PROPOSED','OPEN','IMPAIRED','RESOLVED','VOID']));
 await expect(page.locator('#slices-rows tr')).toHaveCount(5);
 await expect(page.locator('#slices-capacity')).toHaveText(JSON.stringify(registry.capacity,null,2));
 for(const row of registry.slices){
  const button=page.getByRole('button',{name:'검사 '+row.slice_id,exact:true});
  await button.focus();await page.keyboard.press('Enter');await expect(page.locator('#slice-detail-title')).toBeFocused();
  await expect(page.locator('#slice-source')).toHaveText(JSON.stringify(row,null,2));
  for(const key of ['slice_face_krw','outstanding_krw','encumbered_face_krw','served_krw','eligible_line_krw','exposure_krw','shortfall_krw','recourse_received_krw','shadow_discount','shadow_price','holder_first']){
   await expect(page.locator('#slice-facts dt').filter({hasText:new RegExp('^'+key+'$')})).toHaveCount(1);
   await expect(page.locator('#slice-facts dt').filter({hasText:new RegExp('^'+key+'$')}).locator('xpath=following-sibling::dd[1]')).toHaveText(String(row[key]));
  }
  await expect(page.locator('#slice-recourse')).toHaveText(JSON.stringify(row.quotes,null,2));
 }
 const impaired=registry.slices.find(r=>r.status==='IMPAIRED'),resolved=registry.slices.find(r=>r.status==='RESOLVED');
 expect(impaired.served_krw).toBeGreaterThan(0);expect(impaired.outstanding_krw).toBeGreaterThan(0);expect(impaired.quotes.length).toBeGreaterThan(0);expect(resolved.recourse_received_krw).toBeGreaterThan(0);
 const {body,url}=await inspect(page);
 expect([...url.searchParams.keys()]).toEqual(['quote_claim_id','quote_payee_label','expected_days']);
 expect(url.searchParams.get('expected_days')).toBe('60');
 await expect(page.locator('#slices-guard')).toHaveText(JSON.stringify(body.quote.registry_check,null,2));
 await expect(page.locator('#slices-guard')).toContainText('SLICE_OPEN_EXISTS');
 await expect(page.locator('#slices-quote-source')).toHaveText(JSON.stringify(body.quote,null,2));
 await expect(page.locator('#desk-slices')).toContainText('SHADOW_NOT_APPLIED');
 await expect(page.locator('#desk-slices')).toContainText('SIMULATION_ONLY_NOT_OFFERED_V1');
 await expect(page.locator('#slices-freshness')).toContainText('atomic snapshot');
 await page.getByRole('button',{name:'검사 desk-open',exact:true}).click();
 await page.keyboard.press('Tab');await expect(page.locator('#slice-links a').first()).toBeFocused();
 if(width===375){const region=page.getByRole('region',{name:'Claim-slice registry',exact:true});await region.focus();await page.keyboard.press('ArrowRight');await expect.poll(()=>region.evaluate(el=>el.scrollLeft)).toBeGreaterThan(0);}
 await page.screenshot({path:`test-results/slice-registry-${role}-${width}.png`,fullPage:true});
 const advance=page.locator('#slice-links a').filter({hasText:'advance evidence:'});
 await expect(advance).toHaveCount(1);await expect(advance).toHaveAttribute('href','?case=sim-desk-linked-advance#desk');
 await advance.click();await expect(page.locator('#desk-case')).toHaveValue('sim-desk-linked-advance');await expect(page.locator('#slices-status')).toContainText('CURRENT_READ');
 await expect(page.locator('#desk-dossier')).toBeEnabled();
 await page.getByRole('button',{name:'검사 desk-void',exact:true}).click();await expect(page.locator('#slice-links')).toContainText('no linked advance');
 await page.getByRole('button',{name:'검사 desk-open',exact:true}).click();
 const claim=page.locator('#slice-links a').filter({hasText:'청구 근거:'});await claim.focus();await page.keyboard.press('Enter');
 await expect(page.locator('#claim-evidence-demo-alpha-arena')).toBeFocused();await expect(page.locator('#evidence')).toBeVisible();
 await expect(page.locator('#slices-quote')).toBeHidden();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(await cut(request)).toEqual(before);expect(seen.posts).toEqual([]);expect(seen.errors).toEqual([]);
});
test('quote assumptions are explicit, non-negative integer inputs; zero is an explicit assumption',async({page})=>{
 const seen=watch(page);await open(page);const count=seen.sliceGets.length;
 for(const days of ['', '-1','1.5','1e2','9007199254740992']){
  await page.locator('#slices-days').fill(days);await page.locator('#slices-inspect').click();
  await expect(page.locator('#slices-quote-status')).toContainText('INPUT_REQUIRED');
  await expect(page.locator('#slices-quote')).toBeHidden();expect(seen.sliceGets.length).toBe(count);
 }
 const result=await inspect(page,'sim-committed','organizer','0');expect(result.url.searchParams.get('expected_days')).toBe('0');
});
test('literal synthetic quote values, ordered guard reasons and recourse provenance survive without arithmetic or HTML',async({page})=>{
 const hostile='<img src=x onerror=alert(1)>';
 await page.route('**/api/overlay/slices?**',async route=>{
  const response=await route.fetch(),body=await response.json();
  // Deliberately inconsistent amounts: synthetic rendering test, never a financial calculation.
  Object.assign(body.quote,{shadow_slice_face_max:910001,shadow_discount:47,shadow_price:123,input_source:'SIMULATED_TEST_INPUT',detail:hostile});
  Object.assign(body.quote.registry_check,{status:'REFUSED',codes:['Z_SYNTHETIC_FIRST','A_SYNTHETIC_SECOND'],free_face_krw:713,admissible_face_max_krw:19});
  await route.fulfill({json:body});
 });
 await open(page);const {body}=await inspect(page);
 await expect(page.locator('#slices-quote-source')).toHaveText(JSON.stringify(body.quote,null,2));
 await expect(page.locator('#slices-guard')).toHaveText(JSON.stringify(body.quote.registry_check,null,2));
 for(const [key,value] of [['shadow_slice_face_max','910001'],['shadow_discount','47'],['shadow_price','123']])await expect(page.locator('#slices-quote-facts dt').filter({hasText:new RegExp('^'+key+'$')}).locator('xpath=following-sibling::dd[1]')).toHaveText(value);
 await expect(page.locator('#slices-quote-status')).toContainText(hostile);await expect(page.locator('#desk-slices img')).toHaveCount(0);
});
for(const status of ['SHADOW_NOT_BOUND','SHADOW_INPUT_UNKNOWN','SHADOW_INCONSISTENT'])test(`explicit ${status} quote, missing inputs remain unavailable`,async({page})=>{
 await page.route('**/api/overlay/slices?**',async route=>{
  const response=await route.fetch(),body=await response.json();
  Object.assign(body.quote,{status,detail:'SIMULATED_TEST_INPUT',missing_inputs:['server_missing_witness']});
  for(const key of ['shadow_slice_face_max','shadow_discount','shadow_price','registry_check'])delete body.quote[key];
  await route.fulfill({json:body});
 });
 await open(page);await inspect(page);await expect(page.locator('#slices-quote-status')).toContainText(status);
 await expect(page.locator('#slices-quote-facts')).toContainText('server_missing_witness');await expect(page.locator('#slices-guard')).toHaveText('NOT_BOUND · registry_check 없음');
});
test('real unknown inputs and payee refusal are rendered without substituting zero',async({page})=>{
 await open(page);
 const unknown=await inspect(page,'demo-gamma-tour');expect(unknown.body.quote.status).toBe('SHADOW_INPUT_UNKNOWN');
 await expect(page.locator('#slices-quote-status')).toContainText('SHADOW_INPUT_UNKNOWN');
 const refused=await inspect(page,'demo-alpha-arena','platform');expect(refused.body.quote.registry_check.codes).toContain('SLICE_PAYEE_NOT_SLICEABLE');
 await expect(page.locator('#slices-guard')).toContainText('SLICE_PAYEE_NOT_SLICEABLE');
});
for(const fault of ['empty','not-bound','capacity','malformed','malformed-quote','session','invalid-json','execution-flag','missing-quote-amount'])test(`registry state: ${fault} clears any prior quote`,async({page})=>{
 await open(page);await inspect(page);
 await page.route('**/api/overlay/slices*',async route=>{
  if(fault==='capacity')return route.fulfill({status:409,json:{error:'SIMULATION_CAPACITY',detail:{bound:'SIMULATED_TEST_INPUT'}}});
  if(fault==='session')return route.fulfill({status:403,json:{error:'SESSION_REQUIRED'}});
  if(fault==='invalid-json')return route.fulfill({status:200,contentType:'application/json',body:'invalid SIMULATED_TEST_INPUT'});
  const response=await route.fetch(),body=await response.json();
  if(fault==='empty')body.slices=[];
  if(fault==='not-bound'){body.status='NOT_BOUND';body.slices=[];delete body.capacity;delete body.quote;}
  if(fault==='malformed')body.slices[0].served_krw=null;
  if(fault==='execution-flag')body.funds_executed=true;
  if(fault==='missing-quote-amount')delete body.quote.shadow_price;
  if(fault==='malformed-quote')body.quote.registry_check.codes='invalid SIMULATED_TEST_INPUT';
  await route.fulfill({json:body});
 });
 await page.locator(['malformed-quote','missing-quote-amount'].includes(fault)?'#slices-inspect':'#slices-refresh').click();
 await expect(page.locator('#slices-quote')).toBeHidden();
 const expected={empty:'EMPTY', 'not-bound':'NOT_BOUND',capacity:'CAPACITY',session:'STALE_SESSION',malformed:'INVALID_SLICE_RESPONSE','malformed-quote':'INVALID_SLICE_RESPONSE','invalid-json':'UNAVAILABLE','execution-flag':'INVALID_SLICE_RESPONSE','missing-quote-amount':'INVALID_SLICE_RESPONSE'};
 await expect(page.locator('#slices-status')).toContainText(expected[fault]);await expect(page.locator('#slices-quote-source')).toBeEmpty();
 if(!['empty','not-bound'].includes(fault))await expect(page.locator('#slices-rows tr')).toHaveCount(0);
});
test('failed state refresh invalidates quote before state GET settles, and explicit recovery works',async({page})=>{
 await open(page);await inspect(page);
 let release;const gate=new Promise(resolve=>release=resolve);
 await page.route('**/api/state',async route=>{await gate;await route.fulfill({status:503,json:{error:'SIMULATED_STATE_FAILURE'}});});
 await page.locator('#desk-refresh').click();await expect(page.locator('#slices-quote')).toBeHidden();await expect(page.locator('#slices-quote-source')).toBeEmpty();
 release();await expect(page.locator('#slices-status')).toContainText('UNAVAILABLE');await expect(page.locator('#desk-refresh')).toBeEnabled();
 await page.unroute('**/api/state');await page.locator('#desk-refresh').click();await expect(page.locator('#slices-status')).toContainText('CURRENT_READ');await expect(page.locator('#slices-quote')).toBeHidden();
 await inspect(page);
});
test('overlay changes between bracket reads discard registry and quote',async({page})=>{
 await open(page);await inspect(page);let count=0;
 await page.route('**/api/overlay',async route=>{const response=await route.fetch(),body=await response.json();if(++count===2)body.overlay_state_digest='SIMULATED_DIFFERENT_CUT';await route.fulfill({json:body});});
 await page.locator('#slices-inspect').click();await expect(page.locator('#slices-status')).toContainText('STALE_SNAPSHOT');await expect(page.locator('#slices-quote')).toBeHidden();await expect(page.locator('#slices-rows tr')).toHaveCount(0);
});
test('delayed superseded quote cannot replace newer input or a newer quote',async({page})=>{
 await open(page);let release;const gate=new Promise(resolve=>release=resolve);let first=true,entered=false;
 await page.route('**/api/overlay/slices?**',async route=>{
  const response=await route.fetch(),body=await response.json();
  if(first){first=false;entered=true;await gate;body.quote.detail='SIMULATED_OLD_QUOTE';}
  await route.fulfill({json:body});
 });
 await page.locator('#slices-days').fill('60');await page.locator('#slices-inspect').click();await expect.poll(()=>entered).toBe(true);
 await page.locator('#slices-days').fill('61');await expect(page.locator('#slices-quote')).toBeHidden();
 await page.locator('#slices-inspect').click();await expect(page.locator('#slices-quote')).toBeVisible();
 const source=await page.locator('#slices-quote-source').textContent();release();
 // A request after release ensures the late handler has a chance to settle.
 await page.request.get(base+'/api/state');await expect(page.locator('#slices-quote-source')).toHaveText(source);
 await expect(page.locator('#slices-quote-assumptions')).toContainText('expected_days=61');
});
for(const denied of ['observer','organizer-without-permission'])test(`${denied} sends zero registry GETs and no panel command POSTs`,async({page})=>{
 const seen=watch(page);
 if(denied==='organizer-without-permission')await page.route('**/api/state',async route=>{const response=await route.fetch(),body=await response.json();body.auth.permissions['projection:read']={allowed:false,reason:'SIMULATED_DENIED_PROJECTION'};await route.fulfill({json:body});});
 await page.addInitScript(role=>sessionStorage.setItem('kix-capital-role',role),denied==='observer'?'observer':'organizer');
 await page.goto(base+'/#desk');await expect(page.locator('#desk-forbidden')).toBeVisible();await expect(page.locator('#role')).toBeEnabled();
 await expect(page.locator('#desk-slices')).toBeHidden();expect(seen.sliceGets).toEqual([]);expect(seen.posts).toEqual([]);expect(seen.errors).toEqual([]);
});
test('role transition and desk exit synchronously retire current quotes',async({page})=>{
 const seen=watch(page);await open(page);await inspect(page);
 await page.locator('#role').selectOption('auditor');await expect(page.locator('#slices-quote')).toBeHidden();await expect(page.locator('#role')).toBeEnabled();await expect(page.locator('#slices-status')).toContainText('CURRENT_READ');
 await inspect(page);await page.locator('nav a[href="#overview"]').click();await expect(page.locator('#slices-quote-source')).toBeEmpty();
 await page.locator('nav a[href="#desk"]').click();await expect(page.locator('#slices-status')).toContainText('CURRENT_READ');await expect(page.locator('#slices-quote')).toBeHidden();
 await page.locator('#role').selectOption('observer');await expect(page.locator('#desk-forbidden')).toBeVisible();await expect(page.locator('#role')).toBeEnabled();
 const count=seen.sliceGets.length;await page.reload();await expect(page.locator('#desk-forbidden')).toBeVisible();await expect(page.locator('#role')).toBeEnabled();
 expect(seen.sliceGets.length).toBe(count);expect(seen.posts).toEqual([]);expect(seen.errors).toEqual([]);
});

test('real disposable empty registry is explicit',async({page,request})=>{
 await stopServer();await startServer(request,true);
 await page.goto(base+'/#desk');await expect(page.locator('#slices-status')).toContainText('EMPTY');
 await expect(page.locator('#slices-rows tr')).toHaveCount(0);await expect(page.locator('#slices-quote')).toBeHidden();
 const listing=await (await request.get(base+'/api/overlay/slices')).json();
 expect(listing.capacity.slices).toBe(0);await expect(page.locator('#slices-capacity')).toHaveText(JSON.stringify(listing.capacity,null,2));
});
test('real restart rejects an old local token and refresh requires fresh explicit inspection',async({page,request})=>{
 const seen=watch(page);await open(page);await inspect(page);
 const before=await (await request.get(base+'/api/state')).json();
 await stopServer();await startServer(request);
 const after=await (await request.get(base+'/api/state')).json();expect(after.instance_id).not.toBe(before.instance_id);
 await page.locator('#slices-refresh').click();await expect(page.locator('#slices-status')).toContainText('STALE_SESSION');
 await expect(page.locator('#slices-quote')).toBeHidden();await expect(page.locator('#slices-rows tr')).toHaveCount(0);
 await page.locator('#desk-refresh').click();await expect(page.locator('#slices-status')).toContainText('STALE_SESSION');
 await page.locator('#slices-reload-session').click();await expect(page.locator('#role')).toBeEnabled();await expect(page.locator('#slices-status')).toContainText('CURRENT_READ');
 await expect(page.locator('#slices-quote')).toBeHidden();await inspect(page);
 expect(seen.posts).toEqual([]);expect(seen.errors).toEqual([]);
});

test('real missing-shadow-note quote envelope remains explicitly SHADOW_NOT_BOUND',async({page,request})=>{
 await stopServer();await startServer(request,false,true);await open(page);
 const {body}=await inspect(page);expect(body.quote.status).toBe('SHADOW_NOT_BOUND');
 expect(body.quote.missing_inputs).toBeUndefined();expect(body.quote.input_source).toBeUndefined();
 await expect(page.locator('#slices-quote-status')).toContainText('SHADOW_NOT_BOUND');
 await expect(page.locator('#slices-quote-source')).toHaveText(JSON.stringify(body.quote,null,2));
 for(const key of ['missing_inputs','input_source','shadow_price'])await expect(page.locator('#slices-quote-facts dt').filter({hasText:new RegExp('^'+key+'$')}).locator('xpath=following-sibling::dd[1]')).toHaveText('—');
});
test('evidence associations expose every exact claim or settlement match, without beneficiary inference',async({page})=>{
 await page.route('**/api/state',async route=>{
  const response=await route.fetch(),body=await response.json(),original=body.cases[0];
  // SYNTHETIC_TEST_INPUT associations: existing case shape; no ownership assertion.
  body.cases.push({...original,advance_id:'sim-association-claim',claim_id:'demo-alpha-arena',settlement_id:'sim-other-claim'},
   {...original,advance_id:'sim-association-settlement',claim_id:'sim-other-claim',settlement_id:'demo-alpha-arena'},
   {...original,advance_id:'sim-association-unrelated',claim_id:'sim-other-claim',settlement_id:'sim-other-claim'});
  await route.fulfill({json:body});
 });
 await open(page);await page.getByRole('button',{name:'검사 desk-open',exact:true}).click();
 const links=page.locator('#slice-links a').filter({hasText:'advance evidence:'});
 await expect(links).toHaveText(['advance evidence: sim-desk-linked-advance','advance evidence: sim-association-claim','advance evidence: sim-association-settlement']);
 await expect(page.locator('#slice-links')).not.toContainText('sim-association-unrelated');
});
