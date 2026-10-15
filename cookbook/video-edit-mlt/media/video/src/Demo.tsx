import React from 'react';
import {
  AbsoluteFill,
  interpolate,
  Loop,
  OffthreadVideo,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
} from 'remotion';

// Every number comes from props.json, written by make_media.py from the judge's own output.
export type Props = {
  decoded: ([number, number] | null)[];
  weights: number[];
  musicInside: number[];
  musicOutside: number[];
  ducking: number;
  dissolve: number;
  lufs: number;
  peak: number;
  edl: number;
  frames: number;
  gates: {name: string; value: string}[];
  mutants: {name: string; gate: string}[];
  bad: {decoded: ([number, number] | null)[]; first: number; edl: number};
};

const FPS = 30;
const SRC_FPS = 25;
const INK = '#f4f1e8';
const GREEN = '#52d9b0';
const RED = '#ff6b4a';
const FONT = 'DejaVu Sans, sans-serif';
const CLIP = 'ABC';

// Scene starts, in frames.
const S = {hook: 0, io: 90, dissolve: 300, pixels: 450, audio: 600, reject: 720, proof: 900, end: 1050};
export const DURATION = 1125;

const srcIndex = (startSec: number, frame: number) =>
  Math.min(224, Math.floor((startSec + frame / FPS) * SRC_FPS));
const label = (code: [number, number] | null | undefined, i: number, weights: number[]) =>
  code ? `${CLIP[code[0]]}:${String(code[1]).padStart(3, '0')}` : `A+B ${weights[i - 100]?.toFixed(2) ?? ''}`;

const Text: React.FC<{size?: number; color?: string; bold?: boolean; style?: React.CSSProperties; children: React.ReactNode}> = ({
  size = 64, color = INK, bold = false, style, children,
}) => (
  <div style={{fontFamily: FONT, fontSize: size, color, fontWeight: bold ? 700 : 400, lineHeight: 1.15,
    textShadow: '0 3px 12px rgba(0,0,0,0.85)', ...style}}>{children}</div>
);

const Pill: React.FC<{color: string; children: React.ReactNode; style?: React.CSSProperties}> = ({color, children, style}) => (
  <div style={{background: color, borderRadius: 18, padding: '18px 34px', display: 'inline-block', ...style}}>{children}</div>
);

// Kinetic headline: each word springs up in turn.
const Headline: React.FC<{text: string; size?: number; delay?: number; color?: string}> = ({text, size = 84, delay = 0, color = INK}) => {
  const f = useCurrentFrame();
  return (
    <div style={{display: 'flex', flexWrap: 'wrap', gap: '0 24px'}}>
      {text.split(' ').map((w, i) => {
        const s = spring({frame: f - delay - i * 3, fps: FPS, config: {damping: 14}});
        return <Text key={i} size={size} bold color={color}
          style={{transform: `translateY(${(1 - s) * 60}px)`, opacity: s}}>{w}</Text>;
      })}
    </div>
  );
};

const Video: React.FC<{src: string; startSec: number; style?: React.CSSProperties}> = ({src, startSec, style}) => (
  <OffthreadVideo src={staticFile(src)} startFrom={Math.round(startSec * FPS)} muted
    style={{width: '100%', height: '100%', objectFit: 'cover', ...style}} />
);

const Counter: React.FC<{to: number; decimals?: number; frames?: number; suffix?: string}> = ({to, decimals = 0, frames = 30, suffix = ''}) => {
  const f = useCurrentFrame();
  const v = interpolate(f, [0, frames], [0, to], {extrapolateRight: 'clamp'});
  return <>{v.toFixed(decimals)}{suffix}</>;
};

const Hook: React.FC<Props> = (p) => {
  const f = useCurrentFrame();
  const badge = spring({frame: f - 8, fps: FPS, config: {damping: 12}});
  const i = srcIndex(0, f);
  return (
    <AbsoluteFill>
      <Video src="render.mp4" startSec={0} />
      <AbsoluteFill style={{padding: 60, background: 'linear-gradient(180deg, rgba(16,24,39,0.85) 0%, rgba(16,24,39,0) 40%)'}}>
        <Headline text="AN AI AGENT EDITED THIS VIDEO" />
        <Text size={60} style={{marginTop: 12}}>and a checker verified every frame</Text>
      </AbsoluteFill>
      <div style={{position: 'absolute', right: 70, bottom: 70, transform: `scale(${badge})`}}>
        <Pill color="#0b6e4f"><Text size={72} bold>PASS {p.frames}/{p.frames}</Text></Pill>
      </div>
      <div style={{position: 'absolute', left: 70, bottom: 80}}>
        <Pill color="rgba(16,24,39,0.85)"><Text size={64} bold color={GREEN}>FRAME {String(i).padStart(3, '0')} = {label(p.decoded[i], i, p.weights)}</Text></Pill>
      </div>
    </AbsoluteFill>
  );
};

const InputOutput: React.FC<Props> = (p) => {
  const f = useCurrentFrame();
  const i = srcIndex(0, f);
  const active = i < 100 ? 0 : i < 125 ? -1 : i < 200 ? 1 : 2;
  const steps = ['A', 'DISSOLVE', 'B', 'C'];
  const step = active === -1 ? 1 : active === 0 ? 0 : active + 1;
  return (
    <AbsoluteFill style={{background: '#101827', padding: 50}}>
      <Text size={64} bold>3 source clips in</Text>
      <div style={{display: 'flex', gap: 30, marginTop: 20}}>
        {['a', 'b', 'c'].map((n, k) => (
          <div key={n} style={{width: 590, height: 332, position: 'relative', borderRadius: 12, overflow: 'hidden',
            outline: k === active ? `8px solid ${GREEN}` : 'none'}}>
            <Video src={`clip_${n}.mp4`} startSec={0} />
            <Text size={64} bold style={{position: 'absolute', left: 20, top: 10}}>{n.toUpperCase()}</Text>
          </div>
        ))}
      </div>
      <div style={{display: 'flex', gap: 40, marginTop: 40, alignItems: 'flex-start'}}>
        <div style={{width: 960, height: 540, borderRadius: 12, overflow: 'hidden', flexShrink: 0}}>
          <Video src="render.mp4" startSec={0} />
        </div>
        <div>
          <Text size={64} bold>1 timeline out</Text>
          {steps.map((s, k) => (
            <Text key={s} size={72} bold color={k === step ? GREEN : '#5b667a'} style={{marginTop: 18}}>
              {k === step ? '> ' : '  '}{s}
            </Text>
          ))}
          <Text size={60} color={GREEN} style={{marginTop: 24}}>frame {String(i).padStart(3, '0')}</Text>
        </div>
      </div>
    </AbsoluteFill>
  );
};

const Dissolve: React.FC<Props> = (p) => {
  const f = useCurrentFrame();
  const local = f % 75;
  const i = srcIndex(3.5, local);
  const w = i >= 100 && i <= 124 ? p.weights[i - 100] : i < 100 ? 0 : 1;
  return (
    <AbsoluteFill>
      <Loop durationInFrames={75}><Video src="render.mp4" startSec={3.5} /></Loop>
      <AbsoluteFill style={{padding: 60}}>
        <Pill color="rgba(16,24,39,0.85)">
          <Headline text="25 FRAMES. ONE DISSOLVE." size={80} />
          <Text size={60} color={GREEN} style={{marginTop: 8}}>frame {i} / clip B weight {w.toFixed(3)}</Text>
        </Pill>
      </AbsoluteFill>
      <div style={{position: 'absolute', left: 60, right: 60, bottom: 70, height: 60, background: 'rgba(16,24,39,0.85)', borderRadius: 30}}>
        <div style={{width: `${w * 100}%`, height: '100%', background: GREEN, borderRadius: 30}} />
      </div>
    </AbsoluteFill>
  );
};

const Pixels: React.FC<Props> = (p) => {
  const f = useCurrentFrame();
  const i = srcIndex(5.4, f);
  return (
    <AbsoluteFill style={{background: '#101827'}}>
      <div style={{position: 'absolute', top: 330, left: 0, width: 1920, height: 750}}>
        <Video src="render.mp4" startSec={5.4} />
      </div>
      {/* The judge decodes rows 8-48 of each 720p frame: show that band stretched 2.5x. */}
      <div style={{position: 'absolute', top: 160, left: 0, width: 1920, height: 160, overflow: 'hidden', borderTop: `4px solid ${GREEN}`, borderBottom: `4px solid ${GREEN}`}}>
        <div style={{position: 'absolute', top: -30, left: 0, width: 1920, height: 1080, transform: 'scaleY(2.5)', transformOrigin: 'top'}}>
          <Video src="render.mp4" startSec={5.4} />
        </div>
      </div>
      <AbsoluteFill style={{padding: '30px 60px'}}>
        <Headline text="THE CHECKER READS THE PIXELS." size={76} />
      </AbsoluteFill>
      <div style={{position: 'absolute', left: 60, bottom: 70}}>
        <Pill color="rgba(16,24,39,0.9)"><Text size={80} bold color={GREEN}>OUTPUT {String(i).padStart(3, '0')} = CLIP {label(p.decoded[i], i, p.weights)}</Text></Pill>
      </div>
    </AbsoluteFill>
  );
};

const Audio: React.FC<Props> = (p) => {
  const f = useCurrentFrame();
  const rms = (v: number[]) => Math.sqrt(v.reduce((a, x) => a + x * x, 0) / v.length);
  const base = rms(p.musicOutside);
  const grow = interpolate(f, [10, 50], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  // Live meter: each bar wobbles through its own measured windows.
  const outside = p.musicOutside[f % p.musicOutside.length] / base;
  const inside = p.musicInside[f % p.musicInside.length] / base;
  const bars: [string, number, string][] = [['NO VOICE', outside, '#56b4e9'], ['VOICE ON', inside, GREEN]];
  return (
    <AbsoluteFill>
      <Video src="render.mp4" startSec={0.6} style={{filter: 'brightness(0.45)'}} />
      <AbsoluteFill style={{padding: 60}}>
        <Headline text="MUSIC DOWN. VOICE THROUGH." size={80} />
        <Text size={60} style={{marginTop: 10}}>music level measured from the exported audio</Text>
        {bars.map(([name, v, c], k) => (
          <div key={name} style={{display: 'flex', alignItems: 'center', marginTop: k ? 30 : 80}}>
            <Text size={64} bold style={{width: 400}}>{name}</Text>
            <div style={{width: 1200 * v * grow, height: 110, background: c, borderRadius: 14}} />
          </div>
        ))}
        <Text size={80} bold color={GREEN} style={{marginTop: 60}}>
          music <Counter to={p.ducking} decimals={1} frames={45} /> dB quieter (needed 8)
        </Text>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const Reject: React.FC<Props> = (p) => {
  const f = useCurrentFrame();
  const startSec = Math.max(0, (p.bad.first - 12) / SRC_FPS);
  const local = f % 60;
  const i = srcIndex(startSec, local);
  const differ = JSON.stringify(p.decoded[i]) !== JSON.stringify(p.bad.decoded[i]);
  const flash = spring({frame: f - 20, fps: FPS, config: {damping: 10}});
  const sides: [string, string, string, ([number, number] | null)[]][] = [
    ['GOOD EDIT', GREEN, 'render.mp4', p.decoded],
    ['OFF-BY-ONE CUT', RED, 'bad.mp4', p.bad.decoded],
  ];
  return (
    <AbsoluteFill style={{background: '#101827', padding: 50}}>
      <Headline text="ONE FRAME OFF? REJECTED." size={80} />
      <div style={{display: 'flex', gap: 40, marginTop: 40}}>
        {sides.map(([name, color, src, decoded]) => (
          <div key={name} style={{width: 890}}>
            <div style={{height: 500, borderRadius: 12, overflow: 'hidden', outline: `10px solid ${color}`}}>
              <Loop durationInFrames={60} layout="none"><Video src={src} startSec={startSec} /></Loop>
            </div>
            <Text size={64} bold color={color} style={{marginTop: 28}}>{name}</Text>
            <Text size={72} bold style={{marginTop: 8}}>frame {i}: {label(decoded[i], i, p.weights)}</Text>
          </div>
        ))}
      </div>
      <div style={{position: 'absolute', left: 50, bottom: 50, transform: `scale(${flash})`, transformOrigin: 'left'}}>
        <Pill color={differ ? RED : '#7a2d1f'}>
          <Text size={64} bold>checker: {p.bad.edl} wrong frame{p.bad.edl === 1 ? '' : 's'} = FAIL</Text>
        </Pill>
      </div>
    </AbsoluteFill>
  );
};

const Proof: React.FC<Props> = (p) => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill>
      <Loop durationInFrames={150}><Video src="render.mp4" startSec={0} style={{filter: 'brightness(0.4)'}} /></Loop>
      <AbsoluteFill style={{padding: 60}}>
        <Headline text="PASS: EVERY GATE" size={84} color={GREEN} />
        <div style={{display: 'flex', gap: 60, marginTop: 20}}>
          <div style={{width: 1000}}>
            {p.gates.map((g, k) => {
              const s = spring({frame: f - 6 - k * 5, fps: FPS, config: {damping: 15}});
              return (
                <div key={g.name} style={{display: 'flex', transform: `translateX(${(1 - s) * -900}px)`, opacity: s, marginTop: 6}}>
                  <Text size={60} bold color={GREEN} style={{width: 110}}>OK</Text>
                  <Text size={60}>{g.name}: {g.value}</Text>
                </div>
              );
            })}
          </div>
          <div>
            <Text size={150} bold color={GREEN}><Counter to={p.frames} frames={40} /></Text>
            <Text size={60}>frames checked</Text>
            <Sequence from={40} layout="none">
              <Text size={150} bold color={RED} style={{marginTop: 40}}><Counter to={p.mutants.length} frames={30} />/{p.mutants.length}</Text>
              <Text size={60}>bad edits rejected</Text>
            </Sequence>
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

const EndCard: React.FC = () => (
  <AbsoluteFill style={{background: '#101827', padding: 100, justifyContent: 'center'}}>
    <Text size={88} bold>PREMIERE, OPEN SOURCE</Text>
    <Text size={70} color={GREEN} style={{marginTop: 20}}>Write the timeline. Prove the cut.</Text>
    <Text size={76} bold style={{marginTop: 120}}>python3 cookbook/video-edit-mlt/run.py</Text>
    <Text size={64} color="#b5becf" style={{marginTop: 60}}>Disposable sandbox. Independent judge.</Text>
  </AbsoluteFill>
);

export const Demo: React.FC<Props> = (p) => {
  const scenes: [number, number, React.FC<Props>][] = [
    [S.hook, S.io, Hook], [S.io, S.dissolve, InputOutput], [S.dissolve, S.pixels, Dissolve],
    [S.pixels, S.audio, Pixels], [S.audio, S.reject, Audio], [S.reject, S.proof, Reject], [S.proof, S.end, Proof],
  ];
  return (
    <AbsoluteFill style={{background: '#101827'}}>
      {scenes.map(([from, to, Scene]) => (
        <Sequence key={from} from={from} durationInFrames={to - from}><Scene {...p} /></Sequence>
      ))}
      <Sequence from={S.end}><EndCard /></Sequence>
    </AbsoluteFill>
  );
};
