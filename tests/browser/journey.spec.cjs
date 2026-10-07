const {test,expect}=require('@playwright/test');
async function offer(page,fixture='sim-committed',amount='60000'){
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 await page.locator('#fixture').selectOption(fixture);await page.locator('#amount').fill(amount);
 const created=page.waitForResponse(r=>r.url().endsWith('/api/commands')&&r.request().postDataJSON()?.op==='offer');
 await page.getByRole('button',{name:'모의 제안 생성'}).click();
 const receipt=await(await created).json();
 expect(receipt.outcome).toBe('ACCEPTED');
 await expect(page.locator('#case-title')).toHaveText(receipt.result.credit.advance_id);
 await expect(page.locator('#phase')).toHaveText('제안됨 · OFFERED');
}
async function ready(page,fixture){await offer(page,fixture);await page.getByRole('button',{name:'모의 승인',exact:true}).click();await expect(page.locator('#phase')).toContainText('APPROVED');await page.getByRole('button',{name:'정산 근거 연결'}).click();await expect(page.locator('#facts dt').filter({hasText:'정산 게이트'}).locator('xpath=following-sibling::dd[1]')).toHaveText('BOUND');await expect(page.getByRole('button',{name:'모의 노출 기록'})).toBeEnabled();}

test('complete bound lifecycle, repayment and export',async({page})=>{
 await ready(page);await page.getByRole('button',{name:'모의 노출 기록'}).click();await expect(page.locator('#phase')).toContainText('DRAWN');
 await page.locator('#repay-amount').fill('20000');await page.getByRole('button',{name:'상환 메모 기록'}).click();await expect(page.locator('#facts dt').filter({hasText:'남은 모의 노출'}).locator('xpath=following-sibling::dd[1]')).toHaveText('40,000');
 await page.locator('#repay-amount').fill('40000');await page.getByRole('button',{name:'상환 메모 기록'}).click();await expect(page.getByRole('button',{name:'노출 종결'})).toBeVisible();await page.getByRole('button',{name:'노출 종결'}).click();await expect(page.locator('#phase')).toContainText('CLOSED');
 await page.getByRole('button',{name:'저널 재생 검증'}).click();await expect(page.locator('#notice')).toContainText('저널 재생');
 const data=await (await page.request.get('/api/export')).json();expect(data.replay_matched).toBe(true);expect(data.funds_executed).toBe(false);
});
test('pending settlement and refund are visible refusals',async({page})=>{
 await ready(page,'sim-pending');await page.getByRole('button',{name:'모의 노출 기록'}).click();await expect(page.locator('#notice')).toContainText('SETTLEMENT_NOT_COMMITTED');await expect(page.locator('#phase')).toContainText('APPROVED');
 await page.locator('#fixture').selectOption('sim-refund');await page.getByRole('button',{name:'모의 제안 생성'}).click();await expect(page.locator('#notice')).toContainText('REFUND_OBLIGATION_OPEN');
});
test('accepted response loss fences reload and resolves via receipt GET only',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');let posts=0;
 await page.route('**/api/commands',async route=>{posts++;await route.fetch();await route.abort('failed');});
 await page.getByRole('button',{name:'모의 제안 생성'}).click();await expect(page.locator('#recovery')).toBeVisible();await expect(page.getByRole('button',{name:'모의 제안 생성'})).toBeDisabled();
 await page.reload();await expect(page.locator('#recovery')).toBeVisible();await page.getByRole('button',{name:'원 요청 결과 조회'}).click();await expect(page.locator('#recovery')).toBeHidden();expect(posts).toBe(1);
});
test('pre-application loss remains UNKNOWN and blocks new commands',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');let posts=0;
 await page.route('**/api/commands',async route=>{posts++;await route.abort('failed');});
 await page.getByRole('button',{name:'모의 제안 생성'}).click();await page.getByRole('button',{name:'원 요청 결과 조회'}).click();await expect(page.locator('#notice')).toContainText('UNKNOWN');await expect(page.getByRole('button',{name:'모의 제안 생성'})).toBeDisabled();expect(posts).toBe(1);
});
test('mobile layout, keyboard focus and no browser errors',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#fixture').focus();await page.keyboard.press('Tab');await expect(page.locator('#amount')).toBeFocused();
 await page.screenshot({path:'test-results/capital-mobile.png',fullPage:true});expect(errors).toEqual([]);
});
test('desktop overview screenshot and status separation',async({page})=>{
 await page.setViewportSize({width:1440,height:1100});await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 await expect(page.locator('#capabilities')).toContainText('수익참여·채권 매입·담보 상품');await expect(page.locator('#readiness-integrity')).toContainText('NOT_BOUND');await page.screenshot({path:'test-results/capital-desktop.png',fullPage:true});
});
test('read-only evidence keeps missing financial facts distinct',async({page})=>{
 await page.goto('/');await expect(page.locator('#evidence-rows tr')).toHaveCount(3);await expect(page.locator('#evidence-scope')).toContainText('NOT_BOUND');const value=await(await page.request.get('/api/evidence')).json();expect(value.source_cut).toBeNull();expect(value.unavailable).toContain('actual_paid');expect(value.rows.find(r=>r.claim_id==='sim-refund').refund_outstanding).toBe(10000);
});
test('malformed accepted receipt stays UNKNOWN until verified original is read',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 await page.route('**/api/commands',async route=>{const r=await route.fetch();const body=await r.json();delete body.result;await route.fulfill({response:r,json:body});});
 await page.getByRole('button',{name:'모의 제안 생성'}).click();await expect(page.locator('#recovery')).toBeVisible();await expect(page.getByRole('button',{name:'모의 제안 생성'})).toBeDisabled();await page.getByRole('button',{name:'원 요청 결과 조회'}).click();await expect(page.locator('#recovery')).toBeHidden();
});
test('two tabs serialize a delayed recovery and preserve the next unknown request',async({page,context})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 await page.route('**/api/commands',async route=>{await route.fetch();await route.abort('failed');});
 await page.getByRole('button',{name:'모의 제안 생성'}).click();await expect(page.locator('#recovery')).toBeVisible();
 const other=await context.newPage();await other.goto('/');await expect(other.locator('#recovery')).toBeVisible();
 let release;const gate=new Promise(resolve=>release=resolve);let seen;const requested=new Promise(resolve=>seen=resolve);
 await page.route('**/api/operations/**',async route=>{const response=await route.fetch();seen();await gate;await route.fulfill({response});});
 await page.getByRole('button',{name:'원 요청 결과 조회'}).click();await requested;
 await other.getByRole('button',{name:'원 요청 결과 조회'}).click();await expect(other.locator('#notice')).toContainText('다른 탭');await expect(other.getByRole('button',{name:'모의 제안 생성'})).toBeDisabled();
 release();await expect(page.locator('#recovery')).toBeHidden();await expect(other.locator('#recovery')).toBeHidden();
 await other.route('**/api/commands',route=>route.abort('failed'));
 await other.getByRole('button',{name:'모의 제안 생성'}).click();await expect(other.locator('#recovery')).toBeVisible();await expect(page.locator('#recovery')).toBeVisible();
 const record=await page.evaluate(()=>JSON.parse(localStorage.getItem('kix-capital-pending-v1')));expect(record.op).toBe('offer');await expect(page.getByRole('button',{name:'모의 제안 생성'})).toBeDisabled();
});
test('old process acknowledgment never resends previous command',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 await page.evaluate(()=>localStorage.setItem('kix-capital-pending-v1',JSON.stringify({instance_id:'previous-process',operation_id:'old-operation',op:'draw',advance_id:'sim-old',args:{}})));
 let posts=0;page.on('request',r=>{if(r.method()==='POST')posts++;});await page.reload();await expect(page.getByRole('button',{name:'모의 제안 생성'})).toBeDisabled();await page.getByRole('button',{name:'서버 재시작 확인'}).click();await expect(page.locator('#recovery')).toBeHidden();await expect(page.locator('#notice')).toContainText('이전 세션 결과는 UNKNOWN');expect(posts).toBe(0);
});
test('unavailable storage fails closed before POST',async({page})=>{
 await page.addInitScript(()=>{Storage.prototype.setItem=()=>{throw new Error('blocked');};});
 let posts=0;page.on('request',r=>{if(r.method()==='POST')posts++;});await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');await page.getByRole('button',{name:'모의 제안 생성'}).click();await expect(page.getByRole('button',{name:'모의 제안 생성'})).toBeDisabled();expect(posts).toBe(0);
});
test('scenario comparison and refund recovery remain read only',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');let posts=0;page.on('request',r=>{if(r.method()==='POST')posts++;});
 const before=await(await page.request.get('/api/state')).json();
 await page.locator('#scenario-select').selectOption('shortfall-platform');await expect(page.locator('#scenario-comparison')).toContainText('주최자 우선');await expect(page.locator('#scenario-comparison')).toContainText('3,000');
 await page.locator('#scenario-select').selectOption('full-after');await expect(page.locator('#scenario-diagnostic')).toContainText('REFUND_ACCEPTANCE_EXCEEDS_OBLIGATION');await expect(page.locator('#scenario-facts')).toContainText('97,000');
 const final=page.locator('#scenario-facts dt').filter({hasText:'은행 반환 종결'}).locator('xpath=following-sibling::dd[1]');await expect(final).toHaveText('false');
 await page.locator('#scenario-steps button').first().click();await expect(page.locator('#scenario-step-title')).toContainText('아직 현금 없음');
 const after=await(await page.request.get('/api/state')).json();expect(after.state_digest).toBe(before.state_digest);expect(after.operation_count).toBe(before.operation_count);expect(posts).toBe(0);await page.screenshot({path:'test-results/capital-scenarios.png',fullPage:true});
});
test('readiness separates local capability from actual blocking dependencies',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 await page.locator('#readiness-filter').selectOption('DECISION_REQUIRED');await expect(page.locator('#capabilities article')).toHaveCount(1);await expect(page.locator('#capabilities')).toContainText('수익·원가 정의');
 await page.locator('#readiness-filter').selectOption('UPSTREAM_REQUIRED');await expect(page.locator('#capabilities')).toContainText('stage5/6');await expect(page.locator('#capabilities')).toContainText('SEMANTIC_CONFORMANCE');
 await page.locator('#readiness-filter').selectOption('AVAILABLE_LOCAL');await expect(page.locator('#capabilities article')).toHaveCount(1);await expect(page.locator('#capabilities')).toContainText('로컬 합성 프로파일만');
});
test('draw preview refuses pending settlement without creating active effects',async({page})=>{
 await ready(page,'sim-pending');const before=await(await page.request.get('/api/state')).json();let posts=0;page.on('request',r=>{if(r.method()==='POST')posts++;});
 await page.getByRole('button',{name:'읽기 전용 인출 사전점검'}).click();await expect(page.locator('#preview-result')).toContainText('SETTLEMENT_NOT_COMMITTED');
 const after=await(await page.request.get('/api/state')).json();expect(after.state_digest).toBe(before.state_digest);expect(after.operation_count).toBe(before.operation_count);expect(posts).toBe(0);
});
test('late scenario response cannot replace the selected scenario',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 let release;const gate=new Promise(resolve=>release=resolve);let seen;const started=new Promise(resolve=>seen=resolve);
 await page.route('**/api/scenarios/full-after',async route=>{const response=await route.fetch();seen();await gate;await route.fulfill({response});});
 await page.locator('#scenario-select').selectOption('full-after');await started;await page.locator('#scenario-select').selectOption('partial-before');await expect(page.locator('#scenario-diagnostic')).toContainText('DISTRIBUTION_BLOCKED_REFUND_BEARER_UNDEFINED');
 release();await expect(page.locator('#scenario-select')).toHaveValue('partial-before');await expect(page.locator('#scenario-description')).toContainText('환불 부담자가 미정');
});
