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
}: {
  intent: CameraIntent;
  sceneRadius: number;
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
    const offset = new Vector3(0.64, 0.58, 0.52).normalize().multiplyScalar(framing.distance);
    // Keep an isometric approach while fitting the limiting viewport dimension.
    void c.setLookAt(
      x + offset.x,
      y + offset.y,
      z + offset.z,
      x,
      y,
      z,
      initialized.current,
    );
    initialized.current = true;
  }, [intent, framing, sceneRadius]);
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
