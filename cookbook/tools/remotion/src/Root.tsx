import {Composition} from 'remotion';
import {Demo} from './Demo';
import {DemoProps, FPS, totalFrames} from './props';
import './fonts';

const defaultProps: DemoProps = {
  headline: 'Demo headline',
  shots: [{clip: 'staged/shot0.mp4', duration: 5}],
  verdict: {pass: true, gates: [{name: 'gate', measured: 0, threshold: 0}]},
  launch: {command: 'python3 run.py', ask_agent: 'run the demo'},
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Demo"
      component={Demo}
      fps={FPS}
      width={1920}
      height={1080}
      durationInFrames={FPS}
      defaultProps={defaultProps}
      calculateMetadata={({props}) => ({
        durationInFrames: totalFrames(props as DemoProps, FPS),
      })}
    />
  );
};
