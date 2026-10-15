// examples/good/drive.js — the artifact's deterministic driver.
//
// Runs inside the judge harness (judge/driver/index.html + engine.js) via
// window.__WFS__. No wall clock: the engine's frame(dt) is the only clock.
// The sequence is fully scripted by scene/config.json: the probe splat (the
// tracked physics calibration), the aim splat (fired at the obstacles), and
// the decorative "show" splats. The obstacle mask program comes from the
// artifact's own obstacle.frag.
(async function () {
    const T = window.__WFS__;
    await T.ready;
    const s = T.scene();

    // The agent's GLSL patch enforces the declared obstacles on both the dye
    // and the velocity fields after every solver step.
    T.setMaskProgram(T.frag());

    const show = s.show || [];
    for (let k = 0; k < s.frames; k++) {
        for (const spl of show) {
            if (spl.frame === k)
                T.splat(spl.x, spl.y, spl.dx, spl.dy, spl.rgb);
        }
        if (k === s.probe.frame)
            T.splat(s.probe.x, s.probe.y, s.probe.dx, s.probe.dy, s.probe.rgb);
        // Stationary decay patch: zero velocity, dye only — its boxed mass
        // decays purely by DENSITY_DISSIPATION (gate 5's oracle).
        if (k === s.decay.frame)
            T.splat(s.decay.x, s.decay.y, 0.0, 0.0, s.decay.rgb);
        if (k === s.aim.frame)
            T.splat(s.aim.x, s.aim.y, s.aim.dx, s.aim.dy, s.aim.rgb);
        T.frame(s.dt);
    }
    T.finish();
})().catch(function (e) {
    window.__WFS_CONSOLE__.errors.push('drive.js: ' + (e && e.message || e));
    window.__WFS_ABORTED__ = true;
});
