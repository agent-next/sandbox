import {spring, useCurrentFrame, useVideoConfig} from 'remotion';
import type {Gate} from './props';
import {FONT} from './fonts';

// Colour-blind-safe palette: teal = pass, orange = fail.
const TEAL = '#2EC4B6';
const ORANGE = '#F58518';

const Check: React.FC<{color: string; size: number}> = ({color, size}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path
      d="M4 12.5 9.5 18 20 6.5"
      stroke={color}
      strokeWidth={3.4}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

const Cross: React.FC<{color: string; size: number}> = ({color, size}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path
      d="M6 6l12 12M18 6L6 18"
      stroke={color}
      strokeWidth={3.4}
      strokeLinecap="round"
    />
  </svg>
);

const GateRow: React.FC<{gate: Gate; index: number; pass: boolean}> = ({
  gate,
  index,
  pass,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p = spring({
    frame: Math.max(0, frame - 12 - index * 4),
    fps,
    config: {damping: 20, stiffness: 200},
  });
  const color = pass ? TEAL : ORANGE;
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '12px 0',
        borderTop: '1px solid rgba(255,255,255,0.12)',
        transform: `translateX(${(1 - p) * 70}px)`,
        opacity: p,
      }}
    >
      {pass ? <Check color={color} size={30} /> : <Cross color={color} size={30} />}
      <div style={{flex: 1}}>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 32,
            fontWeight: 600,
            color: 'white',
          }}
        >
          {gate.name}
        </div>
        <div
          style={{
            fontFamily: FONT,
            fontSize: 24,
            color: 'rgba(255,255,255,0.6)',
          }}
        >
          gate {gate.threshold}
        </div>
      </div>
      <div
        style={{
          fontFamily: FONT,
          fontSize: 32,
          fontWeight: 700,
          color,
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {gate.measured}
      </div>
    </div>
  );
};

// PASS/FAIL badge + gate rows sliding in over the still-playing final clip.
export const Proof: React.FC<{verdict: {pass: boolean; gates: Gate[]}}> = ({
  verdict,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const color = verdict.pass ? TEAL : ORANGE;
  const badge = spring({
    frame,
    fps,
    config: {damping: 11, stiffness: 170},
  });
  return (
    <div
      style={{
        position: 'absolute',
        top: 100,
        right: 48,
        width: 460,
        padding: '30px 34px',
        borderRadius: 22,
        background: 'rgba(6,10,18,0.62)',
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        border: `2px solid ${color}`,
        boxShadow: `0 24px 70px rgba(0,0,0,0.55), 0 0 44px ${color}33`,
      }}
    >
      <div style={{display: 'flex', alignItems: 'center', gap: 22}}>
        <div
          style={{
            width: 104,
            height: 104,
            borderRadius: '50%',
            background: `radial-gradient(circle at 32% 30%, ${color}, ${color}88)`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            transform: `scale(${badge})`,
            boxShadow: `0 0 30px ${color}66`,
          }}
        >
          {verdict.pass ? (
            <Check color="#04110e" size={56} />
          ) : (
            <Cross color="#1a0d02" size={56} />
          )}
        </div>
        <div>
          <div
            style={{
              fontFamily: FONT,
              fontSize: 62,
              fontWeight: 700,
              color,
              letterSpacing: 3,
              lineHeight: 1,
            }}
          >
            {verdict.pass ? 'PASS' : 'FAIL'}
          </div>
          <div
            style={{
              fontFamily: FONT,
              fontSize: 24,
              fontWeight: 600,
              letterSpacing: 4,
              color: 'rgba(255,255,255,0.55)',
              marginTop: 8,
              textTransform: 'uppercase',
            }}
          >
            judge verdict
          </div>
        </div>
      </div>
      <div style={{marginTop: 22}}>
        {verdict.gates.map((gate, i) => (
          <GateRow key={i} gate={gate} index={i} pass={verdict.pass} />
        ))}
      </div>
    </div>
  );
};
