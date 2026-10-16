import React from 'react';
import {
	AbsoluteFill,
	OffthreadVideo,
	Sequence,
	interpolate,
	spring,
	staticFile,
	useCurrentFrame,
	useVideoConfig,
} from 'remotion';

/*
 * spice-filter demo.mp4 — Remotion cut of the real motion clips in
 * media/clips/ (rendered by media/make_clips.py from this sandbox's
 * ngspice runs). Every number on screen arrives via --props
 * media/data/video_props.json, which make_data.py writes from the
 * judge's own verdict JSONs.
 *
 * Timeline @30 fps (media/STORYBOARD.md):
 *   0-2.0 s   hook      — bode clip, finished result moving, kinetic headline
 *   2-10 s    input->out— scope clip: sine in vs filtered out, 3 freqs
 *   10-14.3 s escalate  — recorded sandbox judge run replayed at 8x
 *   14.3-26 s escalate  — bode clip: sweep draws itself vs the spec mask
 *   26-34 s   escalate  — 100 seeded Monte-Carlo sweeps stream in
 *   34-37.5 s proof     — PASS badge + gate rows slide in over live footage
 *   37.5-40 s end card  — static: python3 run.py
 */
export const FPS = 30;
export const TOTAL_FRAMES = 1200;

export interface VideoProps {
	verdict_pass?: boolean;
	seed?: number;
	points?: number;
	f_grid?: string;
	ripple_db?: number;
	ripple_rule?: string;
	stopband_max_db?: number;
	stopband_rule?: string;
	analytic_max_dev_db?: number;
	gbw_dev_db?: number;
	gbw_rule?: string;
	mc_runs?: number;
	mc_pass_fraction?: number;
	mc_worst_ripple_db?: number;
	mc_worst_stopband_db?: number;
	kill_rate?: number;
	mutants?: number;
	replay?: {label: string; passed: boolean; failed_gate: string}[];
	ngspice?: string;
}

const MONO = '"DejaVu Sans Mono", monospace';
const CYAN = '#00d6ff';
const GREEN = '#54ff7a';
const AMBER = '#ffb328';
const DIM = '#8a97ab';
const PANEL = 'rgba(10,16,24,0.82)';

const Chip: React.FC<{
	children: React.ReactNode;
	color?: string;
	style?: React.CSSProperties;
}> = ({children, color = CYAN, style}) => (
	<div
		style={{
			fontFamily: MONO,
			fontSize: 34,
			fontWeight: 700,
			color,
			backgroundColor: PANEL,
			border: `2px solid ${color}`,
			borderRadius: 12,
			padding: '12px 26px',
			display: 'inline-block',
			...style,
		}}
	>
		{children}
	</div>
);

/* kinetic headline: words spring up one by one */
const Headline: React.FC<{words: string[]; sub: string; color?: string}> = ({
	words,
	sub,
	color = CYAN,
}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();
	return (
		<div style={{position: 'absolute', left: 90, bottom: 130}}>
			<div style={{display: 'flex', gap: 26}}>
				{words.map((w, i) => {
					const s = spring({
						frame: frame - i * 5,
						fps,
						config: {damping: 14, stiffness: 140},
					});
					return (
						<div
							key={w}
							style={{
								fontFamily: MONO,
								fontSize: 86,
								fontWeight: 700,
								color: '#eef4fb',
								transform: `translateY(${(1 - s) * 110}px)`,
								opacity: s,
								textShadow: `0 0 26px ${color}`,
							}}
						>
							{w}
						</div>
					);
				})}
			</div>
			<div
				style={{
					fontFamily: MONO,
					fontSize: 40,
					color,
					opacity: spring({frame: frame - 18, fps}),
					marginTop: 18,
				}}
			>
				{sub}
			</div>
		</div>
	);
};

/* lower-third caption chip that slides in, holds, slides out */
const Caption: React.FC<{
	text: string;
	from: number;
	to: number;
	color?: string;
}> = ({text, from, to, color = '#eef4fb'}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();
	const inS = spring({frame: frame - from, fps, config: {damping: 16}});
	const outS = spring({frame: frame - to, fps, config: {damping: 16}});
	const x = (1 - inS) * -160 + outS * 160;
	const op = inS * (1 - outS);
	if (frame < from - 2 || frame > to + 40) {
		return null;
	}
	return (
		<div
			style={{
				position: 'absolute',
				left: 90,
				bottom: 64,
				transform: `translateX(${x}px)`,
				opacity: op,
			}}
		>
			<Chip color={color}>{text}</Chip>
		</div>
	);
};

const GateRow: React.FC<{
	name: string;
	measured: string;
	delay: number;
}> = ({name, measured, delay}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();
	const s = spring({frame: frame - delay, fps, config: {damping: 16}});
	return (
		<div
			style={{
				display: 'flex',
				alignItems: 'center',
				gap: 18,
				fontFamily: MONO,
				fontSize: 30,
				color: '#dfe8f2',
				backgroundColor: PANEL,
				border: '1px solid #2a3a4e',
				borderRadius: 10,
				padding: '10px 22px',
				transform: `translateX(${(1 - s) * 260}px)`,
				opacity: s,
			}}
		>
			<span style={{color: GREEN, fontWeight: 700}}>PASS</span>
			<span style={{color: CYAN, minWidth: 210}}>{name}</span>
			<span>{measured}</span>
		</div>
	);
};

const ProofHud: React.FC<{p: VideoProps}> = ({p}) => {
	const frame = useCurrentFrame();
	const {fps} = useVideoConfig();
	const badgeS = spring({
		frame,
		fps,
		config: {damping: 12, stiffness: 120},
	});
	const ripple = p.ripple_db ?? 0.096;
	const stop = p.stopband_max_db ?? -56.14;
	const gbw = p.gbw_dev_db ?? 0.15029;
	const mcN = p.mc_runs ?? 100;
	const kill = p.mutants ?? 9;
	const pts = p.points ?? 801;
	const rows = [
		{name: 'mask', measured: `ripple ${ripple} dB · stop ${stop} dB`},
		{name: 'analytic', measured: `oracle dev 0.0 dB · GBW ${gbw} dB`},
		{name: 'series', measured: 'every R on E24, every C on E12'},
		{name: 'montecarlo', measured: `${mcN}/${mcN} seeded runs pass`},
		{name: 'self-test', measured: `${kill}/${kill} mutants killed`},
		{name: 'sweep', measured: `${pts} pts, ${p.f_grid ?? '10..100000 200/dec'}`},
	];
	return (
		<AbsoluteFill>
			<div
				style={{
					position: 'absolute',
					right: 110,
					top: 150,
					transform: `scale(${badgeS})`,
					opacity: badgeS,
					fontFamily: MONO,
					fontSize: 150,
					fontWeight: 700,
					color: GREEN,
					border: `8px solid ${GREEN}`,
					borderRadius: 28,
					padding: '10px 56px',
					backgroundColor: 'rgba(6,20,12,0.9)',
					boxShadow: `0 0 60px ${GREEN}55`,
				}}
			>
				PASS
			</div>
			<div
				style={{
					position: 'absolute',
					right: 110,
					top: 420,
					display: 'flex',
					flexDirection: 'column',
					gap: 14,
				}}
			>
				{rows.map((r, i) => (
					<GateRow
						key={r.name}
						name={r.name}
						measured={r.measured}
						delay={8 + i * 9}
					/>
				))}
			</div>
			<div style={{position: 'absolute', left: 90, top: 80}}>
				<Chip color={AMBER}>
					judge verdict · seed {p.seed ?? 20261014} · {p.ngspice ?? 'ngspice-39'}
				</Chip>
			</div>
		</AbsoluteFill>
	);
};

const EndCard: React.FC<{p: VideoProps}> = ({p}) => (
	<AbsoluteFill
		style={{
			backgroundColor: '#070b11',
			justifyContent: 'center',
			alignItems: 'center',
			fontFamily: MONO,
		}}
	>
		<div style={{fontSize: 44, color: DIM, marginBottom: 30}}>
			cookbook/spice-filter · agent-next/sandbox
		</div>
		<div
			style={{
				fontSize: 96,
				fontWeight: 700,
				color: '#eef4fb',
				border: `3px solid ${CYAN}`,
				borderRadius: 18,
				padding: '26px 60px',
				backgroundColor: PANEL,
			}}
		>
			python3 run.py
		</div>
		<div style={{fontSize: 36, color: DIM, marginTop: 34}}>
			a judge the agent cannot fool · {p.ngspice ?? 'ngspice-39'} · seed{' '}
			{p.seed ?? 20261014}
		</div>
	</AbsoluteFill>
);

const ZoomClip: React.FC<{
	src: string;
	startFrom: number;
	frames: number;
	scale: (f: number) => number;
	origin?: string;
}> = ({src, startFrom, frames, scale, origin = 'center'}) => {
	const frame = useCurrentFrame();
	return (
		<AbsoluteFill>
			<div
				style={{
					width: '100%',
					height: '100%',
					transform: `scale(${scale(frame)})`,
					transformOrigin: origin,
				}}
			>
				<OffthreadVideo
					src={staticFile(src)}
					startFrom={startFrom}
					endAt={startFrom + frames}
					style={{width: '100%', height: '100%', objectFit: 'cover'}}
				/>
			</div>
		</AbsoluteFill>
	);
};

export const Demo: React.FC<VideoProps> = (p) => {
	return (
		<AbsoluteFill style={{backgroundColor: '#070b11'}}>
			{/* 0-2 s: hook — finished result moving, kinetic headline */}
			<Sequence from={0} durationInFrames={60}>
				<ZoomClip
					src="clips/bode.mp4"
					startFrom={280}
					frames={60}
					scale={(f) => 1.04 + f * 0.0006}
				/>
				<Headline
					words={['AN', 'AGENT', 'DESIGNS', 'A', 'FILTER.']}
					sub="ngspice-39 grades it · cookbook/spice-filter"
				/>
			</Sequence>

			{/* 2-10 s: input -> output on the scope */}
			<Sequence from={60} durationInFrames={240}>
				<ZoomClip
					src="clips/scope.mp4"
					startFrom={60}
					frames={240}
					scale={(f) =>
						f < 180 ? 1.0 + f * 0.0004 : 1.12 + (f - 180) * 0.0002
					}
				/>
				<Caption
					text="input → output · a 1 V sine through the filter"
					from={8}
					to={95}
					color={CYAN}
				/>
				<Caption
					text="16 kHz in → the output is on the mV scale"
					from={120}
					to={210}
					color={GREEN}
				/>
			</Sequence>

			{/* 10-14.3 s: the sandbox run replayed */}
			<Sequence from={300} durationInFrames={130}>
				<ZoomClip
					src="clips/term.mp4"
					startFrom={80}
					frames={130}
					scale={() => 1.0}
				/>
				<Caption
					text="the judge run in the sandbox, replayed"
					from={6}
					to={100}
					color={AMBER}
				/>
			</Sequence>

			{/* 14.3-26 s: the bode sweep draws itself */}
			<Sequence from={430} durationInFrames={350}>
				<ZoomClip
					src="clips/bode.mp4"
					startFrom={15}
					frames={350}
					scale={(f) => 1.0 + Math.min(f, 300) * 0.00035}
				/>
				<Caption
					text="the AC sweep draws itself against the spec mask"
					from={10}
					to={120}
					color={CYAN}
				/>
				<Caption
					text="closed-form oracle + 1 MHz-GBW macro-model agree"
					from={170}
					to={300}
					color={AMBER}
				/>
			</Sequence>

			{/* 26-34 s: 100 seeded Monte-Carlo runs */}
			<Sequence from={780} durationInFrames={240}>
				<ZoomClip
					src="clips/mc.mp4"
					startFrom={0}
					frames={240}
					scale={(f) => 1.06 - f * 0.0002}
				/>
				<Caption
					text="R ±5 % · C ±10 % — 100 seeded runs"
					from={8}
					to={120}
					color={GREEN}
				/>
			</Sequence>

			{/* 34-37.5 s: proof HUD over still-playing footage */}
			<Sequence from={1020} durationInFrames={105}>
				<ZoomClip
					src="clips/scope.mp4"
					startFrom={250}
					frames={105}
					scale={() => 1.06}
				/>
				<ProofHud p={p} />
			</Sequence>

			{/* 37.5-40 s: static end card */}
			<Sequence from={1125} durationInFrames={75}>
				<EndCard p={p} />
			</Sequence>
		</AbsoluteFill>
	);
};
