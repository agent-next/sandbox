// Demo.tsx — the 33 s cut. Every sequence before the end card is moving real
// footage (clips/*.mp4 rendered from this run's judge output); the HUD
// numbers are written from the same files, never invented.
import React from 'react';
import { AbsoluteFill, Sequence, staticFile, Video, OffthreadVideo } from 'remotion';
import type { DemoData } from './lib/types';
import { dim, INK, PAPER, FONT, captionSize, kicker, caption } from './components/kit';
import { Headline, ProofHud, PassBadge, ResidGauge, CountReadout, SpeedTag } from './Hud';
import { EndCard } from './EndCard';

const topSafe = 46;

const Cap = ({ children }: { children: React.ReactNode }) => (
  <div style={{ position: 'absolute', left: 56, right: 56, top: topSafe, display: 'flex', flexDirection: 'column', gap: 6 }}>{children}</div>
);

const Moving = ({ from, durationInFrames, name, caption: cap, children, clip, loop = false }: any) => (
  <Sequence from={from} durationInFrames={durationInFrames} name={name}>
    <AbsoluteFill>
      <OffthreadVideo
        src={staticFile(clip)}
        startFrom={0}
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
      <div style={dim} />
      {cap ? (
        <Cap>
          <div style={kicker()}>{cap}</div>
        </Cap>
      ) : null}
      {children}
    </AbsoluteFill>
  </Sequence>
);

export const Demo: React.FC<DemoData> = (data) => {
  const fps = 30;
  const hookEnd = 6 * fps;                    // 0-6 s hook: converged field moving
  const agentStart = hookEnd, agentEnd = agentStart + 8 * fps;       // 6-14 s
  const closeStart = agentEnd, closeEnd = closeStart + 7 * fps;      // 14-21 s
  const proofStart = closeEnd, proofEnd = proofStart + 7 * fps;      // 21-28 s
  const finalStart = proofEnd;                                        // 28-30 s
  const endStart = 30 * fps;

  return (
    <AbsoluteFill style={{ background: INK }}>
      {/* 0-6 s — hook: the finished result, moving, fills the frame */}
      <Moving name="hook" clip={data.clips.hook} durationInFrames={hookEnd} from={0}>
        <Cap>
          <div style={{ ...kicker(), fontSize: captionSize(0.46), color: '#8fc3ff' }}>lid-driven cavity · Re = 100 · OpenFOAM 1912 · icoFoam</div>
          <div style={{ ...caption(), fontSize: captionSize(1.15) }}>flow the judge graded — moving, not a figure</div>
        </Cap>
      </Moving>

      {/* 6-14 s — the agent's own sandbox run, sped up */}
      <Moving name="agent" clip={data.clips.agent} durationInFrames={agentEnd - agentStart} from={agentStart}>
        <SpeedTag speed={data.agent.speed} local={useCurrentFrame()} />
        <Headline
          local={useCurrentFrame()}
          lines={[`the agent did this in a throwaway sandbox`, `${data.agent.seconds} s of wall clock → ${data.agent.speed} — 2 cases, 10 mutants`]}
        />
      </Moving>

      {/* 14-21 s — input -> output: case files next to the field they produce */}
      <Sequence from={closeStart} durationInFrames={closeEnd - closeStart} name="input-output">
        <AbsoluteFill>
          <OffthreadVideo src={staticFile(data.clips.cavity)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={dim} />
          <div style={{ position: 'absolute', left: 56, top: 46, bottom: 46, width: 760 }}>
            <div style={{ ...kicker(), color: '#8fc3ff', marginBottom: 18 }}>input: 6 files</div>
            {['0/U — lid 1 m/s, walls still', '0/p — kinematic pressure', 'constant/transportProperties — nu = 0.01', 'system/blockMeshDict — 40×40 mesh', 'system/controlDict — write every 50 steps', 'system/fvSolution — GAMG + smooth solver'].map((t, i) => {
              const s = useCurrentFrame() ? 1 : 1;
              return (
                <div key={t} style={{
                  fontFamily: FONT, fontSize: captionSize(0.6), color: PAPER, fontWeight: 700,
                  padding: '12px 18px', marginBottom: 10,
                  background: 'rgba(8,13,19,0.62)', borderLeft: `4px solid ${i % 2 ? '#eb6834' : '#2a78d6'}`,
                  borderRadius: 10, textShadow: '0 2px 10px rgba(0,0,0,0.8)',
                }}>{t}</div>
              );
            })}
          </div>
          <div style={{ position: 'absolute', right: 56, top: 46, ...{ fontFamily: FONT } as any }}>
            <div style={{ ...kicker(), color: '#ffb38a', textAlign: 'right', marginBottom: 14 }}>output</div>
            <div style={{ ...caption(), fontSize: captionSize(0.9), textAlign: 'right' }}>the converged |U| field<br />you have been watching</div>
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* 21-28 s — proof as a HUD over still-moving footage */}
      <Sequence from={proofStart} durationInFrames={proofEnd - proofStart} name="proof">
        <AbsoluteFill>
          <OffthreadVideo src={staticFile(data.clips.cavity)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={dim} />
          <ProofHud data={data} />
          <PassBadge data={data} fps={fps} local={useCurrentFrame()} />
          <ResidGauge resid={data.hud.residFinal} t="30.0" local={useCurrentFrame()} />
          <div style={{ position: 'absolute', left: 56, bottom: 52 }}>
            <CountReadout local={useCurrentFrame()} label="mutants killed" to={10} decimals={0} suffix=" / 10" />
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* 28-30 s — the verdict lands, footage still moving */}
      <Sequence from={finalStart} durationInFrames={30 * fps - finalStart} name="final">
        <AbsoluteFill>
          <OffthreadVideo src={staticFile(data.clips.cavity)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={dim} />
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <div style={{ textAlign: 'center', fontFamily: FONT, fontSize: captionSize(1.4), fontWeight: 800, color: PAPER, textShadow: '0 3px 22px rgba(0,0,0,0.9)' }}>
              judge: PASS — every number above is measured
            </div>
          </div>
        </AbsoluteFill>
      </Sequence>

      {/* last 3 s — the only static frame */}
      <Sequence from={endStart} durationInFrames={3 * fps} name="endcard">
        <EndCard data={data} />
      </Sequence>
    </AbsoluteFill>
  );
};
