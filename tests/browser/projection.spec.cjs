const {test, expect} = require('@playwright/test');

async function accepted(page, name, op, phase) {
  const pending = page.waitForResponse(r => r.url().endsWith('/api/commands') && r.request().postDataJSON()?.op === op);
  await page.getByRole('button', {name, exact: true}).click();
  const receipt = await (await pending).json();
  expect(receipt.outcome).toBe('ACCEPTED');
  await expect(page.locator('#phase')).toHaveText(phase);
  return receipt;
}

test('projection panel balances after draw and repay', async ({page}) => {
  await page.goto('/');
  await expect(page.locator('#notice')).toContainText('합성 데이터');
  await expect(page.locator('#projection')).toContainText('SYNTHETIC_UNADOPTED');
  await expect(page.locator('#projection')).toContainText('NOT_BOUND');
  await page.locator('#fixture').selectOption('sim-committed');
  await page.locator('#amount').fill('60000');
  const created = page.waitForResponse(r => r.url().endsWith('/api/commands') && r.request().postDataJSON()?.op === 'offer');
  await page.getByRole('button', {name: '모의 제안 생성'}).click();
  const offer = await (await created).json();
  expect(offer.outcome).toBe('ACCEPTED');
  await accepted(page, '모의 승인', 'approve', '모의 승인 · APPROVED');
  await accepted(page, '정산 근거 연결', 'bind_settlement', '모의 승인 · APPROVED');
  await accepted(page, '모의 노출 기록', 'draw', '노출 기록 · DRAWN');
  await expect(page.locator('#projection-body')).toBeVisible();
  await expect(page.locator('#projection-debit')).toHaveText('360,000');
  await expect(page.locator('#projection-credit')).toHaveText('360,000');
  await expect(page.locator('#projection')).toContainText('차변');
  await expect(page.locator('#projection')).toContainText('대변');
  const state = await (await page.request.get('/api/state')).json();
  await expect(page.locator('#projection-cut')).toContainText(state.state_digest);
  expect(state.funds_executed).toBe(false);
  await page.locator('#repay-amount').fill('20000');
  await accepted(page, '상환 메모 기록', 'repay', '노출 기록 · DRAWN');
  const memo = page.locator('#projection-accounts tr').filter({hasText: 'SIM_REPAY_MEMO'});
  await expect(memo).toContainText('20,000');
  await expect(page.locator('#projection-debit')).toHaveText('380,000');
  await expect(page.locator('#projection-credit')).toHaveText('380,000');
});

test('projection read failure leaves commands available', async ({page}) => {
  await page.route('**/api/projection', route => route.abort());
  await page.goto('/');
  await expect(page.locator('#projection-error')).toBeVisible();
  await expect(page.locator('#projection-error')).toContainText('투영');
  await expect(page.locator('#projection-body')).toBeHidden();
  await expect(page.locator('#projection')).toContainText('SYNTHETIC_UNADOPTED');
  await expect(page.getByRole('button', {name: '모의 제안 생성'})).toBeEnabled();
  let posts = 0;
  page.on('request', request => { if (request.method() === 'POST') posts += 1; });
  await page.getByRole('button', {name: '모의 제안 생성'}).click();
  await expect(page.locator('#phase')).toContainText('OFFERED');
  expect(posts).toBe(1);
});
