// Types shared by the Remotion components. Every string/number is filled
// from data.json passed with --props, which media/make_media.sh writes
// from THIS run's judge verdict JSONs — nothing is invented.
export interface DemoData {
  clips: {
    hook: string;
    develop: string;
    closeup: string;
    agent: string;
    proof: string;
    verdict: string;
    endcardStill: string;
  };
  hud: {
    residFinal: string;   // max final initial residual (cavity, gate 2)
    cellCount: string;    // cavity mesh cells
    l2: string;           // Poiseuille L2 vs analytic (gate 3)
    orders: string;       // mesh-convergence orders (gate 4)
    ghiaU: string;        // cavity max u error vs Ghia 1982 (gate 5)
    ghiaV: string;        // cavity max v error vs Ghia 1982 (gate 5)
    kills: string;        // '10/10' mutant kill count
    continuity: string;   // global continuity error
    tEnd: string;         // cavity endTime, s
  };
  agent: { wallSeconds: number; speed: string };
  verdict: {
    pass: boolean;
    gates: { name: string; ok: boolean }[];
  };
}
