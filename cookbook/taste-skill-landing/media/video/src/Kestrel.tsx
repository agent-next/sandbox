import React from "react";
import { OffthreadVideo, Sequence, useCurrentFrame, useVideoConfig } from "remotion";
import {
  ACCENT, Chip, Counter, GateRow, KineticHeadline, PassBadge,
  PAPER, INK, FONT_SANS, FONT_SERIF,
} from "./hud";
import { Gates, BaselineFails, WindWidgetSentence, KillCount } from "./facts";

const CLIPS = "../clips";
const W = 1920, H = 1080;

/** One moving shot: the real browser footage, presented with a continuous
 *  per-frame camera move (Remotion interpolates every frame, so no rendered
 *  frame repeats even when the source recorder duplicated one). */
const Shot: React.FC<{
  src: string; from: number; durationInFrames: number;
  zoomFrom?: number; zoomTo?: number; panFrom?: [number, number];
  panTo?: [number, number];
}> = ({ src, from, durationInFrames, zoomFrom = 1.0, zoomTo = 1.14,
        panFrom = [0, 0], panTo = [0, 0] }) => {
  const frame = useCurrentFrame();
  const t = Math.min(1, Math.max(0, (frame - from) / durationInFrames));
  const z = zoomFrom + (zoomTo - zoomFrom) * t;
  const px = panFrom[0] + (panTo[0] - panFrom[0]) * t;
  const py = panFrom[1] + (panTo[1] - panFrom[1]) * t;
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      <OffthreadVideo
        src={src}
        style={{
          position: "absolute", width: W, height: H,
          transform: `translate(${px}px, ${py}px) scale(${z})`,
          transformOrigin: `${50 + px * 0.02}% 50%`,
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
  const fps = 30;
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
        <Shot src={`${CLIPS}/scroll-hero.mp4`} from={0} durationInFrames={60}
              zoomFrom={1.02} zoomTo={1.16} />
        <Chip text="examples/good/site — judged live in headless Chromium 153"
              x={72} y={H - 130} delay={6} />
        <KineticHeadline words={["Kestrel", "—", "all", "7", "gates", "pass"]}
                         x={72} y={H - 320} size={72} delay={2} />
      </Sequence>

      {/* 2 — input -> output (2-10 s) */}
      <Sequence from={60} durationInFrames={240} name="input-output">
        <Shot src={`${CLIPS}/brief-scroll.mp4`} from={60} durationInFrames={240}
              zoomFrom={1.0} zoomTo={1.10} panFrom={[0, 0]} panTo={[-40, 0]} />
        {/* the built site slides in over the brief as the output */}
        <OutputOverlay />
        <Chip text="the brief" x={72} y={H - 130} delay={2} />
      </Sequence>

      {/* 3 — escalate: the live wind widget, real interaction (10-16.5 s) */}
      <Sequence from={300} durationInFrames={195} name="widget">
        <Shot src={`${CLIPS}/widget-scrub.mp4`} from={300}
              durationInFrames={195}
              zoomFrom={1.55} zoomTo={1.85}
              panFrom={[0, 0]} panTo={[-260, 140]} />
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

/** Slot 2: the brief on the left, the built site fading in on the right. */
const OutputOverlay: React.FC = () => {
  const frame = useCurrentFrame();
  const local = frame - 60;
  const slideIn = Math.min(1, Math.max(0, (local - 40) / 30));
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <div style={{
        position: "absolute", left: 0, top: 0, bottom: 0,
        width: W * 0.505, overflow: "hidden", background: PAPER,
        transform: `translateX(${-W * 0.5 * (1 - 1)}px)`,
        borderRight: `4px solid ${INK}`,
      }}>
        <Shot src={`${CLIPS}/brief-scroll.mp4`} from={60}
              durationInFrames={240} zoomFrom={1.0} zoomTo={1.0} />
      </div>
    </div>
  );
};

/** Slot 4: three widths side by side, each scrolling (real responsive layout). */
const Breakpoints: React.FC = () => {
  const frame = useCurrentFrame();
  const local = frame - 495;
  const panes = [
    { src: `${CLIPS}/resp-375.mp4`, w: 375, label: "375 px" },
    { src: `${CLIPS}/resp-768.mp4`, w: 768, label: "768 px" },
    { src: `${CLIPS}/resp-1440.mp4`, w: 1440, label: "1440 px" },
  ];
  const totalW = panes.reduce((s, p) => s + p.w, 0);   // 2583
  const scale = (W - 2 * 72 - (panes.length - 1) * 24) / totalW; // fit to frame
  const paneH = H - 240;
  return (
    <div style={{ position: "absolute", inset: 0, background: PAPER }}>
      {panes.map((p, i) => {
        const sIn = Math.min(1, Math.max(0, (local - i * 8) / 22));
        const x = 72 + panes.slice(0, i).reduce((s, q) => s + (q.w * scale) + 24, 0);
        return (
          <div key={p.label} style={{
            position: "absolute", left: x, top: 96,
            width: p.w * scale, height: paneH,
            overflow: "hidden", borderRadius: 12,
            border: `2px solid rgba(26,36,31,0.25)`,
            opacity: sIn, transform: `translateY(${(1 - sIn) * 40}px)`,
          }}>
            <OffthreadVideo src={p.src} style={{
              position: "absolute", left: 0, top: 0,
              width: p.w * scale, height: "100%",
              objectFit: "cover",
            }} />
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

/** Slot 5: the agent's sandbox run, sped up, over moving terminal footage. */
const AgentRun: React.FC = () => {
  const frame = useCurrentFrame();
  const local = frame - 705;
  // the real grade.sh output scrolls by at 8x the recorded speed
  const speed = 8;
  return (
    <div style={{ position: "absolute", inset: 0, background: "#10161A" }}>
      <div style={{ position: "absolute", inset: 0 }}>
        <OffthreadVideo src={`${CLIPS}/grade-run.mp4`} style={{
          position: "absolute", inset: 0, width: W, height: H,
          transform: `scale(${1.0 + 0.10 * Math.min(1, local / 210)})`,
        }} />
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
  const frame = useCurrentFrame();
  const local = frame - 915;
  const half = W / 2;
  return (
    <div style={{ position: "absolute", inset: 0, background: INK }}>
      <div style={{ position: "absolute", left: 0, top: 0, width: half,
                    height: H, overflow: "hidden" }}>
        <OffthreadVideo src={`${CLIPS}/site-scroll-full.mp4`} style={{
          position: "absolute", left: 0, top: 0, width: half, height: H,
          objectFit: "cover", objectPosition: "0 0",
        }} />
        <div style={{
          position: "absolute", left: 28, top: 28,
          background: ACCENT, color: PAPER, fontFamily: FONT_SANS,
          fontSize: 25, fontWeight: 600, padding: "8px 18px",
          borderRadius: 8,
        }}>with the skill</div>
      </div>
      <div style={{ position: "absolute", right: 0, top: 0, width: half,
                    height: H, overflow: "hidden" }}>
        <OffthreadVideo src={`${CLIPS}/baseline-scroll.mp4`} style={{
          position: "absolute", left: 0, top: 0, width: half, height: H,
          objectFit: "cover", objectPosition: "0 0",
        }} />
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
        the same brief: {BaselineFails.count} of 7 gates fail without the
        taste rules
      </div>
    </div>
  );
};

/** Slot 7: the proof HUD — gate rows slide in over the still-moving site. */
const ProofHud: React.FC = () => {
  const frame = useCurrentFrame();
  const local = frame - 1080;
  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Shot src={`${CLIPS}/site-scroll-slow.mp4`} from={1080}
            durationInFrames={105} zoomFrom={1.05} zoomTo={1.22}
            panFrom={[0, 0]} panTo={[-120, -60]} />
      <Chip text={`seed 42 — ${Gates.passText} · contrast AA 5.19:1 · axe-core 4.10.3 clean`}
            x={72} y={H - 130} delay={0} />
      {Gates.rows.map((g, i) => (
        <GateRow key={g.name} name={g.name} detail={g.detail}
                 passed={g.passed}
                 y={96 + i * 74} delay={2 + i * 6} />
      ))}
      <PassBadge x={1180} y={H - 420} delay={54} />
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
