import React from "react";
import {Composition} from "remotion";
import {Demo, durationInFrames, HEIGHT, WIDTH} from "./Demo";

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Demo"
    component={Demo}
    durationInFrames={durationInFrames}
    fps={30}
    width={WIDTH}
    height={HEIGHT}
  />
);
