// Root.tsx — Remotion composition registry for the cfd-openfoam demo video.
// 1920x1080 @ 30 fps, 35 s (1050 frames): 32.5 s of moving footage + a 2.5 s
// static end card. All values come from --props=data.json, written by
// media/make_media.sh from THIS run's judge output — nothing invented.
import React from 'react';
import { Composition } from 'remotion';
import type { DemoData } from './lib/types';
import { Demo } from './Demo';

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const VIDEO_S = 25;
export const ENDCARD_S = 2.5;
export const TOTAL_S = VIDEO_S + ENDCARD_S;

// Fallback props so `remotion still`/bundling never hangs; the real render
// always passes --props=../clips/data.json written from judge output.
export const defaultData: DemoData = {
  clips: {
    hook: 'hook.mp4',
    develop: 'develop.mp4',
    closeup: 'closeup.mp4',
    agent: 'agent.mp4',
    proof: 'proof.mp4',
    verdict: 'verdict.mp4',
    endcardStill: 'endcard_still.jpg',
  },
  hud: {
    residFinal: '7.6e-7',
    cellCount: '1600',
    l2: '0.0043',
    orders: '2.15 / 1.91',
    ghiaU: '0.0033',
    ghiaV: '0.0073',
    kills: '10/10',
    continuity: '2.1e-11',
    tEnd: '30',
  },
  agent: { wallSeconds: 750, speed: '107x' },
  verdict: {
    pass: true,
    gates: [
      { name: 'Mesh quality', ok: true },
      { name: 'Solver convergence', ok: true },
      { name: 'Poiseuille accuracy', ok: true },
      { name: 'Mesh convergence', ok: true },
      { name: 'Cavity vs Ghia 1982', ok: true },
    ],
  },
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Compositions"
      component={Demo}
      durationInFrames={Math.round(TOTAL_S * FPS)}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
      defaultProps={defaultData}
    />
  );
};
