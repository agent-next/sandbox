// EndCard.tsx — the only static frame in the video (DEMO-STANDARD: the end
// card alone may be still, and the gate requires the last 2 s to be static).
// NO springs, NO fades: the whole card renders identically on every frame.
// The one-line launch command is verbatim from demo README.md / run.py.
import React from 'react';
import { staticFile, Img } from 'remotion';
import { INK, PAPER, BLUE, GREEN, FONT, MONO, captionSize } from './components/kit';
import type { DemoData } from './lib/types';

export const EndCard: React.FC<{ data: DemoData }> = ({ data }) => (
  <div style={{ position: 'absolute', inset: 0, background: `radial-gradient(120% 140% at 20% 0%, #10202f 0%, ${INK} 60%)` }}>
    {/* ghost of the converged field, very dim, fills the frame */}
    <Img src={staticFile(data.clips.endcardStill)} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.26, filter: 'saturate(1.15)' }} />
    <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', gap: 26 }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontFamily: FONT, fontSize: captionSize(1.4), fontWeight: 800, color: PAPER, letterSpacing: '0.01em' }}>
          OpenFOAM in a disposable sandbox
        </div>
        <div style={{ fontFamily: FONT, fontSize: captionSize(0.62), color: '#9fb6c9', marginTop: 12 }}>
          Poiseuille L2 {data.hud.l2} · Ghia 1982 err {data.hud.ghiaU}/{data.hud.ghiaV} · mutants killed {data.hud.kills}
        </div>
      </div>
      <div style={{ background: 'rgba(244,246,248,0.06)', border: `2px solid ${BLUE}`, borderRadius: 18, padding: '26px 46px' }}>
        <div style={{ fontFamily: MONO, fontSize: captionSize(1.0), fontWeight: 700, color: GREEN }}>
          $ python3 cookbook/cfd-openfoam/run.py
        </div>
      </div>
      <div style={{ fontFamily: FONT, fontSize: captionSize(0.5), color: '#7f97ab', maxWidth: 1300, textAlign: 'center', lineHeight: 1.4 }}>
        one command: sandbox up → OpenFOAM 1912 pinned + sha256-checked → icoFoam → a judge it cannot fool → verdict → sandbox killed
      </div>
    </div>
  </div>
);
