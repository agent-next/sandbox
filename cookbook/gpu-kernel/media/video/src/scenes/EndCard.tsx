import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { DIM, FG, FONT_MONO, FONT_SANS, GREEN, PANEL, ease } from "../theme";

/** Static end card: the one-line launch, the verdict, and where the numbers
 * come from. Nothing moves except a very slow fade-in that finishes well
 * before the last 2 s, so the tail is genuinely static. */
export const EndCard: React.FC<{
  start: number;
  command: string;
  worst: { max_abs: number; rowsum: number; shift: number };
  mutantsKilled: number;
  mutantsTotal: number;
  cases: number;
}> = ({ start, command, worst, mutantsKilled, mutantsTotal, cases }) => {
  const frame = useCurrentFrame();
  const o = ease(frame, start, 14); // reaches 1 by ~0.5 s into the card
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center",
      opacity: o }}>
      <div style={{ fontFamily: FONT_SANS, fontSize: 96, fontWeight: 800,
        color: FG, letterSpacing: -2 }}>
        gpu-kernel demo
      </div>
      <div style={{ fontFamily: FONT_MONO, fontSize: 34, color: DIM,
        marginTop: 10 }}>
        a fused Triton softmax, graded by a judge it cannot fool
      </div>

      <div style={{ marginTop: 46, background: "#010409",
        border: `2px solid ${GREEN}`, borderRadius: 16,
        padding: "26px 40px", fontFamily: FONT_MONO, fontSize: 52, color: FG }}>
        <span style={{ color: DIM }}>$ </span>{command}
      </div>

      <div style={{ display: "flex", gap: 26, marginTop: 44 }}>
        <Chip label={`${cases}/${cases} cases pass`} />
        <Chip label={`worst err ${worst.max_abs.toExponential(1)}`} />
        <Chip label={`${mutantsKilled}/${mutantsTotal} mutants killed`} />
        <Chip label="PASS" highlight />
      </div>
      <div style={{ fontFamily: FONT_MONO, fontSize: 26, color: DIM,
        marginTop: 30 }}>
        numbers from RECEIPT.md and media/data/report.json &middot; CPU judge path runs locally, GPU path needs a 1 GiB VRAM lease
      </div>
    </AbsoluteFill>
  );
};

const Chip: React.FC<{ label: string; highlight?: boolean }> = ({ label, highlight }) => (
  <div style={{ fontFamily: FONT_MONO, fontSize: 30,
    color: highlight ? "#0d1117" : FG,
    background: highlight ? GREEN : PANEL,
    border: `1px solid ${highlight ? GREEN : "#30363d"}`,
    borderRadius: 12, padding: "14px 24px" }}>{label}</div>
);
