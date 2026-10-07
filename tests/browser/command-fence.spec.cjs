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
