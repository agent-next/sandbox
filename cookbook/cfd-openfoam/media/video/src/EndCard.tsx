// EndCard.tsx — the only static frame in the video (DEMO-STANDARD: the end
// card alone may be still). One-line launch command + the ask-your-agent
// prompt, both taken verbatim from demo README.md / result.json.
import React from 'react';
import { staticFile, Img } from 'remotion';
import { INK, PAPER, BLUE, GREEN, FONT, MONO, captionSize, pop } from './components/kit';

export const EndCard: React.FC<{ data: any }> = ({ data }) => {
  const f = 0; // inside a Sequence this starts at 0
  const s1 = pop(f, 4);
  const s2 = pop(f, 16);
  return (
    <div style={{ position: 'absolute', inset: 0, background: `radial-gradient(120% 140% at 20% 0%, #10202f 0%, ${INK} 60%)` }}>
      {/* ghost of the converged field, very dim, fills the frame */}
      <Img src={staticFile('clips/endcard_still.jpg')} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.28, filter: 'saturate(1.15)' }} />
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', gap: 26 }}>
        <div style={{ ...s2 === 0 ? {} : {}, opacity: s1, transform: `translateY(${24 * (1 - s1)}px)`, textAlign: 'center' }}>
          <div style={{ fontFamily: FONT, fontSize: captionSize(1.5), fontWeight: 800, color: PAPER, letterSpacing: '0.01em' }}>
            OpenFOAM in a disposable sandbox
          </div>
          <div style={{ fontFamily: FONT, fontSize: captionSize(0.72), color: '#9fb6c9', marginTop: 10 }}>
            Poiseuille parabola L2 {data.hud.l2} &nbsp;·&nbsp; Ghia 1982 max err {data.hud.ghiaU}/{data.hud.ghiaV} &nbsp;·&nbsp; mutants killed {data.hud.kills}
          </div>
        </div>
        <div style={{ opacity: s2, transform: `translateY(${24 * (1 - s2)}px)`, background: 'rgba(244,246,248,0.06)', border: `2px solid ${BLUE}`, borderRadius: 18, padding: '26px 46px' }}>
          <div style={{ fontFamily: MONO, fontSize: captionSize(1.15), fontWeight: 700, color: GREEN }}>
            $ python3 cookbook/cfd-openfoam/run.py
          </div>
        </div>
        <div style={{ opacity: s2, fontFamily: FONT, fontSize: captionSize(0.56), color: '#7f97ab', maxWidth: 1300, textAlign: 'center', lineHeight: 1.4 }}>
          one command: sandbox up → OpenFOAM 1912 pinned + sha256-checked → icoFoam → a judge it cannot fool → verdict → sandbox killed
        </div>
      </div>
    </div>
  );
};
