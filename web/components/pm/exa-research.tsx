"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { date, write, api } from "@/lib/api";
import { useWorkspace } from "./context";
import { ErrorMessage } from "./shared";

type Candidate = {
  candidate_id: string;
  title: string;
  canonical_url: string;
  supporting_excerpt: string;
  publication_date: string | null;
  retrieved_at: string;
  content_status: "search_lead" | "fetched";
  content?: string;
  vehicle: string;
  market: string;
  uncertainties: string[];
};
type ResearchResponse = {
  candidates: Candidate[];
  cache: { hit: boolean; stale: boolean };
  request_metadata: { cost_dollars_total?: number };
  warnings: string[];
};

export function ExaResearch({ onDone }: { onDone: () => void }) {
  const { scope, actor } = useWorkspace();
  const [query, setQuery] = useState("");
  const [domains, setDomains] = useState("");
  const [maxResults, setMaxResults] = useState(5);
  const [activeQuery, setActiveQuery] = useState("");
  const [publicConfirmed, setPublicConfirmed] = useState(false);
  const [cacheOnly, setCacheOnly] = useState(false);
  const [results, setResults] = useState<ResearchResponse | null>(null);
  const [fetched, setFetched] = useState<Candidate | null>(null);
  const [fetchMeta, setFetchMeta] = useState<{ hit: boolean; cost?: number } | null>(null);
  const [rationale, setRationale] = useState("");
  const [selectionConfirmed, setSelectionConfirmed] = useState(false);
  const status = useQuery({
    queryKey: ["exa-status"],
    queryFn: () => api<{ configured: boolean }>("/research/exa/status"),
  });
  const search = useMutation({
    mutationFn: () =>
      write<ResearchResponse>("/research/exa/search", {
        query: query.trim(),
        public_data_confirmed: true,
        ...scope,
        max_results: maxResults,
        ...(domains.trim() ? { trusted_domains: domains.split(",").map((domain) => domain.trim()).filter(Boolean) } : {}),
        cache_only: cacheOnly,
      }),
    onSuccess: (response) => {
      setActiveQuery(query.trim());
      setResults(response);
      setFetched(null);
      setFetchMeta(null);
      setRationale("");
      setSelectionConfirmed(false);
    },
  });
  const fetchCandidate = useMutation({
    mutationFn: (lead: Candidate) =>
      write<ResearchResponse>("/research/exa/fetch", {
        identifier: lead.canonical_url,
        query: activeQuery,
        public_data_confirmed: true,
        ...scope,
        cache_only: cacheOnly,
      }),
    onSuccess: (response) => {
      setFetched(response.candidates[0] || null);
      setFetchMeta({ hit: response.cache.hit, cost: response.request_metadata.cost_dollars_total });
      setRationale("");
      setSelectionConfirmed(false);
    },
  });
  const importCandidate = useMutation({
    mutationFn: () => {
      if (!fetched || !actor) throw new Error("Select a source and a reviewer first.");
      return write<{ deduplicated: boolean }>("/research/exa/import", {
        candidate_id: fetched.candidate_id,
        actor: actor.id,
        rationale: rationale.trim(),
        selection_confirmed: true,
      });
    },
    onSuccess: (response) => {
      toast.success(response.deduplicated ? "Source already imported." : "Exa source imported for review.");
      onDone();
    },
  });
  const busy = search.isPending || fetchCandidate.isPending || importCandidate.isPending;
  const canRequest = publicConfirmed && (status.data?.configured || cacheOnly);
  return (
    <div className="pm-form">
      <p className="muted text-xs">
        Find public sources for {scope.vehicle} / {scope.market}. Select another market in the workspace to research it.
      </p>
      {status.error && <ErrorMessage error={status.error} />}
      {status.data && !status.data.configured && (
        <p role="status" className="muted text-xs">
          Exa is not configured on the API server. Set EXA_API_KEY in the private root .env
          and restart the API, or use an existing cached request.
        </p>
      )}
      <label className="pm-field">
        <span>Public research topic</span>
        <input
          className="pm-input"
          value={query}
          maxLength={240}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Public charging experience for BMW 5 Series"
        />
      </label>
      <label className="pm-field">
        <span>Trusted public domains (optional)</span>
        <input className="pm-input" value={domains} maxLength={500}
          onChange={(event) => setDomains(event.target.value)}
          placeholder="example.com, another-public-site.org" />
        <span className="muted text-xs">Separate domains with commas to narrow the search.</span>
      </label>
      <label className="pm-field">
        <span>Maximum leads (1–10)</span>
        <input className="pm-input" type="number" min={1} max={10} value={maxResults}
          onChange={(event) => setMaxResults(Math.min(10, Math.max(1, Number(event.target.value) || 1)))} />
      </label>
      <label className="muted text-xs">
        <input type="checkbox" checked={publicConfirmed}
          onChange={(event) => setPublicConfirmed(event.target.checked)} />{" "}
        I confirm the query contains only public, nonpersonal terms. No BMW records or customer verbatims.
      </label>
      <label className="muted text-xs">
        <input type="checkbox" checked={cacheOnly}
          onChange={(event) => setCacheOnly(event.target.checked)} />{" "}
        Cache only — replay the exact query, market, domains and lead limit without a new provider charge.
      </label>
      <Button type="button" disabled={!query.trim() || !canRequest || busy}
        onClick={() => search.mutate()}>
        {search.isPending ? "Searching…" : "Search Exa"}
      </Button>
      <p className="muted text-xs">Live search and fetch are separate requests and may each incur a provider charge.</p>
      {search.error && <ErrorMessage error={search.error} />}
      {results && (
        <div className="pm-form">
          <p className="muted text-xs" role="status">
            {results.candidates.length} unreviewed leads · {results.cache.hit ? "cache hit" :
              `Exa request${results.request_metadata.cost_dollars_total == null ? "" :
                ` · $${results.request_metadata.cost_dollars_total.toFixed(3)}`}`}
          </p>
          {results.candidates.map((lead) => (
            <article className="pm-panel" key={lead.candidate_id}>
              <strong>{lead.title}</strong>
              <p className="muted text-xs">
                {lead.vehicle} / {lead.market} · Published: {lead.publication_date ? date(lead.publication_date) : "unknown"}
              </p>
              <p className="muted text-xs">Market applicability is unverified; inspect the source before selecting it.</p>
              <p className="muted text-xs">{lead.supporting_excerpt.slice(0, 400) || "No search excerpt; fetch before review."}</p>
              <a href={lead.canonical_url} target="_blank" rel="noreferrer" className="text-xs">
                Open public source
              </a>
              <div><Button type="button" disabled={busy || !publicConfirmed}
                onClick={() => fetchCandidate.mutate(lead)}>Fetch source text</Button></div>
            </article>
          ))}
        </div>
      )}
      {fetchCandidate.error && <ErrorMessage error={fetchCandidate.error} />}
      {fetched && (
        <div className="pm-form">
          <p className="muted text-xs" role="status">
            Fetched unreviewed public text for {fetched.vehicle} / {fetched.market}.
            Retrieval: {date(fetched.retrieved_at)}. Publication date:
            {fetched.publication_date ? ` ${date(fetched.publication_date)}` : " unknown"}.
            {fetchMeta && (fetchMeta.hit ? " Cache hit." :
              ` Exa fetch${fetchMeta.cost == null ? "." : ` · $${fetchMeta.cost.toFixed(3)}.`}`)}
          </p>
          <p className="muted text-xs">{fetched.uncertainties.join(" ")}</p>
          <textarea className="pm-input" rows={6} readOnly aria-label="Fetched source preview"
            value={(fetched.content || "").slice(0, 1500)} />
          <label className="pm-field">
            <span>Why select this source?</span>
            <textarea className="pm-input" rows={3} value={rationale} maxLength={2000}
              onChange={(event) => setRationale(event.target.value)}
              placeholder="Explain its relevance and what still needs validation." />
          </label>
          <label className="muted text-xs">
            <input type="checkbox" checked={selectionConfirmed}
              onChange={(event) => setSelectionConfirmed(event.target.checked)} />{" "}
            Save this page snapshot as unreviewed evidence.
          </label>
          {importCandidate.error && <ErrorMessage error={importCandidate.error} />}
          <Button type="button" disabled={!actor || !rationale.trim() || !selectionConfirmed || busy}
            onClick={() => importCandidate.mutate()}>
            {importCandidate.isPending ? "Importing…" : "Import selected source"}
          </Button>
          {!actor && <p className="muted text-xs">Select an active human reviewer in the header first.</p>}
        </div>
      )}
    </div>
  );
}
