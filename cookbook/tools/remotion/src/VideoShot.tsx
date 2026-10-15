import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import type {Gate, Shot} from './props';
import {PROOF_S} from './props';
import {Footage} from './Footage';
import {HudPanel, SpeedChip} from './Hud';
import {Proof} from './Proof';

// One shot of real footage plus its overlays: spring-counting HUD numbers,
// an "Nx speed" chip when sped up, and — on the last shot — the verdict
// panel sliding in over the still-playing clip.
export const VideoShot: React.FC<{
  shot: Shot;
  frames: number;
  verdict?: {pass: boolean; gates: Gate[]};
}> = ({shot, frames, verdict}) => {
  const {fps} = useVideoConfig();
  const proofStart = Math.round(frames - PROOF_S * fps);
  return (
    <AbsoluteFill style={{backgroundColor: '#000'}}>
      <Footage shot={shot} frames={frames} />
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(180deg, rgba(3,5,10,0.28) 0%, rgba(0,0,0,0) 22%, rgba(0,0,0,0) 72%, rgba(3,5,10,0.4) 100%)',
        }}
      />
      {shot.speed && shot.speed > 1 ? <SpeedChip speed={shot.speed} /> : null}
      {shot.hud ? <HudPanel hud={shot.hud} /> : null}
      {verdict ? (
        <Sequence from={proofStart}>
          <Proof verdict={verdict} />
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
};
