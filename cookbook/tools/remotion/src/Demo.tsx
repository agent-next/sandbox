import {AbsoluteFill, Sequence, useVideoConfig} from 'remotion';
import {
  DemoProps,
  PROOF_S,
  buildItems,
  itemFrames,
  mainFrames,
} from './props';
import {VideoShot} from './VideoShot';
import {ModelShot} from './ModelShot';
import {EndCard} from './EndCard';
import {Caption} from './Caption';
import {FONT} from './fonts';

// Timeline: shots (plus the optional 3D turntable as the second item) join
// with hard cuts — the gate's scene-cut detector needs the joins to be real
// cuts (see props.ts) — then the static end card, then overlays.
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

  const starts: number[] = [];
  let cursor = 0;
  for (const item of items) {
    starts.push(cursor);
    cursor += itemFrames(item, fps);
  }

  return (
    <AbsoluteFill style={{backgroundColor: '#04060b', fontFamily: FONT}}>
      {items.map((item, i) => (
        <Sequence key={i} from={starts[i]} durationInFrames={itemFrames(item, fps)}>
          {item.kind === 'model' ? (
            <ModelShot glb={props.model3d!.glb} />
          ) : (
            <VideoShot
              shot={item.shot}
              frames={itemFrames(item, fps)}
              verdict={i === items.length - 1 ? props.verdict : undefined}
            />
          )}
        </Sequence>
      ))}
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
