import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  CheckCircle2,
  Database,
  Factory,
  FileText,
  Loader2,
  Server,
  TriangleAlert,
} from "lucide-react";

import { api, type ManufactureJob } from "@/lib/deals";

export const Route = createFileRoute("/manufacture-data")({
  head: () => ({
    meta: [
      { title: "Manufacture Local MCP Data" },
      {
        name: "description",
        content: "Generate synthetic PDFs and PostgreSQL credit data.",
      },
    ],
  }),
  component: ManufactureData,
});

function ManufactureData() {
  const [companyName, setCompanyName] = useState("");
  const [industry, setIndustry] = useState("");
  const [geography, setGeography] = useState("");
  const [job, setJob] = useState<ManufactureJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  const busy = job?.status === "queued" || job?.status === "running";
  const activeJobId = job?.job_id;

  useEffect(() => {
    if (!activeJobId || !busy) return;
    const timer = window.setInterval(async () => {
      try {
        const latest = await api.manufacture.status(activeJobId);
        setJob(latest);
        if (latest.status === "failed") {
          setError(latest.error || "Data manufacturing failed.");
        }
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Unable to read manufacturing progress.",
        );
      }
    }, 1500);
    return () => window.clearInterval(timer);
  }, [activeJobId, busy]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setJob(null);
    try {
      const created = await api.manufacture.start({
        company_name: companyName.trim(),
        industry: industry.trim(),
        geography: geography.trim(),
      });
      setJob(created);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Unable to start data manufacturing.",
      );
    }
  }

  const result = job?.result;

  return (
    <main className="mx-auto max-w-5xl px-3 py-6 sm:px-6 sm:py-9">
      <div className="mb-6 flex items-start gap-3">
        <div className="rounded-lg bg-primary/10 p-2 text-primary">
          <Factory className="h-6 w-6" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Manufacture Local MCP Data</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Generate 17 synthetic PDFs, upload them to Mistral Library, and populate 16 PostgreSQL
            credit tables. No Railway or Azure is used.
          </p>
        </div>
      </div>

      <form onSubmit={submit} className="doc-card p-5">
        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-1.5 text-sm font-medium">
            Company name
            <input
              required
              minLength={2}
              value={companyName}
              onChange={(event) => setCompanyName(event.target.value)}
              placeholder="Aster Auto Components Limited"
              className="h-10 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Industry
            <input
              required
              minLength={2}
              value={industry}
              onChange={(event) => setIndustry(event.target.value)}
              placeholder="Auto components manufacturing"
              className="h-10 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="space-y-1.5 text-sm font-medium">
            Geography
            <input
              required
              minLength={2}
              value={geography}
              onChange={(event) => setGeography(event.target.value)}
              placeholder="Pune, India"
              className="h-10 w-full rounded-md border border-input bg-background px-3 font-normal outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Factory className="h-4 w-4" />}
            {busy ? "Manufacturing..." : "Manufacture Data"}
          </button>
          <span className="text-xs text-muted-foreground">
            All output is marked synthetic and intended for testing only.
          </span>
        </div>
      </form>

      {job && (
        <section className="doc-card mt-5 p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-sm font-semibold">{job.stage}</p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">Job {job.job_id}</p>
            </div>
            <span className="text-sm font-semibold tabular-nums">{job.percent}%</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-all"
              style={{ width: `${job.percent}%` }}
            />
          </div>
          <div className="mt-5 grid gap-4 md:grid-cols-3">
            <ProgressList
              icon={<FileText className="h-4 w-4" />}
              label="PDFs generated"
              items={job.generated_pdfs}
              total={job.pdf_total}
            />
            <ProgressList
              icon={<Server className="h-4 w-4" />}
              label="PDFs uploaded"
              items={job.uploaded_pdfs}
              total={job.pdf_total}
            />
            <ProgressList
              icon={<Database className="h-4 w-4" />}
              label="Tables completed"
              items={job.completed_tables}
              total={job.table_total}
              formatItem={(item) => item.replace(/^credit_dossier\./, "")}
            />
          </div>
        </section>
      )}

      {error && (
        <div className="mt-5 flex gap-3 rounded-md border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
          <TriangleAlert className="h-5 w-5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {result && (
        <section className="mt-5 space-y-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-primary">
            <CheckCircle2 className="h-5 w-5" />
            Manufacturing completed for {result.companyName}
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <ResultCard
              icon={<FileText className="h-5 w-5" />}
              label="PDF documents"
              value={`${result.pdfCount}`}
              detail={
                result.aiDetailedGeneration
                  ? `${result.uploadedPdfCount} uploaded - Mistral detailed`
                  : `${result.uploadedPdfCount} uploaded - detailed fallback`
              }
            />
            <ResultCard
              icon={<Database className="h-5 w-5" />}
              label="PostgreSQL tables"
              value={`${result.tableCount}`}
              detail={`${result.seededRowCount} rows upserted`}
            />
            <ResultCard
              icon={<Server className="h-5 w-5" />}
              label="Local MCP"
              value="Ready"
              detail={result.mcpUrl}
            />
          </div>
          <div className="doc-card p-4 text-sm">
            <div className="grid gap-2 sm:grid-cols-[180px_1fr]">
              <span className="text-muted-foreground">PostgreSQL database</span>
              <code>{result.databaseName}</code>
              <span className="text-muted-foreground">Mistral Library ID</span>
              <code>{result.mistralLibraryId || "Not uploaded"}</code>
              <span className="text-muted-foreground">Generator</span>
              <code>
                Version {result.generatorVersion} -
                {result.aiDetailedGeneration ? "Mistral AI" : "local fallback"}
              </code>
            </div>
          </div>
          {result.uploadError && (
            <div className="rounded-md border border-warning/40 bg-warning/10 p-4 text-sm">
              PDFs and tables were generated, but Mistral upload did not complete:{" "}
              {result.uploadError}
            </div>
          )}
        </section>
      )}
    </main>
  );
}

function ProgressList({
  icon,
  label,
  items,
  total,
  formatItem = (item) => item,
}: {
  icon: React.ReactNode;
  label: string;
  items: string[];
  total: number;
  formatItem?: (item: string) => string;
}) {
  return (
    <div className="min-w-0 border-t pt-3 md:border-l md:border-t-0 md:pl-4 md:pt-0">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <span className="text-primary">{icon}</span>
          {label}
        </div>
        <span className="text-sm font-bold tabular-nums">
          {items.length}/{total}
        </span>
      </div>
      <div className="mt-2 max-h-44 space-y-1 overflow-y-auto pr-1">
        {items.length === 0 ? (
          <p className="text-xs text-muted-foreground">Waiting</p>
        ) : (
          items.map((item) => (
            <div key={item} className="flex min-w-0 items-center gap-1.5 text-xs">
              <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-primary" />
              <span className="truncate" title={formatItem(item)}>
                {formatItem(item)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function ResultCard({
  icon,
  label,
  value,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="doc-card p-4">
      <div className="flex items-center justify-between text-primary">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        {icon}
      </div>
      <div className="mt-2 text-2xl font-bold">{value}</div>
      <div className="mt-1 break-all text-xs text-muted-foreground">{detail}</div>
    </div>
  );
}
