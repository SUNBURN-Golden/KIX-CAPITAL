const fs = require('fs');
const {test, expect} = require('@playwright/test');

async function switchRole(page, role) {
  const seen = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
  await page.locator('#role').selectOption(role);
  const response = await seen;
  const session = await response.json();
  expect(response.ok()).toBeTruthy();
  expect(session.role).toBe(role);
  await expect(page.locator('#role-status')).toContainText(role);
  return session;
}

test('manifest download states the local limits and observer cannot export', async ({page}) => {
  await page.goto('/');
  await expect(page.locator('#notice')).toContainText('합성 데이터');
  await expect(page.locator('#export-manifest')).toBeEnabled();
  const before = await (await page.request.get('/api/state')).json();
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('#export-manifest').click(),
  ]);
  expect(download.suggestedFilename()).toBe('capital-export-manifest.json');
  const manifest = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
  expect(manifest.format).toBe('KIX_CAPITAL_EXPORT_MANIFEST_V2');
  expect(manifest.funds_executed).toBe(false);
  expect(manifest.stage7_authenticated_export).toBe(false);
  expect(manifest.authentication).toBe('NOT_BOUND');
  expect(manifest.cursor).toBeNull();
  expect(manifest.watermark).toBeNull();
  expect(manifest.source_cut).toBeNull();
  expect(manifest.signature.status).toBe('NOT_BOUND');
  expect(manifest.signature.value).toBeNull();
  expect(manifest.signature).not.toHaveProperty('key');
  for (const name of ['journal', 'receipts', 'projection', 'reconciliation', 'statement', 'fixtures', 'source_pin']) {
    expect(manifest.sections[name].sha256).toMatch(/^[0-9a-f]{64}$/);
  }
  expect(manifest.content_digest).toMatch(/^[0-9a-f]{64}$/);
  expect(manifest.not_bound.filter(row => ['cursor', 'watermark', 'source_cut'].includes(row.id)).every(row => row.status === 'NOT_BOUND' && row.value === null)).toBe(true);
  await expect(page.locator('#notice')).toContainText('stage7 인증 export가 아니며');
  await expect(page.locator('#notice')).toContainText('무결성만');
  const after = await (await page.request.get('/api/state')).json();
  expect(after.operation_count).toBe(before.operation_count);
  expect(after.state_digest).toBe(before.state_digest);

  await switchRole(page, 'observer');
  await expect(page.locator('#export-manifest')).toBeDisabled();
  await expect(page.locator('#export-journal')).toBeDisabled();
  expect(await page.locator('#export-manifest').getAttribute('title')).toBeTruthy();
  await page.locator('#export-manifest').evaluate(button => { button.disabled = false; button.click(); });
  await expect(page.locator('#notice')).toContainText('역할 경계');
  const observerState = await (await page.request.get('/api/state')).json();
  expect(observerState.operation_count).toBe(before.operation_count);

  const session = await switchRole(page, 'auditor');
  const [auditorDownload] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('#export-manifest').click(),
  ]);
  const auditorManifest = JSON.parse(fs.readFileSync(await auditorDownload.path(), 'utf8'));
  expect(auditorManifest.format).toBe('KIX_CAPITAL_EXPORT_MANIFEST_V2');
  expect(auditorManifest.signature.authentication).toBe('NOT_BOUND');
  const probed = await page.request.get('/api/export/manifest', {headers: {'X-Capital-Token': session.local_token}});
  expect(probed.status()).toBe(200);
  const forbidden = await page.request.get('/api/export', {headers: {'X-Capital-Token': session.local_token}});
  expect(forbidden.status()).toBe(200);
});
