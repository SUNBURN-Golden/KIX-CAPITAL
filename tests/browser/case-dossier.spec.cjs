const {test, expect} = require('@playwright/test');
const {spawn, spawnSync} = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const root = path.resolve(__dirname, '../..');
const base = 'http://127.0.0.1:8944';
let child, directory;
test.beforeEach(async ({request})=>{
 directory=fs.mkdtempSync(path.join(os.tmpdir(),'capital-dossier-'));
 const workspace=path.join(directory,'workspace');
 const seeded=spawnSync('python3',['scripts/seed_demo.py','--workspace',workspace],{cwd:root,encoding:'utf8'});
 expect(seeded.status,seeded.stderr).toBe(0);
 child=spawn('python3',['-m','capital.server','--port','8944','--workspace',workspace],{cwd:root,stdio:'ignore'});
 await expect.poll(async()=>{try{return(await request.get(base+'/api/state')).status();}catch{return 0;}}).toBe(200);
});
test.afterEach(async()=>{
 if(child&&child.exitCode===null){const exited=new Promise(resolve=>child.once('exit',resolve));child.kill('SIGTERM');await exited;}
 if(directory)fs.rmSync(directory,{recursive:true,force:true});
});
async function open(page,role){
 await page.addInitScript(value=>sessionStorage.setItem('kix-capital-role',value),role);
 await page.goto(base+'/?case=sim-unbound#desk');
 await expect(page.locator('#role')).toBeEnabled();
 await expect(page.locator('#desk-dossier')).toBeEnabled();
}
for(const role of ['organizer','auditor'])for(const width of [1280,375])test(`dossier download for ${role} at ${width}px`,async({page})=>{
 await page.setViewportSize({width,height:900});
 const errors=[];page.on('pageerror',e=>errors.push(String(e)));
 await open(page,role);
 const posts=[];page.on('request',r=>{if(r.method()==='POST')posts.push(r.url());});
 const download=page.waitForEvent('download');
 await page.locator('#desk-dossier').click();
 const file=await download;
 expect(file.suggestedFilename()).toBe('capital-dossier-sim-unbound.json');
 const body=JSON.parse(fs.readFileSync(await file.path(),'utf8'));
 expect(body.format).toBe('KIX_CAPITAL_CASE_DOSSIER_V1');
 expect(body.advance_id).toBe('sim-unbound');expect(body.funds_executed).toBe(false);
 await expect(page.locator('#desk-dossier-note')).toContainText(body.dossier_digest);
 expect(posts).toEqual([]);expect(errors).toEqual([]);
 await expect(page.locator('#desk img')).toHaveCount(0);
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.screenshot({path:`test-results/dossier-${role}-${width}.png`,fullPage:true});
 await page.locator('#role').selectOption('observer');
 await expect(page.locator('#desk-forbidden')).toBeVisible();
 await expect(page.locator('#desk-dossier')).toBeHidden();
});
test('dossier reasons and download fallback use literal text under CSP',async({page})=>{
 const hostile='<img src=x onerror=alert(1)>';
 await page.route('**/api/cases/*/dossier?*',async route=>{
  const response=await route.fetch(),body=await response.json();
  body.terms_reason=hostile;await route.fulfill({json:body});
 });
 await open(page,'auditor');
 await page.evaluate(()=>{URL.createObjectURL=()=>{throw Error('SIMULATED download fallback');};});
 await page.locator('#desk-dossier').click();
 await expect(page.locator('#desk-dossier-note')).toContainText(hostile);
 await expect(page.locator('#desk-dossier-result')).toContainText(hostile);
 await expect(page.locator('#desk img')).toHaveCount(0);
});
test('dossier is independent of evidence desk manifest compatibility',async({page})=>{
 await page.route('**/api/export/manifest',route=>route.fulfill({status:503,json:{error:'SIMULATED_TEST_FAILURE'}}));
 await open(page,'auditor');
 await expect(page.locator('#desk-audit-content')).toBeHidden();
 const download=page.waitForEvent('download');
 await page.locator('#desk-dossier').click();
 expect((await download).suggestedFilename()).toBe('capital-dossier-sim-unbound.json');
});
test('incompatible dossier responses are withheld',async({page})=>{
 await page.route('**/api/cases/*/dossier?*',async route=>{
  const response=await route.fetch(),body=await response.json();body.advance_id='wrong-case';await route.fulfill({json:body});
 });
 await open(page,'organizer');
 await page.locator('#desk-dossier').click();
 await expect(page.locator('#desk-dossier-note')).toContainText('INVALID_DOSSIER');
 await expect(page.locator('#desk-dossier-result')).toBeHidden();
});
