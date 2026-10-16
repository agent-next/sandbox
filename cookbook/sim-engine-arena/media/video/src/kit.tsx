// Visual primitives shared by every slot. All text sits on translucent
// panels over the moving footage - no frame is ever text-only.
import React from "react";
import {
  AbsoluteFill,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {FONT, INK, PAPER} from "./config";

export const Fade: React.FC<{
  children: React.ReactNode;
  /** frames the fade takes; 0 disables it */
  frames?: number;
  from?: number;
}> = ({children, frames = 9, from = 0}) => {
  const f = useCurrentFrame() - from;
  const opacity = interpolate(f, [0, frames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return <AbsoluteFill style={{opacity}}>{children}</AbsoluteFill>;
};

/**
 * Fades and slides its child in once, at frame `at`. It wraps a single
 * element and does not disturb the parent's layout: the child keeps its
 * own box (no AbsoluteFill) so stacked rows stay stacked.
 */
export const SlideIn: React.FC<{
  children: React.ReactNode;
  at: number;
  from?: "left" | "bottom";
  distance?: number;
  frames?: number;
}> = ({children, at, from = "bottom", distance = 60, frames = 12}) => {
  const f = useCurrentFrame() - at;
  const p = springAt(f, frames);
  const t = (1 - p) * distance;
  const offset = from === "left" ? `translateX(${-t}px)` : `translateY(${t}px)`;
  return (
    <div
      style={{
        opacity: p,
        transform: offset,
        transition: undefined,
      }}
    >
      {children}
    </div>
  );
};

function springAt(frame: number, frames: number): number {
  if (frame <= 0) return 0;
  if (frames <= 0) return 1;
  return interpolate(frame, [0, frames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

/** A translucent scrim that keeps caption contrast over any footage. */
export const Scrim: React.FC<{
  /** CSS inset box: "x y w h" in px */
  inset: [number, number, number, number];
  strength?: number;
  radius?: number;
}> = ({inset, strength = 0.62, radius = 18}) => (
  <div
    style={{
      position: "absolute",
      left: inset[0],
      top: inset[1],
      width: inset[2],
      height: inset[3],
      background: `rgba(11,18,32,${strength})`,
      borderRadius: radius,
      pointerEvents: "none",
    }}
  />
);

export const Cap: React.FC<{
  children: React.ReactNode;
  size?: number;
  color?: string;
  weight?: number;
  tracking?: number;
  style?: React.CSSProperties;
}> = ({children, size = FONT.cap, color = PAPER, weight = 600, tracking = 0, style}) => (
  <div
    style={{
      fontFamily: "'Inter', 'Helvetica Neue', Helvetica, Arial, sans-serif",
      fontSize: size,
      fontWeight: weight,
      letterSpacing: tracking,
      color,
      lineHeight: 1.08,
      textShadow: "0 2px 14px rgba(11,18,32,.65)",
      ...style,
    }}
  >
    {children}
  </div>
);

export const Mono: React.FC<{
  children: React.ReactNode;
  size?: number;
  color?: string;
  style?: React.CSSProperties;
}> = ({children, size = FONT.cap, color = PAPER, style}) => (
  <div
    style={{
      fontFamily: "'SF Mono', 'JetBrains Mono', 'Menlo', 'Consolas', monospace",
      fontSize: size,
      fontWeight: 600,
      color,
      lineHeight: 1.1,
      ...style,
    }}
  >
    {children}
  </div>
);

/** Counts from 0 to `to` across `frames`, formatted by `fmt`. */
export const useCount = (
  to: number,
  frames: number,
  delay = 0,
): string => {
  const f = useCurrentFrame() - delay;
  const {fps} = useVideoConfig();
  const p = interpolate(f, [0, frames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  void fps;
  return format(to * p);
};

export const format = (v: number, digits = 4): string =>
  v.toFixed(digits).replace(/\.?0+$/, "") || "0";

/** A row of the HUD: label left, value right, on a scrim. */
export const HUD: React.FC<{
  x: number;
  y: number;
  w: number;
  rows: Array<{label: string; value: string; color?: string}>;
  title?: string;
  at?: number;
}> = ({x, y, w, rows, title, at = 0}) => {
  const pad = 26;
  const rowH = 58;
  const h = pad * 2 + rows.length * rowH + (title ? 54 : 0);
  return (
    <div style={{position: "absolute", left: x, top: y, width: w}}>
      <Scrim inset={[0, 0, w, h]} strength={0.55} />
      <div style={{position: "absolute", left: pad, top: pad, right: pad}}>
        {title ? (
          <Cap size={FONT.cap} weight={700} tracking={2.5} style={{marginBottom: 14, opacity: .95}}>
            {title}
          </Cap>
        ) : null}
        {rows.map((r, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "baseline",
              height: rowH,
              fontFamily: "'SF Mono','JetBrains Mono','Menlo',monospace",
            }}
          >
            <span style={{fontSize: FONT.cap, color: "#cbd7ea", fontWeight: 500}}>
              {r.label}
            </span>
            <span
              style={{
                fontSize: FONT.cap,
                color: r.color ?? PAPER,
                fontWeight: 700,
                marginLeft: 18,
              }}
            >
              {r.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};

export const K = INK;
export const P = PAPER;
