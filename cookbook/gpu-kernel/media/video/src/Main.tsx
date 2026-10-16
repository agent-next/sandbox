import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { Scene } from "./types";
import { Background } from "./Background";
import { Race } from "./scenes/Race";
import { RowTransform } from "./scenes/RowTransform";
import { Terminal } from "./scenes/Terminal";
import { GpuTiming } from "./scenes/GpuTiming";
import { ProofHud } from "./scenes/ProofHud";
import { EndCard } from "./scenes/EndCard";
import { DIM } from "./theme";

export type MainProps = { scene: Scene };

// timeline (frames @ 30 fps), authored against FRAMES = 46*30 = 1380.
// The end card is the last 2.5 s (frame 1305 on) and is fully static, so the
// gate's end-window (last 2 s) contains no motion.
export const T = {
  hook: [0, 60], // 0-2 s: the finished result, moving, fills the frame
  inOut: [60, 240], // 2-10 s: input -> output
  escRace: [300, 300], // 10-20 s: escalate — camera push on the race
  escTerm: [600, 315], // 20-30.5 s: the agent's run, Nx speed, real footage
  escGpu: [915, 225], // 30.5-38 s: the GPU slice's own timing
  proof: [1140, 165], // 38-43.5 s: verdict HUD over the still-playing run
  end: [1305, 75], // 43.5-46 s: static end card
} as const;

export const Main: React.FC<MainProps> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { gpu, cpu, row, terminal } = scene;
  const runSeconds =
    cpu.wall.setup_s + cpu.wall.selftest_s + cpu.wall.grade_s;
  const speed = Math.max(1, Math.round(runSeconds / terminal.duration_s));
  // the escalation shot plays the run from the top; the proof shot resumes
  // exactly where it stopped, so the footage never jumps
  const escFrames = Math.round(T.escTerm[1]);
  const proofFrom = escFrames;

  return (
    <AbsoluteFill>
      <Background />

      <Sequence from={T.hook[0]} durationInFrames={T.hook[1]} name="hook">
        <Race cases={cpu.cases} start={0} durationInFrames={T.hook[1]}
          caption="live kernel timings"
          subcaption="every point a real timed run of the artifact, this sandbox" />
      </Sequence>

      <Sequence from={T.inOut[0]} durationInFrames={T.inOut[1]} name="in-out">
        <RowTransform start={0} durationInFrames={T.inOut[1]} row={row}
          caption="input row  ->  softmax row"
          subcaption="the real kernel's output for the judge's 37x65 case (seed 5)" />
      </Sequence>

      <Sequence from={T.escRace[0]} durationInFrames={T.escRace[1]}
        name="esc-race">
        <Race cases={cpu.cases} start={0} durationInFrames={T.escRace[1]} zoom
          caption="kernel vs torch, iteration by iteration"
          subcaption="interpreter mode (--cpu-check): correctness first, speed on the GPU slice" />
      </Sequence>

      <Sequence from={T.escTerm[0]} durationInFrames={T.escTerm[1]}
        name="esc-term">
        <Terminal start={0} durationInFrames={T.escTerm[1]}
          clip={terminal.clip} clipSeconds={terminal.duration_s} speed={speed}
          clipFrom={0}
          wall={cpu.wall}
          mutantsKilled={cpu.mutants.filter((m) => m.killed).length}
          mutantsTotal={cpu.mutants.length}
          gradePass={cpu.verdict.judge_intact &&
            Object.values(cpu.verdict.gates).every(Boolean)}
          headline={["the", "agent's", "sandbox", "run"]}
          subheadline="judge/setup.sh -> judge/selftest.sh -> judge/grade.sh, recorded as it ran"
          showHud />
      </Sequence>

      <Sequence from={T.escGpu[0]} durationInFrames={T.escGpu[1]}
        name="esc-gpu">
        <GpuTiming start={0} durationInFrames={T.escGpu[1]}
          kernelMs={gpu.kernel_ms} eagerMs={gpu.eager_ms} speedup={gpu.speedup}
          gbPerS={gpu.gb_per_s}
          caption="on a 1 GiB GPU slice"
          subcaption="same judge, full CUDA path — median of 9 CUDA-event timings" />
      </Sequence>

      <Sequence from={T.proof[0]} durationInFrames={T.proof[1]} name="proof">
        <Terminal start={0} durationInFrames={T.proof[1]}
          clip={terminal.clip} clipSeconds={terminal.duration_s} speed={speed}
          clipFrom={proofFrom}
          wall={cpu.wall}
          mutantsKilled={cpu.mutants.filter((m) => m.killed).length}
          mutantsTotal={cpu.mutants.length}
          gradePass={false}
          headline={["the", "judge", "cannot", "be", "fooled"]}
          subheadline="the run keeps playing under the verdict — same recording, no cuts"
          showHud={false} />
        <ProofHud start={12}
          cases={gpu.cases} gates={gpu.gates} mutants={gpu.mutants}
          mutantsKilled={gpu.mutants_killed} mutantsTotal={gpu.mutants_total}
          worst={gpu.worst} judgeIntact={gpu.judge_intact}
          lease={gpu.lease} totalS={gpu.total_s} />
      </Sequence>

      <Sequence from={T.end[0]} durationInFrames={T.end[1]} name="end">
        <EndCard start={0} command="python3 run.py"
          worst={gpu.worst} mutantsKilled={gpu.mutants_killed}
          mutantsTotal={gpu.mutants_total} cases={gpu.cases.length} />
      </Sequence>

      {/* persistent corner tag (hidden on the static end card) */}
      <div style={{ position: "absolute", left: 56, bottom: 30,
        fontFamily: "monospace", fontSize: 22, color: DIM,
        opacity: frame > 30 && frame < T.end[0] ? 0.7 : 0 }}>
        gpu-kernel &middot; lease {gpu.lease} &middot; created, graded, destroyed
      </div>
    </AbsoluteFill>
  );
};
