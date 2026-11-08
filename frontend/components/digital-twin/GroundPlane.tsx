"use client";
import { useEffect, useMemo } from 'react';
import { CanvasTexture, SRGBColorSpace } from 'three';

/** A soft light pool anchors the real geometry without a tiled foreground grid. */
export default function GroundPlane({ size, center = [0, 0], radius = size / 4 }: { size: number; center?: [number, number]; radius?: number }) {
  const texture = useMemo(() => {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 320;
    const context = canvas.getContext('2d')!;
    const cx = 160 + center[0] / size * 320;
    const cy = 160 - center[1] / size * 320;
    const gradient = context.createRadialGradient(cx,cy,0,cx,cy,radius / size * 320);
    gradient.addColorStop(0,'#344a58');
    gradient.addColorStop(.5,'#293e4c');
    gradient.addColorStop(1,'#192c39');
    context.fillStyle = gradient; context.fillRect(0,0,320,320);
    const map = new CanvasTexture(canvas);
    map.colorSpace = SRGBColorSpace;
    map.anisotropy = 4;
    return map;
  },[size, center[0], center[1], radius]);
  useEffect(() => () => texture.dispose(),[texture]);
  return <group><mesh rotation={[-Math.PI/2,0,0]} position={[0,-3.51,0]}>
    <planeGeometry args={[size,size]}/>
    <meshBasicMaterial map={texture} toneMapped={false}/>
  </mesh><mesh rotation={[-Math.PI/2,0,0]} position={[0,-3.5,0]} receiveShadow>
    <planeGeometry args={[size,size]}/><shadowMaterial transparent opacity={.38} depthWrite={false}/>
  </mesh></group>;
}
