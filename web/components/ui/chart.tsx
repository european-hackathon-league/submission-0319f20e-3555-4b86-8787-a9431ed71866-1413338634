"use client"

import * as React from "react"
import { cn } from "cn"
import * as RechartsPrimitive from "recharts"
import type { TooltipValueType } from "recharts"

// Format: { THEME_NAME: CSS_SELECTOR }
const THEMES = { light: "", dark: ".dark" } as const

const INITIAL_DIMENSION = { width: 320, height: 200 } as const
type TooltipNameType = number | string

export type ChartConfig = Record<
  string,
  {
    label?: React.ReactNode
    icon?: React.ComponentType
  } & (
    | { color?: string; theme?: never }
    | { color?: never; theme: Record<keyof typeof THEMES, string> }
  )
>

type ChartContextProps = {
  config: ChartConfig
}

const ChartContext = React.createContext<ChartContextProps | null>(null)

function useChart() {
  const context = React.useContext(ChartContext)

  if (!context) {
    throw new Error("useChart must be used within a <ChartContainer />")
  }

  return context
}

function ChartContainer({
  id,
  className,
  children,
  config,
  initialDimension = INITIAL_DIMENSION,
  ...props
}: React.ComponentProps<"div"> & {
  config: ChartConfig
  children: React.ComponentProps<
    typeof RechartsPrimitive.ResponsiveContainer
  >["children"]
  initialDimension?: {
    width: number
    height: number
  }
}) {
  const uniqueId = React.useId()
  const chartId = `chart-${id ?? uniqueId.replace(/:/g, "")}`

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        data-slot="chart"
        data-chart={chartId}
        className={cn(
          "flex aspect-video justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line[stroke='#ccc']]:stroke-border/50 [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-dot[stroke='#fff']]:stroke-transparent [&_.recharts-layer]:outline-hidden [&_.recharts-polar-grid_[stroke='#ccc']]:stroke-border [&_.recharts-radial-bar-background-sector]:fill-muted [&_.recharts-rectangle.recharts-tooltip-cursor]:fill-muted [&_.recharts-reference-line_[stroke='#ccc']]:stroke-border [&_.recharts-sector]:outline-hidden [&_.recharts-sector[stroke='#fff']]:stroke-transparent [&_.recharts-surface]:outline-hidden",
          className
        )}
        {...props}
      >
        <ChartStyle id={chartId} config={config} />
        <RechartsPrimitive.ResponsiveContainer
          initialDimension={initialDimension}
        >
          {children}
        </RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  )
}

const ChartStyle = ({ id, config }: { id: string; config: ChartConfig }) => {
  const colorConfig = Object.entries(config).filter(
    ([, config]) => config.theme ?? config.color
  )

  if (!colorConfig.length) {
    return null
  }

  return (
    <style
      dangerouslySetInnerHTML={{
        __html: Object.entries(THEMES)
          .map(
            ([theme, prefix]) => `
${prefix} [data-chart=${id}] {
${colorConfig
  .map(([key, itemConfig]) => {
    const color =
      itemConfig.theme?.[theme as keyof typeof itemConfig.theme] ??
      itemConfig.color
    return color ? `  --color-${key}: ${color};` : null
  })
  .join("\n")}
}
`
          )
          .join("\n"),
      }}
    />
  )
}

function ChartTooltip(props: React.ComponentProps<typeof RechartsPrimitive.Tooltip>) {
  return <RechartsPrimitive.Tooltip {...props} isAnimationActive={false} />
}

function useChartTooltipMotion(active: boolean) {
  const tooltipRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    if (!active) return

    const frame = requestAnimationFrame(() => {
      tooltipRef.current?.setAttribute("data-motion-ready", "")
    })

    return () => cancelAnimationFrame(frame)
  }, [active])

  return tooltipRef
}

function ChartTooltipContent({
  active,
  payload,
  className,
  indicator = "dot",
  hideLabel = false,
  hideIndicator = false,
  label,
  labelFormatter,
  labelClassName,
  formatter,
  color,
  nameKey,
  labelKey,
}: React.ComponentProps<typeof RechartsPrimitive.Tooltip> &
  React.ComponentProps<"div"> & {
    hideLabel?: boolean
    hideIndicator?: boolean
    indicator?: "line" | "dot" | "dashed"
    nameKey?: string
    labelKey?: string
  } & Omit<
    RechartsPrimitive.DefaultTooltipContentProps<
      TooltipValueType,
      TooltipNameType
    >,
    "accessibilityLayer"
  >) {
  const { config } = useChart()
  const tooltipRef = useChartTooltipMotion(Boolean(active && payload?.length))

  const tooltipLabel = React.useMemo(() => {
    if (hideLabel || !payload?.length) {
      return null
    }

    const [item] = payload
    const datum = item?.payload as Record<string, unknown> | undefined
    const datumLabel = labelKey ? datum?.[labelKey] : undefined
    const rawLabel = typeof datumLabel === "string" || typeof datumLabel === "number" ? datumLabel : label
    if (rawLabel == null || rawLabel === "") return null

    const value = typeof rawLabel === "string" ? (config[rawLabel]?.label ?? rawLabel) : rawLabel
    const formattedLabel = labelFormatter ? labelFormatter(value, payload) : value
    if (formattedLabel == null || formattedLabel === "") return null

    return <div className={cn("break-words font-medium leading-4 text-foreground", labelClassName)}>{formattedLabel}</div>
  }, [
    label,
    labelFormatter,
    payload,
    hideLabel,
    labelClassName,
    config,
    labelKey,
  ])

  if (!active || !payload?.length) {
    return null
  }

  return (
    <div
      ref={tooltipRef}
      className={cn(
        "grid min-w-40 max-w-72 items-start gap-2 rounded-lg border border-border bg-background p-3 text-xs shadow-xl",
        className
      )}
    >
      {tooltipLabel}
      <div className="grid gap-2">
        {payload
          .filter((item) => item.type !== "none" && item.value != null)
          .map((item, index) => {
            const datum = item.payload as Record<string, unknown> | undefined
            const seriesKey = String(item.dataKey ?? "value")
            const datumKey = typeof datum?.key === "string" ? datum.key : undefined
            const configKey = datumKey && config[datumKey] ? datumKey : seriesKey
            const itemConfig = getPayloadConfigFromPayload(config, item, configKey)
            const rawName = nameKey ? datum?.[nameKey] : undefined
            const datumName = typeof rawName === "string" || typeof rawName === "number" ? rawName : undefined
            const itemName = itemConfig?.label ?? datumName ?? item.name ?? seriesKey
            const indicatorColor = color ?? itemConfig?.color ??
              (itemConfig?.theme ? `var(--color-${configKey})` : undefined) ??
              item.color ?? "var(--chart-2)"
            const indicatorBackground = typeof datum?.tooltipColor === "string" ? datum.tooltipColor : indicatorColor
            const formatted = formatter?.(item.value!, item.name ?? seriesKey, item, index, payload)
            const displayValue = Array.isArray(formatted) ? formatted[0] : formatted ??
              (typeof item.value === "number" ? item.value.toLocaleString("de-DE") : String(item.value))
            const displayName = Array.isArray(formatted) ? (formatted[1] ?? itemName) : itemName

            return (
              <div
                key={`${seriesKey}-${index}`}
                className="flex min-w-0 items-start gap-2 [&>svg]:size-2.5 [&>svg]:shrink-0 [&>svg]:text-muted-foreground"
              >
                {itemConfig?.icon ? <itemConfig.icon /> : !hideIndicator && (
                  <span
                    className={cn(
                      "mt-0.5 size-2.5 shrink-0 rounded-none",
                      indicator === "line" && "h-3 w-1",
                      indicator === "dashed" && "h-3 w-0 border-l-2 border-dashed bg-transparent"
                    )}
                    style={{ background: indicator === "dashed" ? undefined : indicatorBackground, borderColor: indicatorColor }}
                  />
                )}
                <div className="flex min-w-0 flex-1 items-start justify-between gap-4 leading-4">
                  <span className="min-w-0 break-words text-muted-foreground">{displayName}</span>
                  <span className="shrink-0 whitespace-nowrap text-right font-mono font-medium text-foreground tabular-nums">{displayValue}</span>
                </div>
              </div>
            )
          })}
      </div>
    </div>
  )
}

const ChartLegend = RechartsPrimitive.Legend

function ChartLegendContent({
  className,
  hideIcon = false,
  payload,
  verticalAlign = "bottom",
  nameKey,
}: React.ComponentProps<"div"> & {
  hideIcon?: boolean
  nameKey?: string
} & RechartsPrimitive.DefaultLegendContentProps) {
  const { config } = useChart()

  if (!payload?.length) {
    return null
  }

  return (
    <div
      className={cn(
        "flex items-center justify-center gap-4",
        verticalAlign === "top" ? "pb-3" : "pt-3",
        className
      )}
    >
      {payload
        .filter((item) => item.type !== "none")
        .map((item, index) => {
          const key = `${nameKey ?? item.dataKey ?? "value"}`
          const itemConfig = getPayloadConfigFromPayload(config, item, key)

          return (
            <div
              key={index}
              className={cn(
                "flex items-center gap-1.5 [&>svg]:h-3 [&>svg]:w-3 [&>svg]:text-muted-foreground"
              )}
            >
              {itemConfig?.icon && !hideIcon ? (
                <itemConfig.icon />
              ) : (
                <div
                  className="h-2 w-2 shrink-0 rounded-none"
                  style={{
                    backgroundColor: item.color,
                  }}
                />
              )}
              {itemConfig?.label}
            </div>
          )
        })}
    </div>
  )
}

function getPayloadConfigFromPayload(
  config: ChartConfig,
  payload: unknown,
  key: string
) {
  if (typeof payload !== "object" || payload === null) {
    return undefined
  }

  const payloadPayload =
    "payload" in payload &&
    typeof payload.payload === "object" &&
    payload.payload !== null
      ? payload.payload
      : undefined

  let configLabelKey: string = key

  if (
    key in payload &&
    typeof payload[key as keyof typeof payload] === "string"
  ) {
    configLabelKey = payload[key as keyof typeof payload] as string
  } else if (
    payloadPayload &&
    key in payloadPayload &&
    typeof payloadPayload[key as keyof typeof payloadPayload] === "string"
  ) {
    configLabelKey = payloadPayload[
      key as keyof typeof payloadPayload
    ] as string
  }

  return configLabelKey in config ? config[configLabelKey] : config[key]
}

export {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  ChartLegend,
  ChartLegendContent,
  ChartStyle,
  useChartTooltipMotion,
}
