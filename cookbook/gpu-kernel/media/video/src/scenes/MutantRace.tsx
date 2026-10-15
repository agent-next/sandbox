import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { DIM, FG, FONT_MONO, FONT_SANS, GREEN, RED, PANEL, ease } from "../theme";
import { ScanBand } from "../ScanBand";

/** The mutant kill race: 11 real broken kernels, each graded by the real
 * judge in this sandbox, bars growing to each grade's measured wall time and
 * stamped with the gate that killed it. */
export const MutantRace: React.FC<{
  start: number;
  durationInFrames: number;
  mutants: { name: string; killed: boolean; wall_s: number }[];
  caption: string;
  subcaption: string;
}> = ({ start, durationInFrames, mutants, caption, subcaption }) => {
  const frame = useCurrentFrame();
  const maxS = Math.max(...mutants.map((m) => m.wall_s));
  const revealF = Math.round(durationInFrames * 0.72);

  return (
    <AbsoluteFill>
      <ScanBand start={start} durationInFrames={durationInFrames} left={100}
        width={760} top={200} height={mutants.length * 62 + 20} color={RED}
        period={64} />
      <div style={{ position: "absolute", left: 100, top: 44 }}>
        <div style={{ fontFamily: FONT_SANS, fontSize: 62, fontWeight: 700,
          color: FG, letterSpacing: -1 }}>{caption}</div>
        <div style={{ fontFamily: FONT_MONO, fontSize: 30, color: DIM,
          marginTop: 8 }}>{subcaption}</div>
      </div>

      <div style={{ position: "absolute", left: 100, top: 210, right: 100 }}>
        {mutants.map((m, i) => {
          const t0 = start + 8 + i * (revealF / mutants.length);
          const t = ease(frame, t0, 26);
          const killed = frame >= t0 + 34;
          const w = 760 * (m.wall_s / maxS) * t;
          return (
            <div key={m.name} style={{ display: "flex", alignItems: "center",
              height: 62, opacity: t === 0 ? 0 : 1 }}>
              <div style={{ width: 460, fontFamily: FONT_MONO, fontSize: 30,
                color: killed ? FG : DIM, textOverflow: "ellipsis" }}>
                {m.name}
              </div>
              <div style={{ width: 780, height: 34, background: "#161b22",
                borderRadius: 8, border: "1px solid #30363d",
                overflow: "hidden" }}>
                <div style={{ width: w, height: "100%",
                  background: killed ? RED : GREEN }} />
              </div>
              <div style={{ width: 170, fontFamily: FONT_MONO, fontSize: 28,
                color: DIM, marginLeft: 16 }}>
                {t > 0.02 ? `${m.wall_s.toFixed(1)} s` : ""}
              </div>
              <div style={{ width: 320, fontFamily: FONT_MONO, fontSize: 30,
                marginLeft: 8 }}>
                {killed ? (
                  <span style={{ color: RED }}>
                    {String.fromCodePoint(0x2717)} killed
                  </span>
                ) : t > 0.02 ? (
                  <span style={{ color: DIM }}>grading&hellip;</span>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ position: "absolute", right: 100, bottom: 60,
        fontFamily: FONT_MONO, fontSize: 34, color: GREEN, opacity:
        ease(frame, start + revealF + 6, 14) }}>
        {mutants.filter((m) => m.killed).length}/{mutants.length} mutants killed &middot; judge intact
      </div>
    </AbsoluteFill>
  );
};
