"use client";
import { useEffect, useMemo, useRef } from "react";
import { CameraControls, CameraControlsImpl } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { Box3, MathUtils, Vector3 } from "three";
import type { CameraIntent } from "../../lib/types";

/** Intent is the sole camera interface, so future input devices can issue the same commands. */
export default function CameraController({
  intent,
  sceneRadius,
  inspectionOpen = false,
}: {
  intent: CameraIntent;
  sceneRadius: number;
  inspectionOpen?: boolean;
}) {
  const controls = useRef<CameraControls>(null);
  const { size } = useThree();
  const initialized = useRef(false);
  const lastNavigation = useRef<number | null>(null);
  const framing = useMemo(() => {
    const aspect = size.width / Math.max(size.height, 1);
    const halfFov = (42 * Math.PI) / 360;
    const limitingFov = Math.min(
      halfFov,
      Math.atan(Math.tan(halfFov) * aspect),
    );
    const fittedDistance = intent.radius / Math.sin(limitingFov);
    // Allow local inspection inside a large view, independently of screen aspect.
    const minDistance = Math.max(10, intent.radius * 1.25);
    const maxDistance = Math.max(minDistance + 8, fittedDistance * 1.3);
    // Start closer to fill the stage; portrait screens retain extra framing room.
    const presentationPadding = aspect < 1 ? 0.85 : 0.65;
    return { distance: MathUtils.clamp(fittedDistance * presentationPadding, minDistance, maxDistance), minDistance, maxDistance };
  }, [intent.radius, size.width, size.height]);
  useEffect(() => {
    const c = controls.current;
    if (!c) return;
    c.minDistance = framing.minDistance;
    c.maxDistance = framing.maxDistance;
    const [x, y, z] = intent.target;
    // Include the board's perimeter, so any corner can become the orbit center.
    const panRadius = Math.max(6, Math.min(sceneRadius * 1.5, intent.radius * 1.25));
    c.setBoundary(new Box3(
      new Vector3(x - panRadius, 0, z - panRadius),
      new Vector3(x + panRadius, Math.max(3, y + 1.5), z + panRadius),
    ));
    // Resizing the canvas may update limits, but must not undo the user's pan/orbit.
    if (initialized.current && lastNavigation.current === intent.revision) return;
    lastNavigation.current = intent.revision;
    const direction = new Vector3(0.64, 0.58, 0.52).normalize();
    const offset = direction.clone().multiplyScalar(framing.distance);
    const aim = new Vector3(x, y, z);
    if (inspectionOpen) {
      const unitsPerPixel = 2 * Math.tan(42 * Math.PI / 360) * framing.distance / Math.max(1, size.height);
      const right = new Vector3(direction.z, 0, -direction.x).normalize();
      if (size.width >= 700) {
        aim.addScaledVector(right, Math.min(380, size.width * 0.42) / 2 * unitsPerPixel);
      } else {
        const forward = new Vector3(direction.x, 0, direction.z).normalize();
        aim.addScaledVector(forward, Math.min(240, size.height * 0.4) / 2 * unitsPerPixel / direction.y);
      }
    }
    // Optical framing accounts for the actual canvas and inspector, without changing input mapping.
    void c.setLookAt(aim.x + offset.x, aim.y + offset.y, aim.z + offset.z,
      aim.x, aim.y, aim.z, initialized.current);
    initialized.current = true;
  }, [intent, framing, sceneRadius, inspectionOpen, size.width, size.height]);
  return (
    <CameraControls
      ref={controls}
      makeDefault
      smoothTime={0.18}
      draggingSmoothTime={0.06}
      regress
      minDistance={framing.minDistance}
      maxDistance={framing.maxDistance}
      minPolarAngle={MathUtils.degToRad(40)}
      maxPolarAngle={MathUtils.degToRad(69)}
      boundaryFriction={0.15}
      boundaryEnclosesCamera={false}
      mouseButtons={{
        left: CameraControlsImpl.ACTION.ROTATE,
        middle: CameraControlsImpl.ACTION.SCREEN_PAN,
        right: CameraControlsImpl.ACTION.SCREEN_PAN,
        wheel: CameraControlsImpl.ACTION.DOLLY,
      }}
      azimuthRotateSpeed={0.65}
      polarRotateSpeed={0.65}
      dollySpeed={0.65}
      dollyToCursor={false}
      truckSpeed={0.85}
      infinityDolly={false}
    />
  );
}
