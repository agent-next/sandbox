import React from 'react';
import {Composition} from 'remotion';
import {Demo, TOTAL_FRAMES, VideoProps} from './Demo';

export const Root: React.FC = () => {
	return (
		<Composition
			id="Demo"
			component={Demo}
			durationInFrames={TOTAL_FRAMES}
			fps={30}
			width={1920}
			height={1080}
			defaultProps={{} as VideoProps}
		/>
	);
};
