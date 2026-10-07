// Regenerate the README screenshots in docs/ from a running Darkroom server.
//
//   npm i --no-save puppeteer-core          # once
//   python3 server.py &                      # needs a working COMFY_API_KEY
//   node scripts/screenshots.mjs [http://127.0.0.1:8765]
//
// Makes one real 4-image run at 1K (billed to your key) for the loading and feed shots.
// Set CHROME to your Chrome/Chromium binary if it is not in the default macOS location.
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

const base = process.argv[2] || 'http://127.0.0.1:8765';
const docs = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'docs');
const chrome = process.env.CHROME || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const PROMPT = 'A fox reading a map in a lantern-lit forest, gouache illustration, warm palette';
const sleep = ms => new Promise(r => setTimeout(r, ms));

const browser = await puppeteer.launch({ executablePath: chrome, headless: 'new', args: ['--ignore-gpu-blocklist'] });
const errors = [];
const open = async (w, h) => {
  const p = await browser.newPage();
  await p.setViewport({ width: w, height: h });
  p.on('pageerror', e => errors.push(String(e)));
  return p;
};

// 1. First screen. Serve an empty gallery so the real outputs folder is left alone.
{
  const p = await open(1600, 1000);
  await p.setRequestInterception(true);
  p.on('request', r => r.url().endsWith('/api/gallery') ? r.respond({ contentType: 'application/json', body: '[]' }) : r.continue());
  await p.goto(base, { waitUntil: 'networkidle0' });
  await p.evaluate(() => { try { localStorage.clear(); } catch {} });
  await p.reload({ waitUntil: 'networkidle0' });
  await p.mouse.move(5, 990);
  await p.screenshot({ path: path.join(docs, 'welcome.png') });
  await p.close();
}

// 2. Loading tiles mid-run, then 3. the feed with the full settings panel open.
{
  const p = await open(1900, 1150);
  await p.goto(base, { waitUntil: 'networkidle0' });
  await p.evaluate(() => { try { localStorage.clear(); } catch {} });
  await p.reload({ waitUntil: 'networkidle0' });
  await p.evaluate(prompt => {
    set('size', '1K'); set('runs', 4);
    const t = document.querySelector('#prompt'); t.value = prompt; t.dispatchEvent(new Event('input'));
  }, PROMPT);
  await p.click('#go');
  await p.mouse.move(5, 1140);
  await sleep(4000);
  await p.screenshot({ path: path.join(docs, 'loading.png') });
  await p.waitForFunction(() => !document.querySelector('.cell.pending'), { timeout: 180000 });
  const failed = await p.$$eval('.job:first-child .cell.err', e => e.length);
  if (failed) errors.push(`${failed} image(s) failed in the capture run`);
  await sleep(2200);
  await p.evaluate(() => {
    set('size', '2K');
    const t = document.querySelector('#prompt'); t.value = ''; t.dispatchEvent(new Event('input'));
    togglePanel(true); document.querySelector('#more').open = true;
  });
  await sleep(400);
  await p.screenshot({ path: path.join(docs, 'feed.png') });
  await p.close();
}

await browser.close();
if (errors.length) { console.error('Problems:\n' + errors.join('\n')); process.exit(1); }
console.log('Updated docs/welcome.png, docs/loading.png and docs/feed.png');
