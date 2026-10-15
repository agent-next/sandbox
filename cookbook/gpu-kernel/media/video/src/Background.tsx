import React from "react";
import { AbsoluteFill } from "remotion";
import { BG } from "./theme";

/** Static dark gradient + faint grid behind the panels. Rendered once and
 * composited per frame — every scene keeps the frame alive with its own
 * moving content, so the backdrop never needs to re-raster. */
export const Background: React.FC<{ opacity?: number }> = ({
  opacity = 1,
}) => (
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
  </AbsoluteFill>
);
