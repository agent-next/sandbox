import React from "react";
import {
  AbsoluteFill, OffthreadVideo, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";
import { DIM, FG, FONT_MONO, FONT_SANS, GREEN, lin, ramp } from "../theme";

/** The agent's real sandbox run, sped up: the recorded judge run plays here
 * with a HUD on top (the real speed-up, the phase, and a growing progress
 * bar). The footage itself is moving the whole time. */
export const Terminal: React.FC<{
  start: number;
  durationInFrames: number;
  clip: string;
  clipSeconds: number;
  speed: number;
  clipFrom: number;
  wall: { setup_s: number; selftest_s: number; grade_s: number };
  mutantsKilled: number;
  mutantsTotal: number;
  gradePass: boolean;
  kicker: string;
}> = ({ start, durationInFrames, clip, clipSeconds, speed, clipFrom, wall,
        mutantsKilled, mutantsTotal, gradePass, kicker }) => {
  const frame = useCurrentFrame();
  const { width } = useVideoConfig();
  const p = lin(frame, start, durationInFrames);
  const total = wall.setup_s + wall.selftest_s + wall.grade_s;
  const done = Math.min(mutantsTotal, Math.floor(p * mutantsTotal + 0.001));
  const elapsed = Math.round(p * total);

  return (
    <AbsoluteFill>
      {/* the real recorded footage fills the frame, always moving */}
      <OffthreadVideo src={staticFile(clip)} startFrom={clipFrom} muted
        style={{ width: "100%", height: "100%", objectFit: "cover" }} />

      {/* top kicker */}
      <div style={{ position: "absolute", left: 0, right: 0, top: 0,
        height: 96, background: "linear-gradient(180deg,#0d1117ee,#0d111700)",
        display: "flex", alignItems: "center", padding: "0 56px",
        justifyContent: "space-between" }}>
        <div style={{ fontFamily: FONT_SANS, fontSize: 44, fontWeight: 700,
          color: FG }}>{kicker}</div>
        <div style={{ fontFamily: FONT_MONO, fontSize: 40, color: GREEN }}>
          {speed}&times; speed &middot; real run {total.toFixed(0)} s
        </div>
      </div>

      {/* bottom HUD: phases + progress */}
      <div style={{ position: "absolute", left: 0, right: 0, bottom: 0,
        padding: "40px 56px 48px",
        background: "linear-gradient(0deg,#0d1117f2,#0d111700)" }}>
        <div style={{ display: "flex", gap: 28, fontFamily: FONT_MONO,
          fontSize: 30 }}>
          <Phase label={`setup ${wall.setup_s.toFixed(0)}s`}
            on={p > 0} />
          <Phase label={`selftest ${wall.selftest_s.toFixed(0)}s`}
            on={p * total > wall.setup_s} />
          <Phase label={`grade ${wall.grade_s.toFixed(0)}s`}
            on={p * total > wall.setup_s + wall.selftest_s} />
          <div style={{ color: DIM, marginLeft: "auto" }}>
            mutants killed {done}/{mutantsTotal} &middot; elapsed {elapsed}s
          </div>
        </div>
        <div style={{ marginTop: 18, height: 22, background: "#161b22",
          borderRadius: 11, overflow: "hidden", border: "1px solid #30363d" }}>
          <div style={{ width: `${p * 100}%`, height: "100%",
            background: `linear-gradient(90deg,#1f6feb,#3fb950)` }} />
        </div>
        {gradePass && p > 0.62 ? (
          <div style={{ marginTop: 18, fontFamily: FONT_MONO, fontSize: 34,
            color: GREEN, opacity: ramp(frame, start + durationInFrames * 0.62, 12) }}>
            &#10003; known-good kernel PASS &middot; every mutant killed
          </div>
        ) : null}
      </div>

      {/* a soft vignette so the HUD text stays readable over any frame */}
      <AbsoluteFill style={{ boxShadow: "inset 0 0 240px 40px #0d1117cc",
        pointerEvents: "none" }} />
    </AbsoluteFill>
  );
};

const Phase: React.FC<{ label: string; on: boolean }> = ({ label, on }) => (
  <div style={{ padding: "8px 20px", borderRadius: 10,
    border: `1px solid ${on ? GREEN : "#30363d"}`,
    color: on ? GREEN : DIM, background: on ? "#3fb95018" : "transparent" }}>
    {label}
  </div>
);
