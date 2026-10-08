const fs = require('fs');
const path = require('path');
const zlib = require('zlib');
const {test, expect} = require('@playwright/test');

const OUT = path.join('test-results', 'acceptance');
const VIEWS = [
  ['portfolio', '#workspace .table-wrap'],
  ['case', '#detail'],
  ['projection', '#projection'],
  ['statement', '#statement'],
  ['reconciliation', '#reconciliation-panel'],
  ['readiness', '#roadmap'],
];
const ROLES = ['organizer', 'auditor', 'observer'];
const ROLE_SHOTS = ['role-organizer', 'role-auditor', 'role-observer'];
const VIEWPORTS = [
  ['desktop', 1280, 800],
  ['mobile', 375, 667],
];

function paeth(left, up, upLeft) {
  const estimate = left + up - upLeft;
  const dl = Math.abs(estimate - left);
  const du = Math.abs(estimate - up);
  const dul = Math.abs(estimate - upLeft);
  if (dl <= du && dl <= dul) return left;
  if (du <= dul) return up;
  return upLeft;
}

function uniqueColors(png) {
  if (png.length < 8 || png.readUInt32BE(0) !== 0x89504e47) throw new Error('not a png');
  let offset = 8;
  let width = 0;
  let height = 0;
  let bitDepth = 0;
  let colorType = 0;
  const idats = [];
  while (offset + 8 <= png.length) {
    const length = png.readUInt32BE(offset);
    const type = png.toString('ascii', offset + 4, offset + 8);
    const data = png.subarray(offset + 8, offset + 8 + length);
    if (type === 'IHDR') {
      width = data.readUInt32BE(0);
      height = data.readUInt32BE(4);
      bitDepth = data[8];
      colorType = data[9];
    } else if (type === 'IDAT') idats.push(data);
    else if (type === 'IEND') break;
    offset += 12 + length;
  }
  if (width < 20 || height < 20) throw new Error(`blank size ${width}x${height}`);
  if (bitDepth !== 8 || (colorType !== 2 && colorType !== 6)) throw new Error(`png type ${colorType}/${bitDepth}`);
  const channels = colorType === 6 ? 4 : 3;
  const stride = width * channels;
  const raw = zlib.inflateSync(Buffer.concat(idats));
  const rows = [];
  let pos = 0;
  for (let y = 0; y < height; y++) {
    const filter = raw[pos++];
    const row = Buffer.alloc(stride);
    const prev = y > 0 ? rows[y - 1] : null;
    for (let i = 0; i < stride; i++) {
      const value = raw[pos++];
      const left = i >= channels ? row[i - channels] : 0;
      const up = prev ? prev[i] : 0;
      const upLeft = prev && i >= channels ? prev[i - channels] : 0;
      if (filter === 0) row[i] = value;
      else if (filter === 1) row[i] = (value + left) & 255;
      else if (filter === 2) row[i] = (value + up) & 255;
      else if (filter === 3) row[i] = (value + Math.floor((left + up) / 2)) & 255;
      else if (filter === 4) row[i] = (value + paeth(left, up, upLeft)) & 255;
      else throw new Error(`png filter ${filter}`);
    }
    rows.push(row);
  }
  const colors = new Set();
  const stepX = Math.max(1, Math.floor(width / 48));
  const stepY = Math.max(1, Math.floor(height / 48));
  for (let y = 0; y < height; y += stepY) {
    const row = rows[y];
    for (let x = 0; x < width; x += stepX) {
      const i = x * channels;
      colors.add((row[i] << 16) | (row[i + 1] << 8) | row[i + 2]);
    }
  }
  return colors.size;
}

async function saveShot(locatorOrPage, file, element) {
  fs.mkdirSync(path.dirname(file), {recursive: true});
  const png = element
    ? await locatorOrPage.screenshot({path: file})
    : await locatorOrPage.screenshot({path: file, fullPage: true});
  expect(png.length).toBeGreaterThan(400);
  expect(uniqueColors(png)).toBeGreaterThanOrEqual(4);
}

async function switchRole(page, role) {
  if (await page.locator('#role').inputValue() === role) {
    await expect(page.locator('#role-status')).toContainText(role);
    return;
  }
  const seen = page.waitForResponse(response => response.url().endsWith('/api/session') && response.request().method() === 'POST');
  await page.locator('#role').selectOption(role);
  const response = await seen;
  const session = await response.json();
  expect(response.ok()).toBeTruthy();
  expect(session.role).toBe(role);
  expect(session.identity).toBe('NOT_BOUND');
  expect(session.authentication).toBe('NOT_BOUND');
  await expect(page.locator('#role-status')).toContainText(role);
}

test('seeded demo screenshots cover the book and each role', async ({page}) => {
  test.setTimeout(120000);
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  page.on('console', message => {
    if (message.type() !== 'error') return;
    const text = message.text();
    if (text.includes('favicon.ico')) return;
    errors.push(text);
  });
  await page.goto('/?case=sim-closed');
  await expect(page.locator('#notice')).toContainText('합성 데이터');
  await expect(page.locator('#cases tr')).toHaveCount(6);
  await expect(page.locator('#case-title')).toHaveText('sim-closed');
  await expect(page.locator('#phase')).toContainText('CLOSED');
  await expect(page.locator('#workspace .table-wrap')).toContainText('종결');
  await expect(page.locator('#workspace .table-wrap')).toContainText('미이행');
  await expect(page.locator('#workspace .table-wrap')).toContainText('거절');
  await expect(page.locator('#workspace .table-wrap')).toContainText('취소');
  await expect(page.locator('#workspace .table-wrap')).toContainText('UNBOUND');
  await expect(page.locator('#workspace .table-wrap')).toContainText('BOUND');
  await expect(page.locator('#projection-body')).toBeVisible();
  await expect(page.locator('#projection-debit')).not.toHaveText('0');
  await expect(page.locator('#statement-body')).toBeVisible();
  await expect(page.locator('#recon-body')).toBeVisible();
  await expect(page.locator('#readiness-integrity')).toContainText('NOT_BOUND');
  await expect(page.locator('#capabilities article').first()).toBeVisible();
  await expect(page.locator('#role')).toHaveValue('organizer');

  for (const [viewport, width, height] of VIEWPORTS) {
    await page.setViewportSize({width, height});
    if (viewport === 'mobile') {
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    }
    for (const [name, selector] of VIEWS) {
      const locator = page.locator(selector);
      await locator.scrollIntoViewIfNeeded();
      await expect(locator).toBeVisible();
      await saveShot(locator, path.join(OUT, viewport, `${name}.png`), true);
    }
  }
  for (const [viewport, width, height] of VIEWPORTS) {
    await page.setViewportSize({width, height});
    for (const role of ROLES) {
      await switchRole(page, role);
      await expect(page.locator('#role-status')).toContainText('NOT_BOUND');
      if (role === 'observer') await expect(page.locator('#projection-error')).toBeVisible();
      else await expect(page.locator('#projection-body')).toBeVisible();
      await saveShot(page, path.join(OUT, viewport, `${ROLE_SHOTS[ROLES.indexOf(role)]}.png`), false);
    }
  }
  expect(errors).toEqual([]);
});
