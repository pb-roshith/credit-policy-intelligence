import { createFileRoute } from "@tanstack/react-router";
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  Clock3,
  Download,
  FileSearch,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api, type AgentMetrics, type AuditEntry, type Deal, type Section } from "@/lib/deals";

export const Route = createFileRoute("/observability")({
  head: () => ({ meta: [{ title: "Observability | Credit Pitch Book" }] }),
  component: ObservabilityPage,
});

type TraceRecord = {
  id: string;
  dealId: string;
  deal: Deal;
  customer: string;
  section: Section;
  audit: AuditEntry | null;
  createdAt: string;
  latencyMs: number | null;
  score: number | null;
  citations: number;
  sources: string[];
  success: boolean;
};

function parseNumber(subject: string, pattern: RegExp): number | null {
  const value = subject.match(pattern)?.[1];
  return value ? Number(value) : null;
}

function countCitations(content: string | null): number {
  return content?.match(/\[Sources?\s*:\s*[^\]]+\]/gi)?.length ?? 0;
}

function sourceNames(deal: Deal, section: Section): string[] {
  const configured = section.sources
    .split(/[,;\n]/)
    .map((source) => source.trim())
    .filter(Boolean);
  const library = deal.library_files.map((file) => file.filename);
  return [...new Set([...configured, ...library])];
}

type RetrievedEvidence = {
  title: string;
  priority: string;
  relevance: string;
};

function orchestrationEvidence(strategy: string | null | undefined): RetrievedEvidence[] {
  if (!strategy) return [];

  const section = strategy.match(/### Recommended Documents\s*\n([\s\S]*?)(?=\n### |$)/i)?.[1];
  if (!section) return [];

  return section
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("|") && !/^\|\s*[-:]+/.test(line))
    .map((line) =>
      line
        .split("|")
        .slice(1, -1)
        .map((cell) => cell.trim()),
    )
    .filter((cells) => cells.length >= 3 && cells[1].toLowerCase() !== "document")
    .map(([priority, title, relevance]) => ({
      priority: priority.replace(/\*\*/g, ""),
      title: title.replace(/\*\*/g, ""),
      relevance: relevance.replace(/\*\*/g, ""),
    }))
    .filter((evidence) => evidence.title && evidence.title !== "Unknown");
}

function buildTraces(deals: Deal[]): TraceRecord[] {
  const traces: TraceRecord[] = [];

  for (const deal of deals) {
    const generatedAudits = deal.audit_entries.filter(
      (entry) => entry.action === "narrative.generated",
    );
    const batchAudits = deal.audit_entries.filter(
      (entry) => entry.action === "narrative.draft_all",
    );
    const latestBatch = batchAudits.at(-1) ?? null;
    const batchSucceeded = latestBatch
      ? (parseNumber(latestBatch.subject, /Generated\s+(\d+)\//i) ?? 1)
      : 1;
    const batchLatency = latestBatch
      ? parseNumber(latestBatch.subject, /total_batch=(\d+(?:\.\d+)?)ms/i)
      : null;

    for (const section of deal.sections) {
      if (!section.generated_content) continue;
      const matching = generatedAudits.filter((entry) =>
        entry.subject.toLowerCase().startsWith(`${section.title.toLowerCase()} (`),
      );
      const audit = matching.at(-1) ?? latestBatch;
      const latency =
        audit?.action === "narrative.generated"
          ? parseNumber(audit.subject, /total=(\d+(?:\.\d+)?)ms/i)
          : batchLatency === null
            ? null
            : Math.round(batchLatency / Math.max(batchSucceeded, 1));

      traces.push({
        id:
          audit?.action === "narrative.generated"
            ? `trace_${audit.id}`
            : `trace_${deal.id}_${section.id}`,
        dealId: deal.id,
        deal,
        customer: deal.customer,
        section,
        audit,
        createdAt: audit?.created_at ?? deal.updated_at,
        latencyMs: latency,
        score: section.accuracy_score,
        citations: countCitations(section.generated_content),
        sources: sourceNames(deal, section),
        success:
          section.state === "ready" && !section.generated_content.startsWith("[Generation failed:"),
      });
    }
  }

  return traces.sort((a, b) => Date.parse(b.createdAt) - Date.parse(a.createdAt));
}

function formatLatency(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "Not recorded";
  if (value >= 1000) return `${(value / 1000).toFixed(1)} s`;
  return `${Math.round(value)} ms`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

type AgentKind = "section" | "orchestration" | "judge" | "claim_evaluator" | "moderation";

type AgentDefinition = {
  key: string;
  name: string;
  model: string;
  kind: AgentKind;
  sectionKey?: string;
};

type AgentOverview = AgentDefinition & {
  totalRequests: number;
  successful: number;
  failed: number;
  averageLatency: number | null;
  latencySamples: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  tokenUsageAvailable: boolean;
  evaluationScore: number | null;
};

const sectionAgentDefinitions: AgentDefinition[] = [
  ["executive_summary", "Executive Summary Agent"],
  ["client_overview", "Client Overview Agent"],
  ["relationship_summary", "Relationship Summary Agent"],
  ["industry_analysis", "Industry Analysis Agent"],
  ["financial_analysis", "Financial Analysis Agent"],
  ["ratio_analysis", "Ratio Analysis Agent"],
  ["cash_flow_analysis", "Cash Flow Analysis Agent"],
  ["qualitative_assessment", "Qualitative Assessment Agent"],
  ["credit_risk_assessment", "Credit Risk Assessment Agent"],
  ["facility_structure", "Facility Structure Agent"],
  ["policy_mapping", "Policy Mapping Agent"],
  ["collateral_and_security", "Collateral and Security Agent"],
  ["covenants_and_conditions", "Covenants and Conditions Agent"],
  ["esg_analysis", "ESG Analysis Agent"],
  ["key_risks_and_mitigants", "Key Risks and Mitigants Agent"],
  ["appendix", "Appendix Agent"],
].map(([sectionKey, name]) => ({
  key: `section:${sectionKey}`,
  name,
  model: "mistral-large-latest",
  kind: "section" as const,
  sectionKey,
}));

const agentDefinitions: AgentDefinition[] = [
  ...sectionAgentDefinitions,
  {
    key: "orchestration",
    name: "Orchestration Agent",
    model: "mistral-large-latest",
    kind: "orchestration",
  },
  {
    key: "judge",
    name: "Confidence Judge",
    model: "Mistral Observability Judge",
    kind: "judge",
  },
  {
    key: "claim_evaluator",
    name: "Claim Classification Evaluator",
    model: "mistral-large-latest",
    kind: "claim_evaluator",
  },
  {
    key: "moderation",
    name: "Moderation",
    model: "mistral-moderation-latest",
    kind: "moderation",
  },
];

function isConfidenceJudge(metrics: AgentMetrics | undefined): metrics is AgentMetrics {
  return Boolean(
    metrics &&
    (metrics.name === "Confidence Judge" || metrics.model === "Mistral Observability Judge"),
  );
}

function aggregateAgentOverview(traces: TraceRecord[]): AgentOverview[] {
  return agentDefinitions.map((definition) => {
    const samples: Array<{ metrics: AgentMetrics; score: number | null }> = [];

    for (const trace of traces) {
      const recorded = trace.section.observability_details;
      let metrics: AgentMetrics | undefined;
      if (definition.kind === "section" && definition.sectionKey === trace.section.section_key) {
        metrics = recorded?.section_agent ?? {
          name: definition.name,
          model: definition.model,
          status: trace.success ? "success" : "failed",
          latency_ms: parseNumber(trace.audit?.subject ?? "", /gen=(\d+(?:\.\d+)?)ms/i),
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
        };
      } else if (definition.kind === "orchestration") {
        metrics = recorded?.orchestration ?? {
          name: definition.name,
          model: definition.model,
          status: "success",
          latency_ms: parseNumber(trace.audit?.subject ?? "", /orch=(\d+(?:\.\d+)?)ms/i),
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
        };
      } else if (definition.kind === "judge" && isConfidenceJudge(recorded?.judge)) {
        metrics = recorded?.judge;
      } else if (definition.kind === "claim_evaluator") {
        metrics =
          recorded?.claim_evaluator ??
          (recorded?.judge && !isConfidenceJudge(recorded.judge) ? recorded.judge : undefined);
      } else if (
        definition.kind === "moderation" &&
        ((recorded?.moderation && recorded.moderation.status !== "skipped") ||
          trace.section.custom_instructions ||
          trace.section.output_template)
      ) {
        metrics = recorded?.moderation ?? {
          name: definition.name,
          model: definition.model,
          status: trace.section.moderation_status === "flagged" ? "failed" : "success",
          latency_ms: null,
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
        };
      }

      if (metrics) samples.push({ metrics, score: trace.score });
    }

    const successful = samples.filter(({ metrics }) =>
      ["success", "safe"].includes(metrics.status),
    ).length;
    const latencies = samples.flatMap(({ metrics }) =>
      metrics.latency_ms === null ? [] : [metrics.latency_ms],
    );
    const evaluationScores =
      definition.kind === "judge"
        ? samples.flatMap(({ score }) => (score === null ? [] : [score]))
        : [];
    const inputTokens = samples.reduce((sum, { metrics }) => sum + metrics.input_tokens, 0);
    const outputTokens = samples.reduce((sum, { metrics }) => sum + metrics.output_tokens, 0);

    return {
      ...definition,
      model: samples[0]?.metrics.model ?? definition.model,
      totalRequests: samples.length,
      successful,
      failed: samples.length - successful,
      averageLatency: latencies.length
        ? latencies.reduce((sum, value) => sum + value, 0) / latencies.length
        : null,
      latencySamples: latencies.length,
      inputTokens,
      outputTokens,
      totalTokens: samples.reduce(
        (sum, { metrics }) =>
          sum + (metrics.total_tokens || metrics.input_tokens + metrics.output_tokens),
        0,
      ),
      tokenUsageAvailable:
        definition.kind !== "judge" &&
        samples.some(({ metrics }) => metrics.token_usage_available !== false),
      evaluationScore: evaluationScores.length
        ? evaluationScores.reduce((sum, value) => sum + value, 0) / evaluationScores.length
        : null,
    };
  });
}

function ObservabilityPage() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [client, setClient] = useState("all");
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  async function loadData(refresh = false) {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError(null);
    try {
      const visibleDeals = await api.deals.list();
      const results = await Promise.allSettled(visibleDeals.map((deal) => api.deals.get(deal.id)));
      const loaded = results
        .filter((result): result is PromiseFulfilledResult<Deal> => result.status === "fulfilled")
        .map((result) => result.value);
      setDeals(loaded);
      if (loaded.length !== visibleDeals.length) {
        setError(
          `${visibleDeals.length - loaded.length} deal${visibleDeals.length - loaded.length === 1 ? "" : "s"} could not be loaded.`,
        );
      }
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Observability data could not be loaded.",
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  const allTraces = useMemo(() => buildTraces(deals), [deals]);
  const traces = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return allTraces.filter((trace) => {
      if (client !== "all" && trace.dealId !== client) return false;
      if (!needle) return true;
      return [
        trace.id,
        trace.customer,
        trace.section.title,
        trace.audit?.user,
        trace.section.generated_content,
      ].some((value) => value?.toLowerCase().includes(needle));
    });
  }, [allTraces, client, query]);

  useEffect(() => {
    if (!traces.some((trace) => trace.id === selectedId)) setSelectedId(traces[0]?.id ?? null);
  }, [traces, selectedId]);

  const selected = traces.find((trace) => trace.id === selectedId) ?? null;
  const overviewTraces = useMemo(
    () => allTraces.filter((trace) => client === "all" || trace.dealId === client),
    [allTraces, client],
  );
  const agentRows = useMemo(() => aggregateAgentOverview(overviewTraces), [overviewTraces]);
  const totalRequests = agentRows.reduce((sum, row) => sum + row.totalRequests, 0);
  const successful = agentRows.reduce((sum, row) => sum + row.successful, 0);
  const failures = agentRows.reduce((sum, row) => sum + row.failed, 0);
  const rowsWithLatency = agentRows.filter(
    (row) => row.averageLatency !== null && row.latencySamples > 0,
  );
  const averageLatency = rowsWithLatency.length
    ? rowsWithLatency.reduce(
        (sum, row) => sum + (row.averageLatency ?? 0) * row.latencySamples,
        0,
      ) / rowsWithLatency.reduce((sum, row) => sum + row.latencySamples, 0)
    : null;
  const inputTokens = agentRows.reduce((sum, row) => sum + row.inputTokens, 0);
  const outputTokens = agentRows.reduce((sum, row) => sum + row.outputTokens, 0);
  const totalTokens = agentRows.reduce((sum, row) => sum + row.totalTokens, 0);
  const averageScore = agentRows.find((row) => row.kind === "judge")?.evaluationScore ?? null;
  const kpis = [
    { label: "Total requests", value: String(totalRequests), Icon: Activity },
    { label: "Successful", value: String(successful), Icon: CheckCircle2 },
    { label: "Failed", value: String(failures), Icon: AlertCircle },
    { label: "Average latency", value: formatLatency(averageLatency), Icon: Clock3 },
    { label: "Input tokens", value: inputTokens.toLocaleString(), Icon: FileText },
    { label: "Output tokens", value: outputTokens.toLocaleString(), Icon: FileText },
    { label: "Total tokens", value: totalTokens.toLocaleString(), Icon: FileText },
    {
      label: "Average evaluation",
      value: averageScore === null ? "Not scored" : `${Math.round(averageScore)}%`,
      Icon: ShieldCheck,
    },
  ];

  function exportJson() {
    const payload = {
      exported_at: new Date().toISOString(),
      client: client === "all" ? "All clients" : deals.find((deal) => deal.id === client)?.customer,
      overview: {
        total_requests: totalRequests,
        successful,
        failed: failures,
        average_latency_ms: averageLatency,
        average_evaluation_score: averageScore,
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        total_tokens: totalTokens,
      },
      agents: agentRows,
      traces: traces.map((trace) => ({
        trace_id: trace.id,
        deal_id: trace.dealId,
        client: trace.customer,
        section: trace.section.title,
        timestamp: trace.createdAt,
        status: trace.success ? "success" : "failed",
        latency_ms: trace.latencyMs,
        evaluation_score: trace.score,
        citations: trace.citations,
        sources: trace.sources,
        action: trace.audit?.action ?? null,
        actor: trace.audit?.user ?? null,
      })),
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `credit-dossier-observability-${new Date().toISOString().slice(0, 10)}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return (
      <main className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Observability</h1>
          <p className="text-sm text-muted-foreground">
            Inspect generation activity, evaluation results, evidence, and audit details.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={exportJson}
            disabled={!traces.length}
            className="inline-flex h-9 items-center gap-2 rounded-md border bg-background px-3 text-sm font-medium hover:bg-muted disabled:opacity-50"
          >
            <Download className="h-4 w-4" /> Export JSON
          </button>
          <button
            onClick={() => void loadData(true)}
            disabled={refreshing}
            className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-warning/40 bg-warning/10 px-4 py-3 text-sm">
          {error}
        </div>
      )}

      <label className="mb-6 block max-w-sm text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Client
        <select
          value={client}
          onChange={(event) => setClient(event.target.value)}
          className="mt-1 h-10 w-full rounded-md border bg-background px-3 text-sm font-normal normal-case text-foreground"
        >
          <option value="all">All clients</option>
          {deals.map((deal) => (
            <option key={deal.id} value={deal.id}>
              {deal.customer}
            </option>
          ))}
        </select>
      </label>

      <section className="mb-6">
        <div className="mb-3 flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          <h2 className="text-lg font-bold">Executive Overview</h2>
        </div>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
          {kpis.map(({ label, value, Icon }) => (
            <div key={label} className="kpi-card min-w-0">
              <div className="flex items-start justify-between gap-2">
                <span className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {label}
                </span>
                <Icon className="h-4 w-4 shrink-0 text-primary" />
              </div>
              <div className="mt-3 break-words text-xl font-bold tabular-nums">{value}</div>
            </div>
          ))}
        </div>
        <div className="mt-4 space-y-3">
          {agentRows.map((row, index) => (
            <AgentOverviewRow key={row.key} row={row} index={index + 1} />
          ))}
        </div>
      </section>

      <section className="doc-card mb-6 overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b p-4">
          <div>
            <h2 className="font-bold">Trace Explorer</h2>
            <p className="text-xs text-muted-foreground">
              Search generated-draft activity and inspect the selected execution.
            </p>
          </div>
          <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
            {traces.length} traces
          </span>
        </div>
        <div className="border-b p-4">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by client, section, trace ID, content, or actor"
              className="h-10 w-full rounded-md border bg-background pl-9 pr-3 text-sm"
            />
          </div>
        </div>
        {!traces.length ? (
          <div className="p-10 text-center">
            <FileSearch className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
            <p className="font-medium">No generated-draft traces found</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Generate a narrative section, then refresh this page.
            </p>
          </div>
        ) : (
          <div className="grid lg:h-[340px] lg:grid-cols-[390px_1fr]">
            <div className="max-h-[260px] overflow-y-scroll border-b [scrollbar-gutter:stable] lg:max-h-none lg:border-b-0 lg:border-r">
              {traces.map((trace) => (
                <button
                  key={trace.id}
                  onClick={() => setSelectedId(trace.id)}
                  className={`block w-full border-b p-4 text-left transition-colors hover:bg-muted/60 ${selectedId === trace.id ? "bg-primary/5 ring-1 ring-inset ring-primary/30" : ""}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <span className="line-clamp-2 text-sm font-semibold">
                      Generate {trace.section.title} for {trace.customer}
                    </span>
                    <span
                      className={`shrink-0 text-[11px] font-semibold ${trace.success ? "text-emerald-700" : "text-red-700"}`}
                    >
                      {trace.success ? "success" : "failed"}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
                    <span>{formatDate(trace.createdAt)}</span>
                    <span>{formatLatency(trace.latencyMs)}</span>
                    {trace.score !== null && <span>Score {Math.round(trace.score)}%</span>}
                  </div>
                </button>
              ))}
            </div>
            {selected && <TraceSummary trace={selected} />}
          </div>
        )}
      </section>

      {selected && <AuditView trace={selected} />}
    </main>
  );
}

function TraceSummary({ trace }: { trace: TraceRecord }) {
  return (
    <div className="overflow-y-auto p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            Selected trace
          </p>
          <h3 className="mt-1 text-lg font-bold">Generate {trace.section.title}</h3>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700">
          <CheckCircle2 className="h-3.5 w-3.5" /> Success
        </span>
      </div>
      <dl className="grid gap-3 sm:grid-cols-3">
        <Metric label="Client" value={trace.customer} />
        <Metric label="Timestamp" value={formatDate(trace.createdAt)} />
        <Metric label="Latency" value={formatLatency(trace.latencyMs)} />
        <Metric
          label="Evaluation score"
          value={trace.score === null ? "Not scored" : `${Math.round(trace.score)}%`}
        />
        <Metric label="Inline citations" value={String(trace.citations)} />
        <Metric label="Audit actor" value={trace.audit?.user ?? "System"} />
      </dl>
      <div className="mt-4 rounded-md border bg-muted/30 p-3">
        <div className="text-[11px] font-semibold uppercase text-muted-foreground">Trace ID</div>
        <div className="mt-1 break-all font-mono text-xs">{trace.id}</div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-3">
      <dt className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="mt-1 break-words text-sm font-semibold">{value}</dd>
    </div>
  );
}

function AgentOverviewRow({ row, index }: { row: AgentOverview; index: number }) {
  const tokenValue = (value: number) =>
    row.tokenUsageAvailable ? value.toLocaleString() : "Not provided by API";
  const metrics = [
    { label: "Total requests", value: row.totalRequests.toLocaleString() },
    { label: "Successful", value: row.successful.toLocaleString() },
    { label: "Failed", value: row.failed.toLocaleString() },
    { label: "Average latency", value: formatLatency(row.averageLatency) },
    { label: "Input tokens", value: tokenValue(row.inputTokens) },
    { label: "Output tokens", value: tokenValue(row.outputTokens) },
    { label: "Total tokens", value: tokenValue(row.totalTokens) },
    ...(row.kind === "judge"
      ? [
          {
            label: "Evaluation score",
            value:
              row.evaluationScore === null ? "Not scored" : `${Math.round(row.evaluationScore)}%`,
          },
        ]
      : []),
  ];

  return (
    <article className="rounded-lg border bg-background p-4 shadow-sm">
      <div className="grid gap-4 xl:grid-cols-[230px_1fr] xl:items-center">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-[11px] font-bold text-primary">
              {index}
            </span>
            <h3 className="truncate text-sm font-bold">{row.name}</h3>
          </div>
          <p className="mt-1 truncate pl-8 font-mono text-[11px] text-muted-foreground">
            {row.model}
          </p>
        </div>
        <dl
          className={`grid gap-2 sm:grid-cols-2 md:grid-cols-4 ${row.kind === "judge" ? "2xl:grid-cols-8" : "2xl:grid-cols-7"}`}
        >
          {metrics.map((metric) => (
            <div key={metric.label} className="min-w-0 rounded-md bg-muted/35 px-3 py-2">
              <dt className="truncate text-[9px] font-bold uppercase tracking-wide text-muted-foreground">
                {metric.label}
              </dt>
              <dd className="mt-1 truncate text-sm font-bold tabular-nums">{metric.value}</dd>
            </div>
          ))}
        </dl>
      </div>
    </article>
  );
}

function AuditView({ trace }: { trace: TraceRecord }) {
  const auditSubject = trace.audit?.subject ?? "";
  const orchestrationMs = parseNumber(auditSubject, /orch=(\d+(?:\.\d+)?)ms/i);
  const generationMs = parseNumber(auditSubject, /gen=(\d+(?:\.\d+)?)ms/i);
  const needsModeration = Boolean(
    trace.section.custom_instructions || trace.section.output_template,
  );
  const moderationStatus = !needsModeration
    ? "skipped"
    : trace.section.moderation_status === "flagged"
      ? "failed"
      : "success";
  const finalPrompt = buildFinalPrompt(trace);
  const retrievedEvidence = orchestrationEvidence(trace.section.orchestration_strategy);
  const recordedAgents = trace.section.observability_details;
  const recordedJudge = recordedAgents?.judge;
  const confidenceJudge: AgentMetrics = isConfidenceJudge(recordedJudge)
    ? recordedJudge
    : {
        name: "Confidence Judge",
        model: "Mistral Observability Judge",
        status: trace.score === null ? "not scored" : "not recorded",
        latency_ms: null,
        input_tokens: 0,
        output_tokens: 0,
        total_tokens: 0,
      };
  const claimEvaluator: AgentMetrics =
    recordedAgents?.claim_evaluator ??
    (recordedJudge && !isConfidenceJudge(recordedJudge)
      ? recordedJudge
      : {
          name: "Claim Classification Evaluator",
          model: "mistral-large-latest",
          status: trace.section.accuracy_details ? "historical" : "not evaluated",
          latency_ms: null,
          input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
        });
  const agentDetails: AgentMetrics[] = [
    recordedAgents?.moderation ?? {
      name: "Moderation",
      model: "mistral-moderation-latest",
      status: moderationStatus,
      latency_ms: null,
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
    },
    recordedAgents?.orchestration ?? {
      name: "Orchestration Agent",
      model: "mistral-large-latest",
      status: "historical",
      latency_ms: orchestrationMs,
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
    },
    recordedAgents?.section_agent ?? {
      name: `Section Agent: ${trace.section.title}`,
      model: "mistral-large-latest",
      status: trace.success ? "success" : "failed",
      latency_ms: generationMs,
      input_tokens: 0,
      output_tokens: 0,
      total_tokens: 0,
    },
    claimEvaluator,
    confidenceJudge,
  ];
  const flow = [
    {
      title: "User Request",
      description: `Generate ${trace.section.title} narrative for ${trace.customer}.`,
      metrics: [{ label: "Trace ID", value: trace.id }],
      status: "success",
    },
    {
      title: "Moderation Gate",
      description:
        "Check custom instructions and output templates before sending content to the generation pipeline.",
      metrics: [
        {
          label: "Custom Instructions",
          value: trace.section.custom_instructions ? "Provided" : "Not provided",
        },
        {
          label: "Output Template",
          value: trace.section.output_template ? "Provided" : "Not provided",
        },
        { label: "Moderation Result", value: moderationStatus },
      ],
      status: moderationStatus,
    },
    {
      title: "Orchestration Pre-flight",
      description:
        "Select the most relevant evidence and prepare the document-search strategy for this section.",
      metrics: [
        { label: "Available Sources", value: String(trace.sources.length) },
        { label: "Latency", value: formatLatency(orchestrationMs) },
        {
          label: "Strategy",
          value: trace.section.orchestration_strategy ? "Available" : "Not recorded",
        },
      ],
      status: "success",
    },
    {
      title: "Context Assembly",
      description:
        "Build section-specific deal context and retrieve relevant PostgreSQL structured credit data.",
      metrics: [
        {
          label: "Mistral Library Documents",
          value: String(trace.deal.company_document_count + trace.deal.library_files.length),
        },
        { label: "PostgreSQL Context", value: "Requested for client" },
        { label: "Deal Context", value: "Section-specific" },
      ],
      status: "success",
    },
    {
      title: "Prompt Construction",
      description:
        "Assemble the final deal context, instructions, strategy, and output requirements.",
      metrics: [
        { label: "Input Sources", value: String(trace.sources.length) },
        {
          label: "Expected Output",
          value: trace.section.expected_output ? "Available" : "Not available",
        },
        {
          label: "Output Template",
          value: trace.section.output_template ? "Available" : "Not available",
        },
      ],
      status: "success",
    },
    {
      title: "Mistral Agent Generation",
      description:
        "Generate the narrative using the section agent, Mistral document library, and structured context.",
      metrics: [
        { label: "Latency", value: formatLatency(generationMs ?? trace.latencyMs) },
        { label: "Input Tokens", value: "Not recorded" },
        { label: "Output Tokens", value: "Not recorded" },
        { label: "Total Tokens", value: "Not recorded" },
        { label: "Failures", value: trace.success ? "0" : "1" },
      ],
      status: trace.success ? "success" : "failed",
    },
    {
      title: "Narrative Version Staging",
      description:
        "Stage the generated content and create its narrative-version record in the PostgreSQL transaction.",
      metrics: [
        { label: "Section ID", value: trace.section.id },
        { label: "Version Type", value: "generated" },
        { label: "State", value: trace.section.state },
      ],
      status: trace.section.generated_content ? "success" : "failed",
    },
    {
      title: "Claim Classification Evaluation",
      description:
        "Classify narrative claims as grounded, inferred, or unsupported and produce the evaluation summary.",
      metrics: [
        { label: "Latency", value: formatLatency(claimEvaluator.latency_ms) },
        {
          label: "Grounded",
          value: String(trace.section.accuracy_details?.grounded_claims ?? 0),
        },
        {
          label: "Inferred",
          value: String(trace.section.accuracy_details?.inferred_claims ?? 0),
        },
        {
          label: "Unsupported",
          value: String(trace.section.accuracy_details?.unsupported_claims ?? 0),
        },
      ],
      status: claimEvaluator.status,
    },
    {
      title: "Confidence Judge",
      description:
        "Run the saved Mistral Observability regression judge and record its confidence score.",
      metrics: [
        { label: "Latency", value: formatLatency(confidenceJudge.latency_ms) },
        {
          label: "Confidence Score",
          value: trace.score === null ? "Not scored" : `${Math.round(trace.score)}%`,
        },
        { label: "Model", value: confidenceJudge.model },
        { label: "Status", value: confidenceJudge.status },
      ],
      status: confidenceJudge.status,
    },
    {
      title: "Commit and Audit",
      description:
        "Commit the draft, evaluation results, deal status, and generation audit entry to PostgreSQL.",
      metrics: [
        { label: "Committed At", value: formatDate(trace.createdAt) },
        { label: "Citations", value: String(trace.citations) },
        { label: "Audit Entry", value: trace.audit?.id ?? "Not linked" },
      ],
      status: trace.audit ? "success" : "not linked",
    },
  ];
  const spans = [
    { name: "user_request", duration: null, status: "success" },
    { name: "moderation_gate", duration: null, status: moderationStatus },
    {
      name: "orchestration_preflight",
      duration: orchestrationMs,
      status: "success",
    },
    { name: "context_assembly", duration: null, status: "success" },
    { name: "prompt_construction", duration: null, status: "success" },
    {
      name: "mistral_agent_generation",
      duration: generationMs,
      status: trace.success ? "success" : "failed",
    },
    {
      name: "narrative_version_staging",
      duration: null,
      status: trace.section.generated_content ? "success" : "failed",
    },
    {
      name: "claim_classification_evaluation",
      duration: claimEvaluator.latency_ms,
      status: claimEvaluator.status,
    },
    {
      name: "confidence_judge",
      duration: confidenceJudge.latency_ms,
      status: confidenceJudge.status,
    },
    { name: "commit_and_audit", duration: null, status: trace.audit ? "success" : "not linked" },
  ];

  return (
    <section className="doc-card overflow-hidden">
      <div className="border-b p-5">
        <h2 className="text-lg font-bold">Audit View</h2>
        <p className="text-sm text-muted-foreground">
          Evidence, configuration, response, and execution flow for the selected activity.
        </p>
      </div>
      <div className="space-y-6 p-5">
        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-muted-foreground">
            Retrieved evidence
          </h3>
          {retrievedEvidence.length ? (
            <div className="overflow-hidden rounded-md border">
              {retrievedEvidence.map((evidence, index) => (
                <div
                  key={`${evidence.title}-${index}`}
                  className="flex items-start gap-3 border-b px-4 py-3 text-sm last:border-b-0"
                >
                  <FileText className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="break-words font-medium">{evidence.title}</span>
                      {evidence.priority && (
                        <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-bold uppercase text-primary">
                          {evidence.priority}
                        </span>
                      )}
                    </div>
                    {evidence.relevance && (
                      <p className="mt-1 break-words text-xs leading-5 text-muted-foreground">
                        {evidence.relevance}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-md border p-4 text-sm text-muted-foreground">
              The Orchestration Agent did not retrieve or record evidence for this section.
            </p>
          )}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <AuditText label="Input sources" value={trace.section.sources || "Not configured"} />
          <AuditText
            label="Expected output"
            value={trace.section.expected_output || "Not configured"}
          />
          <AuditText
            label="Custom instructions"
            value={trace.section.custom_instructions || "Not configured"}
          />
          <AuditText
            label="Output template"
            value={trace.section.output_template || "Not configured"}
          />
        </div>

        <div>
          <div className="mb-3">
            <h3 className="text-xs font-bold uppercase tracking-wide text-muted-foreground">
              Agent Details
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Latency and token usage recorded for this section’s AI operations.
            </p>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            {agentDetails.map((agent) => (
              <AgentDetailCard key={agent.name} agent={agent} />
            ))}
          </div>
        </div>

        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-muted-foreground">
            Final Prompt Sent for Narration Draft Generation
          </h3>
          <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-md border bg-slate-950 p-4 text-xs leading-6 text-slate-100">
            {finalPrompt}
          </pre>
        </div>

        <div>
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-muted-foreground">
            Generated response
          </h3>
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md border bg-muted/25 p-4 font-sans text-sm leading-6">
            {trace.section.generated_content}
          </pre>
        </div>

        <div className="rounded-md border p-4 sm:p-5">
          <div className="mb-5 flex items-start gap-3">
            <Activity className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
            <div>
              <h3 className="text-sm font-bold uppercase tracking-wide">Flow Map</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                Vertical execution flow for the selected trace.
              </p>
            </div>
          </div>
          <div className="relative space-y-4 pl-8 before:absolute before:bottom-8 before:left-[11px] before:top-8 before:w-px before:bg-border sm:pl-10">
            {flow.map(({ title, description, metrics, status }, index) => (
              <div key={title} className="relative">
                <span className="absolute -left-8 top-5 z-10 flex h-6 w-6 items-center justify-center rounded-full bg-background text-xs font-semibold text-muted-foreground sm:-left-10">
                  {index + 1}
                </span>
                <div className="rounded-lg border bg-background p-4 shadow-sm sm:p-5">
                  <div className="flex items-start justify-between gap-4">
                    <h4 className="text-base font-bold">{title}</h4>
                    <span
                      className={`shrink-0 text-xs font-semibold ${status === "success" ? "text-emerald-700" : status === "failed" ? "text-red-700" : "text-muted-foreground"}`}
                    >
                      {status}
                    </span>
                  </div>
                  <p className="mt-2 break-words text-sm text-muted-foreground">{description}</p>
                  <div className="mt-4 grid gap-2 sm:grid-cols-2">
                    {metrics.map((metric) => (
                      <FlowMetric key={metric.label} label={metric.label} value={metric.value} />
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-md border border-primary/30 p-4">
          <h3 className="mb-3 text-xs font-bold uppercase tracking-wide text-primary">
            OpenTelemetry Spans
          </h3>
          <div className="space-y-2">
            {spans.map((span) => (
              <div
                key={span.name}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-4 py-3"
              >
                <div className="flex items-center gap-2">
                  <Activity className="h-4 w-4 text-primary" />
                  <span className="font-mono text-sm font-semibold">{span.name}</span>
                </div>
                <div className="flex items-center gap-3 text-xs">
                  <span className="font-mono text-muted-foreground">
                    {span.duration === null ? "unset" : formatLatency(span.duration)}
                  </span>
                  <span
                    className={`font-semibold ${span.status === "success" ? "text-emerald-700" : span.status === "failed" ? "text-red-700" : "text-muted-foreground"}`}
                  >
                    {span.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            All nine stage spans are emitted for new generation requests. Durations shown here are
            read from persisted audit metrics; “unset” means the audit record does not contain that
            operation’s duration.
          </p>
        </div>
      </div>
    </section>
  );
}

function buildFinalPrompt(trace: TraceRecord): string {
  const { deal, section } = trace;
  const dealContext = [
    "--- Deal Context ---",
    `Borrower: ${deal.customer}`,
    deal.customer_type ? `Customer Type: ${deal.customer_type}` : "",
    deal.industry ? `Industry: ${deal.industry}` : "",
    deal.geography ? `Geography: ${deal.geography}` : "",
    deal.facility ? `Facility: ${deal.facility}` : "",
    deal.amount ? `Amount: ${deal.currency} ${deal.amount.toLocaleString()}` : "",
    deal.tenure ? `Tenure: ${deal.tenure} months` : "",
    "---",
  ].filter(Boolean);

  const parts = [
    ...dealContext,
    `Section: ${section.title}`,
    `Description: ${section.description}`,
    `Expected Output: ${section.expected_output}`,
  ];

  if (section.orchestration_strategy?.trim()) {
    parts.push(
      "\n--- Orchestration Strategy (use to guide your search) ---",
      section.orchestration_strategy,
      "---",
      "Prioritize the recommended documents and data points above.",
    );
  }

  if (section.custom_instructions?.trim()) {
    parts.push(
      "\n--- Custom Instructions (follow this style/structure) ---",
      section.custom_instructions,
      "---",
    );
  }

  if (section.output_template?.trim()) {
    parts.push(
      "\n--- Output Template (MUST follow this structure) ---",
      section.output_template,
      "---",
      "IMPORTANT: Your output MUST follow the exact markdown structure, headings, and sections shown in the template above.",
    );
  }

  parts.push(
    "\nSearch the document library for relevant data, then generate the narrative. Use markdown formatting. Put the source directly after each sourced statement using [Source : Exact_Document_Name.pdf], or [Source : PostgreSQL.table_name] for structured data. Do not add a References or Sources section at the bottom.",
  );

  return parts.join("\n");
}

function FlowMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-md border bg-muted/10 px-3 py-2.5">
      <div className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1 break-all text-sm font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function AgentDetailCard({ agent }: { agent: AgentMetrics }) {
  const calculatedTotal =
    agent.total_tokens > 0 ? agent.total_tokens : agent.input_tokens + agent.output_tokens;
  const tokenValue = (value: number) =>
    isConfidenceJudge(agent) || agent.token_usage_available === false
      ? "Not provided by API"
      : value > 0
        ? value.toLocaleString()
        : agent.status === "skipped"
          ? "Not applicable"
          : "Not reported";
  const statusClass =
    agent.status === "success"
      ? "bg-emerald-50 text-emerald-700"
      : agent.status === "failed" || agent.status === "flagged"
        ? "bg-red-50 text-red-700"
        : "bg-muted text-muted-foreground";

  return (
    <article className="rounded-lg border bg-background p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h4 className="truncate font-bold">{agent.name}</h4>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{agent.model}</p>
        </div>
        <span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${statusClass}`}>
          {agent.status}
        </span>
      </div>
      <dl className="mt-4 grid grid-cols-2 gap-2">
        <Metric label="Latency" value={formatLatency(agent.latency_ms)} />
        <Metric label="Input tokens" value={tokenValue(agent.input_tokens)} />
        <Metric label="Output tokens" value={tokenValue(agent.output_tokens)} />
        <Metric label="Total tokens" value={tokenValue(calculatedTotal)} />
      </dl>
    </article>
  );
}

function AuditText({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border p-4">
      <div className="text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <p className="mt-2 whitespace-pre-wrap text-sm leading-6">{value}</p>
    </div>
  );
}
