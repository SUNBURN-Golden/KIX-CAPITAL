const {test, expect} = require('@playwright/test');
const {spawn} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const LABEL = 'simulated policy application — not executed distribution, not bank movement';

function startServer(port, extra) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-policy-'));
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

test('adopted order is shown beside fixture orders and the page does not POST', async ({page}) => {
  const port = 8893;
  const started = startServer(port, []);
  const posts = [];
  page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()); });
  try {
    const before = await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/#policy`);
    await expect(page.locator('#policy-label')).toHaveText(LABEL);
    await expect(page.locator('#policy-outcome')).toContainText('DECIDED');
    const simulation = await getJson(port, '/api/policy/simulation');
    expect(simulation.status).toBe(200);
    expect(simulation.body.label).toBe(LABEL);
    expect(simulation.body.mode).toBe('SIMULATED_POLICY_APPLICATION');
    expect(simulation.body.funds_executed).toBe(false);
    expect(simulation.body.workspace_mutated).toBe(false);
    expect(simulation.body.comparison).toHaveLength(3);
    await expect(page.locator('#policy-head th[data-kind="DECIDED"]')).toHaveCount(1);
    await expect(page.locator('#policy-head th[data-kind="FIXTURE"]')).toHaveCount(2);
    const decided = simulation.body.comparison.find(row => row.kind === 'DECIDED');
    for (const line of decided.per_payee) {
      const cell = page.locator(`#policy-body td[data-kind="DECIDED"][data-payee="${line.payee}"]`);
      await expect(cell).toContainText(String(line.distributed));
      await expect(cell).toContainText(String(line.face));
      await expect(cell).toContainText(String(line.outstanding));
    }
    await expect(page.locator('#policy-unsupported')).toContainText('UNSUPPORTED_BY_PINNED_FSM');
    await expect(page.locator('#policy-unsupported')).toContainText('computed false');
    expect(posts).toEqual([]);
    const after = await getJson(port, '/api/state');
    expect(after.body.state_digest).toBe(before.state_digest);
    expect(after.body.operation_count).toBe(before.operation_count);
    await page.setViewportSize({width: 375, height: 667});
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
  }
});

test('undecided allocation stays comparison-only', async ({page}) => {
  const port = 8894;
  const note = path.join(os.tmpdir(), `kix-capital-policy-note-${process.pid}.md`);
  const source = fs.readFileSync(path.join(root, 'docs/decisions/CAPITAL_SETTLEMENT_POLICY.md'), 'utf8');
  const flipped = source.replace('"status": "ADOPTED"', '"status": "UNDETERMINED"');
  fs.writeFileSync(note, flipped);
  const started = startServer(port, ['--policy-note', note]);
  const posts = [];
  page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()); });
  try {
    await waitReady(port);
    await page.goto(`http://127.0.0.1:${port}/#policy`);
    await expect(page.locator('#policy-label')).toHaveText(LABEL);
    await expect(page.locator('#policy-outcome')).toContainText('POLICY_UNDECIDED');
    await expect(page.locator('#policy-head th[data-kind="DECIDED"]')).toHaveCount(0);
    await expect(page.locator('#policy-head th[data-kind="FIXTURE"]')).toHaveCount(2);
    const simulation = await getJson(port, '/api/policy/simulation');
    expect(simulation.body.outcome).toBe('POLICY_UNDECIDED');
    expect(simulation.body.decided).toBeNull();
    expect(simulation.body.comparison.every(row => row.kind === 'FIXTURE')).toBe(true);
    expect(posts).toEqual([]);
  } finally {
    await stopServer(started.child);
    fs.rmSync(started.directory, {recursive: true, force: true});
    fs.rmSync(note, {force: true});
  }
});
