// Timing and design constants for the sim-engine-arena video.
// Every number shown comes from clips/numbers.json, which clips.py writes
// from media/data/grade.json (this run's real judge output, seed 0) and
// RECEIPT.md. Nothing here invents a measurement.

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

const F = (s: number): number => Math.round(s * FPS);

// Slot table, matching media/STORYBOARD.md. The end card is the only part
// of the video without motion; everything before it is a moving render.
export const SLOTS = {
  hook:     {from: 0,    frames: F(2)    },  // 0-2     finished result, moving
  scenes:   {from: F(2),  frames: F(10)   },  // 2-12    input -> output, 4 scenes
  grid:     {from: F(12), frames: F(5)    },  // 12-17   2x2 grid, all four moving
  agentRun: {from: F(17), frames: F(4)    },  // 17-21   the recorded agent run, sped up
  closeups: {from: F(21), frames: F(2)    },  // 21-23   tracked close-ups
  proof:    {from: F(23), frames: F(6.5)  },  // 23-29.5 PASS badge + gate rows
  endCard:  {from: F(29.5), frames: F(2.5)},  // 29.5-32 static end card
} as const;

export const TOTAL_FRAMES = SLOTS.endCard.from + SLOTS.endCard.frames;

// Clip filenames (media/clips/, copied into video/public/ at build time)
export const CLIP = {
  hook: "01_hook.mp4",
  drop: "02_drop.mp4",
  slide: "03_slide.mp4",
  stick: "04_stick.mp4",
  pendulum: "05_pendulum.mp4",
  quad: "06_quad.mp4",
  closeup: "08_closeup.mp4",
  proof: "09_proof.mp4",
} as const;

// Captions must clear DEMO-STANDARD.md: cap height >= 4% of frame height
// (43.2 px at 1080). DejaVu's capital height is ~0.73 em, so every size
// below is >= 60 px (0.73 * 60 = 43.8 px of cap height).
export const FONT = {
  cap: 60,        // 5.6% caps (43.8 px) - smallest on-screen text
  mono: 60,       // 5.6% - the HUD's numeric rows
  scene: 76,      // 7.0% - scene titles
  stat: 92,       // 8.5% - HUD values
  headline: 128,  // 11.9% - the kinetic headline
  pass: 80,       // 7.4% - the PASS badge
  endCard: 150,   // 13.9% - `python3 run.py`
} as const;

export const INK = "#0b1220";
export const PAPER = "#f7f9fc";
export const ACCENT = "#4f8cff";
export const PASS = "#2fbf71";
export const DIM = "#8fa3bf";

// The measured numbers, from this run's grade.json (seed 0).
export const NUMBERS_FILE = "numbers.json";
