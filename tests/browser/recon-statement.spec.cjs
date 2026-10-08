const {test, expect} = require('@playwright/test');

const CHECKS = [
  'receipts_vs_journal_keys',
  'rejected_receipts_absent_from_journal',
  'replay_digest_equals_state_digest',
  'case_fixture_map_vs_journal_offers',
  'projection_totals_vs_case_views',
  'fixtures_digest',
];

async function accepted(page, name, op, phase) {
  const pending = page.waitForResponse(r => r.url().endsWith('/api/commands') && r.request().postDataJSON()?.op === op);
  await page.getByRole('button', {name, exact: true}).click();
  const receipt = await (await pending).json();
  expect(receipt.outcome).toBe('ACCEPTED');
  await expect(page.locator('#phase')).toHaveText(phase);
  return receipt;
}

test('reconciliation and statement panels stay read-only and unsummed', async ({page}) => {
  await page.goto('/');
  await expect(page.locator('#notice')).toContainText('합성 데이터');
  await expect(page.locator('#reconciliation-panel')).toContainText('NOT_BOUND');
  await expect(page.locator('#statement')).toContainText('합산하지 않습니다');
  await expect(page.locator('#recon-body')).toBeVisible();
  await expect(page.locator('#statement-body')).toBeVisible();
  const rows = page.locator('#recon-checks tr');
  await expect(rows).toHaveCount(CHECKS.length);
  for (const id of CHECKS) {
    await expect(rows.filter({hasText: id})).toContainText('MATCHED');
  }
  for (const gap of ['bank_pg_provider_observations', 'source_cut', 'completeness']) {
    await expect(page.locator('#recon-gaps')).toContainText(gap);
    await expect(page.locator('#recon-gaps')).toContainText('NOT_BOUND');
  }
  await expect(page.locator('#recon-unknown')).toContainText('UNKNOWN_UNRESOLVED');
  await expect(page.locator('#recon-scope')).toContainText('capacity_bound=');
  await expect(page.locator('#recon-scope')).toContainText('source_cut=NOT_BOUND');
  await expect(page.locator('#statement-sales')).toContainText('primary_sales');
  await expect(page.locator('#statement-sales')).toContainText('resale_sales');
  await expect(page.locator('#statement-sales')).toContainText('actual_paid');
  await expect(page.locator('#statement-sales')).toContainText('NOT_BOUND');
  await expect(page.locator('#statement-sales')).toContainText('합산하지 않습니다');
  await expect(page.locator('#statement-scope')).toContainText('NOT_SUMMED');
  await expect(page.locator('#statement-refund')).toContainText('10,000');

  const before = await (await page.request.get('/api/state')).json();
  const probed = await (await page.request.get('/api/reconciliation?operation_id=absent-browser')).json();
  const statement = await (await page.request.get('/api/statement')).json();
  const afterReads = await (await page.request.get('/api/state')).json();
  expect(probed.unknown_unresolved[0]).toMatchObject({
    operation_id: 'absent-browser', outcome: 'UNKNOWN_UNRESOLVED', retry_authorized: false, resolved: false,
  });
  expect(probed.status).toBe('MATCHED');
  expect(statement.sales_combined).toBe(false);
  expect(statement.primary_and_resale).toBe('NOT_SUMMED');
  expect(statement.not_bound.map(row => row.id)).toEqual(['primary_sales', 'resale_sales', 'actual_paid']);
  expect(afterReads.operation_count).toBe(before.operation_count);
  expect(afterReads.state_digest).toBe(before.state_digest);
  const stillUnknown = await (await page.request.get(`/api/operations/absent-browser?instance_id=${before.instance_id}`)).json();
  expect(stillUnknown.outcome).toBe('UNKNOWN');
  expect(stillUnknown.retry_authorized).toBe(false);

  await page.locator('#fixture').selectOption('sim-committed');
  await page.locator('#amount').fill('60000');
  const created = page.waitForResponse(r => r.url().endsWith('/api/commands') && r.request().postDataJSON()?.op === 'offer');
  await page.getByRole('button', {name: '모의 제안 생성'}).click();
  const offer = await (await created).json();
  expect(offer.outcome).toBe('ACCEPTED');
  await accepted(page, '모의 승인', 'approve', '모의 승인 · APPROVED');
  await accepted(page, '정산 근거 연결', 'bind_settlement', '모의 승인 · APPROVED');
  await accepted(page, '모의 노출 기록', 'draw', '노출 기록 · DRAWN');
  await expect(page.locator('#statement-approved')).toContainText('60,000');
  await expect(page.locator('#statement-approved-total')).toContainText('60,000');
  await expect(page.locator('#statement-exposure')).toContainText('60,000');
  await expect(page.locator('#statement-exposure-total')).toContainText('60,000');
  await expect(page.locator('#recon-checks tr').filter({hasText: 'fixtures_digest'})).toContainText('MATCHED');
  const drawn = await (await page.request.get('/api/statement')).json();
  expect(drawn.categories.find(row => row.id === 'approved').total).toBe(60000);
  expect(drawn.categories.find(row => row.id === 'exposure').drawn).toBe(60000);
  expect(drawn.sales_combined).toBe(false);
  const digest = drawn.state_digest;
  const count = drawn.operation_capacity;
  expect(count).toBe(afterReads.operation_capacity);
  const quiet = await (await page.request.get('/api/state')).json();
  expect(quiet.state_digest).toBe(digest);
  await page.locator('#reconcile-readonly').click();
  await expect(page.locator('#reconciliation-result')).toContainText('재생 일치');
  await expect(page.locator('#reconciliation-result')).toContainText('은행 대사 아님');
  const finalState = await (await page.request.get('/api/state')).json();
  expect(finalState.state_digest).toBe(digest);
  expect(finalState.operation_count).toBe(quiet.operation_count);
});
