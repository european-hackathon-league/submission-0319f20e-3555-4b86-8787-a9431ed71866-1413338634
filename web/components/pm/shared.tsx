"use client";
import Link from "next/link";
import { AlertCircle, ArrowUpRight, Loader2, ScanLine } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { readable } from "@/lib/api";
import { useWorkspace } from "./context";
export function Status({ value }: { value: string }) {
  return <span className={`status status-${value}`}>{readable(value)}</span>;
}
export function Grade({ value }: { value: string }) {
  return (
    <span
      className={`grade grade-${value}`}
      title={`Evidence quality: ${value}`}
    >
      {value}
    </span>
  );
}
export function ScoreLabel({ score, grade }: { score: number; grade: string }) {
  return (
    <span className="score-label">
      <span className="tabular-nums">{score.toFixed(1)}</span>
      <Grade value={grade} />
    </span>
  );
}
export function Panel({
  title,
  description,
  action,
  children,
  className = "",
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={`pm-panel ${className}`}>
      <div className="panel-heading">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
export function Heading({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </div>
  );
}
export function Empty({
  title = "Nothing here yet",
  description = "Import evidence and run the pipeline to begin.",
  action,
}: {
  title?: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="pm-empty">
      <ScanLine size={25} />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}
export function Loading({ label = "Loading records…" }: { label?: string }) {
  return (
    <div className="pm-loading" role="status">
      <Loader2 className="animate-spin" size={18} />
      {label}
    </div>
  );
}
export function ErrorMessage({
  error,
  retry,
}: {
  error: Error;
  retry?: () => void;
}) {
  return (
    <div className="pm-alert error" role="alert">
      <AlertCircle size={17} />
      <div>
        {error.message}
        {retry && (
          <button className="text-link block" onClick={retry}>
            Retry loading
          </button>
        )}
      </div>
    </div>
  );
}
export function RequirementLink({
  id,
  children,
  tab,
}: {
  id: string;
  children: React.ReactNode;
  tab?: string;
}) {
  const { base } = useWorkspace();
  const pathname = usePathname();
  const params = useSearchParams();
  const next = new URLSearchParams(
    pathname === `${base}/requirements` ? params : undefined,
  );
  next.set("requirement", id);
  next.delete("version");
  next.delete("score");
  if (tab) next.set("tab", tab);
  else next.delete("tab");
  return (
    <Link className="text-link" href={`${base}/requirements?${next}`}>
      {children}
    </Link>
  );
}
export function MoreLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link className="text-link inline-flex items-center gap-2" href={href}>
      {children}
      <ArrowUpRight size={14} />
    </Link>
  );
}
export function useUrlState() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const set = (values: Record<string, string | undefined>, push = false) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(values)) {
      if (value === undefined || value === "") next.delete(key);
      else next.set(key, value);
    }
    const href = `${pathname}${next.size ? "?" + next.toString() : ""}`;
    if (push) router.push(href, { scroll: false });
    else router.replace(href, { scroll: false });
  };
  return { params, set };
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="pm-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
