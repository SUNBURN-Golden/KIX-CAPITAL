const {test,expect}=require('@playwright/test');

test('offer fences existing actions before the asynchronous writer lock is granted',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 await page.getByRole('button',{name:'모의 제안 생성'}).click();
 await expect(page.locator('#phase')).toContainText('OFFERED');
 await expect(page.getByRole('button',{name:'모의 승인',exact:true})).toBeEnabled();
 const before=await page.locator('#case-title').textContent();
 const fenced=await page.evaluate(()=>{
  document.querySelector('#offer-form button').click();
  return [...document.querySelectorAll('#offer-form input,#offer-form button,#actions button')].every(b=>b.disabled);
 });
 expect(fenced).toBe(true);
 await expect(page.locator('#case-title')).not.toHaveText(before);
 await page.getByRole('button',{name:'모의 승인',exact:true}).click();
 await expect(page.locator('#phase')).toContainText('APPROVED');
});

test('command keeps inputs fenced throughout the post-receipt refresh',async({page})=>{
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 let release,seen;const gate=new Promise(r=>release=r),requested=new Promise(r=>seen=r);
 await page.route('**/api/evidence',async route=>{const response=await route.fetch();seen();await gate;await route.fulfill({response});});
 await page.getByRole('button',{name:'모의 제안 생성'}).click();await requested;
 try {
  // Storage events from another tab must not unlock this tab during its refresh.
  await page.evaluate(()=>window.dispatchEvent(new StorageEvent('storage',{key:'kix-capital-pending-v1'})));
  await expect(page.locator('#amount')).toBeDisabled();
 } finally { release(); }
 await expect(page.locator('#amount')).toBeEnabled();
 await page.getByRole('button',{name:'모의 승인',exact:true}).click();
 await expect(page.locator('#phase')).toContainText('APPROVED');
});

async function newOffer(page){
 await page.goto('/');await expect(page.locator('#notice')).toContainText('합성 데이터');
 const response=page.waitForResponse(r=>r.url().endsWith('/api/commands')&&r.request().postDataJSON()?.op==='offer');
 await page.getByRole('button',{name:'모의 제안 생성'}).click();const receipt=await(await response).json();
 await expect(page.locator('#case-title')).toHaveText(receipt.result.credit.advance_id);
 await expect(page.getByRole('button',{name:'모의 승인',exact:true})).toBeEnabled();
 return receipt.result.credit.advance_id;
}

test('manual refresh fences commands and case selection until its snapshot is complete',async({page})=>{
 const id=await newOffer(page);let release,seen;const gate=new Promise(r=>release=r),captured=new Promise(r=>seen=r);let intercepted=false;
 await page.route('**/api/state',async route=>{if(intercepted)return route.continue();intercepted=true;const response=await route.fetch();seen();await gate;await route.fulfill({response});});
 let posts=0;page.on('request',r=>{if(r.method()==='POST')posts++;});
 await page.locator('#refresh').click();await captured;
 try{
  await expect(page.getByRole('button',{name:'모의 승인',exact:true})).toBeDisabled();
  await expect(page.locator('#refresh')).toBeDisabled();
  expect(await page.locator('#cases button').evaluateAll(rows=>rows.every(b=>b.disabled))).toBe(true);
  await page.evaluate(()=>document.querySelector('#actions button').click());expect(posts).toBe(0);
 }finally{release();}
 await expect(page.locator('#refresh')).toBeEnabled();
 await page.getByRole('button',{name:'모의 승인',exact:true}).click();
 await expect(page.locator('#phase')).toHaveText('모의 승인 · APPROVED');
 const state=await(await page.request.get('/api/state')).json();
 expect(state.cases.find(c=>c.advance_id===id).phase).toBe('APPROVED');expect(posts).toBe(1);
});

test('manual refresh preserves a repayment draft and submits exactly the entered amount',async({page})=>{
 await newOffer(page);
 await page.getByRole('button',{name:'모의 승인',exact:true}).click();
 await page.getByRole('button',{name:'정산 근거 연결'}).click();
 await page.getByRole('button',{name:'모의 노출 기록'}).click();
 await page.locator('#repay-amount').fill('20000');
 let release,seen;const gate=new Promise(r=>release=r),captured=new Promise(r=>seen=r);
 await page.route('**/api/evidence',async route=>{const response=await route.fetch();seen();await gate;await route.fulfill({response});});
 await page.locator('#refresh').click();await captured;
 try{await expect(page.locator('#repay-amount')).toBeDisabled();await expect(page.locator('#repay')).toBeDisabled();}finally{release();}
 await expect(page.locator('#repay-amount')).toBeEnabled();await expect(page.locator('#repay-amount')).toHaveValue('20000');
 const response=page.waitForResponse(r=>r.url().endsWith('/api/commands')&&r.request().postDataJSON()?.op==='repay');
 await page.locator('#repay').click();const result=await response;
 expect(result.request().postDataJSON().args.amount).toBe(20000);
 expect((await result.json()).result.credit.outstanding_exposure).toBe(40000);
 await expect(page.locator('#repay-amount')).toHaveValue('40000');
 // Close the synthetic advance so the shared fixture has no reservation for the next test.
 await page.locator('#repay').click();await page.getByRole('button',{name:'노출 종결'}).click();
 await expect(page.locator('#phase')).toHaveText('종결 · CLOSED');
});

test('initial loading fences forms until state and evidence are both validated',async({page})=>{
 let release,seen;const gate=new Promise(r=>release=r),captured=new Promise(r=>seen=r);
 await page.route('**/api/evidence',async route=>{const response=await route.fetch();seen();await gate;await route.fulfill({response});});
 let posts=0;page.on('request',r=>{if(r.method()==='POST')posts++;});
 await page.goto('/');await captured;
 try{
  await expect(page.locator('#amount')).toBeDisabled();await expect(page.locator('#refresh')).toBeDisabled();
  await page.evaluate(()=>document.querySelector('#offer-form button').click());expect(posts).toBe(0);
 }finally{release();}
 await expect(page.locator('#notice')).toContainText('합성 데이터');await expect(page.locator('#amount')).toBeEnabled();
});
