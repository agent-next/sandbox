import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { CaseResult, MutantResult } from "../types";
import { BLUE, DIM, FG, FONT_MONO, FONT_SANS, GREEN, PANEL, ease, fmtErr } from "../theme";

/** The proof, as a HUD panel that slides in over still-moving footage:
 * the real per-case max-abs errors (log scale, tolerance line at 1e-5), the
 * gate rows, and the mutant kill count — all from the committed GPU run. */
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
  const { width } = useVideoConfig();
  const slide = ease(frame, start, 22);

  const TOL = 1e-5;
  const LO = 1e-10;
  const HI = 1e-3;
  const yOf = (v: number) => {
    const lo = Math.log10(LO), hi = Math.log10(HI);
    const t = (Math.log10(Math.max(v, LO * 1.0001)) - lo) / (hi - lo);
    return 250 - t * 190; // within the 210 px-tall plot area
  };

  const panelW = 1120;
  const panelX = width - panelW - 60;
  const tx = (1 - slide) * (panelW + 80);

  const rows = [
    { name: "structure", pass: gates["structure"] ?? false,
      detail: "contract exact, no delegation names" },
    { name: "device-compile", pass: gates["device-compile"] ?? false,
      detail: "cubins for sm_80 + sm_90" },
    { name: "correctness", pass: gates["correctness"] ?? false,
      detail: `${cases.length}/${cases.length} cases vs torch.softmax` },
    { name: "judge_intact", pass: judgeIntact,
      detail: "judge/ sha256 unchanged" },
  ];

  return (
    <div style={{ position: "absolute", right: 60, top: 60, width: panelW,
      transform: `translateX(${tx}px)`, background: "#0d1117e8",
      border: "1px solid #30363d", borderRadius: 20, padding: "30px 34px",
      boxShadow: "0 20px 60px #0009" }}>
      <div style={{ display: "flex", alignItems: "baseline",
        justifyContent: "space-between" }}>
        <div style={{ fontFamily: FONT_SANS, fontSize: 48, fontWeight: 700,
          color: FG }}>judge verdict</div>
        <Badge pass={rows.every((r) => r.pass)} />
      </div>

      <div style={{ marginTop: 22 }}>
        {rows.map((r, i) => (
          <Row key={r.name} r={r} on={frame >= start + 26 + i * 12} />
        ))}
      </div>

      <div style={{ marginTop: 22, fontFamily: FONT_MONO, fontSize: 26,
        color: DIM }}>per-case max abs error (log scale) vs the 1e-5 line</div>
      <svg width={panelW - 68} height={230} style={{ marginTop: 4 }}>
        <line x1={0} y1={yOf(TOL)} x2={panelW - 68} y2={yOf(TOL)}
          stroke="#f85149" strokeWidth={2} strokeDasharray="8 6" />
        <text x={panelW - 72} y={yOf(TOL) - 8} fill="#f85149" fontSize={24}
          textAnchor="end" fontFamily={FONT_MONO}>tolerance 1e-5</text>
        {cases.map((c, i) => {
          const bw = (panelW - 88) / cases.length;
          const x = 10 + i * bw;
          const v = c.max_abs ?? 0;
          const y = yOf(v);
          const grown = ease(frame, start + 30 + i * 8, 18);
          return (
            <g key={i}>
              <rect x={x} y={y} width={bw * 0.6}
                height={(250 - y) * grown} fill={c.ok ? GREEN : "#f85149"}
                opacity={0.9} rx={3} />
              <text x={x + bw * 0.3} y={238} fill={DIM} fontSize={18}
                textAnchor="middle" fontFamily={FONT_MONO}>
                {c.dist}
              </text>
            </g>
          );
        })}
      </svg>
      <div style={{ fontFamily: FONT_MONO, fontSize: 26, color: FG }}>
        worst max-abs <b style={{ color: GREEN }}>{fmtErr(worst.max_abs)}</b>
        &nbsp;&middot;&nbsp; row-sum <b style={{ color: GREEN }}>{fmtErr(worst.rowsum)}</b>
        &nbsp;&middot;&nbsp; shift <b style={{ color: GREEN }}>{fmtErr(worst.shift)}</b>
      </div>
      <div style={{ fontFamily: FONT_MONO, fontSize: 26, color: DIM,
        marginTop: 10 }}>
        {mutantsKilled}/{mutantsTotal} mutants killed &middot; lease {lease}
        &middot; create&rarr;grade&rarr;destroy {totalS.toFixed(0)} s
      </div>
    </div>
  );
};

const Row: React.FC<{ r: { name: string; pass: boolean; detail: string }; on: boolean }> = ({
  r, on,
}) => (
  <div style={{ display: "flex", alignItems: "center", height: 50,
    opacity: on ? 1 : 0.15, transform: `translateX(${on ? 0 : 24}px)` }}>
    <div style={{ width: 40, fontFamily: FONT_MONO, fontSize: 32,
      color: r.pass ? GREEN : "#f85149" }}>
      {r.pass ? String.fromCodePoint(0x2713) : String.fromCodePoint(0x2717)}
    </div>
    <div style={{ width: 320, fontFamily: FONT_MONO, fontSize: 30,
      color: r.pass ? GREEN : "#f85149" }}>{r.name}</div>
    <div style={{ fontFamily: FONT_MONO, fontSize: 26, color: DIM }}>
      {r.detail}
    </div>
  </div>
);

const Badge: React.FC<{ pass: boolean }> = ({ pass }) => (
  <div style={{ fontFamily: FONT_SANS, fontSize: 44, fontWeight: 800,
    letterSpacing: 2, color: "#0d1117", background: pass ? GREEN : "#f85149",
    padding: "8px 26px", borderRadius: 12 }}>
    {pass ? "PASS" : "FAIL"}
  </div>
);
