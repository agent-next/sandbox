import React from "react";
import { useCurrentFrame } from "remotion";
import { ease } from "./theme";

/** A number that counts up from `from` to `to` over `dur` frames. */
export const CountUp: React.FC<{
  from?: number;
  to: number;
  start: number;
  dur: number;
  digits?: number;
  prefix?: string;
  suffix?: string;
  style?: React.CSSProperties;
}> = ({ from = 0, to, start, dur, digits = 0, prefix = "", suffix = "", style }) => {
  const frame = useCurrentFrame();
  const t = ease(frame, start, dur);
  const value = from + (to - from) * t;
  return (
    <span style={style}>
      {prefix}
      {value.toFixed(digits)}
      {suffix}
    </span>
  );
};

/** A number that spins fast then settles (odometer feel) — used for the
 * headline "x speed" so the eye sees motion, ending on the real value. */
export const SpinUp: React.FC<{
  to: number;
  start: number;
  dur: number;
  digits?: number;
  style?: React.CSSProperties;
}> = ({ to, start, dur, digits = 2, style }) => {
  const frame = useCurrentFrame();
  const t = ease(frame, start, dur);
  const value = to * (1 - Math.pow(1 - t, 3));
  return (
    <span style={style}>
      x{value.toFixed(digits)}
    </span>
  );
};
