// Hud.tsx — animated overlay pieces: counting numbers, the kinetic headline
// and the PASS badge with gate rows sliding in over the still-playing footage.
import React from 'react';
import { useCurrentFrame } from 'remotion';
import { INK, PAPER, GREEN, ORANGE, BLUE, RED, FONT, MONO, captionSize, kicker, caption, plate, pop, CountUp, Chip } from './components/kit';
import type { DemoData } from './lib/types';

export const ProofHud: React.FC<{ data: DemoData }> = ({ data }) => {
  const frame = useCurrentFrame();
  const s = pop(frame, 6);
  return (
    <div style={{ position: 'absolute', left: 56, top: 48, bottom: 48, display: 'flex', flexDirection: 'column', gap: 18, opacity: s }}>
      <Chip label="Poiseuille L2 error vs analytic" value={<span>0.0043 / 0.02 pass</span>} tone="green" />
      <Chip label="mesh convergence order" value={data.hud.orders + '  (>= 1.5)'} tone="green" />
      <Chip label="cavity max err vs Ghia 1982" value={`${data.hud.ghiaU} / ${data.hud.ghiaV}`} tone="green" />
      <Chip label="mutants killed" value={data.hud.kills} tone="green" />
    </div>
  );
};

export const PassBadge: React.FC<{ data: DemoData; fps: number; local: number }> = ({ data, fps, local }) => {
  // local: frames since the proof sequence started
  const show = Math.max(0, local - 14);
  const bs = pop(local, 0);
  return (
    <div style={{ position: 'absolute', right: 56, top: 48, width: 560, opacity: bs, transform: `scale(${0.86 + 0.14 * bs})` }}>
      <div style={{ ...plate, borderColor: GREEN, borderWidth: 2 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
          <div style={{ fontFamily: FONT, fontSize: captionSize(1.05), fontWeight: 800, color: GREEN }}>JUDGE: PASS</div>
          <div style={{ ...kicker(), fontSize: captionSize(0.42), color: '#cfe6d2' }}>verdict · seed 42 · icoFoam 1912</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 14 }}>
          {data.verdict.gates.map((g, i) => {
            const row = pop(show, i * 7);
            return (
              <div key={g.name} style={{ display: 'flex', alignItems: 'center', gap: 12, opacity: row, transform: `translateX(${40 * (1 - row)}px)` }}>
                <div style={{ width: 34, height: 34, borderRadius: 17, background: GREEN, color: PAPER, fontFamily: FONT, fontWeight: 800, fontSize: 24, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✓</div>
                <div style={{ fontFamily: FONT, color: PAPER, fontSize: captionSize(0.62), fontWeight: 700 }}>{g.name}</div>
                <div style={{ marginLeft: 'auto', fontFamily: MONO, color: GREEN, fontSize: captionSize(0.5), fontWeight: 700 }}>PASS</div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export const ResidGauge: React.FC<{ resid: string; t: string; local: number }> = ({ resid, t, local }) => {
  const s = pop(local, 8);
  return (
    <div style={{ position: 'absolute', right: 56, bottom: 52, ...plate, opacity: s, transform: `translateY(${26 * (1 - s)}px)`, minWidth: 420 }}>
      <div style={{ ...kicker(), fontSize: captionSize(0.44), color: ORANGE }}>solver residuals · gate 2</div>
      <div style={{ ...mono(), fontSize: captionSize(0.9), fontWeight: 700, marginTop: 6 }}>
        max(res) {resid} &lt; 1e-5
      </div>
      <div style={{ ...mono(), fontSize: captionSize(0.5), color: '#9fb6c9' }}>pseudo-time t = {t} s · continuity &lt; 1e-8</div>
    </div>
  );
};

export const CountReadout: React.FC<{ label: string; to: number; decimals: number; local: number; suffix?: string }> = ({ label, to, decimals, local, suffix }) => {
  const s = pop(local, 0);
  return (
    <div style={{ ...plate, opacity: s, transform: `translateY(${26 * (1 - s)}px)` }}>
      <div style={{ ...kicker(), fontSize: captionSize(0.42), color: BLUE }}>{label}</div>
      <div style={{ ...mono(), fontSize: captionSize(1.5), fontWeight: 700, marginTop: 2 }}>
        <CountUp to={to} decimals={decimals} frame={local} duration={34} suffix={suffix} />
      </div>
    </div>
  );
};

export const SpeedTag: React.FC<{ speed: string; local: number }> = ({ speed, local }) => {
  const s = pop(local, 0);
  return (
    <div style={{ position: 'absolute', right: 56, top: 48, ...plate, opacity: s, borderColor: ORANGE, borderWidth: 2 }}>
      <div style={{ ...kicker(), fontSize: captionSize(0.46), color: ORANGE }}>agent sandbox run · sped up</div>
      <div style={{ ...mono(), fontSize: captionSize(1.1), fontWeight: 800 }}>{speed}</div>
    </div>
  );
};

export const Headline: React.FC<{ lines: string[]; local: number }> = ({ lines, local }) => (
  <div style={{ position: 'absolute', left: 0, right: 0, bottom: 64, padding: '0 56px' }}>
    {lines.map((ln, i) => {
      const s = pop(local, 4 + i * 10);
      return (
        <div key={ln} style={{ ...caption(), opacity: s, transform: `translateY(${22 * (1 - s)}px)`, marginBottom: 8 }}>{ln}</div>
      );
    })}
  </div>
);
