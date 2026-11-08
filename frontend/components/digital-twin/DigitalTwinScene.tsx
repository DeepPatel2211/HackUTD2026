"use client";
import { Component, useEffect, useMemo, useRef, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { AdaptiveDpr, Environment, Lightformer } from "@react-three/drei";
import * as THREE from "three";
import type {
  CameraIntent,
  Dashboard,
  Navigation,
  Selection,
} from "../../lib/types";
import type { SceneGraph } from "../../lib/scene-layout";
import type { SceneInteractions } from "./FacilityScene";
import CameraController from "./CameraController";
import { LabelPortal } from "./AssetLabel";
import SystemScene from "./SystemScene";
import GroundPlane from "./GroundPlane";

function Unavailable({ message }: { message?: string }) {
  return (
    <div className="scene-unavailable">
      <span className="technical-label">RENDERER UNAVAILABLE</span>
      <h2>3D view needs WebGL.</h2>
      <p>
        {message ||
          "Enable hardware acceleration or use a WebGL-capable browser. Incident details, telemetry and replay remain available."}
      </p>
      <button className="ui-button" onClick={() => window.dispatchEvent(new Event("nightshift:retry-renderer"))}>
        Retry 3D view
      </button>
    </div>
  );
}
class SceneBoundary extends Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? <Unavailable /> : this.props.children;
  }
}
function ContextMonitor({
  onLost,
  topology,
}: {
  onLost: (lost: boolean) => void;
  topology: string;
}) {
  const gl = useThree((s) => s.gl);
  const invalidate = useThree((s) => s.invalidate);
  const warmupFrames = useRef(3);
  useFrame(() => {
    if (warmupFrames.current > 0) {
      gl.shadowMap.needsUpdate = true;
      warmupFrames.current--;
      invalidate();
    }
  });
  useEffect(() => {
    // Equipment is stationary: reuse its shadow map while flow markers animate.
    gl.shadowMap.autoUpdate = false;
    // Environment capture can consume the first invalidation: warm the main scene too.
    warmupFrames.current = 3;
    gl.shadowMap.needsUpdate = true;
    invalidate();
  }, [gl, topology, invalidate]);
  useEffect(() => {
    const lost = (event: Event) => {
      event.preventDefault();
      onLost(true);
    };
    const restored = () => onLost(false);
    gl.domElement.addEventListener("webglcontextlost", lost);
    gl.domElement.addEventListener("webglcontextrestored", restored);
    return () => {
      gl.domElement.removeEventListener("webglcontextlost", lost);
      gl.domElement.removeEventListener("webglcontextrestored", restored);
    };
  }, [gl, onLost]);
  return null;
}

/** Move the key and its shadow frustum with the visible system, not the whole field. */
function SceneLighting({ graph, navigation }: { graph: SceneGraph; navigation: Navigation }) {
  const system = graph.systems.find(s => s.system.id === navigation.systemId);
  const [x, , z] = system?.position || graph.center;
  const extent = system ? Math.max(system.width, system.depth) * 0.78 : graph.radius * 1.5;
  const target = useMemo(() => {
    const object = new THREE.Object3D();
    object.position.set(x, 0, z);
    return object;
  }, [x, z]);
  return <>
    <primitive object={target}/>
    <ambientLight intensity={0.25}/>
    <hemisphereLight args={["#bfd4e0", "#263746", 0.5]}/>
    <directionalLight key={system?.system.id || "network"} target={target}
      position={[x + 42, 64, z + 24]} intensity={2.4} color="#fff1d9" castShadow
      shadow-mapSize={system ? [2048, 2048] : [1024, 1024]}
      shadow-camera-left={-extent} shadow-camera-right={extent}
      shadow-camera-top={extent} shadow-camera-bottom={-extent}
      shadow-camera-near={1} shadow-camera-far={700}
      shadow-bias={-0.00015} shadow-normalBias={0.025} shadow-radius={3}/>
    <directionalLight target={target} position={[x - 40, 22, z + 35]} intensity={0.7} color="#b5d8ef"/>
    <directionalLight target={target} position={[x + 12, 35, z - 35]} intensity={0.8} color="#c7e1e9"/>
    <Environment resolution={64} frames={1}>
      <Lightformer form="rect" intensity={1.5} position={[0, 20, 0]} scale={[30, 22, 1]}
        rotation={[Math.PI / 2, 0, 0]} color="#e3edf2"/>
      <Lightformer form="rect" intensity={2.4} position={[8, 10, 18]} scale={[9, 20, 1]}
        rotation={[0, Math.PI, 0]} color="#c2dce9"/>
      <Lightformer form="rect" intensity={1.2} position={[-18, 7, 0]} scale={[8, 16, 1]}
        rotation={[0, Math.PI / 2, 0]} color="#ffe8c9"/>
    </Environment>
  </>;
}

function AnimationTicker({ active }: { active: boolean }) {
  const invalidate = useThree(state => state.invalidate);
  useEffect(() => {
    if (!active) return;
    // Camera controls request their own frames; ambient animations need only 30fps.
    const timer = window.setInterval(() => {
      if (document.visibilityState === "visible") invalidate();
    }, 1000 / 30);
    return () => window.clearInterval(timer);
  }, [active, invalidate]);
  return null;
}

export default function DigitalTwinScene({
  graph,
  data,
  navigation,
  selection,
  intent,
  interactions,
  inspectorOpen = false,
}: {
  graph: SceneGraph;
  data: Dashboard;
  navigation: Navigation;
  selection: Selection | null;
  intent: CameraIntent;
  interactions: SceneInteractions;
  inspectorOpen?: boolean;
}) {
  const [contextLost, setContextLost] = useState(false);
  const [rendererKey, setRendererKey] = useState(0);
  useEffect(() => {
    const retry = () => { setContextLost(false); setRendererKey(key => key + 1); };
    window.addEventListener("nightshift:retry-renderer", retry);
    return () => window.removeEventListener("nightshift:retry-renderer", retry);
  }, []);
  const labelPortal = useRef<HTMLDivElement>(null!);
  const visibleSystem = graph.systems.find(system => system.system.id === navigation.systemId);
  return (
    <SceneBoundary key={rendererKey}>
      <div
        className="webgl-surface"
        aria-label="Interactive oilfield digital twin. Drag to orbit, scroll to zoom, right-drag to pan."
      >
        <Canvas
          frameloop="demand"
          shadows="percentage"
          dpr={[1, 1.25]}
          performance={{ min: 0.7, max: 1, debounce: 250 }}
          camera={{
            position: [110, 130, 110],
            fov: 42,
            near: 0.2,
            far: Math.max(2500, graph.radius * 15),
          }}
          gl={{
            antialias: true,
            alpha: false,
            powerPreference: "high-performance",
            toneMapping: THREE.ACESFilmicToneMapping,
            toneMappingExposure: 1.18,
          }}
          fallback={<Unavailable />}
        >
          <LabelPortal.Provider value={labelPortal}>
            <color attach="background" args={["#11212d"]} />
            <fog
              attach="fog"
              args={["#11212d", graph.radius * 5, graph.radius * 12]}
            />
            <SceneLighting graph={graph} navigation={navigation}/>
            <GroundPlane size={graph.radius * 12} center={visibleSystem ? [visibleSystem.position[0], visibleSystem.position[2]] : [0, 0]} radius={visibleSystem ? Math.max(visibleSystem.width, visibleSystem.depth) * 1.8 : graph.radius * 2}/>
            {graph.systems.filter(system => !navigation.systemId || system.system.id === navigation.systemId).map((system) => (
              <SystemScene
                key={system.system.id}
                layout={system}
                graph={graph}
                data={data}
                navigation={navigation}
                selection={selection}
                interactions={interactions}
              />
            ))}
            <CameraController intent={intent} sceneRadius={graph.radius} inspectionOpen={inspectorOpen}/>
            <AdaptiveDpr/>
            <AnimationTicker active={data.facilities.some(f => f.pump_status === 1 || f.category === "pump_failure")}/>
            <ContextMonitor
              onLost={setContextLost}
              topology={"site-pads-3:" + data.start + ":" + data.end + ":" + (navigation.systemId || "all") + ":" + (navigation.facilityId || "all") + ":" + graph.systems
                .map(
                  (s) =>
                    `${s.system.id}:${s.facilities.map((f) => `${f.facility.id}:${f.facility.wells.length}`).join(",")}`,
                )
                .join("|")}
            />
          </LabelPortal.Provider>
        </Canvas>
        <div className="scene-labels" ref={labelPortal} />
        {contextLost && (
          <Unavailable message="The graphics context was lost. It may recover automatically; reload if the scene does not return." />
        )}
      </div>
    </SceneBoundary>
  );
}
