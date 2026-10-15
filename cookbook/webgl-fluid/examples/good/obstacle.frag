// examples/good/obstacle.frag — obstacle enforcement patch for the
// pinned upstream WebGL-Fluid-Simulation.
//
// Compiled by the judge against upstream's baseVertexShader. It samples the
// target texture (blitted over both dye and velocity each frame by the
// engine) and zeroes anything inside the declared obstacle rectangles.
// Rectangles are normalized [0,1] texcoords, y up — the same convention the
// engine and config.json use.
precision highp float;
precision highp sampler2D;

varying vec2 vUv;
uniform sampler2D uTarget;

// {x0, y0, x1, y1}; must match examples/good/config.json obstacles.
const vec4 OBS0 = vec4(0.55, 0.30, 0.62, 0.70);
const vec4 OBS1 = vec4(0.75, 0.10, 0.82, 0.45);

void main () {
    vec4 c = texture2D(uTarget, vUv);
    if (vUv.x > OBS0.x && vUv.x < OBS0.z && vUv.y > OBS0.y && vUv.y < OBS0.w)
        c = vec4(0.0);
    if (vUv.x > OBS1.x && vUv.x < OBS1.z && vUv.y > OBS1.y && vUv.y < OBS1.w)
        c = vec4(0.0);
    gl_FragColor = c;
}
