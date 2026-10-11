"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowUpRight, Download, Focus, RotateCcw, Check } from "lucide-react";
import { useStoredValue } from "@/hooks/use-stored-value";
import { api, locationLabel } from "@/lib/api";
import type { Trace } from "@/lib/types";
import {
  buildZoneRollups,
  vehicleAssets,
  zoneNames,
  type ZoneRollup,
} from "@/lib/vehicle-models";
import { useWorkspace } from "./context";
import { Heading, ScoreLabel, Status } from "./shared";
import { PmSelect } from "./pm-select";

const VehicleViewport = dynamic(
  () => import("./vehicle-viewport").then((module) => module.VehicleViewport),
  {
    ssr: false,
    loading: () => (
      <div className="vehicle-stage vehicle-stage-loading">
        Preparing 3D viewer…
      </div>
    ),
  },
);

type Treatment = "improve" | "preserve" | "investigate" | "defer";
type Draft = Record<string, { treatment?: Treatment; note?: string }>;
const treatments: { value: Treatment; label: string; detail: string }[] = [
  { value: "improve", label: "Improve", detail: "Make the experience better" },
  { value: "preserve", label: "Preserve", detail: "Keep what customers value" },
  { value: "investigate", label: "Investigate", detail: "Find out more" },
  { value: "defer", label: "Defer", detail: "Return to this later" },
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
    return data && typeof data === "object" && !Array.isArray(data)
      ? (data as Draft)
      : {};
  } catch {
    return {};
  }
}

function zoneColor(rollup: ZoneRollup, layer: string) {
  if (!rollup.requirements.length) return "#8c9aa6";
  if (layer === "evidence")
    return rollup.worstGrade === "D" || rollup.worstGrade === "C"
      ? "#a96a27"
      : "#247266";
  if (layer === "review") return rollup.openReviews ? "#b45b3f" : "#247266";
  return (rollup.topPriority || 0) >= 70
    ? "#b45b3f"
    : (rollup.topPriority || 0) >= 45
      ? "#ba842e"
      : "#32749a";
}

export function VehicleStudio() {
  const { scope, requirements, base } = useWorkspace();
  const router = useRouter();
  const pathname = usePathname();
  const search = useSearchParams();
  const asset = vehicleAssets.find(
    ({ manifest }) =>
      manifest.vehicle.code === scope.vehicle &&
      manifest.vehicle.market === scope.market,
  );
  const [layer, setLayer] = useStoredValue("bmw-twin-layer", "priority");
  const [paint, setPaint] = useStoredValue(
    `bmw-twin-paint-${scope.vehicle}`,
    scope.vehicle === "G70" ? "#bdc7cf" : "#244a70",
  );
  const [storedDraft, setStoredDraft] = useStoredValue(
    `bmw-twin-draft-${scope.vehicle}-${scope.market}`,
    "{}",
  );
  const draft = useMemo(() => parseDraft(storedDraft), [storedDraft]);
  const manifest = asset?.manifest;
  const requestedZone = search.get("zone");
  const zoneId =
    manifest && requestedZone && Object.hasOwn(manifest.zones, requestedZone)
      ? requestedZone
      : "charging";
  const rollups = useMemo(
    () => (manifest ? buildZoneRollups(manifest, requirements) : {}),
    [manifest, requirements],
  );
  const pinColors = useMemo(
    () =>
      Object.fromEntries(
        Object.entries(rollups).map(([id, rollup]) => [
          id,
          zoneColor(rollup, layer),
        ]),
      ),
    [rollups, layer],
  );
  const selected = rollups[zoneId];
  const lead = selected?.requirements[0];
  const zone = manifest?.zones[zoneId];
  const selectedDraft = draft[zoneId] || {};
  const [viewRequest, setViewRequest] = useState({
    vehicle: scope.vehicle,
    mode: (requestedZone && manifest?.zones[requestedZone] ? "focus" : "overview") as "overview" | "focus",
    revision: 0,
  });
  const cameraView = useMemo(
    () => viewRequest.vehicle === scope.vehicle ? viewRequest : { mode: "overview" as const, revision: 0 },
    [scope.vehicle, viewRequest],
  );
  const moveCamera = (mode: "overview" | "focus") =>
    setViewRequest((previous) => ({
      vehicle: scope.vehicle,
      mode,
      revision: previous.revision + 1,
    }));
  const signals = useQuery({
    queryKey: [
      "studio-signals",
      lead?.id,
      lead?.current_version_id,
      lead?.score_id,
    ],
    queryFn: ({ signal }) =>
      api<Trace>(
        `/requirements/${encodeURIComponent(lead!.id)}/trace?${new URLSearchParams(
          {
            version_id: lead!.current_version_id,
            score_id: lead!.score_id,
            limit: "6",
            offset: "0",
          },
        )}`,
        { signal },
      ),
    enabled: !!lead,
  });
  const sourceNames = new Map(
    signals.data?.sources.map((item) => [item.id, item.title]) || [],
  );
  const configuredCount = Object.values(draft).filter(
    (value) => value.treatment || value.note,
  ).length;

  const selectZone = (id: string) => {
    moveCamera("focus");
    const params = new URLSearchParams(search.toString());
    params.set("zone", id);
    router.replace(`${pathname}?${params.toString()}`, { scroll: false });
  };
  const changeDraft = (patch: Partial<Draft[string]>) => {
    setStoredDraft(
      JSON.stringify({ ...draft, [zoneId]: { ...selectedDraft, ...patch } }),
    );
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
      zones: Object.fromEntries(
        Object.entries(draft)
          .filter(([, value]) => value.treatment || value.note)
          .map(([id, value]) => [
            id,
            {
              ...value,
              topics: manifest.zones[id]?.topics || [],
              linkedRequirements: (rollups[id]?.requirements || []).map(
                (item) => ({
                  id: item.id,
                  key: item.key,
                  currentVersionId: item.current_version_id,
                  scoreId: item.score_id,
                }),
              ),
            },
          ]),
      ),
      note: "Scenario only. No requirement version, score, decision or vehicle specification was changed.",
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], {
        type: "application/json",
      }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${manifest.vehicle.code.toLowerCase()}-pm-scenario.json`;
    anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="vehicle-studio">
      <Heading
        title="Vehicle studio"
        description="Explore the car and the customer feedback behind each area."
      />
      <div className="studio-toolbar">
        <div className="studio-model-switch" aria-label="Vehicle model">
          {vehicleAssets.map((item) => (
            <Link
              key={item.manifest.id}
              href={`/${item.manifest.vehicle.code.toLowerCase()}/${item.manifest.vehicle.market.toLowerCase()}/twin`}
              aria-current={
                asset?.manifest.id === item.manifest.id ? "page" : undefined
              }
            >
              {item.label}
            </Link>
          ))}
        </div>
        <span className="studio-scope-label">
          {scope.market} · {requirements.length} requirements
        </span>
      </div>

      {!asset || !manifest ? (
        <section className="pm-panel studio-unavailable">
          <h2>
            A model for {scope.vehicle} / {scope.market} is coming soon
          </h2>
          <p>
            Explore the G60 or G70 in the US market using the model selector.
          </p>
        </section>
      ) : (
        <>
          <div className="studio-grid">
            <section
              className="studio-viewer"
              aria-label={`${scope.vehicle} 3D exploration`}
            >
              <div className="studio-viewer-top">
                <div>
                  <span className="studio-eyebrow">
                    {scope.vehicle === "G70" ? "THE 7" : "THE 5"}
                  </span>
                  <h2>BMW {scope.vehicle === "G70" ? "i7" : "i5"}</h2>
                </div>
                <span className="studio-model-detail">
                  {manifest.vehicle.variant.replace(/\s*\(.*\)$/, "")}
                  <small>{manifest.vehicle.modelYear}</small>
                </span>
              </div>
              <VehicleViewport
                key={manifest.id}
                asset={asset}
                selectedZone={zoneId}
                paint={paint}
                responses={draft}
                pinColors={pinColors}
                onSelect={selectZone}
                cameraView={cameraView}
              />
              <div className="studio-viewer-bottom">
                <div className="studio-view-controls" aria-label="Camera view">
                  <button
                    type="button"
                    onClick={() => moveCamera("overview")}
                    aria-label="Reset view to whole car"
                  >
                    <RotateCcw size={15} /> Reset view
                  </button>
                  <button type="button" onClick={() => moveCamera("focus")}>
                    <Focus size={15} /> Focus area
                  </button>
                </div>
                <div
                  className="studio-paint-controls"
                  role="group"
                  aria-label="Paint preview"
                >
                  <span>
                    {paints.find((item) => item.value === paint)?.name ||
                      "Paint"}
                  </span>
                  <div className="studio-swatches">
                    {paints.map((item) => (
                      <button
                        key={item.value}
                        type="button"
                        title={`${item.name} preview`}
                        aria-label={item.name}
                        aria-pressed={paint === item.value}
                        onClick={() => setPaint(item.value)}
                        style={
                          {
                            "--swatch-color": item.value,
                          } as React.CSSProperties
                        }
                      />
                    ))}
                  </div>
                </div>
              </div>
            </section>

            <section
              className="studio-zones"
              aria-label="Customer experience zones"
            >
              <div className="studio-panel-heading">
                <span className="studio-eyebrow">EXPLORE</span>
                <h2>Around the car</h2>
              </div>
              <div className="studio-layer">
                <PmSelect
                  aria-label="Color areas by"
                  value={layer}
                  onValueChange={setLayer}
                  options={[
                    { value: "priority", label: "Priority" },
                    { value: "evidence", label: "Evidence quality" },
                    { value: "review", label: "Needs review" },
                  ]}
                />
              </div>
              <div className="studio-zone-column-label">
                <span>Area</span>
                <span>Requirements</span>
              </div>
              <div className="studio-zone-list">
                {Object.entries(manifest.zones).map(([id]) => {
                  const rollup = rollups[id];
                  return (
                    <button
                      key={id}
                      type="button"
                      className="studio-zone-row"
                      aria-pressed={id === zoneId}
                      data-active={id === zoneId}
                      onClick={() => selectZone(id)}
                    >
                      <i style={{ background: zoneColor(rollup, layer) }} />
                      <span>
                        <strong>{zoneNames[id] || id}</strong>
                        {draft[id]?.treatment && (
                          <small>
                            {
                              treatments.find(
                                (item) => item.value === draft[id].treatment,
                              )?.label
                            }
                          </small>
                        )}
                      </span>
                      <em>{rollup?.requirements.length || 0}</em>
                    </button>
                  );
                })}
              </div>
              <div className="studio-list-footnote">
                <Check size={13} /> {configuredCount}{" "}
                {configuredCount === 1 ? "area" : "areas"} with planning notes
              </div>
            </section>
          </div>

          <div className="studio-detail-grid">
            <section
              className="studio-evidence-panel"
              aria-label="Customer feedback for selected area"
            >
              <div className="studio-panel-heading">
                <span className="studio-eyebrow">CUSTOMER FEEDBACK</span>
                <h2>{zoneNames[zoneId] || zoneId}</h2>
              </div>
              <div className="studio-rollup">
                <div>
                  <strong>{selected?.requirements.length || 0}</strong>
                  <span>Requirements</span>
                </div>
                <div>
                  <strong>
                    {selected?.topPriority == null
                      ? "—"
                      : selected.topPriority.toFixed(1)}
                  </strong>
                  <span>Top priority</span>
                </div>
                <div>
                  <strong>{selected?.worstGrade || "—"}</strong>
                  <span>Lowest evidence grade</span>
                </div>
                <div>
                  <strong>{selected?.openReviews || 0}</strong>
                  <span>Need review</span>
                </div>
              </div>
              <div className="studio-signals">
                {!lead ? (
                  <p>No customer feedback is linked to this area yet.</p>
                ) : signals.isPending ? (
                  <p>Loading customer feedback…</p>
                ) : signals.error ? (
                  <p role="alert">
                    Feedback could not load. Open the requirement to view its
                    sources.
                  </p>
                ) : (
                  <>
                    {signals.data?.evidence.items.slice(0, 1).map((item) => (
                      <blockquote key={item.id}>
                        <p>“{item.content}”</p>
                        <cite>
                          {sourceNames.get(item.source_id) || item.source_id} ·{" "}
                          {locationLabel(item.location)}
                        </cite>
                      </blockquote>
                    ))}
                  </>
                )}
                {lead && (
                  <Link
                    href={`${base}/twin?zone=${encodeURIComponent(zoneId)}&requirement=${encodeURIComponent(lead.id)}&tab=evidence`}
                  >
                    View all supporting and conflicting feedback{" "}
                    <ArrowUpRight size={15} />
                  </Link>
                )}
              </div>
            </section>

            <section
              className="studio-inspector"
              aria-label="Planning scenario"
            >
              <div className="studio-panel-heading">
                <div>
                  <span className="studio-eyebrow">YOUR NOTES</span>
                  <h2>Plan for {zoneNames[zoneId]?.toLowerCase() || zoneId}</h2>
                </div>
                <span className="studio-save-status">
                  Saved in this browser
                </span>
              </div>
              <div className="studio-inspector-content">
                <div
                  className="studio-treatment-list"
                  role="group"
                  aria-label="Planning response"
                >
                  {treatments.map((item) => (
                    <button
                      key={item.value}
                      type="button"
                      aria-pressed={selectedDraft.treatment === item.value}
                      onClick={() => changeDraft({ treatment: selectedDraft.treatment === item.value ? undefined : item.value })}
                    >
                      <strong>{item.label}</strong>
                      <span>{item.detail}</span>
                    </button>
                  ))}
                </div>
                <label className="studio-note">
                  <span>Notes</span>
                  <textarea
                    value={selectedDraft.note || ""}
                    onChange={(event) =>
                      changeDraft({ note: event.target.value })
                    }
                    placeholder="What would improve this experience?"
                    rows={3}
                  />
                </label>
                <div className="studio-note-footer">
                  <span>
                    {configuredCount} {configuredCount === 1 ? "area" : "areas"}{" "}
                    in your plan
                  </span>
                  <button
                    type="button"
                    className="studio-export"
                    onClick={exportDraft}
                  >
                    <Download size={15} /> Download plan
                  </button>
                </div>
              </div>
            </section>
          </div>

          <section
            className="studio-requirements"
            aria-label="Linked requirements"
          >
            <div className="studio-requirements-heading">
              <div>
                <h2>{zoneNames[zoneId] || zoneId} requirements</h2>
                <p>Review the evidence, priority and decision history.</p>
              </div>
              <Link
                href={`${base}/requirements?topic=${encodeURIComponent(zone?.topics[0] || "")}`}
              >
                All requirements <ArrowUpRight size={15} />
              </Link>
            </div>
            {!selected?.requirements.length ? (
              <p className="studio-empty">
                No requirements for this area in {scope.vehicle} /{" "}
                {scope.market} yet.
              </p>
            ) : (
              <div className="studio-requirement-list">
                {selected.requirements.map((item) => (
                  <article key={item.id}>
                    <div>
                      <span className="mono">{item.key}</span>
                      <h3>{item.title}</h3>
                      <span className="studio-requirement-meta">
                        <Status value={item.status} />
                        {item.needs_review && (
                          <span className="studio-review-flag">
                            Needs review
                          </span>
                        )}
                      </span>
                    </div>
                    <ScoreLabel
                      score={item.priority}
                      grade={item.evidence_grade}
                    />
                    <Link
                      href={`${base}/twin?zone=${encodeURIComponent(zoneId)}&requirement=${encodeURIComponent(item.id)}&tab=evidence`}
                    >
                      Review requirement <ArrowUpRight size={15} />
                    </Link>
                  </article>
                ))}
              </div>
            )}
          </section>

          <footer className="studio-credit">
            <span>
              <a href={manifest.source.url} target="_blank" rel="noreferrer">
                {manifest.source.title}
              </a>{" "}
              by{" "}
              <a
                href={manifest.source.creatorUrl}
                target="_blank"
                rel="noreferrer"
              >
                {manifest.source.creator}
              </a>{" "}
              ·{" "}
              <a href={manifest.licence.url} target="_blank" rel="noreferrer">
                CC BY 4.0
              </a>{" "}
              · Geometry and materials adapted
            </span>
            <details>
              <summary>About this model</summary>
              <p>{manifest.vehicle.modelYearBasis}</p>
              <p>
                {manifest.interior
                  ? "The cabin and equipment use simplified artist geometry."
                  : "Cabin, cargo and battery markers use approximate positions on the exterior model."}{" "}
                Paint previews are illustrative. Planning notes stay in this
                browser until downloaded.
              </p>
              <a href={`${asset.base}/${manifest.licence.file}`}>
                View licence
              </a>
            </details>
          </footer>
        </>
      )}
    </div>
  );
}
