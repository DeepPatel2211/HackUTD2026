"use client";
import { useLayoutEffect, useMemo, useRef } from 'react';
import { AdditiveBlending, CanvasTexture, InstancedMesh, Matrix4 } from 'three';

let glowTexture: CanvasTexture | undefined;
function lampTexture() {
  if (glowTexture) return glowTexture;
  const canvas = document.createElement('canvas'); canvas.width = canvas.height = 64;
  const context = canvas.getContext('2d')!;
  const gradient = context.createRadialGradient(32,32,0,32,32,32);
  gradient.addColorStop(0,'rgba(255,239,193,1)');
  gradient.addColorStop(.12,'rgba(255,203,113,.65)');
  gradient.addColorStop(.4,'rgba(255,182,82,.12)');
  gradient.addColorStop(1,'rgba(255,182,82,0)');
  context.fillStyle=gradient; context.fillRect(0,0,64,64);
  glowTexture = new CanvasTexture(canvas); return glowTexture;
}

/** Visual site furnishings only; lamps do not imply telemetry or operational state. */
export default function SiteDetails({ width, depth, top }: { width: number; depth: number; top: number }) {
  const posts = useRef<InstancedMesh>(null);
  const rails = useRef<InstancedMesh>(null);
  const length = width - 2;
  const count = Math.max(2, Math.ceil(length / 5));
  useLayoutEffect(() => {
    const matrix = new Matrix4();
    for (let i=0;i<=count;i++) {
      matrix.makeTranslation(-length/2+i*length/count, top+.5, -depth/2+.5);
      posts.current?.setMatrixAt(i,matrix);
    }
    for(let i=0;i<2;i++) {
      matrix.makeTranslation(0,top+.4+i*.5,-depth/2+.5);
      rails.current?.setMatrixAt(i,matrix);
    }
    if(posts.current) posts.current.instanceMatrix.needsUpdate=true;
    if(rails.current) rails.current.instanceMatrix.needsUpdate=true;
  },[count,length,depth,top]);
  const glow = useMemo(lampTexture,[]);
  return <group>
    <instancedMesh ref={posts} args={[undefined,undefined,count+1]} frustumCulled={false}>
      <boxGeometry args={[.055,1,.055]}/><meshStandardMaterial color="#9c9474" roughness={.55} metalness={.65}/>
    </instancedMesh>
    <instancedMesh ref={rails} args={[undefined,undefined,2]} frustumCulled={false}>
      <boxGeometry args={[length,.045,.045]}/><meshStandardMaterial color="#afa17b" roughness={.5} metalness={.6}/>
    </instancedMesh>
    {[-1,1].map(side=><group key={side} position={[side*(width/2-1),top,-depth/2+1]}>
      <mesh position={[0,1.15,0]}><cylinderGeometry args={[.055,.08,2.3,8]}/><meshStandardMaterial color="#8d9290" metalness={.65} roughness={.45}/></mesh>
      <mesh position={[0,2.35,0]}><sphereGeometry args={[.12,8,6]}/><meshBasicMaterial color="#ffe3a5" toneMapped={false}/></mesh>
      <sprite position={[0,2.35,0]} scale={[2.2,2.2,1]}><spriteMaterial map={glow} transparent opacity={.3} blending={AdditiveBlending} depthWrite={false} toneMapped={false}/></sprite>
    </group>)}
  </group>;
}
