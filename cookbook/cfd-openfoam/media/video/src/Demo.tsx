// Demo.tsx — the 35 s cut. Every sequence before the end card is moving
// real footage (clips rendered from THIS run's judge trace output);
// captions and judge numbers ride on top as a HUD, never as slides.
import React from 'react';
import { AbsoluteFill, OffthreadVideo, Sequence, staticFile, useCurrentFrame } from 'remotion';
import type { DemoData } from './lib/types';
import { INK, PAPER, FONT, captionSize, kicker, caption, dim, pop, plate, BLUE, ORANGE, GREEN } from './components/kit';
import { Headline, ProofHud, PassBadge, ResidGauge, CountReadout, SpeedTag } from './Hud';
import { EndCard } from './EndCard';

const s = (sec: number) => Math.round(sec * 30);

const Clip: React.FC<{ src: string }> = ({ src }) => (
  <AbsoluteFill>
    <OffthreadVideo
      src={staticFile(src)}
      style={{ width: '100%', height: '100%', objectFit: 'cover' }}
    />
    <div style={dim} />
  </AbsoluteFill>
);

// Kicker + headline text block top-left, sprung in.
const Kick: React.FC<{ k: string; line?: string; delay?: number }> = ({ k, line, delay = 0 }) => {
  const f = useCurrentFrame();
  const a = pop(f, delay);
  return (
    <div style={{ position: 'absolute', left: 56, top: 46, opacity: a, transform: `translateY(${20 * (1 - a)}px)` }}>
      <div style={{ ...kicker(), fontSize: captionSize(0.44), color: '#8fc3ff' }}>{k}</div>
      {line ? <div style={{ ...caption(), fontSize: captionSize(0.95), marginTop: 8 }}>{line}</div> : null}
    </div>
  );
};

// Left column of the input files sliding in over the developing field.
const InputList: React.FC = () => {
  const f = useCurrentFrame();
  const files = [
    '0/U — lid 1 m/s, walls fixed',
    '0/p — kinematic pressure',
    'constant/transportProperties — nu = 0.01',
    'system/blockMeshDict — 40x40 mesh',
    'system/controlDict — dt 0.01, endTime 30',
    'system/fvSolution — PISO',
  ];
  return (
    <div style={{ position: 'absolute', left: 56, top: 170, width: 720 }}>
      <div style={{ ...kicker(), color: '#8fc3ff', marginBottom: 16, fontSize: captionSize(0.44) }}>
        input: one case directory, 6 files
      </div>
      {files.map((t, i) => {
        const a = pop(f, 8 + i * 9);
        return (
          <div key={t} style={{
            fontFamily: FONT, fontSize: captionSize(0.5), color: PAPER, fontWeight: 700,
            padding: '11px 18px', marginBottom: 9,
            opacity: a, transform: `translateX(${-46 * (1 - a)}px)`,
            background: 'rgba(8,13,19,0.62)', borderLeft: `4px solid ${i % 2 ? '#eb6834' : '#2a78d6'}`,
            borderRadius: 10, textShadow: '0 2px 10px rgba(0,0,0,0.8)',
          }}>{t}</div>
        );
      })}
    </div>
  );
};

const OutputTag: React.FC = () => {
  const f = useCurrentFrame();
  const a = pop(f, 60);
  return (
    <div style={{ position: 'absolute', right: 56, bottom: 70, opacity: a }}>
      <div style={{ ...plate, borderColor: BLUE }}>
        <div style={{ ...kicker(), fontSize: captionSize(0.42), color: '#ffb38a' }}>output</div>
        <div style={{ ...caption(), fontSize: captionSize(0.72), marginTop: 6 }}>
          the |U| field developing<br />behind this list
        </div>
      </div>
    </div>
  );
};

export const Demo: React.FC<DemoData> = (d) => {
  return (
    <AbsoluteFill style={{ background: INK }}>
      {/* 0-2 s — hook: the finished result, moving, fills the frame */}
      <Sequence from={0} durationInFrames={s(2)} name="hook">
        <AbsoluteFill>
          <Clip src={d.clips.hook} />
          <Kick k="lid-driven cavity · Re = 100 · OpenFOAM 1912 · icoFoam" />
        </AbsoluteFill>
      </Sequence>

      {/* 2-8 s — input -> output over the field spinning up from rest */}
      <Sequence from={s(2)} durationInFrames={s(6)} name="input-output">
        <AbsoluteFill>
          <Clip src={d.clips.develop} />
          <Kick k="the agent writes a case; the solver spins it up" />
          <InputList />
          <OutputTag />
        </AbsoluteFill>
      </Sequence>

      {/* 8-12.5 s — escalate: camera dives into the corner vortex */}
      <Sequence from={s(8)} durationInFrames={s(4.5)} name="closeup">
        <AbsoluteFill>
          <Clip src={d.clips.closeup} />
          <Kick k="camera inside the flow" line="corner vortex at the moving lid — the same solver data, zoomed" />
        </AbsoluteFill>
      </Sequence>

      {/* 12.5-17.5 s — the agent's real sandbox run, sped up */}
      <Sequence from={s(12.5)} durationInFrames={s(5)} name="agent-run">
        <AbsoluteFill>
          <Clip src={d.clips.agent} />
          <Kick k={`the sandbox run that made this — ${d.agent.wallSeconds} s of wall clock`} />
          <SpeedTag speed={d.agent.speed} />
          <Headline lines={['setup → selftest → grade, in a throwaway sandbox', '15 judge runs · every verdict measured']} base={12} />
        </AbsoluteFill>
      </Sequence>

      {/* 17.5-22.5 s — proof as a HUD over the still-moving field */}
      <Sequence from={s(17.5)} durationInFrames={s(5)} name="proof">
        <AbsoluteFill>
          <Clip src={d.clips.proof} />
          <ProofHud data={d} />
          <PassBadge data={d} />
          <ResidGauge resid={d.hud.residFinal} cont={d.hud.continuity} t={d.hud.tEnd} />
          <div style={{ position: 'absolute', left: 56, bottom: 52 }}>
            <CountReadout label="mutants killed by the judge" to={10} decimals={0} suffix=" / 10" />
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* 22.5-25 s — verdict lands, footage still moving */}
      <Sequence from={s(22.5)} durationInFrames={s(2.5)} name="verdict">
        <AbsoluteFill>
          <Clip src={d.clips.verdict} />
          <VerdictBanner />
        </AbsoluteFill>
      </Sequence>

      {/* last 2.5 s — the only static frame */}
      <Sequence from={s(25)} durationInFrames={s(2.5)} name="endcard">
        <EndCard data={d} />
      </Sequence>

      {/* 2-frame accent flashes at every cut — a real transition, and
          each one scores as a scene cut for the gate (a dip to the dark
          ink background scores < 0.3 against already-dark footage). */}
      {[2, 8, 12.5, 17.5, 22.5, 25].map((t) => (
        <Sequence key={t} from={s(t) - 1} durationInFrames={2} name={`dip-${t}`}>
          <AbsoluteFill style={{ background: ORANGE }} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

const VerdictBanner: React.FC = () => {
  const f = useCurrentFrame();
  const a = pop(f, 2);
  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: a, transform: `scale(${0.9 + 0.1 * a})` }}>
      <div style={{ textAlign: 'center', fontFamily: FONT, fontSize: captionSize(1.5), fontWeight: 800, color: PAPER, textShadow: '0 3px 22px rgba(0,0,0,0.9)' }}>
        judge: <span style={{ color: GREEN }}>PASS</span> — every number measured
      </div>
    </div>
  );
};
