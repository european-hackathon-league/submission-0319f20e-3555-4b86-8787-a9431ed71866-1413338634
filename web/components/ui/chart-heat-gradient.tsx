"use client"

import { useId } from "react"
import { usePlotArea } from "recharts"

export const HEAT_PIE_PALETTE = [
  "#1c69d4", "#334762", "#85afe8", "#b8d5fc", "#6a819f", "#4376ba", "#cad5e3",
] as const

const HEAT_GRADIENT_STOPS = [
  ["0%", "#1555ac"], ["45%", "#2b7ae5"], ["100%", "#93beff"],
] as const
const COOL_GRADIENT_STOPS = [
  ["0%", "#3b4e69"], ["45%", "#7389a6"], ["100%", "#b3c3d9"],
] as const

export const HEAT_GRADIENT_CSS = `linear-gradient(to top, ${HEAT_GRADIENT_STOPS.map(([, color]) => color).join(", ")})`
export const COOL_GRADIENT_CSS = `linear-gradient(to top, ${COOL_GRADIENT_STOPS.map(([, color]) => color).join(", ")})`

export function useHeatGradientId() {
  return `chart-heat-${useId().replace(/:/g, "")}`
}

export function ChartHeatGradient({ id, direction = "vertical", tone = "heat" }: { id: string; direction?: "vertical" | "horizontal"; tone?: "heat" | "cool" }) {
  const plotArea = usePlotArea()
  if (!plotArea) return null

  const horizontal = direction === "horizontal"
  const stops = tone === "cool" ? COOL_GRADIENT_STOPS : HEAT_GRADIENT_STOPS
  return <linearGradient
    id={id}
    gradientUnits="userSpaceOnUse"
    x1={plotArea.x}
    y1={horizontal ? plotArea.y : plotArea.y + plotArea.height}
    x2={horizontal ? plotArea.x + plotArea.width : plotArea.x}
    y2={plotArea.y}
  >
    {stops.map(([offset, color]) => <stop key={offset} offset={offset} stopColor={color} />)}
  </linearGradient>
}
