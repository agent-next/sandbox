import React from 'react';
import {Composition} from 'remotion';
import {Demo, DURATION, Props} from './Demo';

export const Root: React.FC = () => (
  <Composition
    id="Demo"
    component={Demo}
    durationInFrames={DURATION}
    fps={30}
    width={1920}
    height={1080}
    defaultProps={{} as Props}
  />
);
