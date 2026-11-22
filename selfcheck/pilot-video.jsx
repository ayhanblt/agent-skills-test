import React from 'react';
import {registerRoot,Composition,AbsoluteFill,useCurrentFrame,Sequence,Audio,staticFile} from 'remotion';
function Card(p) {
  const first = useCurrentFrame()<96;
  return <AbsoluteFill style={{background:first?p.firstColor:p.secondColor,color:'white'}}>
    <div style={{position:'absolute',bottom:24,width:'100%',font:'64px sans-serif',textAlign:'center'}}>
      {first?p.primary:p.secondary}
    </div>
    <Sequence from={24} durationInFrames={12}><Audio src={staticFile(p.sound)}/></Sequence>
  </AbsoluteFill>;
}
registerRoot(()=> <Composition id="Info" component={Card} width={1280} height={720} fps={24} durationInFrames={240}/>);
