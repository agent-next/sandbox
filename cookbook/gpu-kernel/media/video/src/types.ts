export type CaseResult = {
  shape: number[];
  dist: string;
  max_abs: number | null;
  rowsum: number | null;
  ok: boolean;
  seed: number;
};

export type MutantResult = {
  name: string;
  failed: string[];
  detail: Record<string, string>;
};

export type RaceCase = {
  case: number;
  shape: number[];
  dist: string;
  seed: number;
  kernel_ms: number[];
  eager_ms: number[];
};

export type Scene = {
  gpu: {
    kernel_ms: number;
    eager_ms: number;
    speedup: number;
    gb_per_s: number;
    worst: { max_abs: number; rowsum: number; shift: number };
    cases: CaseResult[];
    gates: Record<string, boolean>;
    judge_intact: boolean;
    mode: string;
    mutants: MutantResult[];
    mutants_killed: number;
    mutants_total: number;
    total_s: number;
    lease: string;
  };
  cpu: {
    wall: { setup_s: number; selftest_s: number; grade_s: number };
    mutants: { name: string; killed: boolean; wall_s: number }[];
    verdict: {
      mode: string;
      gates: Record<string, boolean>;
      judge_intact: boolean;
      worst: { max_abs: number; rowsum: number; shift: number };
      cases: number;
    };
    cases: RaceCase[];
  };
  row: { in: number[]; out: number[] };
  terminal: { clip: string; duration_s: number };
};
