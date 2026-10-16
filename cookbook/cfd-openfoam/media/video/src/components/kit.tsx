// kit.tsx — small shared visual pieces for the HUD. Everything is drawn
// with CSS (React DOM), never with an image editor, so a text-only frame is
// impossible by construction: captions live on top of moving footage.
import React from 'react';
import { interpolate, spring, useCurrentFrame } from 'remotion';

export const INK = '#0b121a';
export const PAPER = '#f4f6f8';
export const BLUE = '#2a78d6';
export const ORANGE = '#eb6834';
export const GREEN = '#0ca30c';
export const RED = '#d03b3b';
export const AMBER = '#c9871a';

export const FONT =
  "'DejaVu Sans', 'Helvetica Neue', Arial, sans-serif";
export const MONO = "'DejaVu Sans Mono', 'Menlo', monospace";

/** caption readable on a phone: >= 4 % of frame height (DEMO-STANDARD). */
export function captionSize(scale = 1): number {
  return Math.round(56 * scale); // 56 px = 5.2 % of 1080
}

export function kicker(): React.CSSProperties {
  return {
    fontFamily: FONT,
    fontSize: captionSize(0.52),
    fontWeight: 700,
    letterSpacing: '0.22em',
    textTransform: 'uppercase',
    color: PAPER,
    textShadow: '0 2px 12px rgba(0,0,0,0.85)',
  };
}

export function caption(): React.CSSProperties {
  return {
    fontFamily: FONT,
    fontSize: captionSize(),
    fontWeight: 700,
    color: PAPER,
    textShadow: '0 2px 14px rgba(0,0,0,0.85)',
    lineHeight: 1.15,
  };
}

export function mono(): React.CSSProperties {
  return { fontFamily: MONO, color: PAPER, textShadow: '0 2px 10px rgba(0,0,0,0.85)' };
}

export const dim: React.CSSProperties = {
  position: 'absolute', inset: 0, background: 'linear-gradient(180deg, rgba(6,10,14,0.55) 0%, rgba(6,10,14,0.0) 32%, rgba(6,10,14,0.0) 62%, rgba(6,10,14,0.72) 100%)',
};

export const plate: React.CSSProperties = {
  background: 'rgba(8, 13, 19, 0.68)',
  backdropFilter: 'blur(6px)',
  border: '1px solid rgba(255,255,255,0.16)',
  borderRadius: 14,
  padding: '18px 26px',
};

/** Scale/translate in a spring from the sequence's first frame.
 *  Pure (no hooks) so it is safe inside .map() over fixed lists. */
export function pop(frame: number, delay = 0) {
  return spring({ frame: frame - delay, fps: 30, config: { damping: 24, stiffness: 120, mass: 0.7 } });
}

export function CountUp({
  to, decimals = 0, frame, delay = 0, duration = 28, prefix = '', suffix = '',
}: { to: number; decimals?: number; frame: number; delay?: number; duration?: number; prefix?: string; suffix?: string }) {
  const t = interpolate(frame, [delay, delay + duration], [0, to], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });
  return (
    <span>
      {prefix}
      {t.toFixed(decimals)}
      {suffix}
    </span>
  );
}

export function Chip({ label, value, tone = 'blue', delay = 0 }: { label: string; value: React.ReactNode; tone?: 'blue' | 'green' | 'orange' | 'red'; delay?: number }) {
  const frame = useCurrentFrame();
  const s = pop(frame, delay);
  const color = tone === 'green' ? GREEN : tone === 'orange' ? ORANGE : tone === 'red' ? RED : BLUE;
  return (
    <div style={{ ...plate, opacity: s, transform: `translateY(${26 * (1 - s)}px)`, display: 'inline-flex', flexDirection: 'column', gap: 4, minWidth: 250 }}>
      <div style={{ ...kicker(), color, fontSize: captionSize(0.44) }}>{label}</div>
      <div style={{ ...mono(), fontSize: captionSize(0.95), fontWeight: 700 }}>{value}</div>
    </div>
  );
}
