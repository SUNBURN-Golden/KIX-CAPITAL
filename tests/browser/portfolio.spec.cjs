const {test,expect}=require('@playwright/test');
function gate(page){return page.locator('#facts dt').filter({hasText:'정산 게이트'}).locator('xpath=following-sibling::dd[1]');}
function outstanding(page){return page.locator('#facts dt').filter({hasText:/^남은 모의 노출$/}).locator('xpath=following-sibling::dd[1]');}
function fact(page,label){return page.locator('#facts dt').filter({hasText:label}).locator('xpath=following-sibling::dd[1]');}
async function acceptedClick(page,name,op,phase,advanceId,{exact=false}={}){
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/commands')&&r.request().postDataJSON()?.op===op);
 await page.getByRole('button',{name,exact}).click();
 const receipt=await(await pending).json();
 expect(receipt.outcome).toBe('ACCEPTED');
 expect(receipt.result.credit.advance_id).toBe(advanceId);
 await expect(page.locator('#phase')).toHaveText(phase);
 return receipt;
}
async function offer(page,fixture='sim-committed',amount='60000',{navigate=true}={}){
 if(navigate){await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');}
 await page.locator('#fixture').selectOption(fixture);await page.locator('#amount').fill(String(amount));
 const created=page.waitForResponse(r=>r.url().endsWith('/api/commands')&&r.request().postDataJSON()?.op==='offer');
 await page.getByRole('button',{name:'모의 제안 생성'}).click();
 const receipt=await(await created).json();
 expect(receipt.outcome).toBe('ACCEPTED');
 const advanceId=receipt.result.credit.advance_id;
 await expect(page.locator('#case-title')).toHaveText(advanceId);
 await expect(page.locator('#phase')).toHaveText('제안됨 · OFFERED');
 return receipt;
}
async function approveBindDraw(page,id){
 await acceptedClick(page,'모의 승인','approve','모의 승인 · APPROVED',id,{exact:true});
 await acceptedClick(page,'정산 근거 연결','bind_settlement','모의 승인 · APPROVED',id);
 await expect(gate(page)).toHaveText('BOUND');
 await acceptedClick(page,'모의 노출 기록','draw','노출 기록 · DRAWN',id,{exact:true});
}
async function repay(page,id,amount,phase='노출 기록 · DRAWN'){
 await page.locator('#repay-amount').fill(String(amount));
 await acceptedClick(page,'상환 메모 기록','repay',phase,id);
}
async function closeCase(page,id){
 await acceptedClick(page,'노출 종결','close','종결 · CLOSED',id);
}
function caseRow(page,id){return page.locator('#cases tr').filter({has:page.getByRole('button',{name:`${id} 열기`})});}

test('unknown case query is dropped without inventing a case',async({page})=>{
 await page.goto('/?case=sim-not-a-real-case');
 await expect(page.locator('#notice')).toContainText('합성 데이터');
 await expect(page).not.toHaveURL(/[?&]case=/);
 const state=await(await page.request.get('/api/state')).json();
 const title=await page.locator('#case-title').textContent();
 if(state.cases.length)expect(state.cases.map(c=>c.advance_id)).toContain(title);
 else expect(title).toBe('');
 expect(title).not.toBe('sim-not-a-real-case');
 await page.goto('/?case=not-sim');
 await expect(page.locator('#notice')).toContainText('합성 데이터');
 await expect(page).not.toHaveURL(/[?&]case=/);
 await expect(page.locator('#case-title')).not.toHaveText('not-sim');
});

test('portfolio deep link restores identical case state',async({page})=>{
 const offeredA=await offer(page,'sim-committed',60000);
 const idA=offeredA.result.credit.advance_id;
 await approveBindDraw(page,idA);
 await repay(page,idA,60000);
 await closeCase(page,idA);
 const offeredB=await offer(page,'sim-committed',40000,{navigate:false});
 const idB=offeredB.result.credit.advance_id;
 await approveBindDraw(page,idB);
 await repay(page,idB,10000);
 await expect(outstanding(page)).toHaveText('30,000');
 const rows=page.locator('#cases tr');
 const count=await rows.count();
 expect(count).toBeGreaterThanOrEqual(2);
 for(let i=0;i<count;i++){
  const cells=rows.nth(i).locator('td');
  await expect(cells).toHaveCount(6);
  await expect(cells.nth(4)).toHaveText(/^(UNBOUND|BOUND|MOCK_COMMIT_OBSERVED)$/);
 }
 const rowA=caseRow(page,idA),rowB=caseRow(page,idB);
 await expect(rowA.locator('td').nth(1)).toHaveText('종결');
 await expect(rowA.locator('td').nth(2)).toHaveText('0');
 // reserved_open is the shared claim total, so A's released note still shows B's open reservation.
 await expect(rowA.locator('td').nth(3)).toHaveText('40,000');
 await expect(rowA.locator('td').nth(4)).toHaveText('MOCK_COMMIT_OBSERVED');
 await expect(rowB.locator('td').nth(1)).toHaveText('노출 기록');
 await expect(rowB.locator('td').nth(2)).toHaveText('30,000');
 await expect(rowB.locator('td').nth(3)).toHaveText('40,000');
 await expect(rowB.locator('td').nth(4)).toHaveText('MOCK_COMMIT_OBSERVED');
 await page.getByRole('button',{name:`${idA} 열기`}).click();
 await expect(page).toHaveURL(new RegExp(`[?&]case=${idA}(?:&|$)`));
 await page.getByRole('button',{name:`${idB} 열기`}).click();
 await expect(page).toHaveURL(new RegExp(`[?&]case=${idB}(?:&|$)`));
 await expect(page.locator('#case-title')).toHaveText(idB);
 const title=await page.locator('#case-title').textContent();
 const phase=await page.locator('#phase').textContent();
 const facts=await page.locator('#facts').textContent();
 await page.reload();
 await expect(page.locator('#case-title')).toHaveText(title);
 await expect(page.locator('#phase')).toHaveText(phase);
 await expect(page.locator('#facts')).toHaveText(facts);
 await expect(page).toHaveURL(new RegExp(`[?&]case=${idB}(?:&|$)`));
 await repay(page,idB,30000);
 await closeCase(page,idB);
});

test('advanced UNBOUND journey claims no COMMITTED observation',async({page})=>{
 const offered=await offer(page,'sim-committed',60000);
 const id=offered.result.credit.advance_id;
 await acceptedClick(page,'모의 승인','approve','모의 승인 · APPROVED',id,{exact:true});
 await expect(page.locator('#advanced')).toBeVisible();
 await expect(page.getByRole('button',{name:'모의 노출 기록',exact:true})).toHaveCount(0);
 await page.locator('#advanced summary').click();
 await expect(page.locator('#unbound-draw')).toHaveText('UNBOUND 모의 노출 기록 · no COMMITTED observation claimed');
 const pending=page.waitForResponse(r=>r.url().endsWith('/api/commands')&&r.request().postDataJSON()?.op==='draw');
 await page.locator('#unbound-draw').click();
 const receipt=await(await pending).json();
 expect(receipt.outcome).toBe('ACCEPTED');
 expect(receipt.result.credit.advance_id).toBe(id);
 await expect(page.locator('#phase')).toHaveText('노출 기록 · DRAWN');
 await expect(gate(page)).toHaveText('UNBOUND');
 await expect(page.locator('#case-json')).toContainText('"mock_settlement_commit_observed": false');
 await repay(page,id,60000);
 await closeCase(page,id);
});

test('reconcile replay match leaves UNKNOWN unchanged',async({page})=>{
 const offered=await offer(page,'sim-committed',60000);
 const id=offered.result.credit.advance_id;
 await approveBindDraw(page,id);
 let lostId=null,lostPosts=0;
 await page.route('**/api/commands',async route=>{
  const body=route.request().postDataJSON();
  if(body?.op==='repay'&&!lostId){lostId=body.operation_id;lostPosts+=1;await route.fetch();await route.abort('failed');return;}
  if(lostId&&body?.operation_id===lostId)lostPosts+=1;
  await route.continue();
 });
 await page.locator('#repay-amount').fill('10000');
 await page.getByRole('button',{name:'상환 메모 기록'}).click();
 await expect(page.locator('#recovery')).toBeVisible();
 await expect(page.locator('#notice')).toContainText('UNKNOWN');
 await page.getByRole('button',{name:'원 요청 결과 조회'}).click();
 await expect(page.locator('#recovery')).toBeHidden();
 await expect(outstanding(page)).toHaveText('50,000');
 await expect(page.locator('#repay-amount')).toHaveValue('50000');
 await repay(page,id,50000);
 await closeCase(page,id);
 await page.getByRole('button',{name:'저널 재생 검증'}).click();
 await expect(page.locator('#reconcile-result')).toContainText('재생 일치');
 await expect(page.locator('#reconcile-result')).toContainText('UNKNOWN을 해소하지 않습니다');
 const state=await(await page.request.get('/api/state')).json();
 const unknown=await(await page.request.get(`/api/operations/absent-portfolio-op?instance_id=${encodeURIComponent(state.instance_id)}`)).json();
 expect(unknown.outcome).toBe('UNKNOWN');
 expect(lostPosts).toBe(1);
});

test('default shows synthetic loss labels',async({page})=>{
 const offered=await offer(page,'sim-committed',60000);
 const id=offered.result.credit.advance_id;
 await approveBindDraw(page,id);
 await repay(page,id,10000);
 await expect(outstanding(page)).toHaveText('50,000');
 await acceptedClick(page,'미이행 메모','default','미이행 메모 · DEFAULTED',id);
 await expect(fact(page,/^미회수 모의 노출\(합성\)$/)).toHaveText('50,000');
 await expect(fact(page,/^미이행 사유\(합성\)$/)).toHaveText('synthetic-operator-scenario');
 const help=await page.locator('#next-help').innerText();
 expect(help).toContain('정의되지 않았습니다');
 expect(help).not.toMatch(/이자율|수수료|손실률/);
 expect(await page.locator('#facts').innerText()).not.toMatch(/이자율|수수료|손실률/);
});

test('keyboard order and 375px layout',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.setViewportSize({width:375,height:667});
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#fixture').focus();await page.keyboard.press('Tab');await expect(page.locator('#amount')).toBeFocused();
 await offer(page,'sim-committed',1000,{navigate:false});
 const approved=await offer(page,'sim-committed',2000,{navigate:false});
 const id=approved.result.credit.advance_id;
 await acceptedClick(page,'모의 승인','approve','모의 승인 · APPROVED',id,{exact:true});
 await expect(page.locator('#advanced')).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 expect(await page.evaluate(()=>[...document.querySelectorAll('[tabindex]')].every(el=>el.tabIndex<=0))).toBe(true);
 const buttons=page.locator('#cases button');
 const count=await buttons.count();
 expect(count).toBeGreaterThan(1);
 await buttons.nth(0).focus();
 for(let i=1;i<count;i++){await page.keyboard.press('Tab');await expect(buttons.nth(i)).toBeFocused();}
 await page.locator('#advanced').evaluate(el=>{el.open=true;});
 await page.locator('#advanced summary').focus();
 await page.keyboard.press('Tab');
 await expect(page.locator('#unbound-draw')).toBeFocused();
 await expect(page.locator('#unbound-draw')).toContainText('no COMMITTED observation claimed');
 await page.screenshot({path:'test-results/capital-mobile.png',fullPage:true});
 await page.setViewportSize({width:1440,height:1100});
 await page.locator('#advanced').evaluate(el=>{el.open=true;});
 await expect(page.locator('#unbound-draw')).toBeVisible();
 await expect(page.locator('#cases tr').first()).toBeVisible();
 await page.screenshot({path:'test-results/capital-desktop.png',fullPage:true});
 expect(errors).toEqual([]);
});
