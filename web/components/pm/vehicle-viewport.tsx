"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { VehicleAsset } from "@/lib/vehicle-models";
import { zoneNames } from "@/lib/vehicle-models";
import { disposeVehicle, fittedCameraPosition, studioEnvironment, studioMaterial } from "@/lib/vehicle-rendering";

type CameraView = { mode: "overview" | "focus"; revision: number };
type CameraRig = { show: (zone: string, mode: CameraView["mode"], animate?: boolean) => void };
type CameraPose = { position: THREE.Vector3; target: THREE.Vector3; fov: number };

export function VehicleViewport({ asset, selectedZone, paint, responses, pinColors, onSelect, cameraView }: {
  asset: VehicleAsset;
  selectedZone: string;
  paint: string;
  responses: Record<string, { treatment?: string }>;
  pinColors: Record<string, string>;
  onSelect: (zone: string) => void;
  cameraView?: CameraView;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const pinRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const rigRef = useRef<CameraRig | null>(null);
  const paintRef = useRef<THREE.MeshStandardMaterial[]>([]);
  const paintValueRef = useRef(paint);
  const selectedRef = useRef(selectedZone);
  const viewRef = useRef(cameraView);
  const renderRef = useRef<(() => void) | null>(null);
  const previousZone = useRef(selectedZone);
  const [state, setState] = useState<"loading" | "ready" | "fallback">("loading");
  const [message, setMessage] = useState("");
  const manifest = asset.manifest;

  useEffect(() => { paintValueRef.current = paint; }, [paint]);
  useEffect(() => { selectedRef.current = selectedZone; }, [selectedZone]);
  useEffect(() => { viewRef.current = cameraView; }, [cameraView]);

  useEffect(() => {
    const host = stageRef.current;
    if (!host) return;
    let disposed = false;
    let frame = 0;
    let vehicle: THREE.Object3D | null = null;
    let renderer: THREE.WebGLRenderer;
    let modelBounds: THREE.Box3 | null = null;
    let viewMode: CameraView["mode"] = "overview";
    let manuallyMoved = false;
    let transition: { from: CameraPose; to: CameraPose; start: number } | null = null;
    const anchors = new Map<string, THREE.Vector3>();
    const replacedMaterials = new Set<THREE.Material>();
    const draco = new DRACOLoader().setDecoderPath("/draco/");
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch {
      frame = window.requestAnimationFrame(() => {
        setState("fallback");
        setMessage("3D is unavailable on this device. Choose a zone to explore its requirements.");
      });
      draco.dispose();
      return () => window.cancelAnimationFrame(frame);
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.shadowMap.autoUpdate = false;
    renderer.domElement.className = "vehicle-canvas";
    renderer.domElement.setAttribute("aria-hidden", "true");
    host.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    const environment = studioEnvironment(renderer);
    scene.environment = environment.texture;
    scene.environmentIntensity = 0.9;
    scene.add(new THREE.HemisphereLight(0xf7faff, 0x7e838a, 0.8));
    const key = new THREE.DirectionalLight(0xffffff, 1.35);
    key.position.set(-3, 7, 5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.left = -5;
    key.shadow.camera.right = 5;
    key.shadow.camera.top = 5;
    key.shadow.camera.bottom = -5;
    key.shadow.camera.near = 0.5;
    key.shadow.camera.far = 20;
    key.shadow.normalBias = 0.025;
    key.shadow.bias = -0.0002;
    key.shadow.radius = 4;
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xe2ebff, 0.45);
    fill.position.set(5, 3, -4);
    scene.add(fill);
    const ground = new THREE.Mesh(new THREE.PlaneGeometry(80, 80), new THREE.ShadowMaterial({ color: 0x39444e, opacity: 0.18 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.015;
    ground.receiveShadow = true;
    scene.add(ground);

    // A soft, local contact shadow anchors the chassis between the wheel shadows.
    const shadowCanvas = document.createElement("canvas");
    shadowCanvas.width = shadowCanvas.height = 128;
    const context = shadowCanvas.getContext("2d");
    if (context) {
      const gradient = context.createRadialGradient(64, 64, 18, 64, 64, 64);
      gradient.addColorStop(0, "rgba(27,34,41,0.28)");
      gradient.addColorStop(0.6, "rgba(27,34,41,0.17)");
      gradient.addColorStop(1, "rgba(27,34,41,0)");
      context.fillStyle = gradient;
      context.fillRect(0, 0, 128, 128);
    }
    const contactTexture = new THREE.CanvasTexture(shadowCanvas);
    const contact = new THREE.Mesh(new THREE.PlaneGeometry(3.1, 6.4), new THREE.MeshBasicMaterial({ map: contactTexture, transparent: true, depthWrite: false }));
    contact.rotation.x = -Math.PI / 2;
    contact.position.y = -0.01;
    scene.add(contact);

    const camera = new THREE.PerspectiveCamera(32, 1, 0.03, 100);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.minDistance = 2.5;
    controls.maxDistance = 24;
    controls.minPolarAngle = Math.PI * 0.1;
    controls.maxPolarAngle = Math.PI * 0.49;
    controls.rotateSpeed = 0.7;
    controls.zoomSpeed = 0.8;

    const updatePins = () => {
      for (const [id, point] of anchors) {
        const button = pinRefs.current[id];
        if (!button) continue;
        const projected = point.clone().project(camera);
        const shown = projected.z > -1 && projected.z < 1 && Math.abs(projected.x) < 0.95 && Math.abs(projected.y) < 0.95 &&
          (manifest.zones[id].geometry === "exterior_surface" || id === "charging" || id === selectedRef.current);
        button.style.visibility = shown ? "visible" : "hidden";
        if (shown) {
          button.style.left = `${(projected.x + 1) * host.clientWidth / 2}px`;
          button.style.top = `${(1 - projected.y) * host.clientHeight / 2}px`;
        }
      }
    };
    const poseFor = (zone: string, mode: CameraView["mode"]): CameraPose => {
      const base = manifest.cameras.default_orbit;
      const preset = mode === "focus" ? manifest.cameras[manifest.zones[zone]?.camera] || base : base;
      const target = new THREE.Vector3().fromArray(preset.target);
      const direction = new THREE.Vector3().fromArray(preset.position).sub(target);
      const overview = mode === "overview" || preset === base;
      if (modelBounds && overview) {
        modelBounds.getCenter(target);
        return { target, fov: 32, position: fittedCameraPosition(modelBounds, target, direction, 32, camera.aspect) };
      }
      // Preserve authored zone angles and targets, widening on portrait displays.
      const distance = direction.length() * Math.max(1, 0.95 / camera.aspect);
      return { target, fov: preset.fov, position: target.clone().addScaledVector(direction.normalize(), distance) };
    };
    const applyPose = (pose: CameraPose) => {
      camera.position.copy(pose.position);
      controls.target.copy(pose.target);
      camera.fov = pose.fov;
      camera.updateProjectionMatrix();
      controls.update();
    };
    const render = (now: number) => {
      if (disposed) return;
      if (transition) {
        const progress = Math.min((now - transition.start) / 650, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const fromOrbit = new THREE.Spherical().setFromVector3(transition.from.position.clone().sub(transition.from.target));
        const toOrbit = new THREE.Spherical().setFromVector3(transition.to.position.clone().sub(transition.to.target));
        // Travel around the body when changing sides, rather than through it.
        const thetaDelta = Math.atan2(Math.sin(toOrbit.theta - fromOrbit.theta), Math.cos(toOrbit.theta - fromOrbit.theta));
        const orbit = new THREE.Spherical(
          THREE.MathUtils.lerp(fromOrbit.radius, toOrbit.radius, eased),
          THREE.MathUtils.lerp(fromOrbit.phi, toOrbit.phi, eased),
          fromOrbit.theta + thetaDelta * eased,
        );
        const target = transition.from.target.clone().lerp(transition.to.target, eased);
        applyPose({
          position: new THREE.Vector3().setFromSpherical(orbit).add(target),
          target,
          fov: THREE.MathUtils.lerp(transition.from.fov, transition.to.fov, eased),
        });
        if (progress === 1) transition = null;
      }
      renderer.render(scene, camera);
      updatePins();
      if (transition) scheduleRender();
    };
    const scheduleRender = () => {
      if (frame || disposed) return;
      frame = window.requestAnimationFrame((now) => { frame = 0; render(now); });
    };
    const show = (zone: string, mode: CameraView["mode"], animate = true) => {
      viewMode = mode;
      manuallyMoved = false;
      const to = poseFor(zone, mode);
      if (animate && !reducedMotion.matches) {
        transition = { from: { position: camera.position.clone(), target: controls.target.clone(), fov: camera.fov }, to, start: performance.now() };
      } else {
        transition = null;
        applyPose(to);
      }
      scheduleRender();
    };
    const resizeStage = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      if (!manuallyMoved) show(selectedRef.current, viewMode, false);
      scheduleRender();
    };
    const beginOrbit = () => { transition = null; manuallyMoved = true; };
    controls.addEventListener("start", beginOrbit);
    controls.addEventListener("change", scheduleRender);
    const resize = new ResizeObserver(resizeStage);
    resize.observe(host);
    rigRef.current = { show };
    renderRef.current = scheduleRender;
    resizeStage();

    const loader = new GLTFLoader().setDRACOLoader(draco);
    void loader.loadAsync(`${asset.base}/${manifest.files.model.path}`).then((gltf) => {
      if (disposed) { disposeVehicle(gltf.scene); return; }
      vehicle = gltf.scene;
      vehicle.updateMatrixWorld(true);
      modelBounds = new THREE.Box3().setFromObject(vehicle);
      const refined = new Map<THREE.Material, THREE.Material>();
      for (const [id, zone] of Object.entries(manifest.zones)) {
        const anchor = vehicle.getObjectByName(zone.anchor);
        if (anchor) anchors.set(id, anchor.getWorldPosition(new THREE.Vector3()));
      }
      vehicle.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        object.castShadow = true;
        object.receiveShadow = true;
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        const replacements = materials.map((material) => {
          if (!(material instanceof THREE.MeshStandardMaterial)) return material;
          if (!refined.has(material)) {
            const isPaint = manifest.rendering.paintMaterials.includes(material.name);
            const replacement = studioMaterial(material, paintValueRef.current, isPaint);
            refined.set(material, replacement);
            replacedMaterials.add(material);
            if (isPaint) paintRef.current.push(replacement);
          }
          return refined.get(material)!;
        });
        object.material = Array.isArray(object.material) ? replacements : replacements[0];
      });
      scene.add(vehicle);
      renderer.shadowMap.needsUpdate = true;
      show(selectedRef.current, viewRef.current?.mode || "overview", false);
      setState("ready");
    }).catch(() => {
      if (disposed) return;
      setState("fallback");
      setMessage("The 3D model could not load. Choose a zone to explore its requirements.");
    });

    return () => {
      disposed = true;
      if (frame) window.cancelAnimationFrame(frame);
      resize.disconnect();
      controls.removeEventListener("start", beginOrbit);
      controls.removeEventListener("change", scheduleRender);
      controls.dispose();
      rigRef.current = null;
      renderRef.current = null;
      paintRef.current = [];
      disposeVehicle(scene, replacedMaterials);
      environment.dispose();
      key.shadow.dispose();
      draco.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, [asset, manifest]);

  useEffect(() => {
    paintRef.current.forEach((material) => material.color.set(paint));
    renderRef.current?.();
  }, [paint]);

  useEffect(() => {
    const changedZone = previousZone.current !== selectedZone;
    previousZone.current = selectedZone;
    if (cameraView || changedZone) rigRef.current?.show(selectedZone, cameraView?.mode || "focus");
    else renderRef.current?.();
  }, [selectedZone, cameraView]);

  return <div className="vehicle-stage" ref={stageRef}>
    {state !== "ready" && <div className="vehicle-stage-poster">
      {/* The licensed poster is kept beside the model and carries the same attribution below. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`${asset.base}/${state === "fallback" ? manifest.files.fallback.path : manifest.files.poster.path}`} alt={`${manifest.vehicle.code} vehicle ${state === "fallback" ? "schematic" : "preview"}`} />
      {state === "loading" ? <p role="status">Loading 3D model…</p> : <p role="status">{message}</p>}
    </div>}
    {Object.keys(manifest.zones).map((id) => <button
      key={id}
      ref={(node) => { pinRefs.current[id] = node; }}
      type="button"
      className="vehicle-pin"
      data-selected={id === selectedZone}
      data-treatment={responses[id]?.treatment || ""}
      aria-label={`Explore ${zoneNames[id] || id} on ${manifest.vehicle.code}`}
      title={zoneNames[id] || id}
      onClick={() => onSelect(id)}
      style={{ visibility: "hidden", "--pin-color": pinColors[id] || "#8c9aa6" } as React.CSSProperties}
    ><span /></button>)}
    <span className="vehicle-stage-hint">Drag to rotate · Scroll or pinch to zoom</span>
  </div>;
}
