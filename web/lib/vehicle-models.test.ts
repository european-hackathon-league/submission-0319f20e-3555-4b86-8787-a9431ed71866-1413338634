import { expect, test } from "bun:test";
import { buildZoneRollups, vehicleAssets } from "./vehicle-models";
import type { Requirement } from "./types";

const g60 = vehicleAssets[0].manifest;
const record = (topic: string, overrides: Partial<Requirement> = {}) => ({
  id: topic, key: `REQ-${topic}`, title: topic, topic, vehicle: "G60", market: "US",
  status: "proposed", priority: 61, evidence_grade: "B", score_id: "score-1", version: 1,
  current_version_id: "version-1", approved_version_id: null, approved_score_id: null,
  needs_review: false, created_at: "", updated_at: "", ...overrides,
}) as Requirement;

test("one comfort requirement maps to both cabin zones without leaking across vehicles", () => {
  const rollups = buildZoneRollups(g60, [record("comfort"), record("comfort", { id: "g70-comfort", vehicle: "G70" })]);
  expect(rollups.seats_front.requirements.map((item) => item.id)).toEqual(["comfort"]);
  expect(rollups.rear_cabin.requirements.map((item) => item.id)).toEqual(["comfort"]);
  expect(rollups.charging.requirements).toEqual([]);
});

test("priority, evidence and review state remain distinct in a zone", () => {
  const rollups = buildZoneRollups(g60, [
    record("charging", { id: "high", priority: 82, evidence_grade: "C", needs_review: true }),
    record("charging", { id: "low", priority: 48, evidence_grade: "D", status: "approved" }),
  ]);
  expect(rollups.charging.topPriority).toBe(82);
  expect(rollups.charging.worstGrade).toBe("D");
  expect(rollups.charging.openReviews).toBe(1);
  expect(rollups.charging.approved).toBe(1);
});
