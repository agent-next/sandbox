import {Fragment} from 'react';
import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import {TransitionSeries, linearTiming} from '@remotion/transitions';
import {wipe} from '@remotion/transitions/wipe';
import {
  DemoProps,
  PROOF_S,
  TRANSITION_FRAMES,
  buildItems,
  itemFrames,
  mainFrames,
} from './props';
import {VideoShot} from './VideoShot';
import {ModelShot} from './ModelShot';
import {EndCard} from './EndCard';
import {Caption} from './Caption';
import {FONT} from './fonts';

export const Demo: React.FC<DemoProps> = (props) => {
  const {fps, durationInFrames} = useVideoConfig();
  const items = buildItems(props);
  const main = mainFrames(props, fps);
  const endFrames = Math.max(1, durationInFrames - main);
  const lastItem = items[items.length - 1];
  const lastShot = lastItem.kind === 'shot' ? lastItem.shot : props.shots[props.shots.length - 1];
  const lastShotFrames =
    lastItem.kind === 'shot'
      ? itemFrames(lastItem, fps)
      : itemFrames({kind: 'shot', shot: lastShot}, fps);
  const proofStart = main - Math.round(PROOF_S * fps);

  return (
    <AbsoluteFill style={{backgroundColor: '#04060b', fontFamily: FONT}}>
      <TransitionSeries>
        {items.map((item, i) => (
          <Fragment key={i}>
            {i > 0 ? (
              <TransitionSeries.Transition
                presentation={wipe({direction: 'from-left'})}
                timing={linearTiming({durationInFrames: TRANSITION_FRAMES})}
              />
            ) : null}
            <TransitionSeries.Sequence
              durationInFrames={itemFrames(item, fps)}
            >
              {item.kind === 'model' ? (
                <ModelShot glb={props.model3d!.glb} />
              ) : (
                <VideoShot
                  shot={item.shot}
                  frames={itemFrames(item, fps)}
                  verdict={i === items.length - 1 ? props.verdict : undefined}
                />
              )}
            </TransitionSeries.Sequence>
          </Fragment>
        ))}
      </TransitionSeries>
      <Sequence from={main} durationInFrames={endFrames}>
        <EndCard
          lastShot={lastShot}
          lastShotFrames={lastShotFrames}
          launch={props.launch}
        />
      </Sequence>
      <Caption text={props.headline} untilFrame={proofStart} />
    </AbsoluteFill>
  );
};
