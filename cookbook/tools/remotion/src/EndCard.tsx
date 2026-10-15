import {
  AbsoluteFill,
  Freeze,
  interpolate,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {Shot} from './props';
import {Footage} from './Footage';
import {FONT} from './fonts';

const TEAL = '#2EC4B6';

// Static end card: the dimmed last frame of the final clip behind the
// launch command and the "Ask your agent" prompt. Content settles in the
// first ~0.4 s; the rest of the card is perfectly still (the gate checks
// the final 2 s for motion).
export const EndCard: React.FC<{
  lastShot: Shot;
  lastShotFrames: number;
  launch: {command: string; ask_agent: string};
}> = ({lastShot, lastShotFrames, launch}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({frame, fps, config: {damping: 22, stiffness: 160}});
  const dim = interpolate(frame, [0, 12], [0.55, 0.32], {
    extrapolateRight: 'clamp',
  });
  return (
    <AbsoluteFill style={{backgroundColor: '#04060b'}}>
      <Freeze frame={Math.max(0, lastShotFrames - 1)}>
        <AbsoluteFill style={{filter: `brightness(${dim})`}}>
          <Footage shot={lastShot} frames={lastShotFrames} />
        </AbsoluteFill>
      </Freeze>
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse at 50% 42%, rgba(4,8,14,0.18) 0%, rgba(3,5,10,0.86) 78%)',
        }}
      />
      <AbsoluteFill
        style={{
          justifyContent: 'center',
          alignItems: 'center',
          opacity: p,
          transform: `translateY(${(1 - p) * 22}px)`,
        }}
      >
        <div
          style={{
            fontFamily: FONT,
            fontSize: 30,
            fontWeight: 600,
            letterSpacing: 6,
            textTransform: 'uppercase',
            color: TEAL,
            marginBottom: 26,
          }}
        >
          Launch it
        </div>
        <div
          style={{
            fontFamily: 'monospace',
            fontSize: 58,
            fontWeight: 700,
            color: 'white',
            padding: '24px 46px',
            borderRadius: 18,
            background: 'rgba(10,16,28,0.78)',
            border: '1px solid rgba(255,255,255,0.18)',
            boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
          }}
        >
          $ {launch.command}
        </div>
        <div
          style={{
            marginTop: 34,
            fontFamily: FONT,
            fontSize: 38,
            color: 'rgba(255,255,255,0.85)',
            maxWidth: 1300,
            textAlign: 'center',
            lineHeight: 1.35,
          }}
        >
          Ask your agent: {launch.ask_agent}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
