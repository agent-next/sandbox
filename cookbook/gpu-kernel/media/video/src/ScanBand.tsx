import React from "react";
import { useCurrentFrame } from "remotion";

/** A translucent vertical band that sweeps across a region of the frame. It
 * is a HUD scan over the real data (the same gesture a scope/oscilloscope
 * trace makes), and it keeps every shot visibly alive while it is on screen. */
export const ScanBand: React.FC<{
  start: number;
  durationInFrames: number;
  left: number;
  width: number;
  top: number;
  height: number;
  color?: string;
  period?: number;
}> = ({ start, durationInFrames, left, width, top, height,
        color = "#58a6ff", period = 90 }) => {
  const frame = useCurrentFrame();
  const local = frame - start;
  if (local < 0 || local > durationInFrames) return null;
  const t = ((local % period) / period);
  const x = left - width * 0.6 + t * (width * 1.2);
  return (
    <div style={{ position: "absolute", left: x, top, height,
      width: width * 0.28, pointerEvents: "none",
      background: `linear-gradient(90deg, ${color}00, ${color}55, ${color}00)`,
      filter: "blur(2px)" }} />
  );
};
