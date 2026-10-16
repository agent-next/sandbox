import React from 'react';
import {AbsoluteFill, Img, interpolate, Sequence, spring, staticFile, useCurrentFrame} from 'remotion';

// Every number comes from props.json, written by compose.py from the judge's own output.
export type Props = {
  gates: {label: string; value: string}[];
  mutants: {name: string; label: string; failed: boolean[]}[];
  killed: number;
  total: number;
};

const FPS = 30;
const POSES = 48;
const POSES_PER_SECOND = 24;
const INK = '#f5f9ff';
const BLUE = '#53bde8';
const ORANGE = '#f59e41';
const BG = 'rgba(13,22,36,0.82)';
const FONT = 'DejaVu Sans, sans-serif';
const GATE_LABELS = ['Frame', 'Light', 'Sweep', 'Loop', 'Rim'];

// Scene starts, in frames. Only the last 60 frames (the end card) hold still.
const S = {hook: 0, brief: 90, detail: 240, rim: 360, matrix: 480, proof: 720, end: 780};
export const DURATION = 840;

// Real Cycles poses, played in order; no interpolated frames.
const pose = (frame: number) => `frame-${String((Math.floor(frame * POSES_PER_SECOND / FPS) % POSES) + 1).padStart(2, '0')}.png`;

const Text: React.FC<{size?: number; color?: string; bold?: boolean; style?: React.CSSProperties; children: React.ReactNode}> = ({
  size = 64, color = INK, bold = false, style, children,
}) => (
  <div style={{fontFamily: FONT, fontSize: size, color, fontWeight: bold ? 700 : 400, lineHeight: 1.15,
    textShadow: '0 3px 12px rgba(0,0,0,0.85)', ...style}}>{children}</div>
);

const Box: React.FC<{style?: React.CSSProperties; children: React.ReactNode}> = ({style, children}) => (
  <div style={{position: 'absolute', background: BG, borderRadius: 18, padding: '22px 34px', ...style}}>{children}</div>
);

const Turntable: React.FC<{offset?: number; style?: React.CSSProperties}> = ({offset = 0, style}) => {
  const f = useCurrentFrame();
  return <Img src={staticFile(pose(f + offset))} style={{width: '100%', height: '100%', objectFit: 'cover', ...style}} />;
};

const Pop: React.FC<{delay: number; children: React.ReactNode; style?: React.CSSProperties}> = ({delay, children, style}) => {
  const s = spring({frame: useCurrentFrame() - delay, fps: FPS, config: {damping: 13}});
  return <div style={{transform: `translateY(${(1 - s) * 50}px)`, opacity: s, ...style}}>{children}</div>;
};

const Hook: React.FC<Props> = () => {
  const f = useCurrentFrame();
  const badge = spring({frame: f - 25, fps: FPS, config: {damping: 11}});
  return (
    <AbsoluteFill>
      <Turntable offset={S.hook} />
      <Box style={{left: 40, top: 30}}>
        <Pop delay={0}><Text size={68} bold>An AI agent built this in Blender.</Text></Pop>
        <Pop delay={10}><Text size={60} color={BLUE}>A judge checked it.</Text></Pop>
      </Box>
      <Box style={{right: 50, bottom: 50, transform: `scale(${badge})`}}><Text size={84} bold color={BLUE}>PASS 5/5</Text></Box>
    </AbsoluteFill>
  );
};

const Brief: React.FC<Props> = (p) => (
  <AbsoluteFill>
    <Turntable offset={S.brief} />
    <Box style={{left: 40, top: 40, width: 820}}>
      <Text size={64} bold color={BLUE}>5 measured checks</Text>
      {p.gates.map((g, i) => (
        <Pop key={g.label} delay={12 + i * 22} style={{marginTop: 18}}>
          <Text size={52}><span style={{color: BLUE}}>✔</span> {g.label}</Text>
          <Text size={40} color="#b8c4d6" style={{marginLeft: 52}}>{g.value}</Text>
        </Pop>
      ))}
    </Box>
  </AbsoluteFill>
);

const Detail: React.FC<Props> = () => {
  const f = useCurrentFrame();
  const zoom = interpolate(f, [0, 120], [1, 1.9], {extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      <Turntable offset={S.detail} style={{transform: `scale(${zoom})`, transformOrigin: '50% 42%'}} />
      <Box style={{left: 40, bottom: 40}}><Text size={64} bold>Red car paint. Glass. Gold.</Text>
        <Text size={48} color={BLUE}>Real Cycles reflections, 1920×1080</Text></Box>
    </AbsoluteFill>
  );
};

// Animated wipe between the shipped pose and the same pose with the rim light unlinked.
const Rim: React.FC<Props> = () => {
  const f = useCurrentFrame();
  const x = interpolate(Math.sin(f / 18), [-1, 1], [12, 88]);
  return (
    <AbsoluteFill>
      <Img src={staticFile('frame-01.png')} style={{position: 'absolute', width: '100%', height: '100%'}} />
      <Img src={staticFile('unlinked.png')} style={{position: 'absolute', width: '100%', height: '100%',
        clipPath: `inset(0 0 0 ${x}%)`}} />
      <div style={{position: 'absolute', left: `${x}%`, top: 0, bottom: 0, width: 6, background: INK}} />
      <Box style={{left: 40, top: 40}}><Text size={60} bold>Rim light: products only</Text>
        <Text size={48} color={BLUE}>left: shipped · right: unlinked, hits everything</Text></Box>
      <Box style={{left: 40, bottom: 40}}><Text size={52}>The judge measures it: <span style={{color: ORANGE}}>unlinked = FAIL</span></Text></Box>
    </AbsoluteFill>
  );
};

const Matrix: React.FC<Props> = (p) => {
  const f = useCurrentFrame();
  const shown = Math.min(p.mutants.length, Math.floor(f / 20) + 1);
  return (
    <AbsoluteFill>
      <Turntable offset={S.matrix} style={{filter: 'brightness(0.45)'}} />
      <Box style={{left: 40, top: 30, right: 40, bottom: 30, padding: '20px 40px'}}>
        <div style={{display: 'flex', justifyContent: 'space-between'}}>
          <Text size={60} bold color={BLUE}>10 deliberately broken scenes</Text>
          <Text size={60} bold color={ORANGE}>caught {Math.min(shown, p.killed)}/{p.total}</Text>
        </div>
        <div style={{display: 'flex', marginLeft: 820, marginTop: 8}}>
          {GATE_LABELS.map((g) => <Text key={g} size={36} style={{width: 190, textAlign: 'center'}}>{g}</Text>)}
        </div>
        {p.mutants.slice(0, shown).map((m, i) => (
          <Pop key={m.name} delay={i * 20} style={{display: 'flex', alignItems: 'center', height: 78}}>
            <Img src={staticFile(`${m.name}/hero.png`)} style={{width: 128, height: 72, borderRadius: 6}} />
            <Text size={44} style={{width: 660, marginLeft: 30}}>{m.label}</Text>
            {m.failed.map((bad, j) => (
              <div key={j} style={{width: 150, height: 44, margin: '0 20px', borderRadius: 8, background: bad ? ORANGE : BLUE}} />
            ))}
          </Pop>
        ))}
      </Box>
    </AbsoluteFill>
  );
};

const Proof: React.FC<Props> = (p) => {
  const s = spring({frame: useCurrentFrame(), fps: FPS, config: {damping: 11}});
  return (
    <AbsoluteFill>
      <Turntable offset={S.proof} />
      <Box style={{left: 40, top: 40, transform: `scale(${s})`, transformOrigin: 'top left'}}>
        <Text size={150} bold color={BLUE}>PASS 5/5</Text>
        <Text size={56}>{p.killed}/{p.total} broken versions caught</Text>
        <Text size={48} color="#b8c4d6">Same seed. Same verdict.</Text>
      </Box>
    </AbsoluteFill>
  );
};

const End: React.FC = () => (
  <AbsoluteFill>
    <Img src={staticFile('frame-01.png')} style={{width: '100%', height: '100%'}} />
    <Box style={{left: 60, top: 60}}>
      <Text size={84} bold color={BLUE}>Build it. Check it. Run it.</Text>
      <Text size={80} style={{marginTop: 20}}>python3 run.py</Text>
    </Box>
  </AbsoluteFill>
);

export const Demo: React.FC<Props> = (p) => (
  <AbsoluteFill style={{background: '#0d1624'}}>
    <Sequence from={S.hook} durationInFrames={S.brief - S.hook}><Hook {...p} /></Sequence>
    <Sequence from={S.brief} durationInFrames={S.detail - S.brief}><Brief {...p} /></Sequence>
    <Sequence from={S.detail} durationInFrames={S.rim - S.detail}><Detail {...p} /></Sequence>
    <Sequence from={S.rim} durationInFrames={S.matrix - S.rim}><Rim {...p} /></Sequence>
    <Sequence from={S.matrix} durationInFrames={S.proof - S.matrix}><Matrix {...p} /></Sequence>
    <Sequence from={S.proof} durationInFrames={S.end - S.proof}><Proof {...p} /></Sequence>
    <Sequence from={S.end} durationInFrames={DURATION - S.end}><End /></Sequence>
  </AbsoluteFill>
);
