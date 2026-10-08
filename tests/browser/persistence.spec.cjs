const {test, expect} = require('@playwright/test');
const {spawn} = require('child_process');
const fs = require('fs');
const http = require('http');
const os = require('os');
const path = require('path');

const PORT = 8871;
const root = path.resolve(__dirname, '../..');

function startServer(directory) {
  const log = fs.openSync(path.join(directory, 'server.log'), 'a');
  const child = spawn('python3', ['-m', 'capital.server', '--port', String(PORT), '--workspace', directory], {
    cwd: root, stdio: ['ignore', log, log],
  });
  fs.closeSync(log);
  return child;
}

function stopServer(child) {
  return new Promise(resolve => {
    if (!child || child.exitCode !== null || child.signalCode !== null) return resolve();
    const timer = setTimeout(resolve, 3000);
    child.once('exit', () => { clearTimeout(timer); resolve(); });
    child.kill('SIGKILL');
  });
}

function readState() {
  return new Promise((resolve, reject) => {
    const req = http.get({hostname: '127.0.0.1', port: PORT, path: '/api/state', timeout: 1000}, response => {
      let data = '';
      response.on('data', chunk => { data += chunk; });
      response.on('end', () => {
        try { resolve(JSON.parse(data)); } catch (error) { reject(error); }
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(Error('timeout')); });
  });
}

async function waitReady() {
  const deadline = Date.now() + 8000;
  let last;
  while (Date.now() < deadline) {
    try {
      last = await readState();
      if (last && last.instance_id && last.workspace && last.workspace.status === 'ACTIVE' && last.workspace.kind === 'LOCAL_FILE_WORKSPACE') return last;
    } catch (error) { last = String(error); }
    await new Promise(resolve => setTimeout(resolve, 40));
  }
  throw Error('SERVER_NOT_READY ' + JSON.stringify(last));
}

test('stale tab acknowledges a restarted file workspace and does not resend', async ({page}) => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'kix-capital-ws-'));
  let child = startServer(directory);
  try {
    const first = await waitReady();
    await page.goto(`http://127.0.0.1:${PORT}/`);
    await expect(page.locator('#notice')).toContainText('합성 데이터');
    await expect(page.locator('#storage-label')).toHaveText('로컬 파일 작업공간');
    await expect(page.locator('#storage-note')).toContainText('stage5');
    const offered = page.waitForResponse(response => response.url().endsWith('/api/commands') && response.request().postDataJSON()?.op === 'offer');
    await page.getByRole('button', {name: '모의 제안 생성'}).click();
    const offer = await (await offered).json();
    expect(offer.outcome).toBe('ACCEPTED');
    const advanceId = offer.result.credit.advance_id;
    await expect(page.locator('#case-title')).toHaveText(advanceId);
    await page.route('**/api/commands', route => route.abort('failed'));
    await page.getByRole('button', {name: '모의 승인', exact: true}).click();
    await expect(page.locator('#recovery')).toBeVisible();
    const pending = await page.evaluate(() => JSON.parse(localStorage.getItem('kix-capital-pending-v1')));
    expect(pending.instance_id).toBe(first.instance_id);
    expect(pending.op).toBe('approve');
    const digest = (await readState()).state_digest;

    await stopServer(child);
    child = startServer(directory);
    const second = await waitReady();
    expect(second.instance_id).not.toBe(first.instance_id);
    expect(second.state_digest).toBe(digest);
    expect(second.cases.map(item => item.advance_id)).toContain(advanceId);
    expect(second.durable).toBe('LOCAL_FILE_WORKSPACE');

    let posts = 0;
    page.on('request', request => { if (request.method() === 'POST') posts += 1; });
    await page.reload();
    await expect(page.locator('#recovery')).toBeVisible();
    await expect(page.getByRole('button', {name: '서버 재시작 확인'})).toBeVisible();
    await expect(page.getByRole('button', {name: '모의 제안 생성'})).toBeDisabled();
    const denied = page.waitForResponse(response => response.url().includes('/api/operations/'));
    await page.getByRole('button', {name: '원 요청 결과 조회'}).click();
    expect((await denied).status()).toBe(409);
    await expect(page.locator('#notice')).toContainText('UNKNOWN');
    await expect(page.locator('#recovery')).toBeVisible();
    await expect(page.getByRole('button', {name: '모의 제안 생성'})).toBeDisabled();
    posts = 0;
    await page.getByRole('button', {name: '서버 재시작 확인'}).click();
    await expect(page.locator('#recovery')).toBeHidden();
    await expect(page.locator('#notice')).toContainText('복원된 작업공간');
    await expect(page.locator('#notice')).toContainText('재전송하지 않았습니다');
    expect(posts).toBe(0);
    await expect(page.locator('#phase')).toHaveText('제안됨 · OFFERED');
    await expect(page.locator('#case-title')).toHaveText(advanceId);
    const restored = await (await page.request.get(`http://127.0.0.1:${PORT}/api/operations/${encodeURIComponent(offer.operation_id)}?instance_id=${encodeURIComponent(second.instance_id)}`)).json();
    expect(restored.outcome).toBe('ACCEPTED');
    expect(restored.operation_id).toBe(offer.operation_id);
    expect(restored.instance_id).toBe(first.instance_id);
    expect(restored.instance_id).not.toBe(second.instance_id);
  } finally {
    await stopServer(child);
    fs.rmSync(directory, {recursive: true, force: true});
  }
});
