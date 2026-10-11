import { Suspense } from "react";
import { notFound } from "next/navigation";
import { WorkspaceApp } from "@/components/pm/workspace";
export default async function Page({
  params,
}: {
  params: Promise<{ vehicle: string; market: string; view?: string[] }>;
}) {
  const { vehicle, market, view = [] } = await params;
  if (
    !/^[a-z0-9_-]{1,60}$/i.test(vehicle) ||
    !/^[a-z0-9_-]{1,40}$/i.test(market)
  )
    notFound();
  const section = view[0] || "overview";
  if (
    ![
      "overview",
      "agents",
      "requirements",
      "reviews",
      "evidence",
      "twin",
      "sources",
      "pipeline",
      "markets",
      "signals",
      "requests",
      "priorities",
      "audit",
      "settings",
    ].includes(section)
  )
    notFound();
  return (
    <Suspense fallback={<div className="page-loading">Opening workspace…</div>}>
      <WorkspaceApp
        key={`${vehicle}/${market}`}
        scope={{ vehicle: vehicle.toUpperCase(), market: market.toUpperCase() }}
        section={section}
        deepRequirement={view[1]}
        deepTab={view[2]}
      />
    </Suspense>
  );
}
