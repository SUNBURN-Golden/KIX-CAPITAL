const {test, expect} = require('@playwright/test');
const {execFileSync, spawn} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const SHOTS = path.join(root, 'test-results', 'terms-policy-ui');
const TERMS_LABEL = 'simulated overlay — not vendor FSM arithmetic, not an offer';
const POLICY_LABEL = 'simulated policy application — not executed distribution, not bank movement';
const UW_LABEL = 'simulated underwriting record — rule checks only, not an approval';
const CHECK_PREFIXES = ['U1', 'U2', 'U3', 'U4', 'U5', 'U6'];

function startServer(port, extra) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-underwrite-'));
  const log = fs.openSync(path.join(directory, 'server.log'), 'a');
  const child = spawn('python3', ['-m', 'capital.server', '--port', String(port), ...extra], {
    cwd: root, stdio: ['ignore', log, log],
  });
  fs.closeSync(log);
  return {child, directory};
}

function stopServer(child) {
  return new Promise(resolve => {
    if (!child || child.exitCode !== null || child.signalCode !== null) return resolve();
    const timer = setTimeout(resolve, 3000);
    child.once('exit', () => { clearTimeout(timer); resolve(); });
    child.kill('SIGKILL');
  });
}

function getJson(port, pathname) {
  return new Promise((resolve, reject) => {
    const req = http.get({hostname: '127.0.0.1', port, path: pathname, timeout: 2000}, response => {
      let data = '';
      response.on('data', chunk => { data += chunk; });
      response.on('end', () => {
        try { resolve({status: response.statusCode, body: JSON.parse(data)}); }
        catch (error) { reject(error); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(Error('timeout')); });
  });
}

async function waitReady(port) {
  const deadline = Date.now() + 8000;
  let last;
  while (Date.now() < deadline) {
    try {
      last = await getJson(port, '/api/state');
      if (last.status === 200 && last.body.instance_id) return last.body;
    } catch (error) { last = String(error); }
    await new Promise(resolve => setTimeout(resolve, 40));
  }
  throw Error('SERVER_NOT_READY ' + JSON.stringify(last));
}

// The seeded book lets the page show cases without the test issuing any command.
function seedWorkspace() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-underwrite-seed-'));
  const workspace = path.join(directory, 'ws');
  execFileSync('python3', ['scripts/seed_demo.py', '--workspace', workspace], {cwd: root, stdio: 'ignore'});
  return {directory, workspace};
}

function watchProblems(page) {
  const problems = [];
  page.on('pageerror', error => problems.push(String(error)));
  page.on('console', message => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (text.includes('favicon.ico')) return;
    problems.push(text);
  });
  return problems;
}

function watchRequests(page) {
  const seen = {posts: [], underwrite: []};
  page.on('request', request => {
    const url = new URL(request.url());
    if (request.method() === 'POST') seen.posts.push(url.pathname);
    else if (url.pathname.startsWith('/api/underwrite/')) seen.underwrite.push(url.pathname + url.search);
  });
  return seen;
}

function factMap(page, selector) {
  return page.locator(selector).evaluate(dl => {
    const out = {};
    const nodes = [...dl.children];
    for (let i = 0; i + 1 < nodes.length; i += 2) out[nodes[i].textContent] = nodes[i + 1].textContent;
    return out;
  });
}

async function shot(locator, name) {
  fs.mkdirSync(SHOTS, {recursive: true});
  const file = path.join(SHOTS, name);
  await locator.scrollIntoViewIfNeeded();
  await locator.screenshot({path: file});
  expect(fs.statSync(file).size).toBeGreaterThan(400);
}

async function switchRole(page, role) {
  const seen = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
  await page.locator('#role').selectOption(role);
  const response = await seen;
  expect(response.ok()).toBeTruthy();
  const session = await response.json();
  expect(session.role).toBe(role);
  await expect(page.locator('#role-status')).toContainText(role);
  return session;
}

function underwriteResponse(page, advanceId) {
  return page.waitForResponse(response => response.request().method() === 'GET' && new URL(response.url()).pathname === `/api/underwrite/${advanceId}`);
}

// Every value on the page is compared with the GET body: the UI adds nothing.
async function expectRecord(page, prefix, record) {
  expect(record.status).toBe('BOUND');
  expect(record.checks.map(check => check.id.slice(0, 2))).toEqual(CHECK_PREFIXES);
  await expect(page.locator(`#${prefix}-label`)).toHaveText(UW_LABEL);
  await expect(page.locator(`#${prefix}-body`)).toBeVisible();
  await expect(page.locator(`#${prefix}-error`)).toBeHidden();
  await expect(page.locator(`#${prefix}-summary`)).toContainText(`proposal ${record.proposal}`);
  await expect(page.locator(`#${prefix}-summary`)).toContainText(record.failed_check ? `failed ${record.failed_check}` : 'failed none');
  const rows = page.locator(`#${prefix}-checks tr`);
  await expect(rows).toHaveCount(record.checks.length);
  for (const [index, check] of record.checks.entries()) {
    const cells = rows.nth(index).locator('td');
    await expect(cells.nth(0)).toContainText(check.id);
    await expect(cells.nth(0)).toContainText(check.rule);
    await expect(cells.nth(1)).toHaveText(check.outcome);
    await expect(cells.nth(2)).toHaveText(JSON.stringify(check.detail));
    if (check.outcome === 'FAIL') await expect(cells.nth(1)).toHaveClass(/mismatch/);
    else await expect(cells.nth(1)).not.toHaveClass(/mismatch/);
  }
  const expected = {
    proposal: record.proposal,
    failed_check: record.failed_check === null ? 'null' : record.failed_check,
    tier: record.tier,
    gate: record.gate,
    phase: record.phase,
    amount: String(record.amount),
    beneficiary_role: record.beneficiary_role,
    two_person_required: String(record.two_person_required),
    decided_by_role: record.decided_by_role,
    sim_day: String(record.sim_day),
    single_advance_krw: String(record.caps_remaining.single_advance_krw),
    beneficiary_aggregate_krw: String(record.caps_remaining.beneficiary_aggregate_krw),
    portfolio_krw: String(record.caps_remaining.portfolio_krw),
    terms_version: record.terms_version,
    rules_version: record.rules_version,
    inputs_digest: record.inputs_digest,
    kyc_executed: 'false',
    underwriting_executed: 'false',
  };
  if (record.borrowing_base) {
    expected.eligible_face = String(record.borrowing_base.eligible_face);
    expected.advance_rate_bps = String(record.borrowing_base.advance_rate_bps);
    expected.base_krw = String(record.borrowing_base.base_krw);
  } else expected.borrowing_base = 'null';
  await expect.poll(() => factMap(page, `#${prefix}-facts`)).toEqual(expected);
}

test('terms card, policy table and the case U1-U6 record render from live GETs with zero POSTs', async ({page}) => {
  test.setTimeout(90000);
  const port = 8895;
  const seeded = seedWorkspace();
  const started = startServer(port, ['--workspace', seeded.workspace]);
  const problems = watchProblems(page);
  const seen = watchRequests(page);
  try {
    const before = await waitReady(port);
    const instance = encodeURIComponent(before.instance_id);
    const response = await page.goto(`http://127.0.0.1:${port}/?case=sim-unbound`);
    const csp = response.headers()['content-security-policy'];
    expect(csp).toContain("script-src 'self'");
    expect(csp).toContain("style-src 'self'");
    expect(csp).not.toMatch(/unsafe-(inline|eval)/);
    await expect(page.locator('#case-title')).toHaveText('sim-unbound');
    await expect(page.locator('#role')).toHaveValue('organizer');

    // terms overlay card: interest, maturity and cap readout, values verbatim from the GET
    await page.locator('#terms-as-of-day').fill('3');
    await page.locator('#terms-as-of-day').blur();
    const overlay = (await getJson(port, `/api/terms/sim-unbound?instance_id=${instance}&draw_day=0&as_of_day=3`)).body;
    expect(overlay.label).toBe(TERMS_LABEL);
    expect(overlay.accrual.status).toBe('BOUND');
    await expect(page.locator('#case-terms-label')).toHaveText(TERMS_LABEL);
    await expect.poll(() => factMap(page, '#case-terms-facts')).toMatchObject({
      interest_krw: String(overlay.accrual.interest_krw),
      exact: overlay.accrual.exact,
      maturity_day: String(overlay.schedule.maturity_day),
      cap_ok: String(overlay.accrual.cap_ok),
      all_in_bps_annual: String(overlay.accrual.all_in_bps_annual),
    });
    await shot(page.locator('#case-terms'), 'desktop-case-terms.png');

    // policy comparison: derived order beside the fixture orders, unsupported rows uncomputed
    const simulation = (await getJson(port, '/api/policy/simulation')).body;
    expect(simulation.label).toBe(POLICY_LABEL);
    await expect(page.locator('#policy-label')).toHaveText(POLICY_LABEL);
    await expect(page.locator('#policy-outcome')).toContainText('DECIDED');
    await expect(page.locator('#policy-head th[data-kind="DECIDED"]')).toHaveCount(1);
    await expect(page.locator('#policy-head th[data-kind="FIXTURE"]')).toHaveCount(2);
    const decided = simulation.comparison.find(column => column.kind === 'DECIDED');
    await expect(page.locator('#policy-head th[data-kind="DECIDED"]')).toContainText(`${decided.id} · ${decided.order.join(' → ')}`);
    const payees = [];
    for (const column of simulation.comparison) for (const line of column.per_payee) if (!payees.includes(line.payee)) payees.push(line.payee);
    await expect(page.locator('#policy-body tr')).toHaveCount(payees.length);
    for (const [columnIndex, column] of simulation.comparison.entries()) {
      await expect(page.locator(`#policy-head th[data-id="${column.id}"]`)).toContainText(column.order.join(' → '));
      for (const [rowIndex, payee] of payees.entries()) {
        const row = page.locator('#policy-body tr').nth(rowIndex);
        await expect(row.locator('th')).toHaveText(payee);
        const line = column.per_payee.find(item => item.payee === payee);
        await expect(row.locator('td').nth(columnIndex)).toHaveText(line ? `${line.distributed} / ${line.face} · 잔여 ${line.outstanding}` : '');
      }
    }
    expect(simulation.unsupported.length).toBeGreaterThan(0);
    const unsupported = page.locator('#policy-unsupported li');
    await expect(unsupported).toHaveCount(simulation.unsupported.length);
    for (const [index, item] of simulation.unsupported.entries()) {
      expect(item.computed).toBe(false);
      await expect(unsupported.nth(index)).toContainText(`${item.item}: UNSUPPORTED_BY_PINNED_FSM · computed false`);
    }
    await shot(page.locator('#policy'), 'desktop-policy.png');

    // case record: an APPROVE record for the DRAWN case
    const approve = (await getJson(port, `/api/underwrite/sim-unbound?instance_id=${instance}&sim_day=0`)).body;
    expect(approve.candidate).toBe(false);
    expect(approve.proposal).toBe('APPROVE');
    await expectRecord(page, 'case-uw', approve);
    await shot(page.locator('#case-underwrite'), 'desktop-case-underwrite-approve.png');

    // another sim_day changes the digest and nothing else is mutated
    const later = (await getJson(port, `/api/underwrite/sim-unbound?instance_id=${instance}&sim_day=5`)).body;
    expect(later.inputs_digest).not.toBe(approve.inputs_digest);
    const dayDone = underwriteResponse(page, 'sim-unbound');
    await page.locator('#underwrite-sim-day').fill('5');
    await page.locator('#underwrite-sim-day').blur();
    await dayDone;
    await expectRecord(page, 'case-uw', later);

    // a DECLINE record: U1 and U3 fail on the captured-not-committed case
    const decline = (await getJson(port, `/api/underwrite/sim-pending-settlement?instance_id=${instance}&sim_day=5`)).body;
    expect(decline.proposal).toBe('DECLINE');
    expect(decline.failed_check).toBe('U1_SETTLEMENT_EVIDENCE');
    const opened = underwriteResponse(page, 'sim-pending-settlement');
    await page.getByRole('button', {name: 'sim-pending-settlement 열기'}).click();
    await opened;
    await expect(page.locator('#case-title')).toHaveText('sim-pending-settlement');
    await expectRecord(page, 'case-uw', decline);
    await expect(page.locator('#case-uw-checks td.mismatch')).toHaveCount(decline.checks.filter(check => check.outcome === 'FAIL').length);
    await shot(page.locator('#case-underwrite'), 'desktop-case-underwrite-decline.png');

    expect(seen.posts).toEqual([]);
    expect(seen.underwrite.every(url => url.includes(`instance_id=${before.instance_id}`))).toBe(true);
    const after = await getJson(port, '/api/state');
    expect(after.body.state_digest).toBe(before.state_digest);
    expect(after.body.operation_count).toBe(before.operation_count);
    expect(problems).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
    fs.rmSync(seeded.directory, {recursive: true, force: true});
  }
});

test('candidate record covers APPROVE, the U1 and U2 declines and refuses invalid input without a request', async ({page}) => {
  test.setTimeout(60000);
  const port = 8896;
  const started = startServer(port, []);
  const problems = watchProblems(page);
  const seen = watchRequests(page);
  try {
    const before = await waitReady(port);
    const instance = encodeURIComponent(before.instance_id);
    await page.goto(`http://127.0.0.1:${port}/#underwrite`);
    await expect(page.locator('#empty')).toBeVisible();
    await expect(page.locator('#case-underwrite')).toBeHidden();

    const record = async (fixture, amount) => (await getJson(port, `/api/underwrite/${fixture}?instance_id=${instance}&sim_day=0&amount=${amount}`)).body;

    const approve = await record('sim-committed', 60000);
    expect(approve.candidate).toBe(true);
    expect(approve.proposal).toBe('APPROVE');
    await expectRecord(page, 'cand-uw', approve);
    await shot(page.locator('#underwrite'), 'desktop-candidate-underwrite-approve.png');

    const pending = await record('sim-pending', 60000);
    expect(pending.failed_check).toBe('U1_SETTLEMENT_EVIDENCE');
    expect(pending.checks[0].detail.reason).toBe('SETTLEMENT_NOT_COMMITTED');
    let done = underwriteResponse(page, 'sim-pending');
    await page.locator('#uw-fixture').selectOption('sim-pending');
    await done;
    await expectRecord(page, 'cand-uw', pending);
    await expect(page.locator('#cand-uw-checks tr').nth(0).locator('td').nth(2)).toContainText('SETTLEMENT_NOT_COMMITTED');
    await shot(page.locator('#underwrite'), 'desktop-candidate-underwrite-u1-decline.png');

    const refund = await record('sim-refund', 60000);
    expect(refund.proposal).toBe('DECLINE');
    expect(refund.failed_check).toBe('U2_REFUND_EXPOSURE');
    expect(refund.checks[1].detail.reason).toBe('REFUND_OBLIGATION_OPEN');
    done = underwriteResponse(page, 'sim-refund');
    await page.locator('#uw-fixture').selectOption('sim-refund');
    await done;
    await expectRecord(page, 'cand-uw', refund);
    await expect(page.locator('#cand-uw-checks tr').nth(1).locator('td').nth(2)).toContainText('REFUND_OBLIGATION_OPEN');
    await shot(page.locator('#underwrite'), 'desktop-candidate-underwrite-u2-decline.png');

    // valid amount and day re-query
    const amount = await record('sim-refund', 70000);
    done = underwriteResponse(page, 'sim-refund');
    await page.locator('#uw-amount').fill('70000');
    await page.locator('#uw-amount').blur();
    await done;
    await expectRecord(page, 'cand-uw', amount);

    // invalid input never reaches the server and clears the stale record
    const requestsBefore = seen.underwrite.length;
    for (const bad of ['0', '1000000000001', '1e3', '12.5', '']) {
      await page.locator('#uw-amount').fill(bad);
      await page.locator('#uw-amount').blur();
      await expect(page.locator('#cand-uw-error')).toBeVisible();
      await expect(page.locator('#cand-uw-error')).toContainText('가정 금액');
      await expect(page.locator('#cand-uw-body')).toBeHidden();
    }
    expect(seen.underwrite.length).toBe(requestsBefore);
    done = underwriteResponse(page, 'sim-refund');
    await page.locator('#uw-amount').fill('60000');
    await page.locator('#uw-amount').blur();
    await done;
    const requestsValid = seen.underwrite.length;
    await page.locator('#uw-sim-day').fill('-1');
    await page.locator('#uw-sim-day').blur();
    await expect(page.locator('#cand-uw-error')).toContainText('가정 심사일');
    await expect(page.locator('#cand-uw-body')).toBeHidden();
    expect(seen.underwrite.length).toBe(requestsValid);
    done = underwriteResponse(page, 'sim-refund');
    await page.locator('#uw-sim-day').fill('0');
    await page.locator('#uw-sim-day').blur();
    await done;
    await expect(page.locator('#cand-uw-error')).toBeHidden();
    await expectRecord(page, 'cand-uw', await record('sim-refund', 60000));

    expect(seen.posts).toEqual([]);
    const after = await getJson(port, '/api/state');
    expect(after.body.state_digest).toBe(before.state_digest);
    expect(after.body.operation_count).toBe(before.operation_count);
    expect(problems).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('auditor reads the panels without command controls and observer gets a forbidden notice', async ({page}) => {
  test.setTimeout(90000);
  const port = 8897;
  const seeded = seedWorkspace();
  const started = startServer(port, ['--workspace', seeded.workspace]);
  const problems = watchProblems(page);
  const seen = watchRequests(page);
  try {
    const before = await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/?case=sim-closed`);
    await expect(page.locator('#case-title')).toHaveText('sim-closed');
    await expect(page.locator('#case-uw-body')).toBeVisible();

    const auditor = await switchRole(page, 'auditor');
    await expect(page.locator('#case-title')).toHaveText('sim-closed');
    await expect(page.locator('#case-uw-body')).toBeVisible();
    await expect(page.locator('#cand-uw-body')).toBeVisible();
    await expect(page.locator('#case-uw-error')).toBeHidden();
    await expect(page.locator('#cand-uw-error')).toBeHidden();
    await expect(page.locator('#case-terms-label')).toHaveText(TERMS_LABEL);
    await expect(page.locator('#policy-label')).toHaveText(POLICY_LABEL);
    for (const selector of ['#case-underwrite', '#underwrite']) {
      const block = page.locator(selector);
      await expect(block.locator('button')).toHaveCount(0);
      await expect(block.locator('form')).toHaveCount(0);
      await expect(block.locator('[data-op], [data-permission]')).toHaveCount(0);
    }
    const commandControls = page.locator('#offer-form button, #offer-form input, #offer-form select, #actions button, #repay, #unbound-draw');
    expect(await commandControls.count()).toBeGreaterThan(0);
    for (let index = 0; index < await commandControls.count(); index += 1) await expect(commandControls.nth(index)).toBeDisabled();
    await shot(page.locator('#case-underwrite'), 'desktop-auditor-case-underwrite.png');

    // the auditor can still query other fixtures: a GET, never a command
    // the record echoes the caller's role, so the reference GET carries the auditor token
    const instance = encodeURIComponent(before.instance_id);
    const reference = await page.request.get(`http://127.0.0.1:${port}/api/underwrite/sim-refund?instance_id=${instance}&sim_day=0&amount=60000`, {headers: {'X-Capital-Token': auditor.local_token}});
    expect(reference.ok()).toBeTruthy();
    const refund = await reference.json();
    expect(refund.decided_by_role).toBe('auditor');
    const done = underwriteResponse(page, 'sim-refund');
    await page.locator('#uw-fixture').selectOption('sim-refund');
    await done;
    await expectRecord(page, 'cand-uw', refund);
    await shot(page.locator('#underwrite'), 'desktop-auditor-candidate-underwrite.png');
    expect([...new Set(seen.posts)]).toEqual(['/api/session']);

    const requestsBeforeObserver = seen.underwrite.length;
    await switchRole(page, 'observer');
    for (const prefix of ['case-uw', 'cand-uw']) {
      await expect(page.locator(`#${prefix}-error`)).toBeVisible();
      await expect(page.locator(`#${prefix}-error`)).toContainText('observer');
      await expect(page.locator(`#${prefix}-error`)).toContainText('projection:read');
      await expect(page.locator(`#${prefix}-body`)).toBeHidden();
      await expect(page.locator(`#${prefix}-checks tr`)).toHaveCount(0);
      await expect(page.locator(`#${prefix}-facts dt`)).toHaveCount(0);
    }
    await shot(page.locator('#case-underwrite'), 'desktop-observer-case-underwrite.png');
    await shot(page.locator('#underwrite'), 'desktop-observer-candidate-underwrite.png');
    // changing a control as observer does not fetch either
    await page.locator('#uw-sim-day').fill('2');
    await page.locator('#uw-sim-day').blur();
    await expect(page.locator('#cand-uw-error')).toContainText('projection:read');
    expect(seen.underwrite.length).toBe(requestsBeforeObserver);
    expect([...new Set(seen.posts)]).toEqual(['/api/session']);
    const after = await getJson(port, '/api/state');
    expect(after.body.state_digest).toBe(before.state_digest);
    expect(after.body.operation_count).toBe(before.operation_count);
    expect(problems).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
    fs.rmSync(seeded.directory, {recursive: true, force: true});
  }
});

test('an unbound terms note shows terms not bound with no checks or numbers', async ({page}) => {
  test.setTimeout(60000);
  const port = 8898;
  const seeded = seedWorkspace();
  const note = path.join(seeded.directory, 'missing-terms.md');
  const started = startServer(port, ['--workspace', seeded.workspace, '--terms-note', note]);
  const problems = watchProblems(page);
  const seen = watchRequests(page);
  try {
    const before = await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/?case=sim-closed`);
    const unbound = (await getJson(port, `/api/underwrite/sim-closed?instance_id=${encodeURIComponent(before.instance_id)}&sim_day=0`)).body;
    expect(unbound.status).toBe('NOT_BOUND');
    expect(unbound.reason).toBe('terms not bound');
    expect(unbound.checks).toBeUndefined();
    for (const prefix of ['case-uw', 'cand-uw']) {
      await expect(page.locator(`#${prefix}-label`)).toHaveText(UW_LABEL);
      await expect(page.locator(`#${prefix}-summary`)).toHaveText('NOT_BOUND · terms not bound');
      await expect(page.locator(`#${prefix}-table`)).toBeHidden();
      await expect(page.locator(`#${prefix}-checks tr`)).toHaveCount(0);
      expect(/\d/.test(await page.locator(`#${prefix}-facts`).innerText())).toBe(false);
    }
    expect(seen.posts).toEqual([]);
    expect(problems).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
    fs.rmSync(seeded.directory, {recursive: true, force: true});
  }
});

test('375px shows no horizontal overflow and the new controls follow keyboard order', async ({page}) => {
  test.setTimeout(90000);
  const port = 8899;
  const seeded = seedWorkspace();
  const started = startServer(port, ['--workspace', seeded.workspace]);
  const problems = watchProblems(page);
  const seen = watchRequests(page);
  try {
    await waitReady(port);
    await page.setViewportSize({width: 375, height: 667});
    await page.goto(`http://127.0.0.1:${port}/?case=sim-pending-settlement`);
    await expect(page.locator('#case-title')).toHaveText('sim-pending-settlement');
    await expect(page.locator('#case-uw-body')).toBeVisible();
    await expect(page.locator('#cand-uw-body')).toBeVisible();
    await expect(page.locator('#case-terms-label')).toHaveText(TERMS_LABEL);
    await expect(page.locator('#policy-label')).toHaveText(POLICY_LABEL);
    const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    expect(await fits()).toBe(true);
    for (const selector of ['#case-underwrite', '#underwrite', '#policy', '#case-terms']) {
      const right = await page.locator(selector).evaluate(el => el.getBoundingClientRect().right);
      expect(right).toBeLessThanOrEqual(375);
    }
    await shot(page.locator('#case-terms'), 'mobile-case-terms.png');
    await shot(page.locator('#policy'), 'mobile-policy.png');
    await shot(page.locator('#case-underwrite'), 'mobile-case-underwrite.png');
    await shot(page.locator('#underwrite'), 'mobile-candidate-underwrite.png');

    // tab order inside the case detail: terms days, then the underwrite day
    await page.locator('#terms-settlement-day').focus();
    await page.keyboard.press('Tab');
    await expect(page.locator('#underwrite-sim-day')).toBeFocused();
    // and in the candidate panel: scenario, amount, day
    await page.locator('#uw-fixture').focus();
    await page.keyboard.press('Tab');
    await expect(page.locator('#uw-amount')).toBeFocused();
    await page.keyboard.press('Tab');
    await expect(page.locator('#uw-sim-day')).toBeFocused();
    // the checks table scrolls inside its wrapper, not the page
    await page.locator('#uw-fixture').selectOption('sim-pending');
    await expect(page.locator('#cand-uw-summary')).toContainText('DECLINE');
    expect(await fits()).toBe(true);
    expect(await page.evaluate(() => [...document.querySelectorAll('[tabindex]')].every(el => el.tabIndex <= 0))).toBe(true);
    expect(seen.posts).toEqual([]);
    expect(problems).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
    fs.rmSync(seeded.directory, {recursive: true, force: true});
  }
});

test('static assets keep zero HTML-parsing or eval sinks and no inline script or style', async () => {
  const source = fs.readFileSync(path.join(root, 'capital/static/app.js'), 'utf8');
  for (const sink of [/innerHTML/, /outerHTML/, /insertAdjacentHTML/, /document\.write/, /\beval\s*\(/, /new Function\b/, /createContextualFragment/, /DOMParser/, /srcdoc/]) {
    expect(source).not.toMatch(sink);
  }
  const html = fs.readFileSync(path.join(root, 'capital/static/index.html'), 'utf8');
  expect(html.match(/<script\b/g)).toHaveLength(1);
  expect(html).toContain('<script type="module" src="/app.js"></script>');
  expect(html).not.toMatch(/<style\b/i);
  expect(html).not.toMatch(/\sstyle\s*=/i);
  expect(html).not.toMatch(/\son[a-z]+\s*=/i);
  expect(html).not.toMatch(/javascript:/i);
});
