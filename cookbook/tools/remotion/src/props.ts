// Prop shape + timeline math for the `Demo` composition.
// The constants below are mirrored in ../validate_props.py — keep in sync.

export const FPS = 30;
export const TRANSITION_FRAMES = 6; // 0.2 s wipe between shots
export const END_CARD_S = 2.5;
export const MODEL_SHOT_S = 6;
export const PROOF_S = 4.5; // verdict overlay window at the tail of the last shot

export type HudEntry = {
  label: string;
  value: number | string;
  unit?: string;
};

export type Shot = {
  clip: string;
  start?: number; // seconds into the clip to begin at
  duration: number; // on-screen seconds
  speed?: number; // playback rate; > 1 draws a "Nx speed" chip
  hud?: HudEntry[];
  // Injected by stage_props.py (ffprobe): source length in seconds,
  // used to loop short clips under speed > 1.
  _srcSeconds?: number;
};

export type Gate = {
  name: string;
  measured: number | string;
  threshold: number | string;
};

export type DemoProps = {
  shots: Shot[];
  model3d?: {glb: string};
  verdict: {pass: boolean; gates: Gate[]};
  headline: string;
  launch: {command: string; ask_agent: string};
};

export type TimelineItem =
  | {kind: 'shot'; shot: Shot}
  | {kind: 'model'};

// The 3D turntable becomes the second shot (index 1), right after the hook.
export const buildItems = (props: DemoProps): TimelineItem[] => {
  const items: TimelineItem[] = props.shots.map((shot) => ({
    kind: 'shot' as const,
    shot,
  }));
  if (props.model3d) {
    items.splice(Math.min(1, items.length), 0, {kind: 'model'});
  }
  return items;
};

export const itemFrames = (item: TimelineItem, fps: number): number =>
  item.kind === 'model'
    ? Math.round(MODEL_SHOT_S * fps)
    : Math.max(1, Math.round(item.shot.duration * fps));

export const mainFrames = (props: DemoProps, fps: number): number => {
  const items = buildItems(props);
  const sum = items.reduce((acc, it) => acc + itemFrames(it, fps), 0);
  return sum - (items.length - 1) * TRANSITION_FRAMES;
};

export const totalFrames = (props: DemoProps, fps: number): number =>
  mainFrames(props, fps) + Math.round(END_CARD_S * fps);
