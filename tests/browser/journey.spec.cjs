const {test,expect}=require('@playwright/test');
async function offer(page,fixture='sim-committed',amount='60000'){
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 await page.locator('#fixture').selectOption(fixture);await page.locator('#amount').fill(amount);
 await page.getByRole('button',{name:'모의 제안 생성'}).click();
 await expect(page.locator('#phase')).toContainText('OFFERED');
}
async function ready(page,fixture){await offer(page,fixture);await page.getByRole('button',{name:'모의 승인',exact:true}).click();await expect(page.locator('#phase')).toContainText('APPROVED');await page.getByRole('button',{name:'정산 근거 연결'}).click();await expect(page.locator('#facts')).toContainText('BOUND');}

test('complete bound lifecycle, repayment and export',async({page})=>{
 await ready(page);await page.getByRole('button',{name:'모의 노출 기록'}).click();await expect(page.locator('#phase')).toContainText('DRAWN');
 await page.locator('#repay-amount').fill('20000');await page.getByRole('button',{name:'상환 메모 기록'}).click();await expect(page.locator('#facts')).toContainText('40,000');
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
 await expect(page.locator('#capabilities')).toContainText('수익참여·채권양수');await expect(page.locator('#capabilities')).toContainText('PRODUCER NOT BOUND');await page.screenshot({path:'test-results/capital-desktop.png',fullPage:true});
});
test('read-only evidence keeps missing financial facts distinct',async({page})=>{
 await page.goto('/');await expect(page.locator('#evidence-rows tr')).toHaveCount(3);await expect(page.locator('#evidence-scope')).toContainText('NOT_BOUND');const value=await(await page.request.get('/api/evidence')).json();expect(value.source_cut).toBeNull();expect(value.unavailable).toContain('actual_paid');expect(value.rows.find(r=>r.claim_id==='sim-refund').refund_outstanding).toBe(10000);
});
