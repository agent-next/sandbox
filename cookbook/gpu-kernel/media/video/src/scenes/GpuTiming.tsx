import React from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { BLUE, DIM, FG, FONT_MONO, FONT_SANS, GREEN, PANEL, CYAN, ease, lin } from "../theme";
import { CountUp } from "../CountUp";
import { ScanBand } from "../ScanBand";

/** The GPU slice's own measurement: kernel vs eager ms as growing bars, the
 * speedup spinning up and the effective GB/s counting to the measured value.
 * Every number is from the committed GPU report (media/data/report.json). */
export const GpuTiming: React.FC<{
  start: number;
  durationInFrames: number;
  kernelMs: number;
  eagerMs: number;
  speedup: number;
  gbPerS: number;
  caption: string;
  subcaption: string;
}> = ({ start, durationInFrames, kernelMs, eagerMs, speedup, gbPerS,
        caption, subcaption }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const grow = ease(frame, start + 10, Math.round(durationInFrames * 0.85));
  const zoom = lin(frame, start, durationInFrames);
  const scale = 1 + 0.06 * zoom;

  const maxMs = Math.max(kernelMs, eagerMs) * 1.15;
  const kW = (kernelMs / maxMs) * 720 * grow;
  const eW = (eagerMs / maxMs) * 720 * grow;

  return (
    <AbsoluteFill>
      <ScanBand start={start} durationInFrames={durationInFrames} left={100}
        width={1100} top={300} height={300} color={CYAN} period={70} />
      <div style={{ position: "absolute", inset: 0,
        transform: `scale(${scale})`, transformOrigin: "50% 55%" }}>
        <div style={{ position: "absolute", left: 100, top: 44 }}>
          <div style={{ fontFamily: FONT_SANS, fontSize: 62, fontWeight: 700,
            color: FG, letterSpacing: -1 }}>{caption}</div>
          <div style={{ fontFamily: FONT_MONO, fontSize: 30, color: DIM,
            marginTop: 8 }}>{subcaption}</div>
        </div>

        <div style={{ position: "absolute", left: 100, top: 300,
          width: 1100, background: PANEL, border: "1px solid #30363d",
          borderRadius: 18, padding: "40px 48px" }}>
          <div style={{ display: "flex", alignItems: "center" }}>
            <div style={{ width: 170, fontFamily: FONT_MONO, fontSize: 32,
              color: GREEN }}>kernel</div>
            <div style={{ width: 740, height: 64, background: "#0d1117",
              borderRadius: 12, overflow: "hidden",
              border: "1px solid #30363d" }}>
              <div style={{ width: kW, height: "100%", background: GREEN }} />
            </div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 44, color: GREEN,
              marginLeft: 24 }}>
              <CountUp from={0} to={kernelMs} start={start + 10}
                dur={Math.round(durationInFrames * 0.6)} digits={3} suffix=" ms" />
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", marginTop: 26 }}>
            <div style={{ width: 170, fontFamily: FONT_MONO, fontSize: 32,
              color: BLUE }}>eager</div>
            <div style={{ width: 740, height: 64, background: "#0d1117",
              borderRadius: 12, overflow: "hidden",
              border: "1px solid #30363d" }}>
              <div style={{ width: eW, height: "100%", background: BLUE }} />
            </div>
            <div style={{ fontFamily: FONT_MONO, fontSize: 44, color: BLUE,
              marginLeft: 24 }}>
              <CountUp from={0} to={eagerMs} start={start + 14}
                dur={Math.round(durationInFrames * 0.55)} digits={3} suffix=" ms" />
            </div>
          </div>
          <div style={{ fontFamily: FONT_MONO, fontSize: 28, color: DIM,
            marginTop: 22 }}>median of 9 CUDA-event timings &middot; (4096, 4096) fp32</div>
        </div>

        <div style={{ position: "absolute", right: 90, top: 330, width: 460,
          background: PANEL, border: "1px solid #30363d", borderRadius: 18,
          padding: "36px 40px", textAlign: "right" }}>
          <div style={{ fontFamily: FONT_MONO, fontSize: 26, color: DIM }}>
            effective throughput
          </div>
          <div style={{ fontFamily: FONT_SANS, fontSize: 84, fontWeight: 800,
            color: CYAN, marginTop: 8 }}>
            <CountUp from={0} to={gbPerS} start={start + 20}
              dur={Math.round(durationInFrames * 0.5)} digits={0} />
          </div>
          <div style={{ fontFamily: FONT_MONO, fontSize: 28, color: DIM }}>
            GB/s (cache-resident, not DRAM)
          </div>
          <div style={{ fontFamily: FONT_MONO, fontSize: 64, fontWeight: 700,
            color: FG, marginTop: 26 }}>
            <CountUp from={0.4} to={speedup} start={start + 26}
              dur={Math.round(durationInFrames * 0.45)} digits={2}
              prefix="x" suffix=" vs eager" />
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
