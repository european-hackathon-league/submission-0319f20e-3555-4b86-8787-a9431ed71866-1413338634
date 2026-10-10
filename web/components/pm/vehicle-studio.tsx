"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowUpRight, Download, Info, RotateCcw } from "lucide-react";
import { useStoredValue } from "@/hooks/use-stored-value";
import { api, locationLabel } from "@/lib/api";
import type { Trace } from "@/lib/types";
import { buildZoneRollups, vehicleAssets, zoneNames, type ZoneRollup } from "@/lib/vehicle-models";
import { useWorkspace } from "./context";
import { Heading, ScoreLabel, Status } from "./shared";

const VehicleViewport = dynamic(() => import("./vehicle-viewport").then((module) => module.VehicleViewport), {
  ssr: false,
  loading: () => <div className="vehicle-stage vehicle-stage-loading">Preparing 3D viewer…</div>,
});

type Treatment = "improve" | "preserve" | "investigate" | "defer";
type Draft = Record<string, { treatment?: Treatment; note?: string }>;
const treatments: { value: Treatment; label: string; detail: string }[] = [
  { value: "improve", label: "Improve", detail: "Explore a stronger customer outcome" },
  { value: "preserve", label: "Preserve", detail: "Protect an attribute customers value" },
  { value: "investigate", label: "Investigate", detail: "Collect more evidence before a target" },
  { value: "defer", label: "Defer", detail: "Keep visible for a later planning review" },
];
const paints = [
  { name: "Studio blue", value: "#244a70" },
  { name: "Silver", value: "#bdc7cf" },
  { name: "Graphite", value: "#343943" },
  { name: "Pearl", value: "#e9e9e4" },
];

function parseDraft(value: string): Draft {
  try {
    const data: unknown = JSON.parse(value);
    return data && typeof data === "object" && !Array.isArray(data) ? data as Draft : {};
  } catch { return {}; }
}

function zoneColor(rollup: ZoneRollup, layer: string) {
  if (!rollup.requirements.length) return "#8c9aa6";
  if (layer === "evidence") return rollup.worstGrade === "D" || rollup.worstGrade === "C" ? "#a96a27" : "#247266";
  if (layer === "review") return rollup.openReviews ? "#b45b3f" : "#247266";
  return (rollup.topPriority || 0) >= 70 ? "#b45b3f" : (rollup.topPriority || 0) >= 45 ? "#ba842e" : "#32749a";
}

export function VehicleStudio() {
  const { scope, requirements, base } = useWorkspace();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const asset = vehicleAssets.find(({ manifest }) => manifest.vehicle.code === scope.vehicle && manifest.vehicle.market === scope.market);
  const [layer, setLayer] = useStoredValue("bmw-twin-layer", "priority");
  const [paint, setPaint] = useStoredValue(`bmw-twin-paint-${scope.vehicle}`, scope.vehicle === "G70" ? "#bdc7cf" : "#244a70");
  const [storedDraft, setStoredDraft] = useStoredValue(`bmw-twin-draft-${scope.vehicle}-${scope.market}`, "{}");
  const draft = useMemo(() => parseDraft(storedDraft), [storedDraft]);
  const manifest = asset?.manifest;
  const requestedZone = search.get("zone");
  const zoneId = manifest && requestedZone && Object.hasOwn(manifest.zones, requestedZone) ? requestedZone : "charging";
  const rollups = useMemo(() => manifest ? buildZoneRollups(manifest, requirements) : {}, [manifest, requirements]);
  const pinColors = useMemo(() => Object.fromEntries(Object.entries(rollups).map(([id, rollup]) => [id, zoneColor(rollup, layer)])), [rollups, layer]);
  const selected = rollups[zoneId];
  const lead = selected?.requirements[0];
  const zone = manifest?.zones[zoneId];
  const selectedDraft = draft[zoneId] || {};
  const cameraNote = zone ? manifest?.cameras[zone.camera]?.note : undefined;
  const signals = useQuery({
    queryKey: ["studio-signals", lead?.id, lead?.current_version_id, lead?.score_id],
    queryFn: ({ signal }) => api<Trace>(`/requirements/${encodeURIComponent(lead!.id)}/trace?${new URLSearchParams({
      version_id: lead!.current_version_id, score_id: lead!.score_id, limit: "6", offset: "0",
    })}`, { signal }),
    enabled: !!lead,
  });
  const sourceNames = new Map(signals.data?.sources.map((item) => [item.id, item.title]) || []);
  const configuredCount = Object.values(draft).filter((value) => value.treatment).length;

  const selectZone = (id: string) => {
    const params = new URLSearchParams(search.toString());
    params.set("zone", id);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  };
  const changeDraft = (patch: Partial<Draft[string]>) => {
    setStoredDraft(JSON.stringify({ ...draft, [zoneId]: { ...selectedDraft, ...patch } }));
  };
  const exportDraft = () => {
    if (!manifest) return;
    const payload = {
      kind: "local-planning-scenario",
      exportedAt: new Date().toISOString(),
      vehicle: manifest.vehicle.code,
      market: manifest.vehicle.market,
      model: manifest.id,
      visualPaintPreview: paint,
      zones: Object.fromEntries(Object.entries(draft).filter(([, value]) => value.treatment || value.note).map(([id, value]) => [id, {
        ...value,
        topics: manifest.zones[id]?.topics || [],
        linkedRequirements: (rollups[id]?.requirements || []).map((item) => ({
          id: item.id, key: item.key, currentVersionId: item.current_version_id, scoreId: item.score_id,
        })),
      }])),
      note: "Scenario only. No requirement version, score, decision or vehicle specification was changed.",
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${manifest.vehicle.code.toLowerCase()}-pm-scenario.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return <div className="vehicle-studio">
    <Heading title="Vehicle studio" description="Explore customer experience on the car, test a planning response, then open the source-linked requirement before making a decision." />
    <div className="studio-toolbar">
      <div className="studio-model-switch" aria-label="Vehicle model">
        {vehicleAssets.map((item) => <Link
          key={item.manifest.id}
          href={`/${item.manifest.vehicle.code.toLowerCase()}/${item.manifest.vehicle.market.toLowerCase()}/twin`}
          aria-current={asset?.manifest.id === item.manifest.id ? "page" : undefined}
        >{item.label}</Link>)}
      </div>
      <label className="studio-layer">Color zones by
        <select value={layer} onChange={(event) => setLayer(event.target.value)}>
          <option value="priority">Top priority</option>
          <option value="evidence">Weakest evidence</option>
          <option value="review">Needs review</option>
        </select>
      </label>
    </div>

    {!asset || !manifest ? <section className="pm-panel studio-unavailable">
      <h2>No licensed model for {scope.vehicle} / {scope.market}</h2>
      <p>Choose G60 / US or G70 / US above. Their requirement data stays scoped to its own vehicle and market.</p>
    </section> : <>
      <div className="studio-disclosure"><Info size={15} /><span>Independent licensed artist model · {manifest.vehicle.modelYearBasis} The model is a spatial guide, not engineering geometry or evidence.</span></div>
      <div className="studio-grid">
        <section className="studio-zones" aria-label="Customer experience zones">
          <div className="studio-panel-heading"><span className="mono">01 / EXPLORE</span><h2>Experience zones</h2><p>Mapped from requirement topics in the live {scope.vehicle} / {scope.market} register. {configuredCount} response{configuredCount === 1 ? "" : "s"} drafted.</p></div>
          <div className="studio-zone-list">{Object.entries(manifest.zones).map(([id, item]) => {
            const rollup = rollups[id];
            return <button key={id} type="button" className="studio-zone-row" data-active={id === zoneId} onClick={() => selectZone(id)}>
              <i style={{ background: zoneColor(rollup, layer) }} />
              <span><strong>{zoneNames[id] || id}</strong><small>{item.topics.join(" · ")}{draft[id]?.treatment ? ` · ${draft[id].treatment} draft` : ""}</small></span>
              <em>{rollup?.requirements.length || 0}</em>
            </button>;
          })}</div>
          <p className="studio-list-footnote">Numbers count linked requirements in this scope. They are not customer prevalence.</p>
        </section>

        <section className="studio-viewer" aria-label={`${scope.vehicle} 3D exploration`}>
          <div className="studio-viewer-top"><span className="mono">02 / MODEL VIEW</span><span>{manifest.vehicle.variant} · MY{manifest.vehicle.modelYear} reference</span></div>
          <VehicleViewport key={manifest.id} asset={asset} selectedZone={zoneId} paint={paint} responses={draft} pinColors={pinColors} onSelect={selectZone} />
          <div className="studio-viewer-bottom">
            <div><strong>{zoneNames[zoneId] || zoneId}</strong><span>{zone?.approximation}</span>{cameraNote && <span>{cameraNote}</span>}</div>
            <button type="button" onClick={() => selectZone("exterior")} aria-label="Reset view to exterior"><RotateCcw size={15} /> Exterior view</button>
          </div>
        </section>

        <section className="studio-inspector" aria-label="Planning scenario">
          <div className="studio-panel-heading"><span className="mono">03 / CONFIGURE</span><h2>Planning scenario</h2><p>Local draft · no requirement or decision is changed</p></div>
          <div className="studio-inspector-content">
            <div className="studio-inspector-zone"><span className="mono">SELECTED ZONE</span><h3>{zoneNames[zoneId] || zoneId}</h3><p>{zone?.approximation}</p></div>
            <div className="studio-rollup">
              <div><strong>{selected?.requirements.length || 0}</strong><span>Requirements</span></div>
              <div><strong>{selected?.topPriority == null ? "—" : selected.topPriority.toFixed(1)}</strong><span>Top score</span></div>
              <div><strong>{selected?.worstGrade || "—"}</strong><span>Weakest grade</span></div>
              <div><strong>{selected?.openReviews || 0}</strong><span>Need review</span></div>
            </div>
            <div className="studio-signals"><span className="mono">LIVE CUSTOMER SIGNALS</span>
              {!lead ? <p>No feedback is linked to this zone yet.</p> : signals.isPending ? <p>Loading source-linked feedback…</p> : signals.error ? <p role="alert">Feedback preview is unavailable. Open the requirement trace for the current record.</p> : <>
                {signals.data?.evidence.items.slice(0, 1).map((item) => <blockquote key={item.id}>
                  <p>{item.content}</p>
                  <cite>{sourceNames.get(item.source_id) || item.source_id} · {locationLabel(item.location)}</cite>
                </blockquote>)}
                <p>One linked record from the current version. Open the trace to review the full supporting and conflicting evidence.</p>
                <Link href={`${base}/twin?zone=${encodeURIComponent(zoneId)}&requirement=${encodeURIComponent(lead.id)}&tab=evidence`}>Open full evidence trace <ArrowUpRight size={13} /></Link>
              </>}
            </div>
            <div className="studio-control-block"><span className="mono">VISUAL PAINT PREVIEW</span><div className="studio-swatches">{paints.map((item) => <button key={item.value} type="button" title={item.name} aria-label={item.name} aria-pressed={paint === item.value} onClick={() => setPaint(item.value)} style={{ background: item.value }} />)}</div><p>Illustrative colors. These are not verified BMW paint options.</p></div>
            <div className="studio-control-block"><span className="mono">PM RESPONSE HYPOTHESIS</span><div className="studio-treatment-list">{treatments.map((item) => <button key={item.value} type="button" aria-pressed={selectedDraft.treatment === item.value} onClick={() => changeDraft({ treatment: item.value })}><strong>{item.label}</strong><span>{item.detail}</span></button>)}</div></div>
            <label className="studio-control-block studio-note"><span className="mono">WHY THIS RESPONSE?</span><textarea value={selectedDraft.note || ""} onChange={(event) => changeDraft({ note: event.target.value })} placeholder="Write a planning hypothesis grounded in the linked feedback…" rows={3} /></label>
            <button type="button" className="studio-export" onClick={exportDraft}><Download size={16} /> Download scenario JSON</button>
          </div>
        </section>
      </div>

      <section className="studio-requirements" aria-label="Linked requirements">
        <div className="studio-requirements-heading"><div><span className="mono">SOURCE → DECISION</span><h2>{zoneNames[zoneId] || zoneId} requirements</h2><p>Current API records for {scope.vehicle} / {scope.market}; open a row for evidence, score, versions and PM history.</p></div><Link href={`${base}/requirements?topic=${encodeURIComponent(zone?.topics[0] || "")}`}>Open register <ArrowUpRight size={15} /></Link></div>
        {!selected?.requirements.length ? <p className="studio-empty">No requirements are linked to this zone in {scope.vehicle} / {scope.market}. The model has no embedded customer feedback or inferred score.</p> : <div className="studio-requirement-list">{selected.requirements.map((item) => <article key={item.id}>
          <div><span className="mono">{item.key}</span><h3>{item.title}</h3><span className="studio-requirement-meta"><Status value={item.status} />{item.needs_review && <span className="studio-review-flag">Needs review</span>}</span></div>
          <ScoreLabel score={item.priority} grade={item.evidence_grade} />
          <Link href={`${base}/twin?zone=${encodeURIComponent(zoneId)}&requirement=${encodeURIComponent(item.id)}&tab=evidence`}>Evidence & decision <ArrowUpRight size={15} /></Link>
        </article>)}</div>}
      </section>

      <div className="studio-credit"><span>{manifest.interior ? "Simplified artist interior; cabin geometry and equipment are illustrative." : "Exterior shell only; cabin, cargo and battery zones are approximate."}</span><span>Model: <a href={manifest.source.url} target="_blank" rel="noreferrer">{manifest.source.title}</a> by <a href={manifest.source.creatorUrl} target="_blank" rel="noreferrer">{manifest.source.creator}</a> · <a href={manifest.licence.url} target="_blank" rel="noreferrer">CC BY 4.0</a> · optimized geometry, materials and anchors modified · <a href={`${asset.base}/${manifest.licence.file}`}>licence file</a>.</span></div>
    </>}
  </div>;
}
