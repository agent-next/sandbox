import { interpolate } from "remotion";

export const BG = "#0d1117";
export const PANEL = "#161b22";
export const FG = "#e6edf3";
export const DIM = "#8b949e";
export const GREEN = "#3fb950";
export const RED = "#f85149";
export const BLUE = "#58a6ff";
export const AMBER = "#d29922";
export const CYAN = "#39c5cf";

export const FONT_MONO =
  "'DejaVu Sans Mono', Menlo, Consolas, 'Liberation Mono', monospace";
export const FONT_SANS = "'DejaVu Sans', Helvetica, Arial, sans-serif";

/** Frame index (relative to `start`) clamped to the interval. */
export const rel = (frame: number, start: number) => frame - start;

/** Smooth 0..1 ramp over [start, start+dur]; holds 1 afterwards. */
export const ramp = (frame: number, start: number, dur: number) =>
  interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

/** Linear 0..1 ramp (no easing) then hold. */
export const lin = (frame: number, start: number, dur: number) =>
  interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

/** Ease-in-out 0..1 ramp over [start, start+dur]. */
export const ease = (frame: number, start: number, dur: number) => {
  const t = lin(frame, start, dur);
  return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
};

export const fmt = (n: number, digits = 3) =>
  n.toFixed(digits).replace(/0+$/, "").replace(/\.$/, "");

/** Scientific-ish short form for very small errors. */
export const fmtErr = (n: number | null) => {
  if (n === null || n === undefined) return "n/a";
  if (n === 0) return "0";
  if (n >= 1e-3) return n.toFixed(4);
  const e = Math.floor(Math.log10(n));
  const m = n / Math.pow(10, e);
  return `${m.toFixed(1)}e${e}`;
};
