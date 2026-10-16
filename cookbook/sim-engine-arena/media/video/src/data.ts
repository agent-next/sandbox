// The on-screen numbers, from clips/numbers.json. clips.py writes that
// file from this run's judge output (media/data/grade.json, seed 0) and
// RECEIPT.md, and make_media.sh copies it into video/public/ before the
// Remotion bundle is built, so it is imported statically - the numbers in
// the video are the numbers of the run by construction.
import raw from "../public/numbers.json";

export type SceneRow = {
  key: string;
  title: string;
  unit: string;
  value: number;
  oracle: number | null;
  err_pct: number | null;
  pass: boolean;
  limit_mm?: number;
};

export type Numbers = {
  scenes: SceneRow[];
  kill_rate: string;
  mutants: Array<{name: string; gates: string[]}>;
  loop: Array<{
    i: number;
    passed: boolean;
    failed: string[];
    change: string;
  }>;
  speeds: Record<string, {wall_s: number; sim_s: number; slowdown: number}>;
  agent_run: {
    receipt_total_s: number;
    slot_s: number;
    factor: number;
    stages: Array<{stage: string; s: number}>;
  };
  killed: number;
  timestep_s: number;
  seed: number;
  mujoco: string;
};

export const NUMBERS = raw as unknown as Numbers;
