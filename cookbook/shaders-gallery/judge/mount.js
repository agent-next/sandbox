/* judge/mount.js — injected into every frame before any page script runs
 * (playwright context.add_init_script).  Installs:
 *
 *   1. a minimal `window.process` shim — the library's dist/core ESM
 *      modules reference Node globals at import time;
 *   2. a WebGPU readback shim — GPUCanvasContext.getCurrentTexture is
 *      wrapped to return a judge-owned RENDER_ATTACHMENT|COPY_SRC
 *      texture, because SwiftShader's canvas presentation path does
 *      not rasterize into the compositor (see SPEC.md).  The library's
 *      own render pass then draws into the texture the judge reads.
 *   3. window.__judge — the mount/frame/capture driver the grader
 *      calls through page.evaluate().
 *
 * None of this modifies the artifact or the library; the measured
 * pixels are produced by the library's real WGSL pipeline.
 */
(() => {
  if (window.__judge) return;

  window.process = window.process || {
    env: { NODE_ENV: 'production' }, platform: 'linux', argv: [],
    cwd: () => '/', stdout: { isTTY: false, columns: 80, rows: 24, write: () => {} },
    stderr: { isTTY: false, write: () => {} }, stdin: { isTTY: false },
    exit: () => {}, execPath: '',
  };

  const conf0 = GPUCanvasContext.prototype.configure;
  GPUCanvasContext.prototype.configure = function (cfg) {
    this.__judgeDev = cfg.device;
    this.__judgeFmt = cfg.format;
    return conf0.call(this, cfg);
  };
  GPUCanvasContext.prototype.getCurrentTexture = function () {
    const w = this.canvas.width || 1, h = this.canvas.height || 1;
    if (!this.__judgeTex || this.__judgeTex.width !== w || this.__judgeTex.height !== h) {
      if (this.__judgeTex) this.__judgeTex.destroy();
      this.__judgeTex = this.__judgeDev.createTexture({
        size: [w, h], format: this.__judgeFmt,
        usage: GPUTextureUsage.RENDER_ATTACHMENT | GPUTextureUsage.COPY_SRC,
      });
    }
    return this.__judgeTex;
  };

  async function readPixels(ctx) {
    const w = ctx.canvas.width, h = ctx.canvas.height, tex = ctx.__judgeTex;
    if (!tex || !w || !h) return null;
    const bpr = Math.ceil(w * 4 / 256) * 256;
    const buf = ctx.__judgeDev.createBuffer({
      size: bpr * h,
      usage: GPUBufferUsage.COPY_DST | GPUBufferUsage.MAP_READ,
    });
    const enc = ctx.__judgeDev.createCommandEncoder();
    enc.copyTextureToBuffer({ texture: tex }, { buffer: buf, bytesPerRow: bpr }, [w, h]);
    ctx.__judgeDev.queue.submit([enc.finish()]);
    await buf.mapAsync(GPUMapMode.READ);
    const px = new Uint8Array(buf.getMappedRange().slice(0));
    buf.unmap(); buf.destroy();
    return { px, bpr, w, h };
  }

  // 64x64 downsample statistics over the RGB channels.
  function stats(cap) {
    if (!cap) return { ok: false };
    const { px, bpr, w, h } = cap;
    let s = 0, s2 = 0; const cols = new Set();
    for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) {
      const i = Math.floor(y * h / 64) * bpr + Math.floor(x * w / 64) * 4;
      const r = px[i], g = px[i + 1], b = px[i + 2];
      const v = (r + g + b) / 3;
      s += v; s2 += v * v;
      cols.add(((r >> 4) << 8) | ((g >> 4) << 4) | (b >> 4));
    }
    const mean = s / 4096;
    return {
      ok: true, w, h,
      variance: +(s2 / 4096 - mean * mean).toFixed(4),
      mean: +mean.toFixed(4),
      distinctColors12: cols.size,
    };
  }

  function diff(a, b) {
    if (!a || !b || a.w !== b.w || a.h !== b.h) return null;
    let s = 0;
    for (let y = 0; y < 64; y++) for (let x = 0; x < 64; x++) {
      const i = Math.floor(y * a.h / 64) * a.bpr + Math.floor(x * a.w / 64) * 4;
      for (let c = 0; c < 3; c++) s += Math.abs(a.px[i + c] - b.px[i + c]);
    }
    return +(s / (64 * 64 * 3)).toFixed(4);
  }

  window.__judge = {
    // One-shot probe of this environment's GPU story (Gate 1 records).
    async probe() {
      const out = { secure: window.isSecureContext, hasGpu: !!navigator.gpu };
      if (navigator.gpu) {
        try {
          const a = await navigator.gpu.requestAdapter();
          out.adapter = a ? {
            vendor: (a.info && a.info.vendor) || '',
            architecture: (a.info && a.info.architecture) || '',
          } : null;
        } catch (e) { out.adapterError = String(e).slice(0, 200); }
      }
      try {
        const gl = document.createElement('canvas').getContext('webgl2');
        const ext = gl && gl.getExtension('WEBGL_debug_renderer_info');
        out.glRenderer = ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null;
      } catch (e) { out.glError = String(e).slice(0, 200); }
      return out;
    },

    // Mount one declared effect on a canvas element. Returns a handle id.
    async mount(canvasSelector, presetJson) {
      const canvas = document.querySelector(canvasSelector);
      if (!canvas) return { ok: false, error: 'canvas not found: ' + canvasSelector };
      const mod = await import('/vendor/dist/core/index.js');
      const preset = JSON.parse(presetJson);
      const r = mod.createRendererFromJSON(preset);
      await r.initialize(canvas);
      const ctx = canvas.getContext('webgpu');
      const id = '__judge_fx_' + (window.__judge._n = (window.__judge._n || 0) + 1);
      window.__judge._live = window.__judge._live || {};
      window.__judge._live[id] = { r, ctx, caps: [] };
      return { ok: true, id, fail: r.getFailureReason() };
    },

    // Deterministic frame step + capture. Keeps the two most recent
    // raw captures for the animation diff.
    async frame(id, deltaSeconds) {
      const L = window.__judge._live && window.__judge._live[id];
      if (!L) return { ok: false, error: 'no such mount: ' + id };
      try {
        await L.r.renderFrame({ deltaSeconds });
      } catch (e) {
        return { ok: false, error: String(e).slice(0, 300), fail: L.r.getFailureReason() };
      }
      const cap = await readPixels(L.ctx);
      L.caps.push(cap);
      if (L.caps.length > 2) L.caps.shift();
      return { ok: true, stats: stats(cap), fail: L.r.getFailureReason() };
    },

    async diffLast(id) {
      const L = window.__judge._live && window.__judge._live[id];
      if (!L || L.caps.length < 2) return null;
      return diff(L.caps[0], L.caps[1]);
    },

    // PNG data-URL of the last capture (used by media/, not the gates).
    async lastFramePng(id) {
      const L = window.__judge._live && window.__judge._live[id];
      if (!L || !L.caps.length) return null;
      const cap = L.caps[L.caps.length - 1];
      const c = document.createElement('canvas');
      c.width = cap.w; c.height = cap.h;
      const x = c.getContext('2d');
      const img = x.createImageData(cap.w, cap.h);
      for (let y = 0; y < cap.h; y++)
        for (let i = 0; i < cap.w * 4; i++)
          img.data[y * cap.w * 4 + i] = cap.px[y * cap.bpr + i];
      x.putImageData(img, 0, 0);
      return c.toDataURL('image/png');
    },

    layout(minRegionH) {
      const se = document.scrollingElement;
      const h1 = document.querySelector('h1');
      return {
        innerWidth, scrollWidth: se ? se.scrollWidth : -1,
        h1Height: h1 ? h1.clientHeight : 0,
      };
    },
    regionBox(sel) {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { w: r.width, h: r.height };
    },
  };
})();
