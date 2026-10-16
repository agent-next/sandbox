import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { DIM, FG, FONT_MONO, FONT_SANS, GREEN, BLUE, lin, ease, PANEL } from "../theme";
import { ScanBand } from "../ScanBand";

/** Input -> output: one real input row and the softmax the real kernel
 * produced for it (clips/row.json), animated as growing bars. The bars move
 * the whole time as the reveal sweeps; the row is the judge's 37x65 case. */
export const RowTransform: React.FC<{
  start: number;
  durationInFrames: number;
  row: { in: number[]; out: number[] };
  caption: string;
  subcaption: string;
}> = ({ start, durationInFrames, row, caption, subcaption }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const n = row.in.length;

  const inMin = Math.min(...row.in);
  const inMax = Math.max(...row.in);
  const outMax = Math.max(...row.out);

  const p = lin(frame, start, Math.round(durationInFrames * 0.96));
  const revealed = Math.max(1, Math.ceil(p * n));
  // a highlight column keeps sweeping the bars while the shot is on screen —
  // fast enough that the frame visibly changes every frame it is up
  const sweepT = Math.max(0, frame - start - Math.round(durationInFrames * 0.3));
  const sweepIdx = Math.floor(((sweepT / 4) % n));

  const colW = (width - 620) / n;
  const left = 130;
  // two stacked bands, each with its label above the tallest possible bar so
  // the bars never cross their own caption
  const inBase = 470;
  const inH = 240;
  const outBase = height - 130;
  const outH = 330;

  const flash = 0.35 + 0.65 * Math.abs(Math.sin((frame - start) / 22));

  return (
    <AbsoluteFill>
      <ScanBand start={start} durationInFrames={durationInFrames} left={110}
        width={width - 220} top={inBase - inH - 40} height={outBase + 70 - (inBase - inH - 40)}
        color={BLUE} period={80} />
      <div style={{ position: "absolute", left: 100, top: 44 }}>
        <div style={{ fontFamily: FONT_SANS, fontSize: 62, fontWeight: 700,
          color: FG, letterSpacing: -1 }}>{caption}</div>
        <div style={{ fontFamily: FONT_MONO, fontSize: 30, color: DIM,
          marginTop: 8 }}>{subcaption}</div>
      </div>

      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        {row.in.slice(0, revealed).map((v, i) => {
          const h = ((v - inMin) / (inMax - inMin || 1)) * inH + 8;
          const x = left + i * colW;
          return (
            <rect key={i} x={x} y={inBase - h} width={colW * 0.72}
              height={h} fill={BLUE} opacity={0.9} rx={3} />
          );
        })}
        <line x1={110} y1={inBase} x2={width - 110} y2={inBase}
          stroke="#30363d" strokeWidth={2} />
        <text x={left} y={inBase - inH - 26} fill={BLUE} fontSize={30}
          fontFamily={FONT_MONO}>
          input x &mdash; one row of the judge&apos;s 37x65 case (values {inMin.toFixed(2)}..{inMax.toFixed(2)})
        </text>

        {row.out.slice(0, revealed).map((v, i) => {
          const h = (v / outMax) * outH + 3;
          const x = left + i * colW;
          return (
            <g key={i}>
              <rect x={x} y={outBase - h} width={colW * 0.72} height={h}
                fill={GREEN} opacity={0.95} rx={3} />
              {i % 8 === 0 ? (
                <text x={x + colW * 0.36} y={outBase - h - 12} fill={GREEN}
                  fontSize={22} fontFamily={FONT_MONO} textAnchor="middle">
                  {v.toFixed(3)}
                </text>
              ) : null}
            </g>
          );
        })}
        {sweepIdx < revealed ? (
          <rect x={left + sweepIdx * colW - 4} y={outBase - outH - 10}
            width={colW * 0.72 + 8} height={outH + 16} fill="none"
            stroke="#ffffff" strokeWidth={3} opacity={0.55} rx={4} />
        ) : null}
        <line x1={110} y1={outBase} x2={width - 110} y2={outBase}
          stroke="#30363d" strokeWidth={2} />
        <text x={left} y={outBase + 44} fill={GREEN} fontSize={30}
          fontFamily={FONT_MONO}>
          output softmax(x) &mdash; rows sum to 1.000000, every value in [0, 1]
        </text>
      </svg>

      <div style={{ position: "absolute", right: 80, top: 260, width: 380,
        background: PANEL, border: "1px solid #30363d", borderRadius: 16,
        padding: "26px 28px", fontFamily: FONT_MONO, fontSize: 28, color: FG,
        opacity: ease(frame, start + 10, 12) }}>
        <div style={{ color: DIM, fontSize: 24 }}>running row sum</div>
        <div style={{ fontSize: 44, color: GREEN, marginTop: 6 }}>
          {row.out.slice(0, revealed).reduce((a, b) => a + b, 0).toFixed(4)}
        </div>
        <div style={{ color: DIM, fontSize: 24, marginTop: 14 }}>
          &rarr; 1.0000 at column {n} (judge gate: |sum-1| &le; 1e-4)
        </div>
        <div style={{ marginTop: 18, height: 14, background: "#0d1117",
          borderRadius: 7, overflow: "hidden" }}>
          <div style={{ width: `${p * 100}%`, height: "100%",
            background: GREEN, opacity: flash }} />
        </div>
        <div style={{ color: DIM, fontSize: 22, marginTop: 14 }}>
          sweeping column {Math.min(sweepIdx + 1, n)} / {n}
        </div>
      </div>
    </AbsoluteFill>
  );
};
