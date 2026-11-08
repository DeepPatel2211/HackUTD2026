"use client";

/** Full rectangular solids; the equipment datum and footprint never move. */
export default function Platform({ width, depth, height, top, color = "#405564" }: {
  width: number; depth: number; height: number; top: number; color?: string;
}) {
  const lip = Math.min(0.08, height / 5);
  return <group>
    <mesh position={[0, top - lip / 2, 0]} castShadow receiveShadow>
      <boxGeometry args={[width, lip, depth]}/>
      <meshStandardMaterial color={color} roughness={0.8} metalness={0.18}/>
    </mesh>
    <mesh position={[0, top - lip - (height - lip) / 2, 0]} castShadow receiveShadow>
      <boxGeometry args={[width - 0.08, height - lip, depth - 0.08]}/>
      <meshStandardMaterial color="#354b5a" roughness={0.82} metalness={0.2}/>
    </mesh>
    <mesh position={[0, top - height + 0.07, 0]} receiveShadow>
      <boxGeometry args={[width - 0.04, 0.045, depth - 0.04]}/>
      <meshStandardMaterial color="#71838d" roughness={0.45} metalness={0.65}/>
    </mesh>
  </group>;
}
