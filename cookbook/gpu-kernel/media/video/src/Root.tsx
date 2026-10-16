import React from "react";
import { Composition } from "remotion";
import { Main, MainProps } from "./Main";
import scene from "./data/scene.json";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;
export const SECONDS = 31;
export const FRAMES = SECONDS * FPS;

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Main"
    component={Main as React.FC<MainProps>}
    durationInFrames={FRAMES}
    fps={FPS}
    width={WIDTH}
    height={HEIGHT}
    defaultProps={{ scene: scene as unknown as MainProps["scene"] }}
  />
);
