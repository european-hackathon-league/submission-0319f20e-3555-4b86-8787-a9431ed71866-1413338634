"use client";
import { createContext, useContext } from "react";
import type {
  Actor,
  Scope,
  Requirement,
  Source,
  Metrics,
  Workspace,
} from "@/lib/types";
export type WorkspaceContextValue = {
  scope: Scope;
  base: string;
  actor: Actor | undefined;
  actors: Actor[];
  setActor: (id: string) => void;
  requirements: Requirement[];
  sources: Source[];
  metrics: Metrics | undefined;
  workspace: Workspace | undefined;
  loading: boolean;
  error: Error | null;
  refresh: () => void;
  compact: boolean;
  setCompact: (value: boolean) => void;
};
export const WorkspaceContext = createContext<WorkspaceContextValue | null>(
  null,
);
export function useWorkspace() {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error("Workspace provider missing");
  return context;
}
