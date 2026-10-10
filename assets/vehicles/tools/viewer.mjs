import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { DRACOLoader } from "three/addons/loaders/DRACOLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
const $ = (id) => document.getElementById(id),
  manifest = await fetch("../g60-us/manifest.json").then((r) => r.json());
$("attribution").textContent = manifest.licence.attribution;
const sourceLink = document.createElement("a");
sourceLink.href = manifest.source.url;
sourceLink.textContent = " Source";
$("attribution").append(sourceLink);
const ccLink = document.createElement("a");
ccLink.href = manifest.licence.url;
ccLink.textContent = " CC BY 4.0";
$("attribution").append(ccLink);
const link = document.createElement("a");
link.href = "../g60-us/LICENSE.txt";
link.textContent = " Licence";
$("attribution").append(link);
const stage = $("stage"),
  fallback = $("fallback"),
  pins = $("pins"),
  metrics = $("metrics");
let renderer,
  scene,
  camera,
  controls,
  model,
  selected,
  showFallback = false,
  lastTime = 0,
  frames = [],
  benchStarted = false,
  selectionSerial = 0;
const buttons = new Map(),
  anchorWorld = new Map();
function setStatus(text) {
  $("status").textContent = text;
}
function escapeText(tag, text, parent) {
  let el = document.createElement(tag);
  el.textContent = text;
  parent.append(el);
  return el;
}
async function json(path) {
  let r = await fetch("/api" + path, { cache: "no-store" });
  if (!r.ok) throw Error(`API ${r.status}: ${await r.text()}`);
  return r.json();
}
async function requirements() {
  let out = [],
    offset = 0;
  while (true) {
    let d = await json(
      `/requirements?vehicle=G60&market=US&limit=1000&offset=${offset}`,
    );
    out.push(...d.items);
    if (out.length >= d.total || !d.items.length) return out;
    offset += d.items.length;
  }
}
function cutaway(on) {
  $("cutaway").checked = on;
  if (!model) return;
  for (let name of manifest.rendering.cutawayHide) {
    let n = model.getObjectByName(name);
    if (n) n.visible = !on;
  }
  render();
}
function preset(name) {
  let p = manifest.cameras[name];
  $("cameraNote").textContent = ["cockpit", "seats", "rear_cabin"].includes(
    name,
  )
    ? "Exterior window view only. Cabin, seating and cargo locations are approximate; no interior geometry."
    : "";
  if (!camera) return;
  camera.position.fromArray(p.position);
  camera.fov = p.fov;
  camera.near = p.near;
  camera.far = p.far;
  camera.updateProjectionMatrix();
  controls.target.fromArray(p.target);
  controls.update();
  render();
}
for (const name of Object.keys(manifest.cameras)) {
  let b = escapeText("button", name.replaceAll("_", " "), $("cameras"));
  b.dataset.camera = name;
  b.onclick = () => preset(name);
}
async function selectZone(id) {
  let serial = ++selectionSerial;
  selected = id;
  $("zoneSelect").value = id;
  for (let [key, b] of buttons) b.dataset.selected = String(id === key);
  let z = manifest.zones[id];
  preset(z.camera);
  $("zoneTitle").textContent = id.replaceAll("_", " ");
  if (
    [
      "battery_range",
      "seats_front",
      "rear_cabin",
      "cockpit",
      "infotainment",
      "acoustics",
      "cargo",
    ].includes(id)
  )
    $("cutaway").checked = true;
  $("approx").textContent = z.approximation;
  $("data").replaceChildren();
  escapeText("p", "Loading G60 / US requirements…", $("data"));
  setStatus(`Selected ${id} · topics: ${z.topics.join(", ")}`);
  render();
  try {
    let all = await requirements();
    if (serial !== selectionSerial) return;
    let rows = all.filter(
      (r) =>
        r.vehicle === "G60" && r.market === "US" && z.topics.includes(r.topic),
    );
    $("data").replaceChildren();
    escapeText(
      "p",
      `${rows.length} matching requirement(s) from the live API`,
      $("data"),
    );
    for (let row of rows) {
      let b = escapeText(
        "button",
        `${row.key || row.id} · ${row.title} · score ${row.priority ?? "unavailable"} · ${row.status}`,
        $("data"),
      );
      b.dataset.requirement = row.id;
      b.onclick = () => trace(row, serial);
    }
    if (!rows.length)
      escapeText(
        "p",
        "No matching requirements. No evidence or scores are invented.",
        $("data"),
      );
  } catch (e) {
    if (serial === selectionSerial) {
      $("data").textContent = e.message;
    }
  }
}
async function trace(row, serial) {
  try {
    const base = `/requirements/${encodeURIComponent(row.id)}/trace`;
    const d = await json(base + "?limit=1000");
    while (d.evidence.items.length < d.evidence.total) {
      const next = await json(
        base + `?limit=1000&offset=${d.evidence.items.length}`,
      );
      if (!next.evidence.items.length) break;
      d.evidence.items.push(...next.evidence.items);
    }
    const auditBase = `/audit?entity_id=${encodeURIComponent(row.id)}&limit=1000`,
      a = await json(auditBase);
    let cursor = a.next_after,
      pageSize = a.items.length;
    while (pageSize === 1000 && serial === selectionSerial) {
      const page = await json(
        auditBase + `&after=${encodeURIComponent(cursor)}`,
      );
      if (!page.items.length || page.next_after <= cursor) break;
      a.items.push(...page.items);
      cursor = page.next_after;
      pageSize = page.items.length;
    }
    if (serial !== selectionSerial) return;
    $("data").replaceChildren();
    escapeText("h3", `${row.key || row.id} — ${row.title}`, $("data"));
    escapeText(
      "p",
      `API score: ${d.version.score?.total ?? "unavailable"} · evidence grade: ${d.version.score?.evidence_grade ?? "unavailable"}`,
      $("data"),
    );
    for (let source of d.sources) {
      let p = escapeText(
        "p",
        `Source: ${source.title} · ${source.reference}`,
        $("data"),
      );
      if (/synthetic/i.test(source.title + " " + source.reference))
        p.className = "warning";
    }
    escapeText(
      "p",
      `Evidence ${d.evidence.items.length} of ${d.evidence.total} · decisions ${d.decisions.length} · audit events ${a.items.length}`,
      $("data"),
    );
    for (let e of d.evidence.items.slice(0, 5)) {
      let p = escapeText(
        "div",
        `${e.content}\nLocation: ${JSON.stringify(e.location)}`,
        $("data"),
      );
      p.className = "source";
    }
    for (let [title, value] of [
      ["All original evidence", d.evidence.items],
      ["Score", d.version.score],
      ["PM decisions", d.decisions],
      ["Audit history", a.items],
    ]) {
      let details = document.createElement("details");
      escapeText("summary", title, details);
      escapeText("pre", JSON.stringify(value, null, 2), details);
      $("data").append(details);
    }
    setStatus(
      "Live requirement → original source location → score → decisions → audit loaded.",
    );
  } catch (e) {
    $("data").textContent = e.message;
  }
}
const emptyOption = escapeText("option", "Select a zone…", $("zoneSelect"));
emptyOption.value = "";
emptyOption.disabled = true;
emptyOption.selected = true;
for (let [id, z] of Object.entries(manifest.zones)) {
  let o = escapeText("option", id.replaceAll("_", " "), $("zoneSelect"));
  o.value = id;
  let b = escapeText(
    "button",
    id === "charging" ? "⚡ Charging" : id.replaceAll("_", " "),
    pins,
  );
  b.className = "pin";
  b.dataset.zone = id;
  b.setAttribute("aria-label", `${id.replaceAll("_", " ")} requirements`);
  b.onclick = () => selectZone(id);
  buttons.set(id, b);
}
$("zoneSelect").onchange = (e) => selectZone(e.target.value);
$("cutaway").onchange = (e) => {
  render();
};
$("isolate").onchange = (e) => {
  model.traverse((n) => {
    if (n.isMesh)
      n.visible =
        e.target.value === "all" || n.material.name === e.target.value;
  });
  render();
};
$("paint").value =
  "#" +
  new THREE.Color()
    .fromArray(manifest.rendering.paintDefaultLinearRGB)
    .getHexString();
$("paint").oninput = (e) => {
  model?.traverse((n) => {
    if (n.material?.name === "body_paint") n.material.color.set(e.target.value);
  });
  render();
};
$("fallbackToggle").onclick = () => {
  showFallback = !showFallback;
  fallback.style.display = showFallback ? "block" : "none";
  if (renderer)
    renderer.domElement.style.display = showFallback ? "none" : "block";
  pins.style.display = showFallback ? "none" : "block";
  $("fallbackToggle").textContent = showFallback ? "3D model" : "2D fallback";
  setStatus(
    showFallback
      ? "2D schematic: use the accessible zone selector for the same live requirement actions."
      : "Drag to orbit · scroll to zoom",
  );
  render();
};
function render() {
  if (!renderer || !model || showFallback) return;
  renderer.render(scene, camera);
  for (let [id, b] of buttons) {
    let v = anchorWorld.get(id).clone().project(camera);
    b.style.left = `${(v.x * 0.5 + 0.5) * stage.clientWidth}px`;
    b.style.top = `${(-v.y * 0.5 + 0.5) * stage.clientHeight}px`;
    let interior = [
      "battery_range",
      "seats_front",
      "rear_cabin",
      "cockpit",
      "infotainment",
      "acoustics",
      "cargo",
    ].includes(id);
    const normal = manifest.zones[id].surfaceNormal;
    const backFacing =
      normal &&
      new THREE.Vector3()
        .fromArray(normal)
        .dot(camera.position.clone().sub(anchorWorld.get(id))) <= 0;
    b.style.display =
      backFacing || v.z > 1 || v.z < -1 || (interior && !$("cutaway").checked)
        ? "none"
        : "block";
  }
}
try {
  renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.88;
  stage.prepend(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(38, 1, 0.03, 60);
  const studio = new THREE.Scene();
  studio.background = new THREE.Color(0x626b78);
  for (const [position, size, intensity] of [
    [[-3, 4, 2], [6, 3], 3],
    [[4, 3, -2], [5, 3], 2],
    [[0, 6, 0], [5, 7], 2],
  ]) {
    const panel = new THREE.Mesh(
      new THREE.PlaneGeometry(...size),
      new THREE.MeshBasicMaterial({
        color: new THREE.Color().setRGB(intensity, intensity, intensity),
        side: THREE.DoubleSide,
      }),
    );
    panel.position.fromArray(position);
    panel.lookAt(0, 0.7, 0);
    studio.add(panel);
  }
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(studio, 0.16).texture;
  pmrem.dispose();
  scene.add(new THREE.HemisphereLight(0xe9f4ff, 0x5b687d, 0.75));
  let key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(-3, 7, 4);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, {
    left: -4,
    right: 4,
    top: 4,
    bottom: -4,
    near: 0.1,
    far: 20,
  });
  key.shadow.bias = -0.00015;
  key.shadow.normalBias = 0.012;
  scene.add(key);
  let fill = new THREE.DirectionalLight(0x8ec4ec, 0.7);
  fill.position.set(4, 3, -4);
  scene.add(fill);
  const floor = new THREE.Mesh(
    new THREE.CircleGeometry(3.3, 80),
    new THREE.ShadowMaterial({ color: 0x000000, opacity: 0.4 }),
  );
  floor.receiveShadow = true;
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -0.016;
  scene.add(floor);
  controls = new OrbitControls(camera, renderer.domElement);
  controls.minDistance = 0.4;
  controls.maxDistance = 14;
  controls.maxPolarAngle = Math.PI * 0.49;
  controls.addEventListener("change", render);
  new ResizeObserver(() => {
    renderer.setSize(stage.clientWidth, stage.clientHeight);
    camera.aspect = stage.clientWidth / stage.clientHeight;
    camera.updateProjectionMatrix();
    render();
  }).observe(stage);
  const start = performance.now();
  let gltf = await new GLTFLoader()
    .setDRACOLoader(
      new DRACOLoader().setDecoderPath(
        "./node_modules/three/examples/jsm/libs/draco/gltf/",
      ),
    )
    .loadAsync("../g60-us/i5-m60.glb");
  model = gltf.scene;
  model.traverse((n) => {
    if (n.isMesh) n.castShadow = true;
  });
  scene.add(model);
  model.updateMatrixWorld(true);
  for (let [id, z] of Object.entries(manifest.zones)) {
    let n = model.getObjectByName(z.anchor);
    if (!n) throw Error(`Missing ${z.anchor}`);
    anchorWorld.set(id, n.getWorldPosition(new THREE.Vector3()));
  }
  let loadMs = performance.now() - start;
  metrics.dataset.loadMs = loadMs.toFixed(1);
  metrics.dataset.triangles = manifest.files.model.triangles;
  metrics.dataset.bytes = manifest.files.model.bytes;
  metrics.dataset.anchors = anchorWorld.size;
  metrics.dataset.renderer = renderer
    .getContext()
    .getParameter(renderer.getContext().RENDERER);
  preset("default_orbit");
  setStatus(
    "Drag to orbit · scroll to zoom · charging port is on vehicle right",
  );
  const benchmarkPosition = camera.position.clone(),
    benchmarkTarget = controls.target.clone(),
    benchmarkOffset = benchmarkPosition.clone().sub(benchmarkTarget);
  function benchmark(t) {
    if (lastTime) frames.push(t - lastTime);
    lastTime = t;
    camera.position.copy(
      benchmarkOffset
        .clone()
        .applyAxisAngle(
          new THREE.Vector3(0, 1, 0),
          Math.sin((frames.length / 180) * Math.PI) * 0.65,
        )
        .add(benchmarkTarget),
    );
    camera.lookAt(benchmarkTarget);
    render();
    if (frames.length < 180) requestAnimationFrame(benchmark);
    else {
      let samples = frames.slice(30).sort((a, b) => a - b),
        p95 = samples[Math.floor(samples.length * 0.95)],
        med = samples[Math.floor(samples.length / 2)];
      metrics.dataset.p95Ms = p95.toFixed(1);
      metrics.dataset.medianFps = (1000 / med).toFixed(1);
      metrics.dataset.drawCalls = renderer.info.render.calls;
      metrics.dataset.benchmark = "180-frame orbit, first 30 discarded";
      preset("default_orbit");
      metrics.textContent = `GLB ${(manifest.files.model.bytes / 1e6).toFixed(2)} MB · ${manifest.files.model.triangles.toLocaleString()} triangles\nLoad ${loadMs.toFixed(0)} ms · ${anchorWorld.size} anchors\nMedian ${(1000 / med).toFixed(0)} fps · p95 ${p95.toFixed(1)} ms\n${renderer.info.render.calls} draw calls · DPR ${renderer.getPixelRatio()}`;
      render();
    }
  }
  requestAnimationFrame(benchmark);
} catch (e) {
  showFallback = true;
  fallback.style.display = "block";
  pins.style.display = "none";
  setStatus(
    `3D unavailable: ${e.message}. Use the zone selector with the 2D schematic.`,
  );
  metrics.textContent = "WebGL fallback active";
}
$("poster").onclick = () => {
  if (!renderer) return;
  let p = manifest.cameras.default_orbit;
  preset("default_orbit");
  let oldAspect = camera.aspect,
    oldDpr = renderer.getPixelRatio();
  renderer.setPixelRatio(1);
  renderer.setSize(1600, 1000, false);
  camera.aspect = 1.6;
  camera.updateProjectionMatrix();
  renderer.render(scene, camera);
  let canvas = document.createElement("canvas");
  canvas.width = 1600;
  canvas.height = 1000;
  let ctx = canvas.getContext("2d");
  let gradient = ctx.createRadialGradient(800, 460, 100, 800, 460, 1000);
  gradient.addColorStop(0, "#344352");
  gradient.addColorStop(1, "#101923");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 1600, 1000);
  ctx.drawImage(renderer.domElement, 0, 0);
  ctx.fillStyle = "#e5edf6";
  ctx.font = "500 34px system-ui";
  ctx.fillText("G60 / US · Requirement Twin", 58, 73);
  ctx.fillStyle = "#acbfd0";
  ctx.font = "20px system-ui";
  ctx.fillText(
    "Licensed artist model · US MY2024 reference scope · exterior only",
    58,
    110,
  );
  ctx.font = "17px system-ui";
  ctx.fillText(manifest.licence.attribution, 58, 947);
  ctx.font = "12px system-ui";
  ctx.fillText(manifest.source.url + " | " + manifest.licence.url, 58, 978);
  canvas.toBlob((blob) => {
    let a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "poster.png";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }, "image/png");
  renderer.setPixelRatio(oldDpr);
  renderer.setSize(stage.clientWidth, stage.clientHeight);
  camera.aspect = oldAspect;
  camera.updateProjectionMatrix();
  render();
};

const facts = await fetch("../g60-us/official-facts.json").then((r) =>
  r.json(),
);
for (const f of facts.facts) {
  const p = document.createElement("p");
  p.textContent = `${f.id.replaceAll("_", " ")}: ${JSON.stringify(f.value)} ${f.units || ""} · ${f.market} MY${f.modelYear}. ${f.caveat} `;
  const a = document.createElement("a");
  a.href = f.sourceUrl;
  a.textContent = "BMW source";
  p.append(a);
  $("officialFacts").append(p);
}
