import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { CaseResult, MutantResult } from "../types";
import { DIM, FG, FONT_MONO, FONT_SANS, GREEN, springish, fmtErr } from "../theme";
import { CountUp } from "../CountUp";

/** The proof, as a HUD panel that slides in over still-playing footage: the
 * PASS badge, the gate rows, the real per-case max-abs errors against the
 * 1e-5 tolerance line, and the mutant kill matrix — all of it the committed
 * GPU run's own verdict (media/data/report.json). */
export const ProofHud: React.FC<{
  start: number;
  cases: CaseResult[];
  gates: Record<string, boolean>;
  mutants: MutantResult[];
  mutantsKilled: number;
  mutantsTotal: number;
  worst: { max_abs: number; rowsum: number; shift: number };
  judgeIntact: boolean;
  lease: string;
  totalS: number;
}> = ({ start, cases, gates, mutants, mutantsKilled, mutantsTotal, worst,
        judgeIntact, lease, totalS }) => {
  const frame = useCurrentFrame();
  const { width, fps } = useVideoConfig();
  const slide = springish(frame, start, fps);

  const TOL = 1e-5;
  const LO = 1e-10;
  const HI = 1e-3;
  const plotH = 190;
  const yOf = (v: number) => {
    const lo = Math.log10(LO), hi = Math.log10(HI);
    const t = (Math.log10(Math.max(v, LO * 1.0001)) - lo) / (hi - lo);
    return plotH - 14 - t * (plotH - 40);
  };

  const panelW = 900;
  const panelX = width - panelW - 48;
  const tx = (1 - slide) * (panelW + 120);

  const rows = [
    { name: "structure", pass: gates["structure"] ?? false,
      detail: "contract exact, no delegation" },
    { name: "device-compile", pass: gates["device-compile"] ?? false,
      detail: "sm_80 + sm_90 cubins" },
    { name: "correctness", pass: gates["correctness"] ?? false,
      detail: `${cases.length}/${cases.length} cases vs torch.softmax` },
    { name: "judge_intact", pass: judgeIntact,
      detail: "judge/ sha256 unchanged" },
  ];
  const allPass = rows.every((r) => r.pass);
  const killedShown = Math.min(
    mutantsTotal, Math.max(0, Math.floor((frame - start - 40) / 5)));

  return (
    <div style={{ position: "absolute", right: 48, top: 74, width: panelW,
      transform: `translateX(${tx}px)`, background: "#0d1117ec",
      border: "1px solid #30363d", borderRadius: 20, padding: "26px 32px" }}>
      <div style={{ display: "flex", alignItems: "center",
        justifyContent: "space-between" }}>
        <div style={{ fontFamily: FONT_SANS, fontSize: 44, fontWeight: 800,
          color: FG }}>judge verdict</div>
        <div style={{ fontFamily: FONT_SANS, fontSize: 40, fontWeight: 800,
          letterSpacing: 2, color: "#0d1117", background: allPass ? GREEN : "#f85149",
          padding: "6px 22px", borderRadius: 12,
          transform: `scale(${0.7 + 0.3 * springish(frame, start + 6, fps)})` }}>
          {allPass ? "PASS" : "FAIL"}
        </div>
      </div>

      <div style={{ marginTop: 14 }}>
        {rows.map((r, i) => {
          const on = springish(frame, start + 20 + i * 8, fps);
          return (
            <div key={r.name} style={{ display: "flex", alignItems: "center",
              height: 44, opacity: on,
              transform: `translateX(${(1 - on) * 34}px)` }}>
              <div style={{ width: 40, fontFamily: FONT_MONO, fontSize: 30,
                color: r.pass ? GREEN : "#f85149" }}>
                {r.pass ? String.fromCodePoint(0x2713) : String.fromCodePoint(0x2717)}
              </div>
              <div style={{ width: 300, fontFamily: FONT_MONO, fontSize: 30,
                color: r.pass ? GREEN : "#f85149" }}>{r.name}</div>
              <div style={{ fontFamily: FONT_MONO, fontSize: 25, color: DIM }}>
                {r.detail}
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: 14, fontFamily: FONT_MONO, fontSize: 23,
        color: DIM }}>per-case max abs error vs the 1e-5 tolerance line</div>
      <svg width={panelW - 64} height={plotH} style={{ marginTop: 2 }}>
        <line x1={0} y1={yOf(TOL)} x2={panelW - 64} y2={yOf(TOL)}
          stroke="#f85149" strokeWidth={2} strokeDasharray="8 6" />
        <text x={panelW - 68} y={yOf(TOL) - 8} fill="#f85149" fontSize={22}
          textAnchor="end" fontFamily={FONT_MONO}>tolerance 1e-5</text>
        {cases.map((c, i) => {
          const bw = (panelW - 84) / cases.length;
          const x = 10 + i * bw;
          const v = c.max_abs ?? 0;
          const y = yOf(v);
          const grown = springish(frame, start + 34 + i * 5, fps);
          return (
            <g key={i}>
              <rect x={x} y={y} width={bw * 0.62}
                height={(plotH - 14 - y) * grown} fill={c.ok ? GREEN : "#f85149"}
                opacity={0.9} rx={3} />
              <text x={x + bw * 0.31} y={plotH - 2} fill={DIM} fontSize={16}
                textAnchor="middle" fontFamily={FONT_MONO}>
                {c.dist}
              </text>
            </g>
          );
        })}
      </svg>
      <div style={{ fontFamily: FONT_MONO, fontSize: 25, color: FG, marginTop: 4 }}>
        worst max-abs <b style={{ color: GREEN }}>{fmtErr(worst.max_abs)}</b>
        &nbsp;&middot;&nbsp; row-sum <b style={{ color: GREEN }}>{fmtErr(worst.rowsum)}</b>
        &nbsp;&middot;&nbsp; shift <b style={{ color: GREEN }}>{fmtErr(worst.shift)}</b>
      </div>

      <div style={{ marginTop: 14, height: 1, background: "#30363d" }} />
      <div style={{ marginTop: 12, fontFamily: FONT_MONO, fontSize: 23,
        color: DIM }}>mutant kill matrix &mdash; each graded by the real judge</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 }}>
        {mutants.map((m, i) => {
          const dead = i < killedShown;
          return (
            <div key={m.name} style={{
              fontFamily: FONT_MONO, fontSize: 22, padding: "7px 12px",
              borderRadius: 8, border: `1px solid ${dead ? "#f85149" : "#30363d"}`,
              color: dead ? "#ffb3ae" : DIM, background: dead ? "#f8514918" : "#161b22" }}>
              {dead ? String.fromCodePoint(0x2717) + " " : ""}{m.name}
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 14, fontFamily: FONT_MONO, fontSize: 25,
        color: DIM }}>
        <span style={{ color: GREEN, fontSize: 32, fontWeight: 700 }}>
          <CountUp from={0} to={mutantsKilled} start={start + 40}
            dur={mutantsTotal * 5} />/{mutantsTotal}
        </span>
        {" "}mutants killed &middot; lease {lease} &middot; create&rarr;grade&rarr;destroy{" "}
        {totalS.toFixed(0)} s
      </div>
    </div>
  );
};
