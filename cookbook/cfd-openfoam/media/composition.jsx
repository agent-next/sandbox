import React from 'react';
import {AbsoluteFill, Composition, OffthreadVideo, Sequence, registerRoot, staticFile, useCurrentFrame} from 'remotion';
import verdict from './verdict.json';
const Flow = () => {
  const frame = useCurrentFrame();
  const end = frame >= 780;
  const time = (frame < 60 ? verdict.end_time - 2 + frame / 30 : verdict.start_time + (Math.min(frame, 779) - 60) / 30).toFixed(2);
  const label = frame < 60 ? 'FINISHED CAVITY FLOW' : frame < 240 ? 'BUILDING THE CAVITY' : frame < 480 ? 'MOVING LID / SHEAR LAYER' : 'RETURN FLOW / RECIRCULATION';
  const panel = {position:'absolute',left:48,top:42,width:620,padding:24,background:'rgba(7,18,30,.90)',borderLeft:'5px solid #16d3dc',fontFamily:'sans-serif',color:'white'};
  return <AbsoluteFill style={{background:'#07121e'}}>
    <Sequence durationInFrames={780}><OffthreadVideo src={staticFile('flow.mp4')} pauseWhenBuffering style={{width:1920,height:1080}} /></Sequence>
    <div style={panel}>
      <div style={{fontSize:60,fontWeight:700,lineHeight:1.15}}>{label}</div>
      <div style={{fontSize:60,marginTop:22,color:'#a8d4e2'}}>OpenFOAM · Re = 100</div>
      <div style={{fontSize:60,marginTop:20}}>Solver t = {time} s</div>
      <div style={{fontSize:60,marginTop:18}}>1× time · 1,100 tracers</div>

    </div>
    {frame >= 600 && !end && <div style={{...panel,top:715,width:1050,borderLeft:'5px solid #75d091'}}>
      <div style={{fontSize:64,color:'#75d091',fontWeight:700}}>FINAL CASE: PASS</div>
      <div style={{fontSize:60,marginTop:12}}>u error {verdict.u} · v error {verdict.v}</div>
      <div style={{fontSize:60,marginTop:12}}>t = {verdict.end_time} s · limit ≤ 0.02 · mutants {verdict.killed}/10</div>
    </div>}
    {end && <AbsoluteFill style={{background:'#07121e',alignItems:'center',justifyContent:'center',fontFamily:'sans-serif',color:'white',fontSize:60}}>python3 cookbook/cfd-openfoam/run.py</AbsoluteFill>}
  </AbsoluteFill>;
};
registerRoot(() => <Composition id="Cavity" component={Flow} width={1920} height={1080} fps={30} durationInFrames={840}/>);
