import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { FONT_SANS, springish } from "./theme";

/** A kinetic headline: word groups snap up into place with a staggered
 * spring, so the frame keeps moving even under a static sentence. */
export const KineticHeadline: React.FC<{
  words: string[];
  start: number;
  size?: number;
  color?: string;
  sub?: string;
}> = ({ words, start, size = 66, color, sub }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div>
      <div style={{ display: "flex", flexWrap: "wrap", columnGap: 22 }}>
        {words.map((w, i) => {
          const s = springish(frame, start + i * 3, fps);
          return (
            <span
              key={i}
              style={{
                display: "inline-block",
                fontFamily: FONT_SANS,
                fontSize: size,
                fontWeight: 800,
                letterSpacing: -1.5,
                color: color,
                transform: `translateY(${(1 - s) * 46}px) scale(${0.86 + 0.14 * s})`,
                opacity: s,
              }}
            >
              {w}
            </span>
          );
        })}
      </div>
      {sub ? (
        <div
          style={{
            fontFamily: FONT_SANS,
            fontSize: 28,
            color: "#8b949e",
            marginTop: 8,
            opacity: Math.min(1, Math.max(0, (frame - start - words.length * 3) / 8)),
          }}
        >
          {sub}
        </div>
      ) : null}
    </div>
  );
};
