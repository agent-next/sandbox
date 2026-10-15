import {interpolate, spring, useCurrentFrame, useVideoConfig} from 'remotion';
import {FONT} from './fonts';

const TEAL = '#2EC4B6';
const FADE = 10; // frames for the exit fade

// The headline as a kinetic caption: per-word spring entrance done by
// ~0.5 s, sitting bottom-left on a glass strip; fades out before proof.
export const Caption: React.FC<{text: string; untilFrame: number}> = ({
  text,
  untilFrame,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const out = interpolate(
    frame,
    [untilFrame - FADE, untilFrame],
    [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  const bar = spring({frame, fps, config: {damping: 18, stiffness: 200}});
  const words = text.split(' ');
  return (
    <div
      style={{
        position: 'absolute',
        left: 56,
        bottom: 56,
        maxWidth: 1150,
        display: 'flex',
        alignItems: 'stretch',
        gap: 24,
        opacity: out,
      }}
    >
      <div
        style={{
          width: 8,
          borderRadius: 4,
          background: TEAL,
          transform: `scaleY(${bar})`,
          transformOrigin: 'bottom',
        }}
      />
      <div
        style={{
          fontFamily: FONT,
          fontSize: 68,
          fontWeight: 700,
          lineHeight: 1.12,
          color: 'white',
          textShadow: '0 4px 30px rgba(0,0,0,0.75)',
          display: 'flex',
          flexWrap: 'wrap',
          columnGap: 18,
        }}
      >
        {words.map((word, i) => {
          const p = spring({
            frame: Math.max(0, frame - i),
            fps,
            config: {damping: 14, stiffness: 260},
          });
          return (
            <span
              key={i}
              style={{
                display: 'inline-block',
                transform: `translateY(${(1 - p) * 0.55}em)`,
                opacity: p,
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
    </div>
  );
};
