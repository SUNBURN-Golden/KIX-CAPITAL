const {test,expect}=require('@playwright/test');
const {spawnSync}=require('child_process');
// Server-calculated SIMULATED fixtures: browser tests never derive financial values.
const generated=spawnSync('python3',['-c',`
import json
from scripts.seed_demo import build_service
from capital.service import CapitalService
from capital.terms import DecisionNoteTermsPolicy
s=build_service()
e=CapitalService()
n=CapitalService(terms=DecisionNoteTermsPolicy('/tmp/kix-comparison-absent-note'))
print(json.dumps({'catalogue':s.risk_scenarios(),'snapshot':s.portfolio_snapshot(s.instance_id),
 'scenarios':{k:s.risk_scenarios(k) for k in s.risk_scenarios()['scenarios'] for k in [k['scenario_id']]},
 'empty':e.risk_scenarios('largest-advance-default'),
 'unbound':n.risk_scenarios('largest-advance-default')}))
`],{encoding:'utf8'});
if(generated.status!==0)throw Error(generated.stderr);
const fixtures=JSON.parse(generated.stdout);
const ids=Object.keys(fixtures.scenarios);
const clone=value=>JSON.parse(JSON.stringify(value));
async function setup(page){
 const seen=[];const errors=[];const control={scenario:null,snapshot:null,delay:null,catalogue:null};
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',r=>{if(r.url().includes('/api/risk/scenarios')||r.url().includes('/api/portfolio/snapshot'))seen.push({method:r.method(),url:r.url()});});
 await page.route('**/api/risk/scenarios**',async route=>{
  const response=await route.fetch();const actual=await response.json();
  const id=new URL(route.request().url()).pathname.split('/')[4];
  let body=clone(id?fixtures.scenarios[id]:fixtures.catalogue);
  body.instance_id=actual.instance_id;
  if(id&&control.scenario)body=control.scenario(body,id);
  if(!id&&control.catalogue)body=control.catalogue(body);
  if(control.delay)await control.delay(id);
  await route.fulfill({response,json:body});
 });
 await page.route('**/api/portfolio/snapshot?*',async route=>{
  const response=await route.fetch();const actual=await response.json();
  let body=clone(fixtures.snapshot);body.instance_id=actual.instance_id;
  if(control.snapshot)body=control.snapshot(body);
  await route.fulfill({response,json:body});
 });
 await page.goto('/');
 await expect(page.locator('#risk-comparison-select option')).toHaveCount(4);
 await expect(page.locator('#risk-comparison-refresh')).toHaveAttribute('aria-disabled','false');
 return {seen,errors,control};
}
const status=page=>page.locator('#risk-comparison-status');
const results=page=>page.locator('#risk-comparison-results');
const refresh=page=>page.locator('#risk-comparison-refresh');
const select=page=>page.locator('#risk-comparison-select');
async function capture(page){await refresh(page).click();await expect(page.locator('#risk-comparison')).toHaveAttribute('data-status','ready');}

test('four server scenarios show paired results, assumptions and keyboard focus at 375px',async({page})=>{
 const {seen,errors}=await setup(page);
 await select(page).focus();await page.keyboard.press('ArrowDown');await expect(select(page)).toBeFocused();
 await page.keyboard.press('Tab');await expect(refresh(page)).toBeFocused();await page.keyboard.press('Enter');
 await expect(status(page)).toContainText('captured sim_day');await expect(refresh(page)).toBeFocused();
 for(const id of ids){
  await select(page).focus();await select(page).selectOption(id);
  await expect(page.locator('#risk-comparison-details')).toContainText(fixtures.scenarios[id].scenario.assumption);
  await expect(select(page)).toBeFocused();
  const rows=results(page).locator('table').first().locator('tbody tr');
  const row=rows.filter({has:page.locator('th',{hasText:/^outstanding_krw$/})});
  await expect(row.locator('td').nth(0)).toHaveText(new Intl.NumberFormat('ko-KR').format(fixtures.snapshot.risk.totals.outstanding_krw));
  await expect(row.locator('td').nth(1)).toHaveText(new Intl.NumberFormat('ko-KR').format(fixtures.scenarios[id].risk.totals.outstanding_krw));
 }
 expect(seen.filter(r=>r.url.includes('/snapshot'))).toHaveLength(1);
 await results(page).locator('summary').first().focus();await page.keyboard.press('Enter');
 await expect(results(page).locator('details').first()).toHaveAttribute('open','');
 await page.keyboard.press('Tab');await expect(results(page).locator('details').first().locator('[role=region]')).toBeFocused();
 await page.setViewportSize({width:375,height:800});await page.locator('#risk-comparison').scrollIntoViewIfNeeded();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(seen.every(r=>r.method==='GET')).toBe(true);expect(errors).toEqual([]);
});

test('each digest mismatch latches stale until explicit capture, including missing and null digests',async({page})=>{
 const {control}=await setup(page);await capture(page);
 for(const field of ['baseline_risk_digest','baseline_covenant_digest']){
  for(const value of ['f'.repeat(64),null,undefined]){
   control.scenario=body=>{body.reconciliation[field]=value;return body;};
   await select(page).selectOption('refund-shock');await expect(status(page)).toContainText('REFRESH_REQUIRED');await expect(results(page)).toBeEmpty();
   control.scenario=null;
   await select(page).selectOption('all-watch-breach');await expect(status(page)).toContainText('REFRESH_REQUIRED');await expect(results(page)).toBeEmpty();
   await capture(page);
  }
 }
});

test('NOT_BOUND, unevaluated and incomplete snapshots retain reasons without numeric results',async({page})=>{
 const {control}=await setup(page);await capture(page);
 control.scenario=body=>({...clone(fixtures.unbound),instance_id:body.instance_id});
 await select(page).selectOption('refund-shock'); // invalid identity must also clear old results
 await expect(status(page)).toContainText('검증 실패');await expect(results(page)).toBeEmpty();
 await select(page).selectOption('largest-advance-default');await expect(status(page)).toContainText('NOT_BOUND');await expect(status(page)).toContainText(fixtures.unbound.reason);
 control.scenario=body=>({...clone(fixtures.empty),instance_id:body.instance_id,
  observed_state_digest:fixtures.snapshot.cut.state_digest,
  reconciliation:{...fixtures.empty.reconciliation,baseline_risk_digest:fixtures.snapshot.risk.risk_digest,baseline_covenant_digest:fixtures.snapshot.covenants.covenant_digest}});
 await refresh(page).click();await expect(status(page)).toContainText('not evaluated');await expect(status(page)).toContainText(fixtures.empty.unevaluated_reason);await expect(results(page)).toBeEmpty();
 await expect(page.locator('#risk-comparison-details')).not.toContainText('outstanding_krw');
 control.scenario=null;control.snapshot=body=>({...body,status:'INCOMPLETE',complete:false,completeness:{...body.completeness,reasons:['TERMS_NOT_BOUND']},risk:null});
 await refresh(page).click();await expect(status(page)).toContainText('INCOMPLETE');await expect(status(page)).toContainText('TERMS_NOT_BOUND');await expect(results(page)).toBeEmpty();
 control.snapshot=null;await capture(page);
});

test('delayed selection and role changes discard responses; observer makes no comparison reads',async({page})=>{
 const {control,seen}=await setup(page);await capture(page);
 let release;const gate=new Promise(resolve=>release=resolve);let started;const pending=new Promise(resolve=>started=resolve);
 control.delay=async id=>{if(id==='refund-shock'){started();await gate;}};
 await select(page).selectOption('refund-shock');await pending;
 await select(page).selectOption('all-watch-breach');await expect(page.locator('#risk-comparison-details')).toContainText(fixtures.scenarios['all-watch-breach'].scenario.assumption);
 release();await expect(page.locator('#risk-comparison-details')).not.toContainText(fixtures.scenarios['refund-shock'].scenario.assumption);
 control.delay=null;
 let releaseRole;const roleGate=new Promise(resolve=>releaseRole=resolve);let roleStarted;const rolePending=new Promise(resolve=>roleStarted=resolve);
 control.delay=async id=>{if(id==='refund-shock'){roleStarted();await roleGate;}};
 await select(page).selectOption('refund-shock');await rolePending;
 const before=seen.length;await page.locator('#role').focus();await page.locator('#role').selectOption('observer');
 await expect(status(page)).toContainText('observer');await expect(page.locator('#role')).toBeFocused();releaseRole();
 await expect(results(page)).toBeEmpty();await expect(select(page)).toBeDisabled();expect(seen.length).toBe(before);
 await page.locator('#role').selectOption('auditor');await expect(select(page)).toBeEnabled();await capture(page);
});

test('network and malformed-result recovery retains capture focus and never substitutes zero',async({page})=>{
 const {control}=await setup(page);await capture(page);
 await page.route('**/api/portfolio/snapshot?*',route=>route.abort());
 await refresh(page).focus();await page.keyboard.press('Space');await expect(status(page)).toContainText('검증 실패');await expect(refresh(page)).toBeFocused();await expect(results(page)).toBeEmpty();
 await page.unroute('**/api/portfolio/snapshot?*');
 // Restore snapshot interception after the controlled network error.
 await page.route('**/api/portfolio/snapshot?*',async route=>{const response=await route.fetch();const actual=await response.json();await route.fulfill({response,json:{...clone(fixtures.snapshot),instance_id:actual.instance_id}});});
 control.scenario=body=>{delete body.risk.totals;return body;};await refresh(page).click();await expect(status(page)).toContainText('검증 실패');await expect(results(page)).toBeEmpty();
 control.scenario=body=>{body.risk.reserve.requirement_krw=null;return body;};await capture(page);
 await results(page).locator('summary').filter({hasText:'Reserve / stress'}).click();
 await expect(results(page).locator('tr').filter({has:page.locator('th',{hasText:/^reserve.requirement_krw$/})}).first().locator('td').nth(1)).toHaveText('unavailable');
});


test('agent helper denies even a supplied projection permission and mismatched sessions',async({page})=>{
 await page.goto('/');
 const script=await (await page.request.get('/app.js')).text();
 const block=script.slice(script.indexOf('// risk-scenario-desk:'),script.indexOf('// /risk-scenario-desk'));
 const decisions=await page.evaluate(block=>{
  const probe=new Function('currentRole','state','can','$',block+';return comparisonAllowed();');
  return [...['agent','observer','organizer','auditor'].map(role=>probe(()=>role,{auth:{role}},()=>true,()=>({addEventListener(){}}))),probe(()=>'organizer',{auth:{role:'auditor'}},()=>true,()=>({addEventListener(){}}))];
 },block);
 expect(decisions).toEqual([false,false,true,true,false]);
});

test('invalid snapshot digests, reconciliation and execution flags never qualify',async({page})=>{
 const {control}=await setup(page);
 for(const modify of [
  body=>{body.risk.risk_digest=null;return body;},
  body=>{delete body.covenants.covenant_digest;return body;},
 ]){
  control.snapshot=modify;await refresh(page).click();await expect(status(page)).toContainText('REFRESH_REQUIRED');await expect(results(page)).toBeEmpty();
 }
 control.snapshot=null;
 for(const modify of [
  body=>{body.reconciliation.matched=false;return body;},
  body=>{body.sim_day=99;return body;},
  body=>{body.observed_state_digest='f'.repeat(64);return body;},
  body=>{body.applied=true;return body;},
  body=>{body.risk.stress.applied=true;return body;},
  body=>{body.covenants.advances[0].enforced=true;return body;},
 ]){
  control.scenario=modify;await refresh(page).click();await expect(page.locator('#risk-comparison')).not.toHaveAttribute('data-status','loading');await expect(results(page)).toBeEmpty();
 }
 control.scenario=null;await capture(page);
});


test('application refresh invalidates a delayed pair and catalogue errors recover explicitly',async({page})=>{
 const {control,seen}=await setup(page);await capture(page);
 let release;const gate=new Promise(resolve=>release=resolve);let started;const pending=new Promise(resolve=>started=resolve);
 control.delay=async id=>{if(id==='refund-shock'){started();await gate;}};
 await select(page).selectOption('refund-shock');await pending;
 control.catalogue=body=>({...body,policy_adopted:true});
 await page.locator('#refresh').click();await expect(status(page)).toContainText('목록 조회 실패');release();
 await expect(results(page)).toBeEmpty();await expect(select(page)).toBeDisabled();
 await expect(refresh(page)).toHaveAttribute('aria-disabled','false');
 control.catalogue=null;control.delay=null;
 await capture(page);await expect(select(page).locator('option')).toHaveCount(4);
 expect(seen.every(r=>r.method==='GET')).toBe(true);
});
