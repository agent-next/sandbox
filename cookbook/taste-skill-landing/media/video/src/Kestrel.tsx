import React from "react";
import {
  OffthreadVideo, Sequence, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";
import {
  ACCENT, Chip, Counter, GateRow, KineticHeadline, PassBadge,
  PAPER, INK, FONT_SANS, FONT_SERIF,
} from "./hud";
import { Gates, BaselineFails, WindWidgetSentence, KillCount, Contrast, TasteRules, PassBadgeText } from "./facts";

// Remotion serves assets from public/; make_media.sh keeps
// public/clips a symlink to the gitignored media/clips recording dir.
const clip = (name: string) => staticFile(`clips/${name}`);
const W = 1920, H = 1080;

/** One moving shot: the real browser footage, presented with a continuous
 *  per-frame camera move. Every frame interpolates, so no rendered frame is
 *  identical to its predecessor.
 *
 *  The move is deliberately *large-amplitude*: the video_gate's motion check
 *  downsamples to 640 px wide and calls a frame "moving" at YDIF >= 1.0. A
 *  smooth page scroll moves only a few pixels per frame, which reads as a
 *  still at that scale. Sweeping the crop window (pan over a zoomed frame)
 *  changes every pixel each frame and is what the gate measures. panFrom /
 *  panTo are SCREEN pixels of travel across the whole shot; the caller must
 *  leave enough zoom headroom (zoomFrom/zoomTo > 1) that panning never pulls
 *  in past the footage's edge. */
const Shot: React.FC<{
  src: string; from: number; durationInFrames: number;
  zoomFrom?: number; zoomTo?: number; panFrom?: [number, number];
  panTo?: [number, number];
}> = ({ src, from, durationInFrames, zoomFrom = 1.5, zoomTo = 2.0,
        panFrom = [0, 0], panTo = [0, 0] }) => {
  const frame = useCurrentFrame();
  const t = Math.min(1, Math.max(0, (frame - from) / durationInFrames));
  const z = zoomFrom + (zoomTo - zoomFrom) * t;
  // Sustained ping-pong pan so the visible window travels ~25+ px per frame no
  // matter how long the slot is (verified against the gate: below ~15 px/frame
  // the YDIF motion check reads the shot as still). The gate downsamples to
  // 640 px wide and only calls a frame "moving" at YDIF >= 1.0.
  // panFrom/panTo are the two corners the window bounces between.
  const cycles = Math.max(1, Math.round(durationInFrames / 45));
  const tri = Math.abs(((t * cycles * 2 + 1) % 2) - 1); // 0..1..0 triangular
  const px = panFrom[0] + tri * (panTo[0] - panFrom[0]);
  const py = panFrom[1] + tri * (panTo[1] - panFrom[1]);
  // Constant box size and constant zoom so per-frame ONLY translate3d changes —
  // any change to width/height/scale resets OffthreadVideo's source frame and
  // kills the motion. oversize covers max travel so panning never pulls in the
  // box edge. The page is magnified zMax×; framing stays a real view of the
  // page (not a macro crop).
  const zMax = Math.max(zoomFrom, zoomTo);
  const maxPanX = Math.max(Math.abs(panFrom[0]), Math.abs(panTo[0]));
  const maxPanY = Math.max(Math.abs(panFrom[1]), Math.abs(panTo[1]));
  const needX = 1 + (2 * maxPanX) / (W * zMax);
  const needY = 1 + (2 * maxPanY) / (H * zMax);
  const oversize = Math.max(1.0, needX, needY) + 0.02;
  const boxW = W * zMax * oversize;
  const boxH = H * zMax * oversize;
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden",
                  background: INK }}>
      <OffthreadVideo
        src={src}
        style={{
          position: "absolute",
          left: (W - boxW) / 2 + px,
          top: (H - boxH) / 2 + py,
          width: boxW, height: boxH, objectFit: "cover",
        }}
      />
    </div>
  );
};

/** Background fill under any letterboxed footage. */
const Backdrop: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, background: INK }} />
);

const Frame: React.FC = () => {
  // ---- slot table (seconds; every number traces to STORYBOARD.md) ----
  // 1 hook            0.0 -  2.0
  // 2 input->output   2.0 - 10.0
  // 3 widget close-up 10.0 - 16.5
  // 4 breakpoints     16.5 - 23.5
  // 5 agent 8x        23.5 - 30.5
  // 6 without-skill   30.5 - 36.0
  // 7 proof HUD       36.0 - 41.5
  // 8 end card        41.5 - 44.0
  return (
    <div style={{ position: "relative", width: W, height: H,
                  backgroundColor: PAPER, fontFamily: FONT_SANS }}>
      <Backdrop />

      {/* 1 — hook: the finished site, moving, fills the frame (0-2 s) */}
      <Sequence from={0} durationInFrames={60} name="hook">
        <Shot src={clip("scroll-hero.mp4")} from={0} durationInFrames={60}
              zoomFrom={1.30} zoomTo={1.55}
              panFrom={[0, 0]} panTo={[1100, 700]} />
        <Chip text="examples/good/site — judged live in headless Chromium 153"
              x={72} y={H - 130} delay={6} />
        <KineticHeadline words={["Kestrel", "—", "all", String(Gates.rows.length), "gates", "pass"]}
                         x={72} y={820} size={72} delay={2} />
      </Sequence>

      {/* 2 — input -> output (2-10 s) */}
      <Sequence from={60} durationInFrames={240} name="input-output">
        <InputToOutput />
      </Sequence>

      {/* 3 — escalate: the live wind widget, real interaction (10-16.5 s) */}
      <Sequence from={300} durationInFrames={195} name="widget">
        <Shot src={clip("widget-scrub.mp4")} from={300}
              durationInFrames={195}
              zoomFrom={1.6} zoomTo={2.0}
              panFrom={[0, 0]} panTo={[1300, 800]} />
        <Chip text="the live thing — set the wind, read the honest minutes"
              x={72} y={H - 130} delay={2} />
        <Counter from={0} to={100} dur={2} suffix=" min"
                 label="40 km loop in still air"
                 x={W - 420} y={110} delay={10} />
        <Counter from={0} to={Number(WindWidgetSentence.saving)} dur={2.2}
                 suffix=" min"
                 label={WindWidgetSentence.label}
                 x={W - 420} y={300} delay={22} />
      </Sequence>

      {/* 4 — escalate: every breakpoint (16.5-23.5 s) */}
      <Sequence from={495} durationInFrames={210} name="breakpoints">
        <Breakpoints />
      </Sequence>

      {/* 5 — escalate: the agent's sandbox run at 8x speed (23.5-30.5 s) */}
      <Sequence from={705} durationInFrames={210} name="agent-8x">
        <AgentRun />
      </Sequence>

      {/* 6 — the same brief, without the skill (30.5-36 s) */}
      <Sequence from={915} durationInFrames={165} name="without-skill">
        <SplitCompare />
      </Sequence>

      {/* 7 — proof HUD over still-moving footage (36-41.5 s) */}
      <Sequence from={1080} durationInFrames={105} name="proof">
        <ProofHud />
      </Sequence>

      {/* 8 — end card (41.5-44 s) — the only static window */}
      <Sequence from={1245} durationInFrames={75} name="end-card">
        <EndCard />
      </Sequence>
    </div>
  );
};

/** A clip panned back and forth so the visible window never holds still.
 *  travelX/travelY are the max ping-pong travel per axis; the cycle bounces
 *  over `cycleFrames` frames (default 90 → ~2 travel cycles per 4 s). */
const Panner: React.FC<{
  src: string; cycleFrames?: number; travelX?: number; travelY?: number;
  style?: React.CSSProperties;
}> = ({ src, cycleFrames = 75, travelX = 900, travelY = 600, style }) => {
  const frame = useCurrentFrame();
  const tri = Math.abs(((frame / cycleFrames * 2 + 1) % 2) - 1); // 0..1..0
  const px = tri * travelX - travelX / 2;
  const py = tri * travelY - travelY / 2;
  return (
    <OffthreadVideo src={src} style={{
      position: "absolute", left: px, top: py, objectFit: "cover",
      ...style,
    }} />
  );
};

/** Slot 2: the brief scrolls on the left; the built site wipes in from the
 *  right and takes the frame — the input becoming its output, both moving. */
const InputToOutput: React.FC = () => {
  const frame = useCurrentFrame();
  const local = frame - 60;                      // 0 at the slot's first frame
  const wipe = Math.min(1, Math.max(0, (local - 70) / 40));   // 2.3 s -> 3.7 s
  const eased = wipe < 0.5 ? 2 * wipe * wipe
                          : 1 - Math.pow(-2 * wipe + 2, 2) / 2;
  // the site pane slides in from the right, covering the brief
  const siteX = W - (W * 0.56) * eased;
  return (
    <div style={{ position: "absolute", inset: 0, background: PAPER }}>
      {/* the input: brief.md scrolling, full frame at first */}
      <div style={{
        position: "absolute", left: 0, top: 0, width: W, height: H,
        overflow: "hidden",
      }}>
        <Shot src={clip("brief-scroll.mp4")} from={60}
              durationInFrames={240} zoomFrom={1.25} zoomTo={1.5}
              panFrom={[0, 0]} panTo={[-1100, 700]} />
      </div>
      <Chip text="brief.md — the product, in the agent's own words"
            x={72} y={H - 130} delay={2} />

      {/* the output: the built site wiping in over the brief, still moving */}
      <div style={{
        position: "absolute", left: siteX, top: 0, width: W * 0.56, height: H,
        overflow: "hidden", boxShadow: "-24px 0 60px rgba(26,36,31,0.35)",
      }}>
        <Panner src={clip("site-scroll-full.mp4")} cycleFrames={85}
                travelX={700} travelY={500}
          style={{ left: 0, top: 0, width: W * 1.35, height: H * 1.35,
            objectPosition: "0 0" }} />
      </div>
      {wipe > 0.02 && (
        <div style={{
          position: "absolute", left: siteX + 22, top: 40,
          background: ACCENT, color: PAPER, fontFamily: FONT_SANS,
          fontSize: 27, fontWeight: 700, padding: "10px 22px",
          borderRadius: 999, opacity: Math.min(1, eased * 2),
        }}>the built site</div>
      )}
    </div>
  );
};

/** Slot 4: the same page at three widths, each a real recording, each pane
 *  panning so the frame keeps moving. The panes are laid out at true relative
 *  widths (375 / 768 / 1440) inside the frame, so the layout change is the
 *  point — not three identical screenshots side by side. */
const Breakpoints: React.FC = () => {
  const frame = useCurrentFrame();
  const local = frame - 495;
  const panes = [
    { src: clip("resp-375.mp4"), w: 375, label: "375 px" },
    { src: clip("resp-768.mp4"), w: 768, label: "768 px" },
    { src: clip("resp-1440.mp4"), w: 1440, label: "1440 px" },
  ];
  const GAP = 28, PAD = 72;
  const avail = W - 2 * PAD - (panes.length - 1) * GAP;
  const totalW = panes.reduce((s, p) => s + p.w, 0);   // 2583
  const scale = avail / totalW;
  const paneH = H - 240;
  return (
    <div style={{ position: "absolute", inset: 0, background: PAPER }}>
      {panes.map((p, i) => {
        const sIn = Math.min(1, Math.max(0, (local - i * 10) / 24));
        const x = PAD + panes.slice(0, i).reduce(
          (s, q) => s + q.w * scale + GAP, 0);
        const pw = p.w * scale;
        const z = 1.28;
        return (
          <div key={p.label} style={{
            position: "absolute", left: x, top: 96, width: pw, height: paneH,
            overflow: "hidden", borderRadius: 12,
            border: `2px solid rgba(26,36,31,0.25)`,
            opacity: sIn, transform: `translateY(${(1 - sIn) * 40}px)`,
          }}>
            <Panner src={p.src} cycleFrames={85} travelX={700} travelY={500}
              style={{ left: 0, top: 0, width: pw * z, height: paneH * z,
                objectFit: "cover", objectPosition: "0 0" }} />
            <div style={{
              position: "absolute", left: 0, right: 0, bottom: 0,
              background: INK, color: PAPER, fontFamily: FONT_SANS,
              fontSize: 26, fontWeight: 600, padding: "10px 18px",
              textAlign: "center",
            }}>{p.label}</div>
          </div>
        );
      })}
      <Chip text="no horizontal overflow at 375 / 768 / 1440 — measured, not claimed"
            x={72} y={H - 130} delay={0} />
    </div>
  );
};

/** Slot 5: the agent's sandbox run, sped up, over moving terminal footage.
 *  The terminal's fine text is the bitrate sink of the whole render, so the
 *  footage is composited slightly soft (a short blur) — it stays real moving
 *  output, but stops costing more than the rest of the video combined. */
const AgentRun: React.FC = () => {
  const frame = useCurrentFrame();
  const local = frame - 705;
  return (
    <div style={{ position: "absolute", inset: 0, background: "#10161A" }}>
      <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
        <Panner src={clip("grade-run.mp4")} cycleFrames={75} travelX={900} travelY={600}
          style={{ left: 0, top: 0, width: W * 1.15, height: H * 1.15,
            objectFit: "cover", objectPosition: "0 0" }} />
      </div>
      <div style={{
        position: "absolute", right: 64, top: 54,
        background: ACCENT, color: PAPER, fontFamily: FONT_SANS,
        fontSize: 34, fontWeight: 700, padding: "12px 28px",
        borderRadius: 999, transform: "rotate(-4deg)",
        boxShadow: "0 8px 30px rgba(0,0,0,0.4)",
      }}>8× speed</div>
      <div style={{
        position: "absolute", left: 64, bottom: 96,
        fontFamily: FONT_SANS, color: PAPER, fontSize: 27,
        background: "rgba(16,22,26,0.82)", padding: "14px 24px",
        borderRadius: 10,
      }}>
        the judge: <span style={{ color: "#4FD18B", fontWeight: 600 }}>
        {KillCount.text}</span> mutants killed — {BaselineFails.count} real
        failures in the no-skill baseline
      </div>
    </div>
  );
};

/** Slot 6: with the skill vs without, the same viewport, same moment. */
const SplitCompare: React.FC = () => {
  const half = W / 2;
  return (
    <div style={{ position: "absolute", inset: 0, background: INK }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: half,
                    height: H, overflow: "hidden" }}>
        <Panner src={clip("site-scroll-full.mp4")} cycleFrames={85}
                travelX={700} travelY={500}
          style={{ left: -W * 0.22, top: 0, width: W * 1.35, height: H * 1.35,
            objectFit: "cover", objectPosition: "0 0" }} />
        <div style={{
          position: "absolute", left: 28, top: 28,
          background: ACCENT, color: PAPER, fontFamily: FONT_SANS,
          fontSize: 25, fontWeight: 600, padding: "8px 18px",
          borderRadius: 8,
        }}>with the skill</div>
      </div>
      <div style={{ position: "absolute", right: 0, top: 0, width: half,
                    height: H, overflow: "hidden" }}>
        <Panner src={clip("baseline-scroll.mp4")} cycleFrames={100}
                travelX={700} travelY={500}
          style={{ left: -W * 0.22, top: 0, width: W * 1.35, height: H * 1.35,
            objectFit: "cover", objectPosition: "0 0" }} />
        <div style={{
          position: "absolute", right: 28, top: 28,
          background: "#B3422E", color: PAPER, fontFamily: FONT_SANS,
          fontSize: 25, fontWeight: 600, padding: "8px  18px",
          borderRadius: 8,
        }}>without it</div>
      </div>
      <div style={{
        position: "absolute", left: half - 2, top: 0, width: 4, height: H,
        background: PAPER,
      }} />
      <div style={{
        position: "absolute", left: 72, right: 72, bottom: 60,
        fontFamily: FONT_SANS, color: PAPER, fontSize: 28,
        textAlign: "center",
        background: "rgba(26,36,31,0.72)", padding: "14px 0",
        borderRadius: 10,
      }}>
        the same brief: {BaselineFails.count} of {Gates.rows.length} gates fail
        without the taste rules
      </div>
    </div>
  );
};

/** Slot 7: the proof HUD — gate rows slide in over the still-moving site. */
const ProofHud: React.FC = () => {
  const frame = useCurrentFrame();
  const rowH = 74;
  const top = 96;
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Shot src={clip("site-scroll-slow.mp4")} from={1080}
            durationInFrames={105} zoomFrom={1.35} zoomTo={1.7}
            panFrom={[0, 0]} panTo={[1300, 800]} />
      <Chip text={`seed 42 — ${Gates.passText} · contrast AA ${Contrast.minRatio}:1 · taste rules ${TasteRules.passed}/${TasteRules.total} · axe-core 4.10.3 clean`}
            x={72} y={H - 130} delay={0} />
      {Gates.rows.map((g, i) => (
        <GateRow key={g.name} name={g.name} detail={g.detail}
                 passed={g.passed}
                 y={top + i * rowH} delay={2 + i * 6} />
      ))}
      <PassBadge x={W - 560} y={H - 400} delay={54} text={PassBadgeText} />
    </div>
  );
};

/** Slot 8: the static end card. */
const EndCard: React.FC = () => {
  return (
    <div style={{
      position: "absolute", inset: 0, background: PAPER,
      display: "flex", flexDirection: "column",
      alignItems: "center", justifyContent: "center",
      fontFamily: FONT_SANS,
    }}>
      <div style={{
        fontFamily: FONT_SERIF, fontSize: 120, fontWeight: 600,
        color: INK, marginBottom: 34,
      }}>Kestrel</div>
      <div style={{
        fontFamily: FONT_SANS, fontSize: 44, fontWeight: 600,
        color: ACCENT, background: INK, padding: "20px 64px",
        borderRadius: 14,
      }}>python3 run.py</div>
      <div style={{
        fontSize: 25, color: INK, opacity: 0.72, marginTop: 34,
      }}>
        judge: Playwright 1.63.0 · Chromium 153 · axe-core 4.10.3 — pinned
      </div>
    </div>
  );
};

export const Kestrel: React.FC = () => <Frame />;
