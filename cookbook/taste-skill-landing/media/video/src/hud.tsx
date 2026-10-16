import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";

// Brand tokens (the site's own brief.md, fixed):
export const PAPER = "#F4F1EA";   // ground
export const INK = "#1A241F";     // deep pine ink
export const ACCENT = "#0E6E54";  // viridian accent (action + one thing only)

export const FONT_SANS = "'Public Sans', 'DejaVu Sans', sans-serif";
export const FONT_SERIF = "'Fraunces', 'DejaVu Serif', serif";

/** Caption cap height >= 4% of frame height (DEMO-STANDARD): 1080 * 0.04 = 43px
 *  font-size; our smallest burned-in caption uses 44px. */
export const CAPTION_MIN = 44;

export const ease = (t: number) =>
  t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;

/** A stat tile: label + a number that counts up (skill: Sans semibold value,
 *  sentence-case label, tabular figures while counting). */
export const Counter: React.FC<{
  from: number; to: number; dur: number; label: string; suffix?: string;
  x: number; y: number; delay?: number; dark?: boolean;
}> = ({ from, to, dur, label, suffix = "", x, y, delay = 0, dark = false }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = Math.max(0, frame - delay);
  const k = Math.min(1, local / (dur * fps));
  const value = Math.round(from + (to - from) * ease(k));
  const pop = spring({ frame: local, fps, config: { damping: 12 } });
  return (
    <div style={{
      position: "absolute", left: x, top: y,
      opacity: Math.min(1, pop * 1.4),
      transform: `translateY(${(1 - Math.min(1, pop)) * 18}px)`,
      fontFamily: FONT_SANS, color: dark ? PAPER : INK,
      textAlign: "left",
    }}>
      <div style={{
        fontSize: 64, fontWeight: 600, lineHeight: 1,
        fontVariantNumeric: "tabular-nums",
      }}>{value}{suffix}</div>
      <div style={{
        fontSize: 24, marginTop: 8, opacity: 0.82,
        maxWidth: 360, lineHeight: 1.3,
      }}>{label}</div>
    </div>
  );
};

/** A small pill caption riding the footage. */
export const Chip: React.FC<{
  text: string; x: number; y: number; delay?: number;
  filled?: boolean; fontSize?: number;
}> = ({ text, x, y, delay = 0, filled = false, fontSize = 26 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = Math.max(0, frame - delay);
  const s = spring({ frame: local, fps, config: { damping: 14 } });
  return (
    <div style={{
      position: "absolute", left: x, top: y,
      fontFamily: FONT_SANS, fontSize, fontWeight: 500,
      padding: `${Math.round(fontSize * 0.4)}px ${Math.round(fontSize * 0.75)}px`,
      borderRadius: fontSize,
      color: filled ? PAPER : INK,
      background: filled ? INK : "rgba(244,241,234,0.88)",
      opacity: Math.min(1, s * 1.5),
      transform: `scale(${0.7 + 0.3 * Math.min(1, s)})`,
      whiteSpace: "nowrap",
    }}>{text}</div>
  );
};

/** The kinetic headline caption: words slide up in sequence. */
export const KineticHeadline: React.FC<{
  words: string[]; x: number; y: number; size?: number;
  delay?: number; dark?: boolean; wordGap?: number;
}> = ({ words, x, y, size = 72, delay = 0, dark = false,
        wordGap = 0.28 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = Math.max(0, frame - delay);
  // gap in em, so the spacing scales with the size
  const gap = `${wordGap}em`;
  return (
    <div style={{ position: "absolute", left: x, top: y, display: "flex",
                  flexWrap: "wrap", columnGap: gap, rowGap: 0 }}>
      {words.map((w, i) => {
        const t = Math.max(0, local - i * 5);
        const s = spring({ frame: t, fps, config: { damping: 13, mass: 0.7 } });
        return (
          <div key={i} style={{
            fontFamily: FONT_SERIF, fontSize: size, fontWeight: 600,
            color: dark ? PAPER : INK, lineHeight: 1.05,
            opacity: Math.min(1, s * 1.3),
            transform: `translateY(${(1 - Math.min(1, s)) * 46}px)`,
            textShadow: dark ? "none" : "0 2px 24px rgba(244,241,234,0.92)",
          }}>{w}</div>
        );
      })}
    </div>
  );
};

/** One gate row of the proof HUD: slides in from the left, names its rule. */
export const GateRow: React.FC<{
  name: string; detail: string; passed: boolean;
  y: number; delay?: number; width?: number;
}> = ({ name, detail, passed, y, delay = 0, width = 880 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = Math.max(0, frame - delay);
  const s = spring({ frame: local, fps, config: { damping: 15 } });
  const vx = -width + (width + 40) * Math.min(1, s);
  return (
    <div style={{
      position: "absolute", left: 72, top: y,
      transform: `translateX(${vx}px)`,
      display: "flex", alignItems: "center", gap: 18,
      fontFamily: FONT_SANS,
      background: "rgba(244,241,234,0.93)",
      borderRadius: 10, padding: "14px 22px",
      width, boxSizing: "border-box",
      opacity: Math.min(1, s * 2),
    }}>
      <div style={{
        width: 20, height: 20, borderRadius: 4, flexShrink: 0,
        background: passed ? ACCENT : "#B3422E",
      }}/>
      <div style={{ fontSize: 27, fontWeight: 600, color: INK,
                    width: 300, flexShrink: 0 }}>{name}</div>
      <div style={{ fontSize: 21, color: "rgba(26,36,31,0.72)",
                    overflow: "hidden", whiteSpace: "nowrap",
                    textOverflow: "ellipsis" }}>{detail}</div>
    </div>
  );
};

/** The PASS badge that stamps in at the end of the proof. The count comes
 *  from the seed-42 verdict (facts.ts), never a literal. */
export const PassBadge: React.FC<{
  x: number; y: number; delay?: number; text?: string;
}> = ({ x, y, delay = 0, text = "PASS" }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = Math.max(0, frame - delay);
  const s = spring({ frame: local, fps,
                     config: { damping: 9, mass: 0.9, stiffness: 120 } });
  const scale = 1.9 - 0.9 * Math.min(1, s);
  return (
    <div style={{
      position: "absolute", left: x, top: y,
      transform: `scale(${scale}) rotate(${(1 - Math.min(1, s)) * -8}deg)`,
      opacity: Math.min(1, s * 2),
      fontFamily: FONT_SANS, fontWeight: 700, fontSize: 56,
      letterSpacing: 2, color: PAPER, background: ACCENT,
      padding: "20px 54px", borderRadius: 14,
      boxShadow: "0 12px 40px rgba(14,110,84,0.35)",
    }}>{text}</div>
  );
};
