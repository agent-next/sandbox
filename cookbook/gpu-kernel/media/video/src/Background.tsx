import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { BG } from "./theme";

/** Static dark gradient + faint grid behind the panels, with slow vertical
 * scanlines drifting over it. Rendered once and composited per frame — every
 * scene keeps the frame alive with its own moving content on top, and the
 * drifting scanlines mean even a momentarily-still scene still changes. */
export const Background: React.FC<{ opacity?: number }> = ({
  opacity = 1,
}) => {
  const frame = useCurrentFrame();
  const drift = (frame * 2) % 90;
  return (
    <AbsoluteFill style={{ background: BG }}>
      <AbsoluteFill
        style={{
          opacity: 0.55 * opacity,
          background: "radial-gradient(1200px 900px at 50% 40%, #16233a 0%, #0d1117 60%)",
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.14 * opacity,
          backgroundImage:
            "linear-gradient(#1f6feb 1px, transparent 1px), linear-gradient(90deg, #1f6feb 1px, transparent 1px)",
          backgroundSize: "64px 64px",
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.05 * opacity,
          backgroundImage:
            "repeating-linear-gradient(180deg, transparent 0px, transparent 4px, #58a6ff 5px, transparent 6px)",
          transform: `translateY(${drift}px)`,
        }}
      />
    </AbsoluteFill>
  );
};
