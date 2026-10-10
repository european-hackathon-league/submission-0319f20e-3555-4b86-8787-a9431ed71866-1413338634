"use client";
import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import Image from "next/image";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  ListChecks,
  GitBranch,
  FileSearch,
  Files,
  Globe2,
  History,
  Settings,
  Search,
  ArrowUpRight,
  RefreshCw,
  ChevronsUpDown,
  Car,
  Command,
  CircleHelp,
  Info,
} from "lucide-react";
import {
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { AppearanceToggle } from "@/components/appearance";
import { Button } from "@/components/ui/button";
import { api, allPages, query, readable } from "@/lib/api";
import type {
  Actor,
  Metrics,
  Requirement,
  Scope,
  Source,
  Workspace,
} from "@/lib/types";
import { WorkspaceContext } from "./context";
import { useStoredValue } from "@/hooks/use-stored-value";
import { Overview } from "./overview";
import { Register, Reviews } from "./register";
import { RequirementDrawer } from "./requirement";
import { EvidenceExplorer, Sources } from "./sources";
import { Pipeline } from "./pipeline";
import { AuditPage, Markets, SettingsPage } from "./secondary";
import { ErrorMessage, Loading } from "./shared";
const nav = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "requirements", label: "Requirements", icon: ListChecks },
  { key: "pipeline", label: "Pipeline", icon: GitBranch },
  { key: "evidence", label: "Evidence", icon: FileSearch },
  { key: "sources", label: "Sources & imports", icon: Files },
  { key: "markets", label: "Market comparison", icon: Globe2 },
];
const secondary = [
  { key: "reviews", label: "Needs review", icon: ListChecks },
  { key: "audit", label: "Audit trail", icon: History },
  { key: "settings", label: "Settings", icon: Settings },
];
export function WorkspaceApp({
  scope,
  section,
  deepRequirement,
  deepTab,
}: {
  scope: Scope;
  section: string;
  deepRequirement?: string;
  deepTab?: string;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const base = `/${scope.vehicle.toLowerCase()}/${scope.market.toLowerCase()}`;
  const qs = query(scope);
  const [actorId, setActor] = useStoredValue("bmw-pm-actor");
  const [density, setDensity] = useStoredValue("bmw-pm-density", "comfortable");
  const compact = density === "compact";
  const setCompact = (value: boolean) =>
    setDensity(value ? "compact" : "comfortable");
  const [command, setCommand] = useState(false);
  const [search, setSearch] = useState("");
  const workspace = useQuery({
    queryKey: ["workspace", qs],
    queryFn: ({ signal }) => api<Workspace>(`/workspace?${qs}`, { signal }),
  });
  const requirements = useQuery({
    queryKey: ["requirements", qs],
    queryFn: ({ signal }) =>
      allPages<Requirement>(`/requirements?${qs}`, signal),
  });
  const sources = useQuery({
    queryKey: ["sources", qs],
    queryFn: ({ signal }) => api<Source[]>(`/sources?${qs}`, { signal }),
  });
  const metrics = useQuery({
    queryKey: ["metrics", qs],
    queryFn: ({ signal }) => api<Metrics>(`/metrics?${qs}`, { signal }),
  });
  const actors = useQuery({
    queryKey: ["actors"],
    queryFn: ({ signal }) => api<Actor[]>("/actors", { signal }),
  });
  const activeActors =
    actors.data?.filter((a) => a.kind === "human" && a.active) || [];
  const actor = activeActors.find((a) => a.id === actorId);
  const refresh = useCallback(() => {
    void client.invalidateQueries();
  }, [client]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCommand((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const scopes = workspace.data?.available_scopes || [];
  const options = scopes.some(
    (s) => s.vehicle === scope.vehicle && s.market === scope.market,
  )
    ? scopes
    : [scope, ...scopes];
  const title =
    [...nav, ...secondary].find((n) => n.key === section)?.label || "Overview";
  const loadError =
    requirements.error ||
    sources.error ||
    metrics.error ||
    workspace.error ||
    actors.error;
  const context = {
    scope,
    base,
    actor,
    actors: activeActors,
    setActor,
    requirements: requirements.data || [],
    sources: sources.data || [],
    metrics: metrics.data,
    workspace: workspace.data,
    loading: requirements.isPending || sources.isPending || metrics.isPending,
    error: loadError,
    refresh,
    compact,
    setCompact,
  };
  const renderNav = (items: typeof nav) => (
    <SidebarGroup>
      <SidebarMenu>
        {items.map((item) => (
          <SidebarMenuItem key={item.key}>
            <SidebarMenuButton
              isActive={section === item.key}
              tooltip={item.label}
              render={
                <Link
                  href={`${base}${item.key === "overview" ? "" : "/" + item.key}`}
                />
              }
            >
              <item.icon />
              <span>{item.label}</span>
              {item.key === "reviews" &&
                !!metrics.data?.counts.open_reviews && (
                  <span className="nav-count">
                    {metrics.data.counts.open_reviews}
                  </span>
                )}
            </SidebarMenuButton>
          </SidebarMenuItem>
        ))}
      </SidebarMenu>
    </SidebarGroup>
  );
  return (
    <WorkspaceContext.Provider value={context}>
      <a href="#workspace-content" className="skip-link">
        Skip to content
      </a>
      <SidebarProvider
        style={{ "--sidebar-width": "15rem" } as React.CSSProperties}
      >
        <Sidebar collapsible="icon">
          <SidebarHeader>
            <Link
              href={base}
              className="brand-lockup"
              aria-label="BMW Product Intelligence home"
            >
              <span className="brand-symbol">
                <Image
                  src="/brand/bmw-white.svg"
                  alt="BMW"
                  width={38}
                  height={38}
                  priority
                />
              </span>
              <span className="brand-name">
                BMW<span className="brand-subtitle">Product intelligence</span>
              </span>
            </Link>
            <div className="scope-switcher">
              <Car size={20} />
              <div>
                <strong>
                  {scope.vehicle} · {scope.market}
                </strong>
                <span>Vehicle & market</span>
              </div>
              <ChevronsUpDown size={15} />
              <select
                aria-label="Vehicle and market"
                value={`${scope.vehicle}/${scope.market}`}
                onChange={(e) =>
                  router.push("/" + e.target.value.toLowerCase())
                }
              >
                {options.map((s) => (
                  <option
                    key={`${s.vehicle}/${s.market}`}
                    value={`${s.vehicle}/${s.market}`}
                  >
                    {s.vehicle} · {s.market}
                  </option>
                ))}
              </select>
            </div>
          </SidebarHeader>
          <SidebarContent>
            <SidebarGroupLabel>Workspace</SidebarGroupLabel>
            {renderNav(nav)}
            <div className="mt-auto">{renderNav(secondary)}</div>
          </SidebarContent>
          <SidebarFooter>
            <div className="sidebar-scope-note">
              <span className="mono">EVIDENCE TO DECISION</span>
              <span>Successor product planning</span>
              <span className="system-state">
                <i className={loadError ? "failed" : ""} />
                {loadError
                  ? "Connection needs attention"
                  : "Connected to local API"}
              </span>
            </div>
            <Link href={`${base}/settings`} className="workspace-profile">
              <span className="profile-monogram">
                {actor?.display_name.charAt(0) || "B"}
              </span>
              <span className="profile-label">
                <strong>{actor?.display_name || "Select a reviewer"}</strong>
                <span>
                  {actor
                    ? readable(actor.role)
                    : "Declared identity · local workspace"}
                </span>
              </span>
              <ArrowUpRight className="profile-arrow" size={15} />
            </Link>
          </SidebarFooter>
        </Sidebar>
        <SidebarInset>
          <header className="workspace-header">
            <div className="flex items-center gap-4">
              <SidebarTrigger />
              <span className="header-separator" />
              <span className="header-page">{title}</span>
            </div>
            <div className="header-controls">
              <button
                className="global-search"
                onClick={() => setCommand(true)}
                aria-label="Search workspace"
              >
                <Search size={14} />
                <span>Search workspace</span>
                <kbd>⌘ K</kbd>
              </button>
              <span className="workspace-status">Local workspace</span>
              <select
                className="actor-select"
                aria-label="Acting reviewer"
                value={actor?.id || ""}
                onChange={(e) => setActor(e.target.value)}
              >
                <option value="">Select reviewer</option>
                {activeActors.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.display_name} · {readable(a.role)}
                  </option>
                ))}
              </select>
              <Button
                variant="ghost"
                size="icon"
                aria-label="Refresh workspace"
                onClick={refresh}
              >
                <RefreshCw
                  size={16}
                  className={workspace.isFetching ? "animate-spin" : ""}
                />
              </Button>
              <AppearanceToggle />
            </div>
          </header>
          {scope.vehicle === "G60" && scope.market === "US" && (
            <div className="scope-limitation">
              <Info size={14} />
              <span>
                Supplied G60 / US inventory: 72.7% of unique feedback IDs come
                from Source B. Sample counts are not market prevalence.
              </span>
              <Link href={`${base}/evidence`}>
                Inspect evidence <ArrowUpRight size={12} />
              </Link>
            </div>
          )}
          <div
            id="workspace-content"
            tabIndex={-1}
            className={`workspace-content ${compact ? "density-compact" : ""}`}
          >
            <main>
              {loadError ? (
                <ErrorMessage error={loadError} retry={refresh} />
              ) : context.loading ? (
                <Loading label="Loading your evidence and requirements…" />
              ) : (
                <>
                  {section === "overview" && <Overview />}
                  {section === "requirements" && <Register />}
                  {section === "reviews" && <Reviews />}
                  {section === "evidence" && <EvidenceExplorer />}
                  {section === "sources" && <Sources />}
                  {section === "pipeline" && <Pipeline />}
                  {section === "markets" && <Markets />}
                  {section === "audit" && <AuditPage />}
                  {section === "settings" && <SettingsPage />}
                </>
              )}
              <footer className="workspace-footnote">
                <span>BMW concept · Product planning workspace</span>
                <span>
                  <CircleHelp size={12} /> Sample evidence informs decisions. It
                  does not establish market prevalence.
                </span>
              </footer>
            </main>
          </div>
        </SidebarInset>
      </SidebarProvider>
      <RequirementDrawer deepRequirement={deepRequirement} deepTab={deepTab} />
      <Dialog open={command} onOpenChange={setCommand}>
        <DialogContent className="command-dialog">
          <DialogTitle className="flex items-center gap-3">
            <Command size={22} /> Go to your workspace
          </DialogTitle>
          <DialogDescription>
            Search pages, requirement titles and stable keys.
          </DialogDescription>
          <input
            autoFocus
            className="pm-input"
            placeholder="Search requirements or pages…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <div className="command-results">
            {[...nav, ...secondary]
              .filter((n) =>
                n.label.toLowerCase().includes(search.toLowerCase()),
              )
              .map((n) => (
                <Link
                  key={n.key}
                  href={`${base}/${n.key}`}
                  onClick={() => setCommand(false)}
                >
                  <n.icon size={17} />
                  {n.label}
                  <ArrowUpRight size={14} />
                </Link>
              ))}
            {context.requirements
              .filter((r) =>
                `${r.key} ${r.title}`
                  .toLowerCase()
                  .includes(search.toLowerCase()),
              )
              .slice(0, 12)
              .map((r) => (
                <Link
                  key={r.id}
                  href={`${base}/requirements?requirement=${r.id}`}
                  onClick={() => setCommand(false)}
                >
                  <ListChecks size={17} />
                  <span>
                    {r.title}
                    <small>{r.key}</small>
                  </span>
                  <ArrowUpRight size={14} />
                </Link>
              ))}
          </div>
        </DialogContent>
      </Dialog>
    </WorkspaceContext.Provider>
  );
}
