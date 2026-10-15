// judge/driver/engine.js — the judge's deterministic engine over the pinned
// upstream sim. Everything the artifact can do goes through window.__WFS__;
// everything the judge measures is computed here, from the GPU dye texture
// the sim itself produced.
//
// Contract (see SPEC.md):
//   __WFS__.ready          promise, resolves once scene/config.json is applied
//   __WFS__.scene()        the parsed artifact config.json
//   __WFS__.frag()         the artifact's obstacle.frag source text
//   __WFS__.setMaskProgram(src)  compile the artifact's obstacle shader
//   __WFS__.splat(x, y, dx, dy, rgb)  one dye+velocity splat (upstream units)
//   __WFS__.frame(dt)      step(dt) -> apply obstacle mask -> capture frame
//                          (records hash, mass, centroid, per-obstacle
//                          mass, decay-box mass, nonblank count, NaN flag)
//   __WFS__.finish()       seal the run (window.__WFS_RESULT__)
//   __WFS__.resetAll()     zero every FBO, clear the frame log
//   __WFS__.exportFrames(idx)  base64 RGBA of stashed raw frames (media)
//
// Coordinate convention everywhere: upstream texcoords, u right, v UP,
// [0,1]. readPixels row 0 is v=0 (bottom), so pixel row r is v=(r+0.5)/H.
(function () {
    'use strict';

    // ---- pure-JS SHA-256 (no secure-context dependency) -------------------
    var K = new Uint32Array([
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
        0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
        0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
        0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
        0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
        0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
        0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
        0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a56cb6, 0x84c87814, 0x8cc70208,
        0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);

    function sha256hex (bytes) {
        var len = bytes.length;
        var bitLenHi = Math.floor(len / 0x20000000);
        var bitLenLo = (len << 3) >>> 0;
        var withOne = len + 1;
        var total = (((withOne + 8) >> 6) + 1) << 6;
        var m = new Uint8Array(total);
        m.set(bytes);
        m[len] = 0x80;
        var dv = new DataView(m.buffer);
        dv.setUint32(total - 8, bitLenHi);
        dv.setUint32(total - 4, bitLenLo);
        var H = new Uint32Array([
            0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
            0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]);
        var w = new Uint32Array(64);
        for (var off = 0; off < total; off += 64) {
            for (var i = 0; i < 16; i++)
                w[i] = dv.getUint32(off + i * 4);
            for (i = 16; i < 64; i++) {
                var s0 = ((w[i-15] >>> 7) | (w[i-15] << 25)) ^
                         ((w[i-15] >>> 18) | (w[i-15] << 14)) ^
                         (w[i-15] >>> 3);
                var s1 = ((w[i-2] >>> 17) | (w[i-2] << 15)) ^
                         ((w[i-2] >>> 19) | (w[i-2] << 13)) ^
                         (w[i-2] >>> 10);
                w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
            }
            var a = H[0], b = H[1], c = H[2], d = H[3];
            var e = H[4], f = H[5], g = H[6], h = H[7];
            for (i = 0; i < 64; i++) {
                var S1 = ((e >>> 6) | (e << 26)) ^ ((e >>> 11) | (e << 21)) ^
                         ((e >>> 25) | (e << 7));
                var ch = (e & f) ^ (~e & g);
                var t1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
                var S0 = ((a >>> 2) | (a << 30)) ^ ((a >>> 13) | (a << 19)) ^
                         ((a >>> 22) | (a << 10));
                var mj = (a & b) ^ (a & c) ^ (b & c);
                var t2 = (S0 + mj) >>> 0;
                h = g; g = f; f = e;
                e = (d + t1) >>> 0;
                d = c; c = b; b = a;
                a = (t1 + t2) >>> 0;
            }
            H[0] = (H[0] + a) >>> 0; H[1] = (H[1] + b) >>> 0;
            H[2] = (H[2] + c) >>> 0; H[3] = (H[3] + d) >>> 0;
            H[4] = (H[4] + e) >>> 0; H[5] = (H[5] + f) >>> 0;
            H[6] = (H[6] + g) >>> 0; H[7] = (H[7] + h) >>> 0;
        }
        var out = '';
        for (i = 0; i < 8; i++) {
            var s = H[i].toString(16);
            while (s.length < 8) s = '0' + s;
            out += s;
        }
        return out;
    }

    // ---- engine state ------------------------------------------------------
    var st = {
        scene: null, fragSrc: null,
        maskProgram: null, maskBroken: false,
        cap: null, capBuf: null, W: 0, H: 0,
        floatBuf: null, floatRead: null,   // null = untested, false = unsupported
        frames: [], run1Raw: null, rawKept: [], runIndex: 1,
    };

    function fatal (msg) {
        window.__WFS_CONSOLE__.errors.push(String(msg).slice(0, 500));
        window.__WFS_FATAL__ = String(msg).slice(0, 500);
    }

    function zeroFBO (f) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, f.fbo);
        gl.viewport(0, 0, f.width, f.height);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
    }

    function resetAll () {
        zeroFBO(dye.read);      zeroFBO(dye.write);
        zeroFBO(velocity.read); zeroFBO(velocity.write);
        zeroFBO(pressure.read); zeroFBO(pressure.write);
        zeroFBO(divergence);    zeroFBO(curl);
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);
        st.frames = [];
        window.__WFS_RESULT__ = undefined;
    }

    function setMaskProgram (src) {
        var sh = gl.createShader(gl.FRAGMENT_SHADER);
        gl.shaderSource(sh, src);
        gl.compileShader(sh);
        if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
            var log = gl.getShaderInfoLog(sh) || 'no shader info log';
            st.maskBroken = true;
            var err = 'obstacle shader failed to compile: ' +
                      String(log).slice(0, 300);
            window.__WFS_CONSOLE__.errors.push(err);
            throw new Error(err);
        }
        var prog = new Program(baseVertexShader, sh);
        if (!gl.getProgramParameter(prog.program, gl.LINK_STATUS)) {
            var plog = gl.getProgramInfoLog(prog.program) || 'no link log';
            st.maskBroken = true;
            throw new Error('obstacle shader failed to link: ' +
                            String(plog).slice(0, 300));
        }
        st.maskProgram = prog;
    }

    function applyMask () {
        if (st.maskBroken)
            throw new Error('obstacle shader is broken; refusing to step');
        if (!st.maskProgram) return;
        var prog = st.maskProgram;
        gl.disable(gl.BLEND);
        prog.bind();
        gl.uniform1i(prog.uniforms.uTarget, dye.read.attach(0));
        blit(dye.write);
        dye.swap();
        gl.uniform1i(prog.uniforms.uTarget, velocity.read.attach(0));
        blit(velocity.write);
        velocity.swap();
    }

    function probeFloatRead () {
        // Can this implementation readPixels FLOAT from the RGBA16F dye?
        try {
            gl.bindFramebuffer(gl.FRAMEBUFFER, dye.read.fbo);
            var n = dye.width * dye.height * 4;
            var probeBuf = new Float32Array(n);
            gl.readPixels(0, 0, dye.width, dye.height, gl.RGBA, gl.FLOAT,
                          probeBuf);
            var err = gl.getError();
            return err === gl.NO_ERROR;
        } catch (e) {
            return false;
        }
    }

    function captureFrame () {
        var W = st.W, H = st.H, buf = st.capBuf;
        copyProgram.bind();
        gl.uniform1i(copyProgram.uniforms.uTexture, dye.read.attach(0));
        blit(st.cap);
        gl.bindFramebuffer(gl.FRAMEBUFFER, st.cap.fbo);
        gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf);

        var mass = 0, wsum = 0, cx = 0, cy = 0, nonblank = 0;
        var inside = (st.scene.obstacles || []).map(function () { return 0; });
        var db = st.scene.decay && st.scene.decay.box;
        var decayMass = 0;
        var tb = st.scene.probe && st.scene.probe.box;
        var twsum = 0, tcx = 0, tcy = 0;
        for (var row = 0; row < H; row++) {
            var v = (row + 0.5) / H;
            for (var col = 0; col < W; col++) {
                var i = (row * W + col) * 4;
                var r = buf[i], g = buf[i + 1], b = buf[i + 2];
                var mean = (r + g + b) / 3;
                mass += mean;
                if (r + g + b > 0) {
                    nonblank++;
                    var wgt = mean;
                    wsum += wgt;
                    cx += (col + 0.5) * wgt;
                    cy += (row + 0.5) * wgt;
                }
                var u = (col + 0.5) / W;
                for (var o = 0; o < st.scene.obstacles.length; o++) {
                    var ob = st.scene.obstacles[o];
                    if (u >= ob.x0 && u <= ob.x1 && v >= ob.y0 && v <= ob.y1)
                        inside[o] += mean;
                }
                if (db && u >= db.x0 && u <= db.x1 && v >= db.y0 && v <= db.y1)
                    decayMass += mean;
                if (tb && u >= tb.x0 && u <= tb.x1 && v >= tb.y0 && v <= tb.y1) {
                    twsum += mean;
                    tcx += u * mean;
                    tcy += v * mean;
                }
            }
        }
        var f = {
            hash: sha256hex(buf),
            mass: mass / 255,
            decayMass: decayMass / 255,
            nonblank: nonblank,
            cx: wsum > 0 ? cx / wsum / W : null,
            cy: wsum > 0 ? cy / wsum / H : null,
            tcx: twsum > 0 ? tcx / twsum : null,
            tcy: twsum > 0 ? tcy / twsum : null,
            trackMass: twsum / 255,
            inside: inside.map(function (m) { return m / 255; }),
            nan: false,
        };

        // NaN scan on the live float dye texture when supported.
        if (st.floatRead !== false) {
            if (st.floatRead === null) st.floatRead = probeFloatRead();
            if (st.floatRead) {
                gl.bindFramebuffer(gl.FRAMEBUFFER, dye.read.fbo);
                gl.readPixels(0, 0, dye.width, dye.height,
                              gl.RGBA, gl.FLOAT, st.floatBuf);
                var fb = st.floatBuf;
                for (var j = 0; j < fb.length; j += 4) {
                    if (!isFinite(fb[j]) || !isFinite(fb[j + 1]) ||
                        !isFinite(fb[j + 2])) { f.nan = true; break; }
                }
            }
        }
        gl.bindFramebuffer(gl.FRAMEBUFFER, null);

        // Determinism cross-check against run 1 (SSIM on 8-bit luma).
        f.ssim = null;
        var prev = st.run1Raw && st.run1Raw[st.frames.length];
        if (prev && st.runIndex === 2) {
            if (prev.hash === f.hash) {
                f.ssim = 1.0;
            } else {
                f.ssim = globalSSIM(prev.raw, buf);
                st.rawKept[st.frames.length] = buf.slice(0);
            }
        } else if (st.runIndex === 1) {
            st.run1Raw.push({ hash: f.hash, raw: buf.slice(0) });
        }
        st.frames.push(f);
    }

    // Global (single-window) SSIM on 8-bit luma in [0,1]; documented
    // approximation used only when hashes differ (SPEC gate 2).
    function globalSSIM (a, b) {
        var n = a.length / 4, sa = 0, sb = 0;
        for (var i = 0; i < a.length; i += 4) {
            sa += (a[i] * 0.299 + a[i+1] * 0.587 + a[i+2] * 0.114) / 255;
            sb += (b[i] * 0.299 + b[i+1] * 0.587 + b[i+2] * 0.114) / 255;
        }
        sa /= n; sb /= n;
        var va = 0, vb = 0, cov = 0;
        for (i = 0; i < a.length; i += 4) {
            var la = (a[i] * 0.299 + a[i+1] * 0.587 + a[i+2] * 0.114) / 255 - sa;
            var lb = (b[i] * 0.299 + b[i+1] * 0.587 + b[i+2] * 0.114) / 255 - sb;
            va += la * la; vb += lb * lb; cov += la * lb;
        }
        va /= n; vb /= n; cov /= n;
        var C1 = 0.01 * 0.01, C2 = 0.03 * 0.03;
        return (2 * sa * sb + C1) * (2 * cov + C2) /
               ((sa * sa + sb * sb + C1) * (va + vb + C2));
    }

    function frame (dt) {
        if (typeof dt !== 'number' || !(dt > 0))
            throw new Error('frame(dt): dt must be a positive number');
        step(dt);
        applyMask();
        captureFrame();
    }

    function finish () {
        window.__WFS_RESULT__ = {
            frames: st.frames,
            complete: st.frames.length,
        };
    }

    function b64 (u8) {
        var s = '', CH = 0x8000;
        for (var i = 0; i < u8.length; i += CH)
            s += String.fromCharCode.apply(null, u8.subarray(i, i + CH));
        return btoa(s);
    }

    var api = {
        ready: null,
        scene: function () { return st.scene; },
        frag: function () { return st.fragSrc; },
        setMaskProgram: setMaskProgram,
        splat: function (x, y, dx, dy, rgb) {
            // upstream splat() wants a {r,g,b} object; the artifact
            // declares colours as [r,g,b] arrays.
            splat(x, y, dx, dy, { r: rgb[0], g: rgb[1], b: rgb[2] });
        },
        frame: frame,
        finish: finish,
        resetAll: function () {
            // Between the two determinism runs: wipe every upstream FBO,
            // clear the frame log, and switch the determinism cross-check to
            // run 2 (per-frame SSIM against run 1's stashed raw frames).
            resetAll();
            st.runIndex = 2;
            st.rawKept = {};
            window.__WFS_ABORTED__ = undefined;
        },
        exportFrames: function (idxs) {
            return idxs.map(function (i) {
                var src = (st.run1Raw && st.run1Raw[i]) ? st.run1Raw[i].raw
                                                        : null;
                if (!src && st.rawKept) src = st.rawKept[i] || null;
                return src ? b64(src) : null;
            });
        },
    };
    window.__WFS__ = api;
    window.__WFS_RAW__ = function (i) {  // debug: last run raw frame b64
        return st.run1Raw && st.run1Raw[i] ? b64(st.run1Raw[i].raw) : null;
    };

    st.ready = (async function () {
        try {
            var cfgRes = await fetch('/scene/config.json');
            if (!cfgRes.ok) throw new Error('config.json: HTTP ' + cfgRes.status);
            st.scene = await cfgRes.json();
            var fragRes = await fetch('/scene/obstacle.frag');
            if (!fragRes.ok) throw new Error('obstacle.frag: HTTP ' + fragRes.status);
            st.fragSrc = await fragRes.text();

            // Apply the artifact's overrides, then force the pixel-exact
            // display settings the judge's readback relies on.
            var over = st.scene.config || {};
            for (var k of Object.keys(over)) config[k] = over[k];
            config.PAUSED = false;
            config.COLORFUL = false;
            config.SHADING = false;
            config.BLOOM = false;
            config.SUNRAYS = false;
            config.TRANSPARENT = false;
            updateKeywords();
            initFramebuffers();

            st.W = dye.width; st.H = dye.height;
            st.cap = createFBO(dye.width, dye.height, gl.RGBA, gl.RGBA,
                               gl.UNSIGNED_BYTE, gl.NEAREST);
            st.capBuf = new Uint8Array(dye.width * dye.height * 4);
            st.floatBuf = new Float32Array(
                dye.width * dye.height * 4);

            var dbg = gl.getExtension('WEBGL_debug_renderer_info');
            window.__WFS_META__ = {
                glVersion: gl.getParameter(gl.VERSION),
                renderer: dbg ? gl.getParameter(
                    dbg.UNMASKED_RENDERER_WEBGL) : 'unknown',
                dyeWidth: dye.width, dyeHeight: dye.height,
                simWidth: velocity.width, simHeight: velocity.height,
                floatRead: probeFloatRead(),
            };
            st.floatRead = window.__WFS_META__.floatRead;

            st.runIndex = 1;
            st.run1Raw = [];
            st.rawKept = {};
            resetAll();
            window.__WFS_READY__ = true;
        } catch (e) {
            fatal('engine init failed: ' + (e && e.message ? e.message : e));
            throw e;
        }
    })();
    api.ready = st.ready;
})();
