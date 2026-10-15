#!/usr/bin/env node
// judge/run_scene.cjs — drive one artifact through the harness twice and
// print one JSON blob (console errors, per-frame metrics of both runs,
// SSIM where hashes differ, raw frames requested for media).
//
// Usage: node run_scene.cjs <artifact_dir> [frame indices to stash ...]
// The blob goes to stdout; logs go to stderr.
//
// The harness stubs requestAnimationFrame (upstream's wall-clock loop must
// never run), so this runner never uses waitForFunction (which polls with
// the page's rAF): every wait is an awaited page.evaluate whose promise is
// resolved from in-page setTimeout polling.

'use strict';

const fs = require('fs');
const path = require('path');
const http = require('http');
const { chromium } = require('playwright-core');

const SCRIPT_DIR = __dirname;
const UPSTREAM_DIR = path.join(SCRIPT_DIR, 'upstream');
const DRIVER_DIR = path.join(SCRIPT_DIR, 'driver');

const RUN_TIMEOUT_MS = 420000;
const READY_TIMEOUT_MS = 60000;

function log(msg) { process.stderr.write(`[runner] ${msg}\n`); }

function parseArgs() {
    const argv = process.argv.slice(2);
    const artifact = argv.shift();
    if (!artifact) {
        console.error('Usage: run_scene.cjs <artifact_dir> [stash idx...]');
        process.exit(2);
    }
    const stash = Math.max(0, parseInt(argv.shift() || '0', 10) || 0);
    const idxs = argv.map(Number).filter(Number.isInteger);
    return { artifact: path.resolve(artifact), stash, idxs };
}

// Tiny static server: harness + verified upstream + artifact scene.
function startServer(sceneDir) {
    const types = { '.html': 'text/html', '.js': 'text/javascript',
                    '.json': 'application/json', '.png': 'image/png',
                    '.frag': 'text/plain' };
    const roots = [
        { prefix: '/up/', dir: UPSTREAM_DIR },
        { prefix: '/driver/', dir: DRIVER_DIR },
        { prefix: '/scene/', dir: sceneDir },
        // Upstream requests assets (LDR_LLL1_0.png) relative to the page,
        // which lives under /driver/: fall back to the upstream dir.
        { prefix: '/driver/', dir: UPSTREAM_DIR },
    ];
    const server = http.createServer((req, res) => {
        try {
            let rel = decodeURIComponent(req.url.split('?')[0]);
            if (rel.includes('..')) { res.writeHead(403); return res.end(); }
            if (rel === '/favicon.ico' || rel === '/driver/favicon.ico') {
                res.writeHead(204); return res.end();
            }
            let p = null;
            for (const r of roots) {
                if (!rel.startsWith(r.prefix)) continue;
                const cand = path.join(r.dir,
                                       rel.slice(r.prefix.length));
                if (fs.existsSync(cand) && fs.statSync(cand).isFile()) {
                    p = cand;
                    break;
                }
            }
            if (!p) { res.writeHead(404); return res.end(); }
            res.writeHead(200, {
                'Content-Type':
                    types[path.extname(p)] || 'application/octet-stream',
            });
            fs.createReadStream(p).pipe(res);
        } catch (e) {
            res.writeHead(500); res.end();
        }
    });
    return new Promise((done, rej) => {
        server.listen(0, '127.0.0.1', () => done(server));
        server.on('error', rej);
    });
}

// In-page wait that does not depend on requestAnimationFrame.
const WAIT = (what) => `(function () {
    return new Promise(function (resolve, reject) {
        function check () {
            var v = ${what};
            if (v !== undefined) return resolve(v);
            if (window.__WFS_ABORTED__ === true) return resolve('aborted');
            setTimeout(check, 200);
        }
        setTimeout(check, 200);
    });
})()`;

async function runOnce(page, driveJs) {
    // The artifact's drive.js is an async IIFE body: fire it, then poll
    // (via setTimeout, never rAF) for the engine's sealed result.
    await page.evaluate(driveJs);
    return page.evaluate(WAIT('window.__WFS_RESULT__ ? "result" : undefined'));
}

(async function main() {
    const { artifact, stash, idxs } = parseArgs();
    for (const f of ['config.json', 'drive.js', 'obstacle.frag'])
        if (!fs.existsSync(path.join(artifact, f))) {
            console.error(`[runner] ERROR: missing ${f} in ${artifact}`);
            process.exit(2);
        }

    const server = await startServer(artifact);
    const port = server.address().port;
    const url = `http://127.0.0.1:${port}/driver/index.html`;

    const browser = await chromium.launch({
        timeout: 120000,
        args: [
            '--no-sandbox', '--disable-dev-shm-usage',
            '--use-gl=angle', '--use-angle=swiftshader',
            '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist',
        ],
    });
    const page = await browser.newPage();
    const consoleErrors = [];
    page.on('console', (m) => {
        if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300));
    });
    page.on('pageerror', (e) => consoleErrors.push(String(e).slice(0, 300)));

    const t0 = Date.now();
    const blob = {
        ok: false, error: null, meta: null, console_errors: [],
        run1: null, run2: null,
        raw_frames: [], stash_indices: [], requested_indices: idxs,
        wall_ms: 0,
    };
    try {
        await page.goto(url, { waitUntil: 'load', timeout: 60000 });
        await page.evaluate(WAIT('window.__WFS_READY__'));
        blob.meta = await page.evaluate('window.__WFS_META__');

        const driveJs = fs.readFileSync(path.join(artifact, 'drive.js'),
                                        'utf8');
        const wrapped = `(async function () {\n${driveJs}\n})()`;

        const how1 = await runOnce(page, wrapped);
        blob.run1 = await page.evaluate('window.__WFS_RESULT__');
        blob.console_errors = await page.evaluate(
            'window.__WFS_CONSOLE__.errors');

        await page.evaluate('window.__WFS__.resetAll()');
        const how2 = await runOnce(page, wrapped);
        blob.run2 = await page.evaluate('window.__WFS_RESULT__');
        blob.console_errors = await page.evaluate(
            'window.__WFS_CONSOLE__.errors');

        if (stash > 0) {
            const pick = idxs.length ? idxs
                : Array.from({ length: stash }, (_, i) => i);
            blob.stash_indices = pick;
            blob.raw_frames = await page.evaluate(
                (ix) => window.__WFS__.exportFrames(ix), pick);
        }
        blob.console_errors = await page.evaluate(
            'window.__WFS_CONSOLE__.errors');
        // Browser-side console errors (resource 404s, uncaught errors) do
        // not pass through the page's console.error wrapper — merge them.
        blob.console_errors = blob.console_errors.concat(consoleErrors);
        blob.ok = how1 === 'result' && how2 === 'result' &&
                  !!(blob.run1 && blob.run2);
        if (!blob.ok)
            blob.error = `run1=${how1} run2=${how2}`;
    } catch (e) {
        blob.error = String(e && e.message ? e.message : e).slice(0, 400);
        try {
            blob.console_errors = await page.evaluate(
                'window.__WFS_CONSOLE__ ? window.__WFS_CONSOLE__.errors : []');
            if (!blob.meta) blob.meta = await page.evaluate(
                'window.__WFS_META__ ? window.__WFS_META__ : null');
            if (!blob.run1) blob.run1 = await page.evaluate(
                'window.__WFS_RESULT__ ? window.__WFS_RESULT__ : null');
        } catch (_) { /* page may be gone */ }
    } finally {
        blob.wall_ms = Date.now() - t0;
        process.stdout.write(JSON.stringify(blob));
        await browser.close().catch(() => {});
        server.close();
    }
    process.exit(0);
})().catch((e) => {
    process.stderr.write(`[runner] fatal: ${e}\n`);
    process.stdout.write(JSON.stringify({
        ok: false, error: String(e).slice(0, 400), meta: null,
        console_errors: [], run1: null, run2: null,
        raw_frames: [], stash_indices: [], requested_indices: [],
        wall_ms: 0,
    }));
    process.exit(0);  // exit 0; the gates decide pass/fail
});
