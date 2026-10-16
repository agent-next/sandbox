import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { RaceCase } from "../types";
import { BLUE, DIM, FG, FONT_MONO, FONT_SANS, GREEN, PANEL, fmt, lin } from "../theme";

type Iter = {
  case: number;
  shape: number[];
  dist: string;
  iter: number;
  kernel_ms: number;
  eager_ms: number;
};

export const flatten = (cases: RaceCase[]): Iter[] => {
  const out: Iter[] = [];
  for (const c of cases) {
    for (let i = 0; i < c.kernel_ms.length; i++) {
      out.push({
        case: c.case,
        shape: c.shape,
        dist: c.dist,
        iter: i,
        kernel_ms: c.kernel_ms[i],
        eager_ms: c.eager_ms[i],
      });
    }
  }
  return out;
};

const PAD_L = 170;
const PAD_R = 90;
const PAD_T = 210;
const PAD_B = 230;

/** The hero shot: the real per-iteration kernel/eager timings drawn live as
 * growing lines, with growing bars for the two current values. Every value is
 * a measured iteration from this sandbox's judge run. */
export const Race: React.FC<{
  cases: RaceCase[];
  start: number;
  durationInFrames: number;
  zoom?: boolean;
  bright?: boolean;
  finished?: boolean;
  caption: string;
  subcaption: string;
}> = ({ cases, start, durationInFrames, zoom = false, bright = false,
        finished = false, caption, subcaption }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const iters = useMemo(() => flatten(cases), [cases]);

  // log scale: interpreter-mode kernel and eager iterations differ by orders
  // of magnitude, and the labels always say so. log10(0.001) = -3 .. log10(max)
  const maxLog = useMemo(() => {
    const hi = Math.max(...iters.map((i) => Math.max(i.kernel_ms, i.eager_ms)));
    return Math.log10(hi) + 0.35;
  }, [iters]);
  const minLog = -3;

  const n = iters.length;
  const chartW = width - PAD_L - PAD_R;
  const chartH = height - PAD_T - PAD_B;
  const xOf = (i: number) => PAD_L + (n <= 1 ? 0 : (i / (n - 1)) * chartW);
  const yOf = (v: number) =>
    PAD_T + chartH - ((Math.log10(v) - minLog) / (maxLog - minLog)) * chartH;

  // The trace reveals fast (the first ~30% of the shot) so the shot is
  // already full, then a playhead sweeps the whole finished trace for the
  // rest of the time, with a pulsing head and value bars that track it. Every
  // frame therefore contains a visibly different state.
  const growF = Math.max(1, Math.round(durationInFrames * 0.3));
  const p = lin(frame, start + 6, growF);
  // `finished` seeds the reveal (the hook opens on the completed trace)
  const floorReveal = finished ? Math.floor(n * 0.75) : 1;
  const revealed = Math.max(floorReveal, Math.ceil(p * n));
  // playhead: a continuous ping-pong sweep across all n iterations
  const sweepT = Math.max(0, frame - (start + 6));
  const cycle = n * 2;
  const pos = (sweepT * 0.55) % cycle;
  const raw = pos < n ? pos : cycle - pos;
  const scanIdx = Math.max(0, Math.min(n - 1, Math.round(raw)));
  const scanX = xOf(scanIdx);
  const scanIter = iters[scanIdx];
  const cur = iters[Math.min(n - 1, revealed - 1)];
  // the head dot pulses so the frame always changes
  const pulse = 0.6 + 0.4 * Math.abs(Math.sin((frame - start) / 4));

  const kPts = iters.slice(0, revealed).map((it, i) => `${xOf(i)},${yOf(it.kernel_ms)}`);
  const ePts = iters.slice(0, revealed).map((it, i) => `${xOf(i)},${yOf(it.eager_ms)}`);

  // case boundaries for faint separators + labels
  const bounds: { x: number; label: string }[] = [];
  let acc = 0;
  for (const c of cases) {
    bounds.push({ x: xOf(acc), label: `${c.shape[0]}x${c.shape[1]}` });
    acc += c.kernel_ms.length;
  }

  // optional slow camera move (a real pan/zoom over the moving chart)
  const zt = lin(frame, start, durationInFrames);
  const scale = zoom ? 1 + 0.10 * zt : 1;
  const tx = zoom ? -40 * zt : 0;
  const ty = zoom ? 24 * zt : 0;

  // log-ish bar scaling so both a 0.1 ms and a 300 ms value stay visible;
  // the exact values are always printed next to the bar.
  const barMax = Math.max(...iters.map((i) => Math.max(i.kernel_ms, i.eager_ms)));
  const loLog = Math.log10(0.001);
  const spanLog = Math.log10(barMax) - loLog;
  const barW = (v: number) =>
    ((Math.log10(Math.max(v, 0.001)) - loLog) / spanLog) * 560;

  return (
    <AbsoluteFill>
      {/* the hook slot opens on a brighter backdrop so the very first frame
          is neither dark nor near-empty; the escalation slot keeps the
          standard set dressing */}
      {bright ? (
        <AbsoluteFill style={{
          background: "radial-gradient(1300px 850px at 50% 42%, #24406f 0%, #14223c 55%, #0e1626 100%)",
        }} />
      ) : null}
      <div
        style={{
          position: "absolute",
          inset: 0,
          transform: `translate(${tx}px, ${ty}px) scale(${scale})`,
          transformOrigin: "58% 46%",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: PAD_L - 12,
            top: PAD_T - 78,
            width: chartW + 40,
            height: chartH + 40,
            background: PANEL,
            border: "1px solid #30363d",
            borderRadius: 18,
          }}
        />
        <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
          {[-3, -2, -1, 0, 1, 2, 3].filter((l) => l <= maxLog).map((l) => {
            const y = yOf(Math.pow(10, l));
            if (y < PAD_T - 4 || y > PAD_T + chartH + 4) return null;
            return (
              <g key={l}>
                <line x1={PAD_L} y1={y} x2={PAD_L + chartW} y2={y}
                  stroke="#21262d" strokeWidth={2} />
                <text x={PAD_L - 20} y={y + 10} fill={DIM} fontSize={28}
                  textAnchor="end" fontFamily={FONT_MONO}>
                  {l === 0 ? "1" : `1e${l}`}
                </text>
              </g>
            );
          })}
          <text x={40} y={PAD_T + chartH / 2} fill={DIM} fontSize={30}
            fontFamily={FONT_MONO}
            transform={`rotate(-90 40 ${PAD_T + chartH / 2})`}
            textAnchor="middle">
            ms per iteration (log scale)
          </text>
          {bounds.map((b, i) => (
            <g key={i}>
              <line x1={b.x} y1={PAD_T} x2={b.x} y2={PAD_T + chartH}
                stroke="#30363d" strokeDasharray="4 8" strokeWidth={2} />
              <text x={b.x + 10} y={PAD_T + chartH + 34} fill={DIM}
                fontSize={24} fontFamily={FONT_MONO}>
                {b.label}
              </text>
            </g>
          ))}
          <polyline points={ePts.join(" ")} fill="none" stroke={BLUE}
            strokeWidth={6} strokeLinejoin="round" opacity={0.95} />
          <polyline points={kPts.join(" ")} fill="none" stroke={GREEN}
            strokeWidth={6} strokeLinejoin="round" />
          <circle cx={scanX} cy={yOf(scanIter.eager_ms)} r={11 * pulse}
            fill={BLUE} stroke="#ffffff" strokeWidth={2} />
          <circle cx={scanX} cy={yOf(scanIter.kernel_ms)} r={14 * pulse}
            fill={GREEN} stroke="#ffffff" strokeWidth={2} />
          <line x1={scanX} y1={PAD_T} x2={scanX} y2={PAD_T + chartH}
            stroke={FG} strokeWidth={2} opacity={0.55} />
          {/* a soft highlight band trailing the playhead keeps the whole
              chart area visibly alive frame to frame */}
          <rect x={Math.max(PAD_L, scanX - 120)} y={PAD_T}
            width={240} height={chartH}
            fill="#ffffff" opacity={0.05} />
        </svg>
      </div>

      {/* headline caption — width-capped so it never runs under the legend */}
      <div style={{ position: "absolute", left: PAD_L - 12, top: 44,
        maxWidth: 1000 }}>
        <div style={{ fontFamily: FONT_SANS, fontSize: 62, fontWeight: 700,
          color: FG, letterSpacing: -1 }}>
          {caption}
        </div>
        <div style={{ fontFamily: FONT_MONO, fontSize: 30, color: DIM,
          marginTop: 8 }}>
          {subcaption}
        </div>
      </div>

      {/* live legend: the numbers tick with the sweeping cursor */}
      <div style={{ position: "absolute", right: 70, top: 56, width: 620,
        textAlign: "right" }}>
        <Legend color={GREEN} label="fused Triton kernel"
          value={`${fmt(scanIter.kernel_ms)} ms`} />
        <Legend color={BLUE} label="torch eager softmax"
          value={`${fmt(scanIter.eager_ms)} ms`} />
        <div style={{ fontFamily: FONT_MONO, fontSize: 26, color: DIM, marginTop: 10 }}>
          iteration {Math.round(scanIdx) + 1} / {n} &middot; {scanIter.shape[0]}x{scanIter.shape[1]} {scanIter.dist}
        </div>
      </div>

      {/* bars for the iteration under the playhead */}
      <div style={{ position: "absolute", left: PAD_L, bottom: 40,
        width: 820 }}>
        <Bar color={GREEN} label="kernel" w={barW(scanIter.kernel_ms)} v={scanIter.kernel_ms} />
        <Bar color={BLUE} label="eager" w={barW(scanIter.eager_ms)} v={scanIter.eager_ms} />
      </div>
    </AbsoluteFill>
  );
};

const Legend: React.FC<{ color: string; label: string; value: string }> = ({
  color, label, value,
}) => (
  <div style={{ fontFamily: FONT_MONO, fontSize: 32, color, marginTop: 6 }}>
    <span style={{ display: "inline-block", width: 26, height: 6,
      background: color, marginRight: 12, verticalAlign: "middle" }} />
    {label} &nbsp;<b>{value}</b>
  </div>
);

const Bar: React.FC<{ color: string; label: string; w: number; v: number }> = ({
  color, label, w, v,
}) => (
  <div style={{ display: "flex", alignItems: "center", marginTop: 12 }}>
    <div style={{ width: 150, fontFamily: FONT_MONO, fontSize: 30, color: DIM }}>
      {label}
    </div>
    <div style={{ width: 580, height: 40, background: "#161b22", borderRadius: 10,
      border: "1px solid #30363d", overflow: "hidden" }}>
      <div style={{ width: w, height: "100%", background: color }} />
    </div>
    <div style={{ width: 240, fontFamily: FONT_MONO, fontSize: 30, color,
      marginLeft: 18 }}>{v.toFixed(3)} ms</div>
  </div>
);
