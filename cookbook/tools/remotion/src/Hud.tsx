import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {HudEntry} from './props';
import {FONT} from './fonts';

const TEAL = '#2EC4B6';

// Format the count-up at the same precision the props declared.
const fmt = (target: number | string, p: number): string => {
  const n = Number(target);
  if (!Number.isFinite(n)) {
    return String(target);
  }
  const decimals = String(target).includes('.')
    ? String(target).split('.')[1].length
    : 0;
  const v = n * Math.min(1, Math.max(0, p));
  return decimals ? v.toFixed(decimals) : String(Math.round(v));
};

const HudRow: React.FC<{entry: HudEntry; delay: number}> = ({
  entry,
  delay,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({
    frame: Math.max(0, frame - delay),
    fps,
    config: {damping: 26, stiffness: 110, mass: 1.2},
  });
  return (
    <div>
      <div
        style={{
          fontFamily: FONT,
          fontSize: 26,
          fontWeight: 600,
          letterSpacing: 4,
          textTransform: 'uppercase',
          color: 'rgba(255,255,255,0.62)',
          marginBottom: 4,
        }}
      >
        {entry.label}
      </div>
      <div style={{display: 'flex', alignItems: 'baseline', gap: 12}}>
        <span
          style={{
            fontFamily: FONT,
            fontSize: 92,
            fontWeight: 700,
            color: 'white',
            fontVariantNumeric: 'tabular-nums',
            lineHeight: 1,
          }}
        >
          {fmt(entry.value, p)}
        </span>
        {entry.unit ? (
          <span
            style={{
              fontFamily: FONT,
              fontSize: 36,
              fontWeight: 600,
              color: TEAL,
            }}
          >
            {entry.unit}
          </span>
        ) : null}
      </div>
    </div>
  );
};

// A glass panel of spring-driven count-up numbers over the footage.
export const HudPanel: React.FC<{hud: HudEntry[]}> = ({hud}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const entrance = spring({
    frame,
    fps,
    config: {damping: 22, stiffness: 160},
  });
  return (
    <div
      style={{
        position: 'absolute',
        right: 56,
        bottom: 56,
        padding: '28px 36px',
        borderRadius: 20,
        background: 'rgba(8,12,22,0.55)',
        backdropFilter: 'blur(14px)',
        WebkitBackdropFilter: 'blur(14px)',
        border: '1px solid rgba(255,255,255,0.16)',
        boxShadow: '0 18px 50px rgba(0,0,0,0.45)',
        transform: `translateY(${(1 - entrance) * 30}px)`,
        opacity: entrance,
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
      }}
    >
      {hud.map((entry, i) => (
        <HudRow key={i} entry={entry} delay={6 + i * 4} />
      ))}
    </div>
  );
};

// Animated "Nx speed" chip, top right.
export const SpeedChip: React.FC<{speed: number}> = ({speed}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const entrance = spring({
    frame,
    fps,
    config: {damping: 15, stiffness: 220},
  });
  const label = Number.isInteger(speed) ? speed : speed.toFixed(1);
  return (
    <div
      style={{
        position: 'absolute',
        top: 44,
        right: 48,
        transform: `scale(${entrance})`,
        transformOrigin: 'top right',
        opacity: entrance,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '14px 26px',
          borderRadius: 999,
          background: 'rgba(8,12,22,0.6)',
          backdropFilter: 'blur(10px)',
          WebkitBackdropFilter: 'blur(10px)',
          border: `2px solid ${TEAL}`,
          fontFamily: FONT,
          fontSize: 34,
          fontWeight: 700,
          letterSpacing: 2,
          color: 'white',
        }}
      >
        <span
          style={{
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: TEAL,
          }}
        />
        {label}&times; SPEED
      </div>
    </div>
  );
};
