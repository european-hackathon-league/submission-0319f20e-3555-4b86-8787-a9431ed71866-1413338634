import g60 from "@/public/models/g60-us/manifest.json";
import g70 from "@/public/models/g70-us/manifest.json";
import type { Requirement } from "./types";

export type VehicleZone = {
  anchor: string;
  position: number[];
  topics: string[];
  camera: string;
  approximation: string;
  geometry: string;
};

export type VehicleManifest = {
  id: string;
  status: string;
  vehicle: { code: string; market: string; variant: string; modelYear: number; modelYearBasis: string };
  source: { url: string; title: string; creator: string; creatorUrl: string };
  licence: { url: string; file: string; brandNotice: string };
  files: { model: { path: string }; poster: { path: string }; fallback: { path: string } };
  interior: boolean;
  interiorDescription: string;
  rendering: { paintMaterials: string[]; paintFinish: string };
  zones: Record<string, VehicleZone>;
  cameras: Record<string, { position: number[]; target: number[]; fov: number; near: number; far: number; note?: string }>;
};

export type VehicleAsset = {
  manifest: VehicleManifest;
  base: string;
  label: string;
};

export const vehicleAssets: VehicleAsset[] = [
  { manifest: g60 as VehicleManifest, base: "/models/g60-us", label: "G60 · i5 M60" },
  { manifest: g70 as VehicleManifest, base: "/models/g70-us", label: "G70 · i7" },
];

export const zoneNames: Record<string, string> = {
  charging: "Charging",
  battery_range: "Battery & range",
  seats_front: "Front seats",
  rear_cabin: "Rear cabin",
  cockpit: "Cockpit & controls",
  infotainment: "Infotainment",
  acoustics: "Acoustics",
  assistance: "Driver assistance",
  chassis: "Ride & handling",
  cargo: "Cargo & access",
  exterior: "Exterior design",
};

export type ZoneRollup = {
  requirements: Requirement[];
  topPriority: number | null;
  worstGrade: string | null;
  openReviews: number;
  approved: number;
};

export function buildZoneRollups(manifest: VehicleManifest, requirements: Requirement[]): Record<string, ZoneRollup> {
  const scoped = requirements.filter((item) => item.vehicle === manifest.vehicle.code && item.market === manifest.vehicle.market);
  return Object.fromEntries(Object.entries(manifest.zones).map(([id, zone]) => {
    const matches = scoped.filter((item) => zone.topics.includes(item.topic)).sort((a, b) => b.priority - a.priority);
    return [id, {
      requirements: matches,
      topPriority: matches.length ? matches[0].priority : null,
      worstGrade: matches.length ? matches.map((item) => item.evidence_grade).sort().at(-1) || null : null,
      openReviews: matches.filter((item) => item.needs_review).length,
      approved: matches.filter((item) => item.status === "approved").length,
    }];
  }));
}
