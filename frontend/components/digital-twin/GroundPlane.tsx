"use client";
import { useEffect, useMemo } from 'react';
import { CanvasTexture, RepeatWrapping, SRGBColorSpace } from 'three';

/** An opaque textured floor keeps the grid beneath solids and avoids shader-grid overdraw. */
export default function GroundPlane({ size }: { size: number }) {
  const texture = useMemo(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 320;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#111f2b'; context.fillRect(0,0,320,320);
    for(let i=0;i<=5;i++) {
      context.strokeStyle = i===0 || i===5 ? '#1f3442' : '#192c39';
      context.lineWidth = i===0 || i===5 ? 1.5 : .8;
      context.beginPath(); context.moveTo(i*64,0); context.lineTo(i*64,320); context.stroke();
      context.beginPath(); context.moveTo(0,i*64); context.lineTo(320,i*64); context.stroke();
    }
    const map = new CanvasTexture(canvas);
    map.colorSpace = SRGBColorSpace;
    map.wrapS = map.wrapT = RepeatWrapping;
    map.repeat.set(size/20,size/20);
    map.anisotropy = 4;
    return map;
  },[size]);
  useEffect(() => () => texture.dispose(),[texture]);
  return <group><mesh rotation={[-Math.PI/2,0,0]} position={[0,-3.51,0]}>
    <planeGeometry args={[size,size]}/>
    <meshBasicMaterial map={texture} toneMapped={false}/>
  </mesh><mesh rotation={[-Math.PI/2,0,0]} position={[0,-3.5,0]} receiveShadow>
    <planeGeometry args={[size,size]}/><shadowMaterial transparent opacity={.38} depthWrite={false}/>
  </mesh></group>;
}
