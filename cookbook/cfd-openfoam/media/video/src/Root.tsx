// Root.tsx — Remotion composition registry for the cfd-openfoam demo video.
// 1920x1080 @ 30 fps, 33 s (990 frames): 30 s of moving footage + a 3 s
// static end card. All input props come from data.json, which is written
// from this run's judge output by media/make_media.sh — nothing invented.
import { Composition } from 'remotion';
import type { DemoData } from './lib/types';
import { Demo } from './Demo';

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const ENDCARD_S = 3;
export const VIDEO_S = 30;

export const defaultData: DemoData = {
  video: { durationInFrames: 990, fps: 30, width: 1920, height: 1080 },
  clips: { hook: 'clips/hook.mp4', cavity: 'clips/cavity.mp4', agent: 'clips/agent.mp4' },
  hud: {
    residFinal: '3.2e-9',
    cellCount: 1600,
    l2: '0.0043',
    orders: '2.15 / 1.91',
    ghiaU: '0.0033',
    ghiaV: '0.0073',
    kills: '10/10',
  },
  agent: { seconds: 54, speed: '6x' },
  verdict: {
    pass: true,
    killPct: '100%',
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
    <>
      <Composition
        id="Compositions"
        component={Demo}
        durationInFrames={(VIDEO_S + ENDCARD_S) * FPS}
        fps={FPS}
        width={WIDTH}
        height={HEIGHT}
        defaultProps={defaultData}
      />
    </>
  );
};
