"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import type { VehicleAsset } from "@/lib/vehicle-models";
import { zoneNames } from "@/lib/vehicle-models";

type CameraRig = { camera: THREE.PerspectiveCamera; controls: OrbitControls; render: () => void };

export function VehicleViewport({ asset, selectedZone, paint, responses, pinColors, onSelect }: {
  asset: VehicleAsset;
  selectedZone: string;
  paint: string;
  responses: Record<string, { treatment?: string }>;
  pinColors: Record<string, string>;
  onSelect: (zone: string) => void;
}) {
  const stageRef = useRef<HTMLDivElement>(null);
  const pinRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const rigRef = useRef<CameraRig | null>(null);
  const paintRef = useRef<THREE.MeshStandardMaterial[]>([]);
  const paintValueRef = useRef(paint);
  const selectedRef = useRef(selectedZone);
  const renderRef = useRef<(() => void) | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "fallback">("loading");
  const [message, setMessage] = useState("");
  const manifest = asset.manifest;

  useEffect(() => { paintValueRef.current = paint; }, [paint]);
  useEffect(() => { selectedRef.current = selectedZone; }, [selectedZone]);

  useEffect(() => {
    const host = stageRef.current;
    if (!host) return;
    let disposed = false;
    let frame = 0;
    let vehicle: THREE.Object3D | null = null;
    let renderer: THREE.WebGLRenderer;
    const anchors = new Map<string, THREE.Vector3>();
    const replacedMaterials = new Set<THREE.Material>();
    const draco = new DRACOLoader().setDecoderPath("/draco/");

    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch {
      frame = window.requestAnimationFrame(() => {
        setState("fallback");
        setMessage("3D rendering is unavailable on this device. Use the zone list to explore the same requirements.");
      });
      draco.dispose();
      return () => window.cancelAnimationFrame(frame);
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.45;
    renderer.domElement.className = "vehicle-canvas";
    renderer.domElement.setAttribute("aria-hidden", "true");
    host.prepend(renderer.domElement);

    const scene = new THREE.Scene();
    scene.add(new THREE.HemisphereLight(0xffffff, 0x8292a0, 2.4));
    const key = new THREE.DirectionalLight(0xffffff, 3);
    key.position.set(-4, 8, 6);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xbcd6ff, 1.35);
    fill.position.set(5, 4, -6);
    scene.add(fill);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.03, 60);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enablePan = false;
    controls.minDistance = 2.5;
    controls.maxDistance = 13;
    controls.maxPolarAngle = Math.PI * 0.8;

    const updatePins = () => {
      const rect = host.getBoundingClientRect();
      for (const [id, point] of anchors) {
        const button = pinRefs.current[id];
        if (!button) continue;
        const projected = point.clone().project(camera);
        const shown = projected.z > -1 && projected.z < 1 &&
          (manifest.zones[id].geometry === "exterior_surface" || id === "charging" || id === selectedRef.current);
        button.style.visibility = shown ? "visible" : "hidden";
        if (shown) {
          button.style.left = `${(projected.x + 1) * rect.width / 2}px`;
          button.style.top = `${(1 - projected.y) * rect.height / 2}px`;
        }
      }
    };
    const render = () => {
      if (disposed) return;
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      if (renderer.domElement.width !== Math.floor(width * renderer.getPixelRatio()) || renderer.domElement.height !== Math.floor(height * renderer.getPixelRatio())) {
        renderer.setSize(width, height, false);
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
      }
      renderer.render(scene, camera);
      updatePins();
    };
    const scheduleRender = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => { frame = 0; render(); });
    };
    controls.addEventListener("change", scheduleRender);
    const resize = new ResizeObserver(scheduleRender);
    resize.observe(host);
    rigRef.current = { camera, controls, render: scheduleRender };
    renderRef.current = scheduleRender;
    const initial = manifest.cameras[manifest.zones[selectedRef.current]?.camera || "default_orbit"] || manifest.cameras.default_orbit;
    camera.position.fromArray(initial.position);
    camera.fov = initial.fov;
    controls.target.fromArray(initial.target);
    controls.update();
    scheduleRender();

    const loader = new GLTFLoader().setDRACOLoader(draco);
    void loader.loadAsync(`${asset.base}/${manifest.files.model.path}`).then((gltf) => {
      if (disposed) {
        gltf.scene.traverse((object) => {
          if (object instanceof THREE.Mesh) {
            object.geometry.dispose();
            const materials = Array.isArray(object.material) ? object.material : [object.material];
            materials.forEach((material) => material.dispose());
          }
        });
        return;
      }
      vehicle = gltf.scene;
      vehicle.updateMatrixWorld(true);
      for (const [id, zone] of Object.entries(manifest.zones)) {
        const anchor = vehicle.getObjectByName(zone.anchor);
        if (anchor) anchors.set(id, anchor.getWorldPosition(new THREE.Vector3()));
      }
      vehicle.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        if (materials.some((material) => manifest.rendering.paintMaterials.includes(material.name))) {
          object.material = materials.map((material) => {
            if (!manifest.rendering.paintMaterials.includes(material.name)) return material;
            const clone = material.clone() as THREE.MeshStandardMaterial;
            clone.color.set(paintValueRef.current);
            replacedMaterials.add(material);
            paintRef.current.push(clone);
            return clone;
          });
          if (!Array.isArray(object.material) || object.material.length === 1) object.material = object.material[0];
        }
      });
      scene.add(vehicle);
      setState("ready");
      scheduleRender();
    }).catch((error: unknown) => {
      if (disposed) return;
      setState("fallback");
      setMessage(error instanceof Error ? `Model could not load: ${error.message}` : "Model could not load.");
    });

    return () => {
      disposed = true;
      if (frame) window.cancelAnimationFrame(frame);
      resize.disconnect();
      controls.removeEventListener("change", scheduleRender);
      controls.dispose();
      rigRef.current = null;
      renderRef.current = null;
      paintRef.current = [];
      if (vehicle) vehicle.traverse((object) => {
        if (!(object instanceof THREE.Mesh)) return;
        object.geometry.dispose();
        const materials = Array.isArray(object.material) ? object.material : [object.material];
        materials.forEach((material) => material.dispose());
      });
      replacedMaterials.forEach((material) => material.dispose());
      draco.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    };
  }, [asset, manifest]);

  useEffect(() => {
    if (paintRef.current.length) {
      paintRef.current.forEach((material) => material.color.set(paint));
      renderRef.current?.();
    }
  }, [paint]);

  useEffect(() => {
    const rig = rigRef.current;
    const zone = manifest.zones[selectedZone];
    if (!rig || !zone) return;
    const preset = manifest.cameras[zone.camera];
    if (!preset) return;
    rig.camera.position.fromArray(preset.position);
    rig.camera.fov = preset.fov;
    rig.camera.near = preset.near;
    rig.camera.far = preset.far;
    rig.camera.updateProjectionMatrix();
    rig.controls.target.fromArray(preset.target);
    rig.controls.update();
    rig.render();
  }, [manifest, selectedZone]);

  return <div className="vehicle-stage" ref={stageRef}>
    <div className="vehicle-stage-glow" aria-hidden="true" />
    {state !== "ready" && <div className="vehicle-stage-poster">
      {/* The licensed poster is kept beside the model and carries the same attribution below. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`${asset.base}/${state === "fallback" ? manifest.files.fallback.path : manifest.files.poster.path}`} alt={`${manifest.vehicle.code} vehicle ${state === "fallback" ? "schematic" : "preview"}`} />
      {state === "loading" ? <p>Loading interactive vehicle…</p> : <p role="status">{message}</p>}
    </div>}
    {Object.keys(manifest.zones).map((id) => <button
      key={id}
      ref={(node) => { pinRefs.current[id] = node; }}
      type="button"
      className="vehicle-pin"
      data-selected={id === selectedZone}
      data-treatment={responses[id]?.treatment || ""}
      aria-label={`Explore ${zoneNames[id] || id} on ${manifest.vehicle.code}`}
      onClick={() => onSelect(id)}
      style={{ visibility: "hidden", "--pin-color": pinColors[id] || "#8c9aa6" } as React.CSSProperties}
    ><span /></button>)}
    <span className="vehicle-stage-hint">Drag to rotate · Scroll to zoom</span>
  </div>;
}
