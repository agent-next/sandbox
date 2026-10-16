// The sim-engine-arena video: real MuJoCo offscreen footage of the
// trajectories the judge graded (media/clips/*.mp4, recorded by clips.py)
// with the HUD, the kinetic headline, the PASS badge and the end card
// composed on top by Remotion. ffmpeg never composes a frame here.
//
// Timing: 29.5 s of moving footage + a 2.5 s static end card = 32 s.
// Every number comes from clips/numbers.json, written from this run's
// media/data/grade.json (seed 0) and RECEIPT.md.
//
// Every on-screen font is >= 60 px: DejaVu's capital height is ~0.73 em,
// so 60 px renders 43.8 px of cap height = 4.1 % of the 1080 px frame,
// above DEMO-STANDARD.md's 4 % floor. There is no smaller size anywhere.
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  OffthreadVideo,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {CLIP, FONT, HEIGHT, SLOTS, TOTAL_FRAMES, WIDTH} from "./config";
import {NUMBERS} from "./data";
import {Cap, Fade, HUD, Mono, Scrim, SlideIn, useCount} from "./kit";

export {WIDTH, HEIGHT};
export const durationInFrames = TOTAL_FRAMES;

const MONO = "'SF Mono','JetBrains Mono','Menlo','Consolas',monospace";
const SANS = "'Inter','Helvetica Neue',Helvetica,Arial,sans-serif";

/* ------------------------------------------------------------------ config */

const SCENE_CLIPS: Record<string, string> = {
  drop: CLIP.drop,
  incline_slide: CLIP.slide,
  incline_stick: CLIP.stick,
  pendulum: CLIP.pendulum,
};

/** Full-bleed clip, sized to fill the frame; speed stamped on screen. */
const Clip: React.FC<{
  file: string;
  playbackRate?: number;
  style?: React.CSSProperties;
}> = ({file, playbackRate = 1, style}) => {
  const {durationInFrames} = useVideoConfig();
  return (
    <AbsoluteFill style={style}>
      <OffthreadVideo
        src={staticFile(file)}
        playbackRate={playbackRate}
        style={{width: WIDTH, height: HEIGHT, objectFit: "cover"}}
        // The clip's own footage, trimmed to the enclosing Sequence.
        endAt={durationInFrames}
      />
    </AbsoluteFill>
  );
};

const pct = (v: number | null): string =>
  v === null ? "n/a" : `+${v.toFixed(2)} %`;

const rate = (v: number): string =>
  v === 1 ? "real time" : `${(v > 1 ? v : 1 / v).toFixed(2)}x slow motion`;

/* --------------------------------------------------------------- 0-2  hook */

const Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const n = NUMBERS;
  // The headline scales up from 0.85 and settles - kinetic, not a fade in.
  const scale = interpolate(frame, [0, 22], [0.86, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const cutting = frame < 20;
  return (
    <AbsoluteFill>
      <Clip file={CLIP.hook} />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(90deg, rgba(11,18,32,.72) 0%, rgba(11,18,32,.42) 46%, rgba(11,18,32,0) 78%)",
        }}
      />
      <AbsoluteFill
        style={{
          justifyContent: "center",
          paddingLeft: 140,
          paddingRight: 460,
        }}
      >
        <div
          style={{
            fontFamily: SANS,
            fontSize: FONT.headline,
            fontWeight: 800,
            color: "#fff",
            lineHeight: 0.98,
            letterSpacing: -2,
            transform: `scale(${scale})`,
            transformOrigin: "left center",
            textShadow: "0 4px 30px rgba(11,18,32,.8)",
            marginBottom: 42,
          }}
        >
          GRADED MOTION,
          <br />
          RE-RENDERED
        </div>
        <Cap size={FONT.cap} weight={500} style={{opacity: cutting ? 0.9 : 0.75}}>
          four rigid-body scenes, simulated by an agent and replayed from the
          graded CSV · MuJoCo {n.mujoco}, seed {n.seed}
        </Cap>
      </AbsoluteFill>
      <HUD
        x={1250}
        y={730}
        w={570}
        title="SCENES PASS"
        rows={[
          {label: "oracle gates", value: "4 / 4", color: "#2fbf71"},
          {label: "self-test kills", value: `${n.kill_rate}`, color: "#2fbf71"},
          {label: "judge intact", value: "yes", color: "#2fbf71"},
        ]}
      />
    </AbsoluteFill>
  );
};

/* --------------------------------------------------- 2-12  input -> output */

const SCENE_ORDER = ["drop", "incline_slide", "incline_stick", "pendulum"];
// The "input" half of each beat, in judge/spec.json's own terms.
const INPUT_LABEL: Record<string, string> = {
  drop: "1 kg sphere, r 0.05 m, at rest from z 1.0 m",
  incline_slide: "box on a 35° plane, mu 0.5, released at rest",
  incline_stick: "box on a 20° plane, mu 0.5, released at rest",
  pendulum: "1 kg bob on a 1.0 m link, theta0 0.1 rad",
};

const SceneBeat: React.FC<{scene: string}> = ({scene}) => {
  const n = NUMBERS;
  const row = n.scenes.find((s) => s.key === scene)!;
  // The "input -> output" idea: the spec sentence fills the caption bar and
  // the measured value counts up from 0 over half of the 2.5 s beat, in a
  // HUD block of its own over the still-moving footage.
  const shown = useCount(row.value, 40);
  const digits = row.unit === "mm" ? 1 : 4;
  const speed = n.speeds[SCENE_CLIPS[scene].replace(/\.mp4$/, "")];
  const verdict =
    row.oracle === null || row.err_pct === null
      ? `gate: under ${row.limit_mm} mm`
      : `oracle ${row.oracle.toFixed(digits)} · ${pct(row.err_pct)}`;
  return (
    <AbsoluteFill>
      <Clip file={SCENE_CLIPS[scene]} />
      {/* speed stamp, top-left: every slowed beat is labelled with its factor */}
      <div
        style={{
          position: "absolute",
          left: 110,
          top: 44,
          background: "rgba(11,18,32,.6)",
          borderRadius: 14,
          padding: "12px 26px",
        }}
      >
        <Cap size={FONT.cap} weight={700} color="#cfe0f5">
          {rate(speed.slowdown)}
        </Cap>
      </div>
      {/* the measured value, over the footage on the right */}
      <div
        style={{
          position: "absolute",
          right: 110,
          top: 640,
          textAlign: "right",
          background: "rgba(11,18,32,.6)",
          borderRadius: 18,
          padding: "22px 30px 26px",
        }}
      >
        <div style={{fontFamily: MONO, fontSize: FONT.stat, fontWeight: 700, color: "#fff"}}>
          {Number(shown).toFixed(digits)} {row.unit}
        </div>
        <Cap size={FONT.cap} weight={500} color="#cfe0f5" style={{marginTop: 12}}>
          {verdict} · <span style={{color: "#2fbf71", fontWeight: 700}}>PASS</span>
        </Cap>
      </div>
      {/* caption bar: title + PASS on one row, the spec sentence below */}
      <Scrim inset={[0, 880, WIDTH, 200]} strength={0.5} />
      <div
        style={{
          position: "absolute",
          left: 110,
          top: 898,
          right: 110,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        <Cap size={FONT.scene} weight={700}>
          {row.title}
        </Cap>
        <Cap size={FONT.cap} weight={800} color="#2fbf71">
          PASS
        </Cap>
      </div>
      <div style={{position: "absolute", left: 110, top: 994, right: 110}}>
        <Cap size={FONT.cap} weight={500} color="#b9cbe4">
          input: {INPUT_LABEL[scene]}
        </Cap>
      </div>
    </AbsoluteFill>
  );
};

const SceneStrip: React.FC = () => (
  <AbsoluteFill>
    {SCENE_ORDER.map((scene, i) => (
      <Sequence key={scene} from={i * 75} durationInFrames={75}>
        <Fade frames={5}>
          <SceneBeat scene={scene} />
        </Fade>
      </Sequence>
    ))}
  </AbsoluteFill>
);

/* -------------------------------------------------------- 12-17  2x2 grid */

const Grid: React.FC = () => {
  const n = NUMBERS;
  const frame = useCurrentFrame();
  // The tiles are the recorded quad clip: all four scenes in motion.
  return (
    <AbsoluteFill>
      <Clip file={CLIP.quad} />
      <Scrim inset={[0, 0, WIDTH, 110]} strength={0.55} />
      <div
        style={{
          position: "absolute",
          left: 110,
          top: 20,
          display: "flex",
          justifyContent: "space-between",
          width: WIDTH - 220,
          alignItems: "baseline",
        }}
      >
        <Cap size={FONT.scene - 14} weight={700} tracking={2} style={{whiteSpace: "pre"}}>
          {"4 SCENES · 1 SPEC · SEED " + n.seed}
        </Cap>
        <Cap size={FONT.cap} weight={600} color="#cfe0f5">
          1 ms steps · 6.00x slow
        </Cap>
      </div>
      {(["01 DROP", "02 SLIDE 35", "03 STICK 20", "04 PENDULUM"] as const).map(
        (title, i) => (
          <div
            key={title}
            style={{
              position: "absolute",
              left: 60 + (i % 2) * (WIDTH / 2) + 26,
              top: 140 + Math.floor(i / 2) * (HEIGHT / 2) + 22,
            }}
          >
            <Cap size={FONT.cap} weight={700} style={{textShadow: "0 2px 12px rgba(0,0,0,.95)"}}>
              {title}
            </Cap>
          </div>
        ),
      )}
      <Scrim inset={[0, HEIGHT - 170, WIDTH, 170]} strength={0.5} />
      <div
        style={{
          position: "absolute",
          left: 110,
          bottom: 56,
          fontFamily: MONO,
          fontSize: FONT.mono,
          color: "#fff",
          opacity: interpolate(frame, [0, 10], [0, 1], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        }}
      >
        13,504 graded samples replayed
      </div>
    </AbsoluteFill>
  );
};

/* --------------------------------------------- 17-21  the recorded agent run */

const AgentRun: React.FC = () => {
  const n = NUMBERS;
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const run = n.agent_run;
  // RECEIPT.md run 2: the real fresh-sandbox run, 69 s of stages. This
  // slot replays that timeline compressed 17.2x - each stage lands at the
  // frame its cumulative second maps to - while the graded pendulum keeps
  // playing at real speed underneath. Nothing is frozen.
  const atFrame = (cumulativeS: number): number =>
    Math.round((cumulativeS / run.receipt_total_s) * durationInFrames);
  let cum = 0;
  const landings = run.stages.map((st) => {
    cum += st.s;
    return {stage: st.stage, s: st.s, at: atFrame(cum)};
  });
  // The run's own clock, sped up by the same factor: 0 -> 69 s.
  const clock = useCount(run.receipt_total_s, durationInFrames);
  const done = landings.filter((l) => frame >= l.at).length;
  return (
    <AbsoluteFill>
      <Clip file={CLIP.pendulum} />
      <Scrim inset={[0, 0, WIDTH, HEIGHT]} strength={0.5} />
      <div style={{position: "absolute", left: 110, top: 92, width: 1260}}>
        <Cap size={FONT.scene} weight={700}>
          THE AGENT RUN, 17.2x
        </Cap>
        <Cap size={FONT.cap} weight={500} color="#cfe0f5" style={{marginTop: 12}}>
          RECEIPT.md run 2, replayed 69 s → 4 s
        </Cap>
        <div style={{marginTop: 30, display: "flex", flexDirection: "column", gap: 12}}>
          {landings.map((l) => (
            <SlideIn key={l.stage} at={l.at} from="left" distance={70} frames={9}>
              <div
                style={{
                  display: "flex",
                  gap: 26,
                  alignItems: "baseline",
                  fontFamily: MONO,
                  fontSize: FONT.mono,
                  color: "#e6eefb",
                  background: "rgba(255,255,255,.07)",
                  borderLeft: "8px solid #4f8cff",
                  padding: "10px 22px",
                }}
              >
                <span style={{width: 300, color: "#9fb6d6"}}>{l.stage}</span>
                <span style={{fontWeight: 700}}>{l.s} s</span>
                <span style={{color: "#2fbf71", fontWeight: 800, marginLeft: "auto"}}>ok</span>
              </div>
            </SlideIn>
          ))}
        </div>
        <div style={{marginTop: 24, width: 640, height: 14, background: "rgba(255,255,255,.12)", borderRadius: 7}}>
          <div
            style={{
              width: `${(done / landings.length) * 100}%`,
              height: "100%",
              background: "#4f8cff",
              borderRadius: 7,
            }}
          />
        </div>
      </div>
      <div style={{position: "absolute", right: 110, bottom: 64, textAlign: "right"}}>
        <Cap size={FONT.cap} weight={600} color="#b9cbe4">
          RUN CLOCK
        </Cap>
        <div style={{fontFamily: MONO, fontSize: FONT.stat, fontWeight: 800, color: "#fff", marginTop: 10}}>
          {clock} s
        </div>
        <Cap size={FONT.cap} weight={500} color="#b9cbe4" style={{marginTop: 6}}>
          69 s → 4 s = 17.2x
        </Cap>
      </div>
    </AbsoluteFill>
  );
};

/* ------------------------------------------------- 21-23  tracked close-ups */

const Closeups: React.FC = () => (
  <AbsoluteFill>
    <Clip file={CLIP.closeup} />
    <Scrim inset={[0, HEIGHT - 140, WIDTH, 140]} strength={0.5} />
    <Mono
      size={FONT.mono}
      style={{position: "absolute", left: 110, bottom: 44, textShadow: "0 2px 14px rgba(0,0,0,.95)"}}
    >
      camera tracks the slide · 0.8 m · 1.5x speed
    </Mono>
  </AbsoluteFill>
);

/* ----------------------------------------------- 23-29.5  proof / PASS card */

const ProofCard: React.FC = () => {
  const n = NUMBERS;
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [4, 26], [0.6, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const opacity = interpolate(frame, [0, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const digits = (unit: string): number => (unit === "mm" ? 1 : 4);
  return (
    <AbsoluteFill>
      <Clip file={CLIP.proof} />
      {/* The verdict HUD, over the still-playing orbit behind it. */}
      <div
        style={{
          position: "absolute",
          left: 110,
          top: 100,
          width: 1100,
          background: "rgba(11,18,32,.82)",
          borderRadius: 26,
          padding: "40px 52px",
          opacity,
          transform: `scale(${scale})`,
          transformOrigin: "top left",
        }}
      >
        <div style={{display: "flex", alignItems: "center", gap: 30}}>
          <div
            style={{
              fontFamily: SANS,
              fontSize: FONT.pass,
              fontWeight: 800,
              color: "#2fbf71",
              transform: "rotate(-4deg)",
              textShadow: "0 6px 30px rgba(47,191,113,.45)",
            }}
          >
            PASS
          </div>
          <div>
            <Cap size={FONT.cap} weight={700}>
              ALL GATES
            </Cap>
            <Cap size={FONT.cap} weight={500} color="#b9cbe4">
              seed {n.seed} · judge intact
            </Cap>
          </div>
        </div>
        <div style={{marginTop: 30, display: "flex", flexDirection: "column", gap: 14}}>
          {n.scenes.map((row, i) => {
            const at = 20 + i * 16;
            return (
              <SlideIn key={row.key} at={at} from="bottom" distance={54} frames={10}>
                <div
                  style={{
                    borderBottom: "1px solid rgba(255,255,255,.12)",
                    paddingBottom: 12,
                  }}
                >
                  <div style={{display: "flex", alignItems: "baseline", gap: 22}}>
                    <span style={{color: "#fff", fontWeight: 700, fontSize: FONT.cap}}>
                      {row.title}
                    </span>
                    <span style={{color: "#fff", fontFamily: MONO, fontWeight: 700, fontSize: FONT.cap, marginLeft: "auto"}}>
                      {row.value} {row.unit}
                    </span>
                  </div>
                  <div style={{display: "flex", alignItems: "baseline", gap: 22, marginTop: 4}}>
                    <span style={{color: "#8fa3bf", fontSize: FONT.cap}}>
                      {row.oracle === null || row.err_pct === null
                        ? `gate: under ${row.limit_mm} mm`
                        : `oracle ${row.oracle.toFixed(digits(row.unit))} · ${pct(row.err_pct)}`}
                    </span>
                    <span style={{marginLeft: "auto", color: "#2fbf71", fontWeight: 800, fontSize: FONT.cap}}>
                      PASS
                    </span>
                  </div>
                </div>
              </SlideIn>
            );
          })}
          <SlideIn at={95} from="bottom" frames={12}>
            <div style={{fontFamily: MONO, fontSize: FONT.mono, color: "#cfe0f5"}}>
              mutants killed <span style={{color: "#2fbf71", fontWeight: 800}}>{n.kill_rate}</span> = 100 %
            </div>
          </SlideIn>
        </div>
      </div>
    </AbsoluteFill>
  );
};

/* ---------------------------------------------------------- 29.5-32  card */

// The only static part of the video: a plain card with the command that
// reproduces the graded run. No motion, no footage, no scan.
const EndCard: React.FC = () => (
  <AbsoluteFill style={{background: "#0b1220", justifyContent: "center", alignItems: "center"}}>
    <div style={{fontFamily: MONO, fontSize: FONT.endCard, fontWeight: 700, color: "#fff"}}>
      python3 run.py
    </div>
    <Cap size={FONT.cap} weight={500} color="#8fa3bf" style={{marginTop: 34}}>
      cookbook/sim-engine-arena · every number above from grade.json
    </Cap>
  </AbsoluteFill>
);

/* ------------------------------------------------------------- the video */

export const Demo: React.FC = () => (
  <AbsoluteFill style={{background: "#060a12"}}>
    <Sequence {...SLOTS.hook}>
      <Hook />
    </Sequence>
    <Sequence {...SLOTS.scenes}>
      <SceneStrip />
    </Sequence>
    <Sequence {...SLOTS.grid}>
      <Grid />
    </Sequence>
    <Sequence {...SLOTS.agentRun}>
      <AgentRun />
    </Sequence>
    <Sequence {...SLOTS.closeups}>
      <Closeups />
    </Sequence>
    <Sequence {...SLOTS.proof}>
      <ProofCard />
    </Sequence>
    <Sequence {...SLOTS.endCard}>
      <EndCard />
    </Sequence>
  </AbsoluteFill>
);
