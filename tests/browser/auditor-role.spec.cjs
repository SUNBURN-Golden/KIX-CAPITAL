const fs = require('fs');
const {test, expect} = require('@playwright/test');

const ops = ['offer','approve','reject','cancel','bind_settlement','draw','repay','close','default','reconcile'];

async function switchRole(page, role){
  const seen = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
  await page.locator('#role').selectOption(role);
  const response = await seen;
  const session = await response.json();
  expect(response.ok()).toBeTruthy();
  expect(session.role).toBe(role);
  expect(session.identity).toBe('NOT_BOUND');
  expect(session.authentication).toBe('NOT_BOUND');
  expect(session.role_provenance).toBe('SYNTHETIC_LOCAL_ROLE');
  expect(session.local_token).toEqual(expect.any(String));
  expect(response.request().postDataJSON()).toEqual({role});
  await expect(page.locator('#role-status')).toContainText(role);
  await expect(page.locator('#role-reason')).toContainText(role);
  return session;
}

test('auditor session blocks every write and still reads export and reconciliation', async ({page}) => {
  let advanceId;
  let posts = 0;
  let sessionPosts = 0;
  page.on('request', request => {
    if (request.method() !== 'POST') return;
    posts += 1;
    if (new URL(request.url()).pathname === '/api/session') sessionPosts += 1;
  });
  try {
    await page.goto('/');
    await expect(page.locator('#notice')).toContainText('합성 데이터');
    await expect(page.locator('#role')).toHaveValue('organizer');
    const scenarioOptions = await page.locator('#scenario-select option').count();
    const offered = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op === 'offer');
    await page.getByRole('button', {name: '모의 제안 생성'}).click();
    const offer = await (await offered).json();
    expect(offer.outcome).toBe('ACCEPTED');
    expect(offer.role).toBe('organizer');
    expect(offer.role_provenance).toBe('SYNTHETIC_LOCAL_ROLE');
    advanceId = offer.result.credit.advance_id;
    await expect(page.locator('#case-title')).toHaveText(advanceId);
    await page.getByRole('button', {name: '모의 승인', exact: true}).click();
    await expect(page.locator('#phase')).toContainText('APPROVED');
    const bound = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op === 'bind_settlement');
    await page.getByRole('button', {name: '정산 근거 연결'}).click();
    const bindReceipt = await (await bound).json();
    expect(bindReceipt.outcome).toBe('ACCEPTED');
    expect(bindReceipt.result.applied).toBe('bind_settlement');
    expect(bindReceipt.result.credit.advance_id).toBe(advanceId);
    await expect(page.locator('#phase')).toContainText('APPROVED');
    await expect(page.getByRole('button', {name: '모의 노출 기록', exact: true})).toBeEnabled();
    const prepared = await (await page.request.get('/api/state')).json();
    const operationCount = prepared.operation_count;
    const stateDigest = prepared.state_digest;
    const postsBeforeAuditor = posts;
    const sessionsBeforeAuditor = sessionPosts;

    const session = await switchRole(page, 'auditor');
    expect(await page.locator('#scenario-select option').count()).toBe(scenarioOptions);
    await expect(page.locator('#projection-body')).toBeVisible();
    const auditorState = await (await page.request.get('/api/state', {headers: {'X-Capital-Token': session.local_token}})).json();
    expect(auditorState.auth.role).toBe('auditor');
    expect(auditorState.auth.identity).toBe('NOT_BOUND');
    expect(auditorState.auth.mode).toBe('LOCAL_SYNTHETIC_ROLES');
    expect(auditorState.operation_count).toBe(operationCount);
    expect(auditorState.state_digest).toBe(stateDigest);

    const controls = page.locator('#offer-form button, #offer-form input, #offer-form select, #actions button, #repay, #unbound-draw');
    const count = await controls.count();
    expect(count).toBeGreaterThan(0);
    for (let index = 0; index < count; index += 1) {
      await expect(controls.nth(index)).toBeDisabled();
      expect(await controls.nth(index).getAttribute('title')).toBeTruthy();
    }
    await expect(page.locator('#role-reason')).toContainText('auditor');
    const postsAtFence = posts;
    await page.evaluate(() => {
      const button = document.querySelector('#actions button');
      button.disabled = false;
      button.click();
    });
    expect(posts).toBe(postsAtFence);
    await expect(page.locator('#notice')).toContainText('역할 경계');

    const probed = await page.evaluate(async ({advanceId, token, instanceId}) => {
      const ops = ['offer','approve','reject','cancel','bind_settlement','draw','repay','close','default','reconcile'];
      const rows = [];
      for (const op of ops) {
        const args = op === 'offer' ? {fixture_id: 'sim-committed', amount: 100} : op === 'repay' ? {amount: 1, sequence: 1} : {};
        const response = await fetch('/api/commands', {
          method: 'POST',
          headers: {'Content-Type': 'application/json', 'X-Capital-Token': token},
          body: JSON.stringify({instance_id: instanceId, operation_id: crypto.randomUUID(), op, advance_id: advanceId, args}),
        });
        rows.push({status: response.status, ...(await response.json())});
      }
      const after = await (await fetch('/api/state', {headers: {'X-Capital-Token': token}})).json();
      return {rows, operation_count: after.operation_count, state_digest: after.state_digest};
    }, {advanceId, token: auditorState.local_token, instanceId: auditorState.instance_id});
    expect(probed.rows).toHaveLength(ops.length);
    for (const row of probed.rows) {
      expect(row.status).toBe(403);
      expect(row.error).toBe('ROLE_FORBIDDEN');
      expect(row.role).toBe('auditor');
    }
    expect(probed.operation_count).toBe(operationCount);
    expect(probed.state_digest).toBe(stateDigest);
    expect(sessionPosts - sessionsBeforeAuditor).toBe(1);
    expect(posts - postsBeforeAuditor).toBe(ops.length + 1);

    const [download] = await Promise.all([
      page.waitForEvent('download'),
      page.locator('#export-journal').click(),
    ]);
    const exported = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
    expect(exported.replay_matched).toBe(true);
    expect(exported.funds_executed).toBe(false);
    await page.locator('#reconcile-readonly').click();
    await expect(page.locator('#reconciliation-result')).toContainText('재생 일치');
    await expect(page.locator('#reconciliation-result')).toContainText('은행 대사 아님');
    expect(posts - postsBeforeAuditor).toBe(ops.length + 1);
    const afterReads = await (await page.request.get('/api/state')).json();
    expect(afterReads.operation_count).toBe(operationCount);
    expect(afterReads.state_digest).toBe(stateDigest);

    await switchRole(page, 'observer');
    await expect(page.locator('#export-journal')).toBeDisabled();
    await expect(page.locator('#reconcile-readonly')).toBeDisabled();
    await expect(page.locator('#preview-draw')).toBeDisabled();
    await expect(page.locator('#projection-body')).toBeHidden();
    await expect(page.locator('#projection-error')).toContainText('observer');
    await expect(page.locator('#evidence-scope')).toContainText('observer');
    expect(await page.locator('#export-journal').getAttribute('title')).toBeTruthy();
    expect(await page.locator('#reconcile-readonly').getAttribute('title')).toBeTruthy();
    await expect(page.locator('#role-reason')).toContainText('observer');
    const postsAtObserver = posts;
    await page.locator('#export-journal').evaluate(button => { button.disabled = false; button.click(); });
    expect(posts).toBe(postsAtObserver);
    await expect(page.locator('#notice')).toContainText('역할 경계');

    await switchRole(page, 'organizer');
    await expect(page.getByRole('button', {name: '모의 노출 기록', exact: true})).toBeEnabled();
    await expect(page.locator('#export-journal')).toBeEnabled();
    await expect(page.locator('#reconcile-readonly')).toBeEnabled();
    await expect(page.locator('#offer-form button')).toBeEnabled();
  } finally {
    if (!advanceId) return;
    if (await page.locator('#role').inputValue() !== 'organizer') await switchRole(page, 'organizer');
    const phase = page.locator('#phase');
    if (await phase.isVisible() && !(await phase.textContent()).includes('CANCELLED')) {
      await page.getByRole('button', {name: '제안 취소'}).click();
      await expect(phase).toContainText('CANCELLED');
    }
  }
});
