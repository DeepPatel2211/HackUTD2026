"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AssetLabel as Html } from "./AssetLabel";
import { useFrame, type ThreeEvent } from "@react-three/fiber";
import * as THREE from "three";
import type { Asset, Selection, Vec3 } from "../../lib/types";
import { colors, metricInfo } from "../../lib/operational-status";

const steel = new THREE.MeshStandardMaterial({
  color: "#a4b6bf",
  metalness: 0.62,
  roughness: 0.38,
});
const trim = new THREE.MeshStandardMaterial({
  color: "#b9c6cc",
  metalness: 0.8,
  roughness: 0.32,
});
const dark = new THREE.MeshStandardMaterial({
  color: "#586c79",
  metalness: 0.6,
  roughness: 0.48,
});
const concrete = new THREE.MeshStandardMaterial({
  color: "#343e45",
  roughness: 0.96,
});
const rubber = new THREE.MeshStandardMaterial({
  color: "#10171e",
  roughness: 0.85,
});
const teal = new THREE.MeshStandardMaterial({
  color: "#94abb4",
  emissive: "#66c7c9",
  emissiveIntensity: 0.035,
  metalness: 0.55,
  roughness: 0.45,
});
const faultHousing = new THREE.MeshStandardMaterial({ color: '#657987', metalness: 0.65, roughness: 0.4, emissive: colors.fault, emissiveIntensity: 0.13 });
const warningHousing = new THREE.MeshStandardMaterial({ color: '#657987', metalness: 0.65, roughness: 0.4, emissive: colors.warning, emissiveIntensity: 0.1 });
const brass = new THREE.MeshStandardMaterial({ color: '#bca46c', metalness: .65, roughness: .4 });

export function Box({
  position = [0, 0, 0],
  size,
  material = steel,
  rotation,
}: {
  position?: Vec3;
  size: Vec3;
  material?: THREE.Material;
  rotation?: Vec3;
}) {
  return (
    <mesh
      position={position}
      rotation={rotation}
      material={material}
      castShadow
      receiveShadow
    >
      <boxGeometry args={size} />
    </mesh>
  );
}
export function Cylinder({
  position = [0, 0, 0],
  radius,
  height,
  material = steel,
  rotation,
  top,
}: {
  position?: Vec3;
  radius: number;
  height: number;
  material?: THREE.Material;
  rotation?: Vec3;
  top?: number;
}) {
  return (
    <mesh
      position={position}
      rotation={rotation}
      material={material}
      castShadow
      receiveShadow
    >
      <cylinderGeometry args={[top ?? radius, radius, height, 24]} />
    </mesh>
  );
}
function Torus({
  position,
  radius,
  tube = 0.035,
  rotation = [Math.PI / 2, 0, 0],
  material = trim,
}: {
  position: Vec3;
  radius: number;
  tube?: number;
  rotation?: Vec3;
  material?: THREE.Material;
}) {
  return (
    <mesh position={position} rotation={rotation} material={material}>
      <torusGeometry args={[radius, tube, 6, 48]} />
    </mesh>
  );
}
export function StatusLight({
  position,
  color,
}: {
  position: Vec3;
  color: string;
}) {
  return (
    <group position={position}>
      <Cylinder radius={0.12} height={0.14} material={dark} />
      <mesh position={[0, 0.13, 0]}>
        <sphereGeometry args={[0.095, 12, 8]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={1.7}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

export function SelectionRing({
  radius,
  fault = false,
}: {
  radius: number;
  fault?: boolean;
}) {
  const mesh = useRef<THREE.Mesh>(null);
  const reducedMotion = useRef(false);
  useEffect(() => {
    const preference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => { reducedMotion.current = preference.matches; };
    update();
    preference.addEventListener("change", update);
    return () => preference.removeEventListener("change", update);
  }, []);
  useFrame(({ clock }) => {
    if (mesh.current && fault) {
      const wave = reducedMotion.current ? 0 : Math.sin(clock.elapsedTime * 2);
      const pulse = 1 + wave * 0.035;
      mesh.current.scale.setScalar(pulse);
      (mesh.current.material as THREE.MeshBasicMaterial).opacity =
        0.45 + wave * 0.15;
    }
  });
  return (
    <mesh ref={mesh} position={[0, 0.12, 0]} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[radius, radius + 0.035, 64]} />
      <meshBasicMaterial
        color={fault ? colors.fault : colors.selected}
        transparent
        opacity={0.8}
        depthWrite={false}
        side={THREE.DoubleSide}
      />
    </mesh>
  );
}

export function AssetAssembly({
  asset,
  position,
  selected,
  onSelect,
  onFocus,
  children,
  label,
  showLabel = false,
  ringRadius = 1.5,
  anchor = [0, 0, 0],
}: {
  asset: Asset;
  position: Vec3;
  selected: boolean;
  onSelect: (selection: Selection) => void;
  onFocus: (asset: Asset) => void;
  children: React.ReactNode;
  label?: string;
  showLabel?: boolean;
  ringRadius?: number;
  anchor?: Vec3;
}) {
  const [hovered, setHovered] = useState(false);
  const select = (event: ThreeEvent<MouseEvent>) => {
    event.stopPropagation();
    if (event.delta <= 5) onSelect({ assetId: asset.id });
  };
  return (
    <group
      position={position}
      onClick={select}
      onDoubleClick={(e) => {
        e.stopPropagation();
        onFocus(asset);
      }}
      onPointerOver={(e) => {
        e.stopPropagation();
        setHovered(true);
      }}
      onPointerOut={() => setHovered(false)}
    >
      {children}
      {(selected || hovered) && (
        <group position={anchor}>
          <SelectionRing radius={ringRadius} />
        </group>
      )}
      {(showLabel || hovered || selected) && (
        <Html
          position={[
            anchor[0],
            anchor[1] + (asset.kind === "tank" ? 4.3 : 3.6),
            anchor[2],
          ]}
          center
          zIndexRange={[15, 0]}
          style={{ pointerEvents: "none" }}
        >
          <div className={"asset-label " + (selected ? "is-selected" : "")}>
            <span>{label || asset.kind}</span>
            <small>{asset.id}</small>
          </div>
        </Html>
      )}
    </group>
  );
}

export function SensorMarker({
  position,
  assetId,
  metric,
  selected,
  onSelect,
}: {
  position: Vec3;
  assetId: string;
  metric: string;
  selected: boolean;
  onSelect: (selection: Selection) => void;
}) {
  return (
    <group position={position}>
      <mesh rotation={[0, 0, Math.PI / 4]}>
        <boxGeometry args={[0.14, 0.14, 0.14]} />
        <meshStandardMaterial
          color={colors.selected}
          emissive={colors.selected}
          emissiveIntensity={0.5}
        />
      </mesh>
      <Html center position={[0.22, 0.08, 0]} zIndexRange={[20, 0]}>
        <button
          className={"sensor-pin " + (selected ? "selected" : "")}
          aria-label={`Inspect ${assetId} ${metric}`}
          title={`${metricInfo[metric]?.label || metric} · schematic marker`}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            onSelect({ assetId, metric });
          }}
        >
          <span className="sensor-symbol"/><span className="sensor-caption">{metricInfo[metric]?.label || metric}</span>
        </button>
      </Html>
    </group>
  );
}

export function WellModel() {
  return (
    <group>
      <Box
        position={[0, 0.08, 0]}
        size={[1.7, 0.16, 1.45]}
        material={concrete}
      />
      <Cylinder
        position={[0, 0.3, 0]}
        radius={0.3}
        height={0.45}
        material={dark}
      />
      <Cylinder position={[0, 1.05, 0]} radius={0.15} height={1.3} />
      {[0.55, 1.05, 1.6].map((y) => (
        <Cylinder
          key={y}
          position={[0, y, 0]}
          radius={0.28}
          height={0.09}
          material={trim}
        />
      ))}
      <Cylinder
        position={[0.36, 1.1, 0]}
        radius={0.11}
        height={0.8}
        rotation={[0, 0, Math.PI / 2]}
      />
      <Box position={[0.35, 1.1, 0]} size={[0.22, 0.3, 0.3]} material={dark} />
      <Torus
        position={[0.35, 1.1, 0.26]}
        radius={0.18}
        rotation={[0, 0, 0]}
        material={teal}
      />
      <Cylinder
        position={[0.35, 1.1, 0.18]}
        radius={0.035}
        height={0.25}
        rotation={[Math.PI / 2, 0, 0]}
      />
      <Cylinder
        position={[0, 1.8, 0]}
        radius={0.06}
        height={0.32}
        material={trim}
      />
      <Torus position={[0, 1.96, 0]} radius={0.22} material={teal} />
      <Cylinder
        position={[0.6, 0.4, 0]}
        radius={0.1}
        height={1}
        rotation={[0, 0, Math.PI / 2]}
        material={teal}
      />
    </group>
  );
}

export function TankModel({
  level,
  warning,
  shutdown,
  color,
}: {
  level: number | null;
  warning: number;
  shutdown: number;
  color: string;
}) {
  const filled = level == null ? 0 : Math.min(100, Math.max(0, level)) / 100;
  return (
    <group>
      <Cylinder
        position={[0, 0.12, 0]}
        radius={1.95}
        height={0.24}
        material={concrete}
      />
      <Cylinder position={[0, 1.8, 0]} radius={1.65} height={3.2} />
      <Cylinder
        position={[0, 3.45, 0]}
        radius={1.65}
        top={1.48}
        height={0.15}
        material={trim}
      />
      <Torus position={[0, 3.88, 0]} radius={1.69} tube={.025} material={brass}/>
      {[0,Math.PI/2,Math.PI,Math.PI*1.5].map(angle=><Cylinder key={`rail-${angle}`} position={[Math.sin(angle)*1.69,3.67,Math.cos(angle)*1.69]} radius={.022} height={.42} material={brass}/>)}
      {[0.25, 1.35, 2.45, 3.4].map((y) => (
        <Torus key={y} position={[0, y, 0]} radius={1.66} tube={0.025} />
      ))}
      {[0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2].map((a) => (
        <Box
          key={a}
          position={[Math.sin(a) * 1.65, 1.8, Math.cos(a) * 1.65]}
          size={[0.025, 3.05, 0.025]}
          material={dark}
        />
      ))}
      <Cylinder
        position={[0, 3.64, 0]}
        radius={0.38}
        height={0.2}
        material={dark}
      />
      <Cylinder
        position={[0, 3.8, 0]}
        radius={0.4}
        height={0.08}
        material={trim}
      />
      {[-0.3, 0.3].map((x) => (
        <Cylinder
          key={x}
          position={[x, 1.95, 1.72]}
          radius={0.025}
          height={3.4}
          material={trim}
        />
      ))}
      {Array.from({ length: 10 }, (_, i) => (
        <Cylinder
          key={i}
          position={[0, 0.45 + i * 0.32, 1.74]}
          radius={0.023}
          height={0.6}
          rotation={[0, 0, Math.PI / 2]}
          material={trim}
        />
      ))}
      <Box
        position={[2.05, 1.8, 0.5]}
        size={[0.16, 3.1, 0.18]}
        material={dark}
      />
      {filled > 0 && (
        <mesh position={[2.05, 0.3 + filled * 1.5, 0.61]}>
          <boxGeometry args={[0.1, filled * 3, 0.035]} />
          <meshBasicMaterial color={color} />
        </mesh>
      )}
      {[
        { value: warning, color: colors.warning },
        { value: shutdown, color: colors.fault },
      ].map((m) => (
        <mesh key={m.color} position={[2.05, 0.3 + (m.value / 100) * 3, 0.64]}>
          <boxGeometry args={[0.35, 0.035, 0.04]} />
          <meshBasicMaterial color={m.color} />
        </mesh>
      ))}
      <StatusLight position={[-1.15, 3.6, 0.1]} color={color} />
      <Cylinder
        position={[1.9, 0.65, 0]}
        radius={0.16}
        height={0.8}
        rotation={[0, 0, Math.PI / 2]}
        material={teal}
      />
      <Cylinder
        position={[-1.9, 0.65, 0]}
        radius={0.14}
        height={0.8}
        rotation={[0, 0, Math.PI / 2]}
        material={teal}
      />
    </group>
  );
}

export function PumpModel({ color, fault }: { color: string; fault: boolean }) {
  const housing = fault ? faultHousing : color === colors.warning ? warningHousing : dark;
  return (
    <group>
      <Box position={[0, 0.15, 0]} size={[3, 0.3, 1.65]} material={dark} />
      {[-1.15, 1.15].map((x) => (
        <Box
          key={x}
          position={[x, 0.05, 0]}
          size={[0.3, 0.1, 1.9]}
          material={concrete}
        />
      ))}
      <Cylinder
        position={[0.55, 0.85, 0]}
        radius={0.48}
        height={1.35}
        rotation={[0, 0, Math.PI / 2]}
        material={housing}
      />
      {Array.from({ length: 7 }, (_, i) => (
        <Cylinder
          key={i}
          position={[0.02 + i * 0.16, 0.85, 0]}
          material={housing}
          radius={0.51}
          height={0.035}
          rotation={[0, 0, Math.PI / 2]}
        />
      ))}
      <Box position={[0.8, 1.38, 0]} size={[0.5, 0.2, 0.5]} material={teal} />
      <Cylinder
        position={[-0.75, 0.85, 0]}
        radius={0.57}
        height={0.65}
        rotation={[0, 0, Math.PI / 2]}
      />
      <Cylinder
        position={[-1.25, 0.85, 0]}
        radius={0.16}
        height={0.6}
        rotation={[0, 0, Math.PI / 2]}
        material={teal}
      />
      <Cylinder
        position={[-0.8, 1.4, 0]}
        radius={0.16}
        height={0.65}
        material={teal}
      />
      <Cylinder
        position={[-0.8, 1.72, 0]}
        radius={0.25}
        height={0.08}
        material={trim}
      />
      <StatusLight position={[0.8, 1.55, 0]} color={color} />
      {fault && <SelectionRing radius={1.7} fault />}
    </group>
  );
}

export function PipelineModel({
  points,
  active = false,
  fault = false,
  radius = 0.12,
}: {
  points: Vec3[];
  active?: boolean;
  fault?: boolean;
  radius?: number;
}) {
  const curve = useMemo(() => {
    const vertices = points.map(p => new THREE.Vector3(...p)).filter((p,i,all) => i===0 || p.distanceToSquared(all[i-1])>1e-8);
    const path = new THREE.CurvePath<THREE.Vector3>();
    let previous = vertices[0];
    for(let i=1;i<vertices.length-1;i++) {
      const corner = vertices[i];
      const bend = Math.min(.65,corner.distanceTo(vertices[i-1])*.25,corner.distanceTo(vertices[i+1])*.25);
      const entry = corner.clone().add(vertices[i-1].clone().sub(corner).normalize().multiplyScalar(bend));
      const exit = corner.clone().add(vertices[i+1].clone().sub(corner).normalize().multiplyScalar(bend));
      path.add(new THREE.LineCurve3(previous,entry));
      path.add(new THREE.QuadraticBezierCurve3(entry,corner,exit));
      previous = exit;
    }
    path.add(new THREE.LineCurve3(previous,vertices[vertices.length-1]));
    return path;
  },[points]);
  const geometry = useMemo(
    () =>
      new THREE.TubeGeometry(
        curve,
        Math.max(24, points.length * 12),
        radius,
        8,
        false,
      ),
    [curve, points.length, radius],
  );
  return (
    <group>
      <mesh geometry={geometry} material={fault ? undefined : teal} castShadow>
        {fault && (
          <meshStandardMaterial
            color="#6e494e"
            metalness={0.6}
            roughness={0.45}
            emissive={colors.fault}
            emissiveIntensity={0.22}
          />
        )}
      </mesh>
      {points
        .filter((_, i) => i === 0 || i === points.length - 1)
        .map((p, i) => (
          <Cylinder
            key={i}
            position={[p[0], 0.24, p[2]]}
            radius={0.16}
            height={0.45}
            material={dark}
          />
        ))}
      {active && (
        <FlowAnimation
          curve={curve}
          color={fault ? colors.warning : colors.selected}
        />
      )}
    </group>
  );
}

function FlowAnimation({
  curve,
  color,
}: {
  curve: THREE.Curve<THREE.Vector3>;
  color: string;
}) {
  const group = useRef<THREE.Group>(null);
  const samples = useMemo(() => {
    const up = new THREE.Vector3(0, 1, 0);
    return Array.from({ length: 129 }, (_, i) => ({
      position: curve.getPointAt(i / 128),
      rotation: new THREE.Quaternion().setFromUnitVectors(up, curve.getTangentAt(i / 128).normalize()),
    }));
  }, [curve]);
  useFrame(({ clock }) => {
    group.current?.children.forEach((child, i) => {
      const t = (clock.elapsedTime * 0.08 + i / 3) % 1;
      const sample = t * 128;
      const index = Math.min(127, Math.floor(sample));
      const alpha = sample - index;
      child.position.lerpVectors(samples[index].position, samples[index + 1].position, alpha);
      child.quaternion.slerpQuaternions(samples[index].rotation, samples[index + 1].rotation, alpha);
    });
  });
  return (
    <group ref={group}>
      {[0, 1, 2].map((i) => (
        <mesh key={i}>
          <coneGeometry args={[0.19, 0.5, 5]} />
          <meshBasicMaterial color={color} transparent opacity={0.8} />
        </mesh>
      ))}
    </group>
  );
}

export function DisposalModel() {
  return (
    <group>
      <Box position={[0, 0.1, 0]} size={[7, 0.2, 5]} material={concrete} />
      {[-1.5, 0.7].map((x) => (
        <group key={x} position={[x, 0, 0]}>
          <Cylinder position={[0, 1.45, 0]} radius={0.65} height={2.6} />
          <Cylinder
            position={[0, 2.85, 0]}
            radius={0.65}
            top={0.28}
            height={0.25}
            material={trim}
          />
          <Torus position={[0, 1, 0]} radius={0.66} />
          <Torus position={[0, 2.6, 0]} radius={0.66} />
          <Cylinder
            position={[0, 3.25, 0]}
            radius={0.12}
            height={0.6}
            material={teal}
          />
        </group>
      ))}
      <PipelineModel
        points={[
          [-3.5, 0.6, 1.7],
          [2.7, 0.6, 1.7],
          [2.7, 0.6, 0],
          [2.7, -0.2, 0],
        ]}
      />
      {[-2.5, 0, 2.5].map((x) => (
        <group key={x}>
          <Cylinder position={[x, 1, 1.7]} radius={0.06} height={0.7} />
          <Torus position={[x, 1.4, 1.7]} radius={0.17} material={teal} />
        </group>
      ))}
      <mesh position={[2.7, 0.15, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.5, 0.55, 32]} />
        <meshBasicMaterial color="#4c7f88" />
      </mesh>
      <StatusLight position={[1.6, 1.5, 1.8]} color={colors.healthy} />
    </group>
  );
}

export function TruckModel() {
  return (
    <group>
      <Box position={[0, 0.65, 0]} size={[4.3, 0.18, 1.65]} material={dark} />
      <Box position={[1.65, 1.35, 0]} size={[1.25, 1.3, 1.6]} />
      <Box
        position={[2.3, 1.57, 0]}
        size={[0.025, 0.47, 1.35]}
        material={dark}
      />
      <Box position={[1.65, 2.05, 0]} size={[1.4, 0.12, 1.7]} material={trim} />
      <Cylinder
        position={[-0.7, 1.4, 0]}
        radius={0.72}
        height={2.9}
        rotation={[0, 0, Math.PI / 2]}
      />
      <Cylinder
        position={[-0.7, 2.17, 0]}
        radius={0.2}
        height={0.15}
        material={trim}
      />
      {[-1.55, -0.6, 1.65].map((x) =>
        [-0.85, 0.85].map((z) => (
          <group key={`${x}-${z}`}>
            <Cylinder
              position={[x, 0.45, z]}
              radius={0.4}
              height={0.25}
              rotation={[Math.PI / 2, 0, 0]}
              material={rubber}
            />
            <Cylinder
              position={[x, 0.45, z * 1.17]}
              radius={0.19}
              height={0.02}
              rotation={[Math.PI / 2, 0, 0]}
              material={trim}
            />
          </group>
        )),
      )}
      <Box position={[2.34, 0.85, 0]} size={[0.1, 0.18, 1.8]} material={trim} />
    </group>
  );
}
