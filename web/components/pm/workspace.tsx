"use client";
import { useEffect, useState, useCallback } from "react";
import dynamic from "next/dynamic";
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
  ChevronRight,
  Layers3,
  Bot,
  CarFront,
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
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarProvider,
  SidebarInset,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { AppearanceToggle } from "@/components/appearance";
import { MotionField } from "@/components/motion-field";
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
const VehicleStudio = dynamic(() => import("./vehicle-studio").then((module) => module.VehicleStudio), {
  ssr: false,
  loading: () => <Loading label="Opening vehicle studio…" />,
});
const primaryPages = [
  { key: "overview", label: "Overview", icon: LayoutDashboard },
  { key: "agents", label: "Multi-agentic system", icon: Bot },
  { key: "twin", label: "Vehicle Studio", icon: CarFront },
];
const softwarePages = [
  { key: "requirements", label: "Requirements", icon: ListChecks },
  { key: "evidence", label: "Evidence", icon: FileSearch },
  { key: "pipeline", label: "Pipeline", icon: GitBranch },
  { key: "sources", label: "Sources & imports", icon: Files },
  { key: "reviews", label: "Needs review", icon: ListChecks },
  { key: "markets", label: "Market comparison", icon: Globe2 },
  { key: "audit", label: "Audit trail", icon: History },
  { key: "settings", label: "Settings", icon: Settings },
];
const pages = [primaryPages[0], ...softwarePages, ...primaryPages.slice(1)];

function SoftwareNavigation({
  base,
  section,
  reviewCount,
}: {
  base: string;
  section: string;
  reviewCount?: number;
}) {
  const { state, setOpen } = useSidebar();
  const [softwareState, setSoftwareState] = useStoredValue(
    "bmw-software-navigation",
    "open",
  );
  const expanded = softwareState !== "closed";
  const active = softwarePages.some((page) => page.key === section);

  return (
    <SidebarMenuItem>
      <SidebarMenuButton
        type="button"
        tooltip="Software"
        isActive={active}
        aria-expanded={expanded}
        aria-controls="software-navigation"
        className="software-nav-trigger"
        onClick={() => {
          if (state === "collapsed") {
            setOpen(true);
            setSoftwareState("open");
          } else {
            setSoftwareState(expanded ? "closed" : "open");
          }
        }}
      >
        <Layers3 />
        <span>Software</span>
        <ChevronRight className={`software-nav-chevron ${expanded ? "is-open" : ""}`} />
      </SidebarMenuButton>
      <SidebarMenuSub id="software-navigation" hidden={!expanded}>
        {softwarePages.map((page) => (
          <SidebarMenuSubItem key={page.key}>
            <SidebarMenuSubButton
              isActive={section === page.key}
              aria-current={section === page.key ? "page" : undefined}
              render={<Link href={`${base}/${page.key}`} />}
            >
              <span>{page.label}</span>
              {page.key === "reviews" && !!reviewCount && (
                <span className="nav-count">{reviewCount}</span>
              )}
            </SidebarMenuSubButton>
          </SidebarMenuSubItem>
        ))}
      </SidebarMenuSub>
    </SidebarMenuItem>
  );
}
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
  const [headerScrolled, setHeaderScrolled] = useState(false);
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
  useEffect(() => {
    if (section !== "overview") return;
    const update = () => setHeaderScrolled(window.scrollY > 8);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, [section]);
  const scopes = workspace.data?.available_scopes || [];
  const options = scopes.some(
    (s) => s.vehicle === scope.vehicle && s.market === scope.market,
  )
    ? scopes
    : [scope, ...scopes];
  const title =
    pages.find((n) => n.key === section)?.label || "Overview";
  const loadError =
    requirements.error ||
    sources.error ||
    metrics.error ||
    workspace.error;
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
  return (
    <WorkspaceContext.Provider value={context}>
      <a href="#workspace-content" className="skip-link">
        Skip to content
      </a>
      <SidebarProvider
        style={{ "--sidebar-width": "15rem" } as React.CSSProperties}
      >
        <Sidebar collapsible="icon" className="workspace-sidebar">
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
            <SidebarGroup>
              <SidebarGroupLabel>Workspace</SidebarGroupLabel>
              <SidebarMenu>
                <SidebarMenuItem>
                  <SidebarMenuButton
                    isActive={section === "overview"}
                    aria-current={section === "overview" ? "page" : undefined}
                    tooltip="Overview"
                    render={<Link href={base} />}
                  >
                    <LayoutDashboard />
                    <span>Overview</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
                <SoftwareNavigation
                  base={base}
                  section={section}
                  reviewCount={metrics.data?.counts.open_reviews}
                />
                {primaryPages.slice(1).map((page) => (
                  <SidebarMenuItem key={page.key}>
                    <SidebarMenuButton
                      isActive={section === page.key}
                      aria-current={section === page.key ? "page" : undefined}
                      tooltip={page.label}
                      render={<Link href={`${base}/${page.key}`} />}
                    >
                      <page.icon />
                      <span>{page.label}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroup>
          </SidebarContent>
          <SidebarFooter>
            <div className="reviewer-switcher">
              <span className="profile-monogram">
                {actor?.display_name.charAt(0) || "B"}
              </span>
              <span className="profile-label">
                <strong>{actor?.display_name || "Select reviewer"}</strong>
                <span>{actor ? readable(actor.role) : "Acting reviewer"}</span>
              </span>
              <ChevronsUpDown className="profile-arrow" size={15} />
              <select
                aria-label="Acting reviewer"
                value={actor?.id || ""}
                onChange={(event) => setActor(event.target.value)}
                disabled={actors.isPending || !!actors.error}
              >
                <option value="">
                  {actors.error ? "Reviewers unavailable" : "Select reviewer"}
                </option>
                {activeActors.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.display_name} · {readable(person.role)}
                  </option>
                ))}
              </select>
            </div>
          </SidebarFooter>
        </Sidebar>
        <SidebarInset className={section === "overview" ? "overview-shell" : undefined}>
          {section === "overview" && <MotionField />}
          <header className={`workspace-header ${section === "overview" && headerScrolled ? "is-scrolled" : ""}`}>
            <div className="flex items-center gap-4">
              <SidebarTrigger />
              <span className="header-page">{title}</span>
            </div>
            <div className="header-controls">
              <button
                className="global-search"
                onClick={() => setCommand(true)}
                aria-label="Search workspace"
              >
                <Search size={14} />
                <span>Search</span>
                <kbd>⌘ K</kbd>
              </button>
              {section !== "agents" && (
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
              )}
              <AppearanceToggle />
            </div>
          </header>
          <div
            id="workspace-content"
            tabIndex={-1}
            className={`workspace-content ${compact ? "density-compact" : ""}`}
          >
            <main>
              {section === "agents" ? (
                <div className="multi-agent-page">
                  <h1>Multi-agentic system</h1>
                </div>
              ) : loadError ? (
                <ErrorMessage error={loadError} retry={refresh} />
              ) : context.loading ? (
                <Loading label="Loading your evidence and requirements…" />
              ) : (
                <>
                  {section === "overview" && <Overview />}
                  {section === "requirements" && <Register />}
                  {section === "reviews" && <Reviews />}
                  {section === "evidence" && <EvidenceExplorer />}
                  {section === "twin" && <VehicleStudio />}
                  {section === "sources" && <Sources />}
                  {section === "pipeline" && <Pipeline />}
                  {section === "markets" && <Markets />}
                  {section === "audit" && <AuditPage />}
                  {section === "settings" && <SettingsPage />}
                </>
              )}
              {section !== "agents" && (
                <footer className="workspace-footnote">
                  <span>BMW concept · Product planning workspace</span>
                  <span>
                    <CircleHelp size={12} /> Sample evidence informs decisions.
                    It does not establish market prevalence.
                  </span>
                </footer>
              )}
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
            {pages
              .filter((n) =>
                n.label.toLowerCase().includes(search.toLowerCase()),
              )
              .map((n) => (
                <Link
                  key={n.key}
                  href={n.key === "overview" ? base : `${base}/${n.key}`}
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
