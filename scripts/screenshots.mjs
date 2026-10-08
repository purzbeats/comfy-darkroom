// Regenerate the README screenshots in docs/ from a running Darkroom server.
//
//   npm i --no-save puppeteer-core          # once
//   python3 server.py &                      # needs a working COMFY_API_KEY
//   node scripts/screenshots.mjs [http://127.0.0.1:8765]
//
// Makes three real 4-image runs at 1K (12 images, billed to your key). Twelve at once is more than
// the server runs together, so the loading shot shows some images waiting in line.
// Set CHROME to your Chrome/Chromium binary if it is not in the usual place for your OS.
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

const base = process.argv[2] || 'http://127.0.0.1:8765';
const docs = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'docs');
const chrome = process.env.CHROME || {
  darwin: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  win32: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
}[process.platform] || '/usr/bin/google-chrome';
const PROMPTS = [   // the last one ends up on top of the feed
  'A ceramic coffee cup on a linen tablecloth, soft window light, top-down product shot',
  'A lone cypress on a ridge at dawn, mist in the valley below, medium format film',
  'A fox reading a map in a lantern-lit forest, gouache illustration, warm palette',
];
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

// 2. Loading tiles mid-run (developing and in line), 3. the feed with the settings panel open,
// 4. the lightbox. Stars added for the shots are taken off again at the end.
const starred = [];
{
  const p = await open(1900, 1150);
  await p.goto(base, { waitUntil: 'networkidle0' });
  await p.evaluate(() => { try { localStorage.clear(); localStorage.setItem('darkroom-notify-asked', '1'); } catch {} });
  await p.reload({ waitUntil: 'networkidle0' });
  await p.evaluate(() => { set('size', '1K'); set('runs', 4); });
  for (const prompt of PROMPTS) {
    await p.evaluate(prompt => { const t = document.querySelector('#prompt'); t.value = prompt; t.dispatchEvent(new Event('input')); }, prompt);
    await p.click('#go');
    await sleep(300);
  }
  await p.evaluate(() => window.scrollTo(0, 0));
  await p.mouse.move(5, 1140);
  await sleep(4000);
  await p.screenshot({ path: path.join(docs, 'loading.png') });
  await p.waitForFunction(() => !document.querySelector('.cell.pending'), { timeout: 300000 });
  const failed = await p.$$eval('.cell.err', e => e.length);
  if (failed) errors.push(`${failed} image(s) failed in the capture run`);
  await sleep(2200);
  // Star the second image of the top row so the feed and lightbox show one.
  starred.push(await p.evaluate(() => { const sl = state.jobs[0].slots[1]; setStarred([sl.item.file], true); return sl.item.file; }));
  await p.evaluate(() => {
    set('size', '2K');
    const t = document.querySelector('#prompt'); t.value = ''; t.dispatchEvent(new Event('input'));
    togglePanel(true); document.querySelector('#more').open = true;
  });
  await sleep(400);
  await p.screenshot({ path: path.join(docs, 'feed.png') });
  await p.evaluate(() => { togglePanel(false); openLb(state.jobs[0].slots[1]); });
  await p.mouse.move(5, 5);
  await sleep(800);
  await p.screenshot({ path: path.join(docs, 'lightbox.png') });
  await p.close();
}

// 5. Organize with a few images selected, two of them starred.
{
  const p = await open(1900, 1150);
  await p.goto(base + '/#organize', { waitUntil: 'networkidle0' });
  await sleep(600);
  starred.push(await p.evaluate(() => { const f = doneSlots()[3].item.file; setStarred([f], true); return f; }));
  await sleep(300);
  const tiles = await p.$$('#org-grid .tile');
  for (const t of tiles.slice(0, 5)) await t.click();
  await p.mouse.move(5, 1140);
  await sleep(300);
  await p.screenshot({ path: path.join(docs, 'organize.png') });
  await p.close();
}
for (const f of starred) await fetch(`${base}/api/outputs/${f}/star`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{"starred":false}' });

// 6. A moodboard's page. Uses the first real board; with none, shows a demo board (never saved).
{
  const p = await open(1900, 1150);
  await p.setRequestInterception(true);
  let demo = false;
  p.on('request', async r => {
    if (!r.url().endsWith('/api/moodboards') || r.method() !== 'GET') return r.continue();
    const real = await (await fetch(r.url())).json();
    if (real.some(b => b.items.length)) return r.respond({ contentType: 'application/json', body: JSON.stringify(real) });
    demo = true;
    const items = (await (await fetch(base + '/api/gallery')).json()).slice(0, 12).map(i => 'outputs/' + i.file);
    r.respond({ contentType: 'application/json', body: JSON.stringify([{ id: 'demo', name: 'Studio picks', items }]) });
  });
  await p.goto(base, { waitUntil: 'networkidle0' });
  const id = await p.evaluate(() => state.boards.find(b => b.items.length)?.id);
  if (id) {
    await p.evaluate(id => go('moodboards/' + id), id);
    await sleep(800);
    await p.mouse.move(5, 1140);
    await p.screenshot({ path: path.join(docs, 'moodboard.png') });
  } else errors.push('no images available for the moodboard shot');
  if (demo) console.log('Moodboard shot used a demo board (no real boards with images).');
  await p.close();
}

await browser.close();
if (errors.length) { console.error('Problems:\n' + errors.join('\n')); process.exit(1); }
console.log('Updated docs/welcome.png, loading.png, feed.png, lightbox.png, organize.png and moodboard.png');
