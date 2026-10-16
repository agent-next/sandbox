// Render every showcase route headless and record a per-demo verdict.
// usage: node render_all.cjs <base-url> <out-dir> <id>...
const { chromium } = require("playwright");
const fs = require("fs");

const [base, out, ...ids] = process.argv.slice(2);
const SETTLE_MS = 20000;
const PATIENCE = Number(process.env.PATIENCE || 1);  // run.py --patience: scales every wait below
const OVERLAY_MS = 300000 * PATIENCE;
const SHOT_MS = 600000 * PATIENCE;
const TARGET_MS = 30 * 60000 * PATIENCE;  // hard cap per target: a hung page must not stall the rest

(async () => {
  fs.mkdirSync(out, { recursive: true });
  const browser = await chromium.launch({
    args: ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"],
  });
  const results = [];
  for (const id of ids) {
    let watchdog;
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 },
                                           recordVideo: { dir: `${out}/video-raw`, size: { width: 1280, height: 800 } } });
    const page = await ctx.newPage();
    watchdog = setTimeout(() => { console.error(`watchdog: closing ${id}`); ctx.close().catch(() => {}); }, TARGET_MS);
    const errors = [];
    page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
    page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
    page.on("requestfailed", (r) => errors.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`));
    const url = id.endsWith(".html") ? `${base}/${id}` : `${base}/#/demo/${id}`;
    const t0 = Date.now();
    let navError = null, overlayCleared = null, overlayWaitMs = null;
    try {
      await page.goto(url, { waitUntil: "load", timeout: 180000 });
      await page.waitForTimeout(SETTLE_MS);
      // The demo viewer shows a dimmed "Framing" overlay until the model is placed; wait it out.
      const t1 = Date.now();
      overlayCleared = await page.waitForFunction(() => !/\bFraming\b/.test(document.body.innerText),
                                                  null, { timeout: OVERLAY_MS, polling: 2000 })
        .then(() => true, () => false);
      overlayWaitMs = Date.now() - t1;
    } catch (e) {
      navError = String(e.message || e).split("\n")[0];
    }
    const png = `${out}/${id.replace(/\.html$/, "")}.png`;
    let canvas = null;
    try {
      await page.screenshot({ path: png, timeout: SHOT_MS });
      // Pixel stats of the largest canvas, taken from the composited screenshot: WebGL canvases
      // without preserveDrawingBuffer read back as black, so the canvas itself is not a usable oracle.
      const box = await page.evaluate(() => {
        const cs = [...document.querySelectorAll("canvas")];
        if (!cs.length) return null;
        const r = cs.map((c) => c.getBoundingClientRect()).sort((a, b) => b.width * b.height - a.width * a.height)[0];
        return { count: cs.length, x: r.x, y: r.y, width: r.width, height: r.height };
      });
      if (box && box.width > 0 && box.height > 0) {
        const buf = await page.screenshot({ clip: { x: box.x, y: box.y, width: box.width, height: box.height }, timeout: SHOT_MS });
        const stats = await page.evaluate(async (b64) => {
          const bytes = Uint8Array.from(atob(b64), (ch) => ch.charCodeAt(0));
          const bmp = await createImageBitmap(new Blob([bytes], { type: "image/png" }));
          const w = 160, h = Math.max(1, Math.round((160 * bmp.height) / bmp.width));
          const o = new OffscreenCanvas(w, h).getContext("2d");
          o.drawImage(bmp, 0, 0, w, h);
          const d = o.getImageData(0, 0, w, h).data;
          let n = 0, s = 0, s2 = 0;
          const colours = new Set();
          for (let i = 0; i < d.length; i += 4) {
            const l = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
            s += l; s2 += l * l; n++;
            colours.add((d[i] >> 4) << 8 | (d[i + 1] >> 4) << 4 | (d[i + 2] >> 4));
          }
          const mean = s / n;
          return { lumaMean: +mean.toFixed(1), lumaStd: +Math.sqrt(Math.max(0, s2 / n - mean * mean)).toFixed(1),
                   colours12bit: colours.size };
        }, buf.toString("base64"));
        canvas = { ...box, ...stats };
      } else {
        canvas = { count: box ? box.count : 0 };
      }
    } catch (e) {
      errors.push(`capture: ${String(e.message || e).split("\n")[0]}`);
    }
    const rendered = !!canvas && canvas.count > 0 && canvas.lumaStd > 3 && canvas.colours12bit > 20;
    const r = { id, url: url.replace(base, ""), ms: Date.now() - t0, navError, canvas, rendered,
                errorCount: errors.length, errors: errors.slice(0, 5),
                overlayCleared, overlayWaitMs,
                verdict: !rendered || navError ? "FAIL" : !overlayCleared ? "LOADING_OVERLAY"
                  : errors.length ? "RENDERED_WITH_ERRORS" : "PASS" };
    results.push(r);
    console.log(JSON.stringify({ id, verdict: r.verdict, ms: r.ms, overlayCleared, canvas, errorCount: errors.length }));
    clearTimeout(watchdog);
    const video = page.video();
    await ctx.close().catch(() => {});
    if (video) {
      try { fs.renameSync(await video.path(), `${out}/${id.replace(/\.html$/, "")}.webm`); } catch (e) { /* closed by watchdog */ }
    }
    fs.writeFileSync(`${out}/results.json`, JSON.stringify(results, null, 2));
  }
  await browser.close();
  fs.writeFileSync(`${out}/results.json`, JSON.stringify(results, null, 2));
})();
