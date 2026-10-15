import {
  AbsoluteFill,
  Easing,
  Loop,
  OffthreadVideo,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {Shot} from './props';

// One clip scaled/cropped to fill the frame, with a subtle camera push
// (1.0 -> 1.06) on top of the moving footage. Clips that are too short
// for `duration * speed` are looped so the shot never freezes.
export const Footage: React.FC<{shot: Shot; frames: number}> = ({
  shot,
  frames,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const speed = shot.speed ?? 1;
  const start = Math.round((shot.start ?? 0) * fps);
  const push = interpolate(frame, [0, frames], [1.0, 1.06], {
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.quad),
  });

  const video = (
    <OffthreadVideo
      src={staticFile(shot.clip)}
      trimBefore={start}
      playbackRate={speed}
      muted
      style={{width: '100%', height: '100%', objectFit: 'cover'}}
    />
  );

  const available = shot._srcSeconds
    ? Math.floor(shot._srcSeconds * fps) - start
    : frames * speed;
  const needed = frames * speed;
  const loopFrames = Math.max(1, Math.floor(available / speed));

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <AbsoluteFill style={{scale: String(push)}}>
        {needed > available ? (
          <Loop durationInFrames={loopFrames}>{video}</Loop>
        ) : (
          video
        )}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
