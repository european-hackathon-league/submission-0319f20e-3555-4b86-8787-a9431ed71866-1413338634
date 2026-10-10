import { TrendingDown, TrendingUp } from "lucide-react"
import { money } from "@/lib/filters"

export type Metric = { label: string; value: number; previous?: number | null; format?: "money" | "count"; increaseBad?: boolean }

export function SectionCards({ metrics, comparisonNoteId }: { metrics: Metric[]; comparisonNoteId?: string }) {
  return <div className="metric-grid" style={{ "--metric-count": metrics.length } as React.CSSProperties}>
    {metrics.map((metric) => {
      const change = metric.previous != null && metric.previous !== 0
        ? ((metric.value - metric.previous) / Math.abs(metric.previous)) * 100 : null
      const good = change == null || change === 0 ? null : metric.increaseBad ? change < 0 : change > 0
      return <section key={metric.label} className="metric-cell" aria-label={metric.label}>
        <h3 className="metric-label">{metric.label}</h3>
        <p className="metric-value">{metric.format === "count" ? new Intl.NumberFormat("de-DE").format(metric.value) : money.format(metric.value)}</p>
        {metric.previous !== undefined && <div className="metric-comparison" aria-describedby={comparisonNoteId}>
          <span className={good === null ? "text-muted-foreground" : good ? "text-success" : "text-destructive"}>
            {change == null ? "No prior comparison" : <>{change >= 0 ? <TrendingUp aria-hidden="true" /> : <TrendingDown aria-hidden="true" />}{change >= 0 ? "+" : ""}{change.toFixed(1)}%</>}
          </span>
          {change != null && <span className="metric-comparison-label">vs. prior period{comparisonNoteId ? "*" : ""}</span>}
        </div>}
      </section>
    })}
  </div>
}
