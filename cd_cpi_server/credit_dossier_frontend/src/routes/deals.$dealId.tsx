import { SharedDealCard } from "../../../credit_dossier_backend/shared/new-deal/NewDealForm";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState, useCallback } from "react";
import {
  ArrowLeft,
  FileText,
  Clock,
  Download,
  Sparkles,
  RefreshCw,
  Plus,
  TriangleAlert,
  Loader2,
  CheckCircle2,
  Upload,
  X,
  FileDown,
  BookOpenCheck,
  Trash2,
  FileType,
  Save,
  File as FileIcon,
  Link as LinkIcon,
  Type,
  Eye,
  EyeOff,
  BarChart3,
  Table as TableIcon,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Info,
  Library,
  History,
} from "lucide-react";
import {
  api,
  formatAmount,
  type Deal,
  type DealDocument,
  type DraftAllJob,
  type NarrativeVersion,
  type Section,
} from "@/lib/deals";
import { diffWords } from "diff";
import { useAuth } from "@/lib/auth";
import { apiErrorFromResponse } from "@/lib/api-error";
import { textInputError, sourceUrlError } from "@/lib/input-validation";

function validateTextInput(label: string, value: string, maxLength: number): boolean {
  const error = textInputError(label, value, maxLength);
  if (error) alert(error);
  return !error;
}

export const Route = createFileRoute("/deals/$dealId")({
  head: () => ({ meta: [{ title: "Deal — Credit Pitch Book" }] }),
  component: DealDetail,
});

type Tab = "overview" | "documents" | "narratives" | "versions" | "export";

function DealDetail() {
  const { dealId } = Route.useParams();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>("overview");
  const [deal, setDeal] = useState<Deal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const fetchDeal = useCallback(
    (isRefresh = false) => {
      if (!isRefresh) setLoading(true);
      api.deals
        .get(dealId)
        .then(setDeal)
        // Do not expose backend error details; show a generic user-facing message.
        .catch(() => setError("Unable to load this deal. Please try again."))
        .finally(() => setLoading(false));
    },
    [dealId],
  );

  useEffect(() => {
    fetchDeal(false);
  }, [fetchDeal]);

  if (loading) {
    return (
      <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
        <div className="flex items-center justify-center gap-2 py-20 text-muted-foreground">
          <Loader2 className="h-5 w-5 animate-spin" /> Loading deal…
        </div>
      </main>
    );
  }

  if (error || !deal) {
    return (
      <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
        <p className="text-sm">
          {error || "Deal not found."}{" "}
          <Link to="/" className="text-primary underline">
            Back to dashboard
          </Link>
        </p>
      </main>
    );
  }

  const tabs: { id: Tab; label: string; Icon: typeof FileText }[] = [
    { id: "overview", label: "Overview", Icon: FileText },
    { id: "documents", label: "Documents", Icon: Library },
    { id: "narratives", label: "Narratives", Icon: Sparkles },
    { id: "versions", label: "Versions", Icon: Clock },
    { id: "export", label: "Export", Icon: Download },
  ];

  return (
    <main className="mx-auto max-w-[1400px] px-3 py-5 sm:px-6 sm:py-8">
      <div className="mb-4">
        <Link
          to="/"
          className="inline-flex h-8 items-center gap-2 rounded-md px-3 text-xs font-medium hover:bg-accent hover:text-accent-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Dashboard
        </Link>
      </div>

      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded-full border border-primary/25 bg-primary/10 px-2 py-0.5 text-[11px] font-medium text-primary">
              {deal.customer_type === "Existing" ? "Existing customer" : "New-to-bank"}
            </span>
            <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              {deal.facility}
            </span>
            <span className="rounded-full border border-border bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              Due {deal.due}
            </span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{deal.customer}</h1>
          <p className="text-sm text-muted-foreground">
            {deal.sector} · {deal.city}
          </p>
        </div>
        <div className="text-right">
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Facility
          </div>
          <div className="font-mono text-xl font-bold">
            {formatAmount(deal.amount, deal.currency)}
          </div>
          <div className="text-xs text-muted-foreground">
            {deal.tenure}M · {deal.pricing}
          </div>
          <button
            onClick={() => setShowDeleteModal(true)}
            className="mt-2 inline-flex h-7 items-center gap-1.5 rounded-md border border-destructive/30 bg-destructive/10 px-2.5 text-[11px] font-medium text-destructive hover:bg-destructive/20 transition-colors"
          >
            <Trash2 className="h-3 w-3" />
            Delete Deal
          </button>
        </div>
      </div>

      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-lg bg-background p-6 shadow-lg border">
            <div className="flex items-center gap-3 text-destructive mb-4">
              <AlertTriangle className="h-6 w-6" />
              <h2 className="text-lg font-semibold">Delete Deal</h2>
            </div>
            <p className="text-sm text-muted-foreground mb-6">
              Are you sure you want to delete the deal for <strong>{deal.customer}</strong>? This
              action cannot be undone and will also delete the associated document library.
            </p>
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setShowDeleteModal(false)}
                disabled={deleting}
                className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-muted transition-colors disabled:opacity-60"
              >
                Cancel
              </button>
              <button
                onClick={async () => {
                  setDeleting(true);
                  try {
                    await api.deals.delete(deal.id);
                    navigate({ to: "/" });
                  } catch (err) {
                    console.error("Delete failed:", err);
                    alert("Failed to delete deal.");
                  } finally {
                    setDeleting(false);
                  }
                }}
                disabled={deleting}
                className="inline-flex items-center gap-2 rounded-md bg-destructive px-4 py-2 text-sm font-medium text-destructive-foreground hover:bg-destructive/90 transition-colors disabled:opacity-60"
              >
                {deleting && <Loader2 className="h-4 w-4 animate-spin" />}
                {deleting ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="mb-6 flex flex-wrap gap-1 border-b">
        {tabs.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium transition-colors ${
              tab === id
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground"
            }`}
          >
            <Icon className="h-4 w-4" /> {label}
          </button>
        ))}
      </div>

      {tab === "overview" && <><SharedDealCard deal={deal} /><OverviewTab deal={deal} refresh={() => fetchDeal(true)} /></>}
      {tab === "documents" && <DocumentsTab deal={deal} refresh={() => fetchDeal(true)} />}
      {tab === "narratives" && <NarrativesTab deal={deal} refresh={() => fetchDeal(true)} />}
      {tab === "versions" && <VersionsTab deal={deal} refresh={() => fetchDeal(true)} />}
      {tab === "export" && <ExportTab deal={deal} refresh={() => fetchDeal(true)} />}
    </main>
  );
}

/* ── Overview Tab ───────────────────────────────────────────── */

function OverviewTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const ready = deal.sections.filter((s) => !s.optional && s.state === "ready").length;
  const total = deal.sections.filter((s) => !s.optional).length;

  return (
    <div className="space-y-4">
      <div className="doc-card">
        <div className="doc-section-header">
          <span>Client &amp; Facility Snapshot</span>
        </div>
        <div className="grid gap-4 p-5 sm:grid-cols-3">
          {(
            [
              ["Segment", deal.segment],
              ["Industry", deal.industry],
              ["Geography", deal.geography],
              ["KYC", deal.kyc],
              ["Facility", deal.facility],
              ["Amount", `${deal.currency} ${deal.amount.toLocaleString()}`],
              ["Tenure", `${deal.tenure} months`],
              ["Pricing", deal.pricing],
              ["Collateral", deal.collateral ? "Secured" : "Clean"],
            ] as const
          ).map(([k, v]) => (
            <div key={k}>
              <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                {k}
              </div>
              <div className="text-sm font-medium">{v}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="doc-card">
        <div className="doc-section-header">
          <Clock className="h-4 w-4 shrink-0" />
          <span>Recent Activity</span>
        </div>
        <ul className="divide-y">
          {deal.audit_entries
            .slice()
            .reverse()
            .map((a) => (
              <li key={a.id} className="flex items-start justify-between gap-4 p-4">
                <div>
                  <div className="font-semibold">{a.action}</div>
                  <div className="text-xs text-muted-foreground">{a.subject}</div>
                </div>
                <div className="text-right text-xs text-muted-foreground">
                  <div className="font-medium text-foreground">{a.user}</div>
                  <div>{new Date(a.created_at).toLocaleString()}</div>
                </div>
              </li>
            ))}
        </ul>
      </div>

      <div className="doc-card">
        <div className="doc-section-header">
          <FileText className="h-4 w-4 shrink-0" />
          <span>Readiness</span>
        </div>
        <div className="space-y-3 p-5">
          <div>
            <div className="mb-1 flex items-center justify-between text-sm">
              <span>Mandatory sections ready</span>
              <span className="font-mono text-muted-foreground">
                {ready}/{total}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${total > 0 ? (ready / total) * 100 : 0}%` }}
              />
            </div>
          </div>
          {(
            [
              ["Library documents", deal.library_files?.length || 0, "bg-info/15 text-info"],
              ["Versions", deal.versions.length, "bg-muted text-muted-foreground"],
            ] as const
          ).map(([label, v, cls]) => (
            <div
              key={String(label)}
              className="flex items-center justify-between border-t pt-3 text-sm"
            >
              <span>{label}</span>
              <span
                className={`min-w-7 rounded-full px-2 py-0.5 text-center text-xs font-semibold ${cls as string}`}
              >
                {v as number}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Narratives Tab ─────────────────────────────────────────── */

function NarrativesTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const [activeId, setActiveId] = useState(deal.sections[0]?.id || "");
  const active = deal.sections.find((s) => s.id === activeId);
  const [expected, setExpected] = useState(active?.expected_output || "");
  const [dataSources, setDataSources] = useState(active?.sources || "");
  const [savingSectionDetails, setSavingSectionDetails] = useState(false);
  const [customInstructions, setCustomInstructions] = useState(active?.custom_instructions || "");
  const [outputTemplate, setOutputTemplate] = useState(active?.output_template || "");
  const [generating, setGenerating] = useState(false);
  const [draftingAll, setDraftingAll] = useState(false);
  const [draftAllJob, setDraftAllJob] = useState<DraftAllJob | null>(null);
  const [savingTemplate, setSavingTemplate] = useState(false);
  const [uploadingTemplate, setUploadingTemplate] = useState(false);
  const [savingInstructions, setSavingInstructions] = useState(false);
  const [sourceUrls, setSourceUrls] = useState<string[]>(
    active?.source_urls?.length ? active.source_urls : [""],
  );
  const [savingUrls, setSavingUrls] = useState(false);
  const [urlMessage, setUrlMessage] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);
  const [showTemplatePreview, setShowTemplatePreview] = useState(false);
  const [editingContent, setEditingContent] = useState(false);
  const [editedContent, setEditedContent] = useState("");
  const [savingContent, setSavingContent] = useState(false);
  const [acquiringEditLock, setAcquiringEditLock] = useState(false);
  const [selectedSectionIds, setSelectedSectionIds] = useState<Set<string>>(new Set());
  const [draftingSelected, setDraftingSelected] = useState(false);
  const [showEdits, setShowEdits] = useState(false);
  const [showCitations, setShowCitations] = useState(true);
  const [showVersionHistory, setShowVersionHistory] = useState(false);
  const [narrativeVersions, setNarrativeVersions] = useState<NarrativeVersion[]>([]);
  const [loadingVersions, setLoadingVersions] = useState(false);
  const [markingFinalVersionId, setMarkingFinalVersionId] = useState<string | null>(null);
  const [deletingNarrativeVersionId, setDeletingNarrativeVersionId] = useState<string | null>(null);
  const [expandedVersionIds, setExpandedVersionIds] = useState<Set<string>>(new Set());
  const [retryingLibrarySync, setRetryingLibrarySync] = useState(false);

  // Moderation state
  const [moderationError, setModerationError] = useState<string | null>(null);
  const [showMoreModeration, setShowMoreModeration] = useState(false);

  useEffect(() => {
    if (active) {
      setExpected(active.expected_output);
      setDataSources(active.sources);
      setCustomInstructions(active.custom_instructions || "");
      setOutputTemplate(active.output_template || "");
      setSourceUrls(active.source_urls?.length ? active.source_urls : [""]);
      setUrlMessage(null);
      setUrlError(null);
      setShowTemplatePreview(false);
      setEditingContent(false);
      setModerationError(null);
      setShowMoreModeration(false);
    }
  }, [activeId, active]);

  useEffect(() => {
    return () => {
      if (activeId) void api.sections.releaseEditLock(deal.id, activeId).catch(() => undefined);
    };
  }, [deal.id, activeId]);

  useEffect(() => {
    if (!editingContent || !activeId) return;
    const timer = window.setInterval(() => {
      void api.sections.acquireEditLock(deal.id, activeId).catch(() => {
        setEditingContent(false);
        window.alert("Your narrative edit lock expired or was lost. Reopen the editor to continue.");
      });
    }, 60_000);
    return () => window.clearInterval(timer);
  }, [deal.id, activeId, editingContent]);

  const handleStartEditing = async () => {
    if (!active || acquiringEditLock) return;
    setAcquiringEditLock(true);
    try {
      await api.sections.acquireEditLock(deal.id, active.id);
      setEditedContent(active.generated_content || "");
      setEditingContent(true);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "This narrative is locked by another user.");
    } finally {
      setAcquiringEditLock(false);
    }
  };

  const handleCancelEditing = async () => {
    if (!active) return;
    setEditingContent(false);
    await api.sections.releaseEditLock(deal.id, active.id).catch(() => undefined);
  };

  const handleSaveSectionDetails = async () => {
    if (!active || savingSectionDetails) return;
    if (!validateTextInput("Data sources", dataSources, 20_000) ||
        !validateTextInput("Expected output", expected, 20_000)) return;
    setSavingSectionDetails(true);
    try {
      await api.sections.update(deal.id, active.id, {
        sources: dataSources,
        expected_output: expected,
      });
      refresh();
    } catch (err) {
      console.error("Saving section details failed:", err);
    } finally {
      setSavingSectionDetails(false);
    }
  };

  useEffect(() => {
    setShowVersionHistory(false);
    setNarrativeVersions([]);
    setExpandedVersionIds(new Set());
  }, [activeId]);

  useEffect(() => {
    if (!draftAllJob || !["queued", "running"].includes(draftAllJob.status)) {
      return;
    }
    const poll = async () => {
      try {
        const latest = await api.sections.generateAllStatus(deal.id, draftAllJob.job_id);
        setDraftAllJob(latest);
        if (["completed", "failed"].includes(latest.status)) {
          setDraftingAll(false);
          refresh();
        }
      } catch (err) {
        console.error("Reading Draft All progress failed:", err);
      }
    };
    const timer = window.setInterval(poll, 1000);
    void poll();
    return () => window.clearInterval(timer);
  }, [deal.id, draftAllJob?.job_id, draftAllJob?.status]);

  const loadNarrativeVersions = async () => {
    if (!active) return;
    setLoadingVersions(true);
    try {
      setNarrativeVersions(await api.sections.versions(deal.id, active.id));
    } catch (err) {
      console.error("Loading narrative versions failed:", err);
    } finally {
      setLoadingVersions(false);
    }
  };

  const handleToggleVersionHistory = async () => {
    const nextOpen = !showVersionHistory;
    setShowVersionHistory(nextOpen);
    if (nextOpen) {
      await loadNarrativeVersions();
    }
  };

  const handleMarkNarrativeVersionFinal = async (versionId: string) => {
    if (!active || markingFinalVersionId) return;
    setMarkingFinalVersionId(versionId);
    try {
      await api.sections.markVersionFinal(deal.id, active.id, versionId);
      await loadNarrativeVersions();
      refresh();
      setEditingContent(false);
      setShowEdits(false);
    } catch (err) {
      console.error("Marking narrative version final failed:", err);
    } finally {
      setMarkingFinalVersionId(null);
    }
  };

  const handleDeleteNarrativeVersion = async (version: NarrativeVersion) => {
    if (!active || deletingNarrativeVersionId) return;
    const confirmed = window.confirm(
      version.is_final
        ? "Delete this final version? The newest remaining version will become the default final."
        : "Delete this narrative version? This cannot be undone.",
    );
    if (!confirmed) return;
    setDeletingNarrativeVersionId(version.id);
    try {
      await api.sections.deleteVersion(deal.id, active.id, version.id);
      await loadNarrativeVersions();
      refresh();
      setEditingContent(false);
      setShowEdits(false);
    } catch (err) {
      console.error("Deleting narrative version failed:", err);
    } finally {
      setDeletingNarrativeVersionId(null);
    }
  };

  const handleGenerate = async () => {
    if (!active || generating) return;
    if (!validateTextInput("Custom instructions", customInstructions, 50_000)) return;
    setModerationError(null);
    setGenerating(true);
    try {
      await api.sections.generate(deal.id, active.id, customInstructions || undefined);
      refresh();
      if (showVersionHistory) await loadNarrativeVersions();
    } catch (err: any) {
      const msg = err?.message || "";
      if (msg.includes("moderation") || msg.includes("flagged") || msg.includes("Flagged")) {
        setModerationError(
          msg
            .replace(/^API \d+:\s*/, "")
            .replace(/^"|"$/g, "")
            .replace(/^\{"detail":"/, "")
            .replace(/"\}$/, ""),
        );
      } else {
        setModerationError(null);
      }
      console.error("Generation failed:", err);
      refresh();
    } finally {
      setGenerating(false);
    }
  };

  const handleDraftAll = async () => {
    if (draftingAll || draftingSelected) return;
    setDraftingAll(true);
    setDraftAllJob(null);
    try {
      const job = await api.sections.startGenerateAll(deal.id);
      setDraftAllJob(job);
    } catch (err) {
      console.error("Draft all failed:", err);
      setDraftingAll(false);
    }
  };

  const handleDraftSelected = async () => {
    if (draftingAll || draftingSelected || selectedSectionIds.size === 0) return;
    setDraftingSelected(true);
    try {
      const promises = Array.from(selectedSectionIds).map((sectionId) =>
        api.sections.generate(deal.id, sectionId),
      );
      await Promise.allSettled(promises);
      refresh();
    } catch (err) {
      console.error("Draft selected failed:", err);
    } finally {
      setDraftingSelected(false);
    }
  };

  // ── Template handlers ──
  const handleSaveTemplate = async () => {
    if (!active || savingTemplate) return;
    if (!validateTextInput("Output template", outputTemplate, 100_000)) return;
    setSavingTemplate(true);
    try {
      await api.sections.update(deal.id, active.id, { output_template: outputTemplate || null });
      setModerationError(null);
      refresh();
    } catch (err) {
      console.error("Save template failed:", err);
    } finally {
      setSavingTemplate(false);
    }
  };

  const handleUploadTemplate = async () => {
    if (!active || uploadingTemplate) return;
    const fileInput = document.getElementById("template-file-input") as HTMLInputElement;
    if (!fileInput?.files?.[0]) return;
    setUploadingTemplate(true);
    try {
      const formData = new FormData();
      formData.append("file", fileInput.files[0]);
      await api.sections.uploadTemplate(deal.id, active.id, formData);
      fileInput.value = "";
      refresh();
    } catch (err) {
      console.error("Template upload failed:", err);
    } finally {
      setUploadingTemplate(false);
    }
  };

  const handleDeleteTemplate = async () => {
    if (!active) return;
    try {
      await api.sections.deleteTemplate(deal.id, active.id);
      setOutputTemplate("");
      setModerationError(null);
      refresh();
    } catch (err) {
      console.error("Delete template failed:", err);
    }
  };

  // ── Custom Instructions handler ──
  const handleSaveInstructions = async () => {
    if (!active || savingInstructions) return;
    if (!validateTextInput("Custom instructions", customInstructions, 50_000)) return;
    setSavingInstructions(true);
    try {
      await api.sections.update(deal.id, active.id, {
        custom_instructions: customInstructions || null,
      });
      setModerationError(null);
      refresh();
    } catch (err) {
      console.error("Save instructions failed:", err);
    } finally {
      setSavingInstructions(false);
    }
  };

  const handleSaveUrls = async () => {
    if (!active || savingUrls) return;
    setUrlMessage(null);
    setUrlError(null);
    const normalized = Array.from(new Set(sourceUrls.map((url) => url.trim()).filter(Boolean)));
    try {
      if (normalized.length > 10) throw new Error("A section can contain at most 10 URLs.");
      for (const url of normalized) {
        const error = sourceUrlError(url);
        if (error) throw new Error(error);
      }
    } catch (error) {
      setUrlError(error instanceof Error ? error.message : "Enter valid HTTP/HTTPS URLs.");
      return;
    }
    setSavingUrls(true);
    try {
      await api.sections.update(deal.id, active.id, { source_urls: normalized });
      setSourceUrls(normalized.length ? normalized : [""]);
      setUrlMessage(normalized.length ? "URLs saved successfully." : "Saved URLs were cleared.");
      refresh();
    } catch (error) {
      setUrlError(error instanceof Error ? error.message : "Saving URLs failed.");
    } finally {
      setSavingUrls(false);
    }
  };

  const handleSaveContent = async () => {
    if (!active || savingContent) return;
    if (!validateTextInput("Narrative content", editedContent, 500_000)) return;
    setSavingContent(true);
    try {
      await api.sections.update(deal.id, active.id, { generated_content: editedContent });
      refresh();
      if (showVersionHistory) await loadNarrativeVersions();
      setEditingContent(false);
      setShowEdits(true);
      await api.sections.releaseEditLock(deal.id, active.id);
    } catch (err) {
      console.error("Save content failed:", err);
    } finally {
      setSavingContent(false);
    }
  };

  if (!active) return null;

  const readySections = deal.sections.filter((s) => s.state === "ready").length;
  const totalSections = deal.sections.length;
  const wordCount = active.generated_content ? active.generated_content.split(/\s+/).length : 0;
  const isFewShot = !!active.custom_instructions;
  const hasTemplate = !!active.output_template;
  const libDocCount = deal.library_files?.length || 0;
  const isFlagged = active.moderation_status === "flagged";
  const isModerationSafe = active.moderation_status === "safe";
  const flaggedCategories = active.moderation_details?.flagged_categories || [];
  const isRefreshingLibrary = deal.library_sync_status === "syncing";
  const isSyncing = isRefreshingLibrary && !deal.company_mistral_library_id;
  const librarySyncFailed = deal.library_sync_status === "error";
  const withoutCitations = (content: string) =>
    content.replace(/\s*\[Sources?\s*:\s*[^\]]+\]/gi, "");
  const visibleNarrativeContent = active.generated_content
    ? showCitations
      ? active.generated_content
      : withoutCitations(active.generated_content)
    : "";

  const retryLibrarySync = async () => {
    if (retryingLibrarySync) return;
    setRetryingLibrarySync(true);
    try {
      await api.library.triggerSync(deal.id);
      refresh();
    } catch (err) {
      console.error("Retrying library refresh failed:", err);
    } finally {
      setRetryingLibrarySync(false);
    }
  };
  const liveDraftSections =
    draftAllJob?.sections.filter((section) => section.status === "running") || [];
  const draftProgressPercent = draftAllJob
    ? draftAllJob.percent
    : totalSections > 0
      ? Math.round((readySections / totalSections) * 100)
      : 0;

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
      {/* ── Left Panel: Section List ── */}
      <div className="space-y-3">
        {/* Syncing Banner */}
        {isRefreshingLibrary && (
          <div className="rounded-md bg-blue-50 border border-blue-200 p-3">
            <div className="flex items-center gap-2 text-blue-700">
              <Loader2 className="h-4 w-4 animate-spin shrink-0" />
              <div className="text-xs font-medium">Library refresh in progress...</div>
            </div>
            <p className="text-[10px] text-blue-600 mt-1 leading-relaxed">
              {isSyncing
                ? "The company source-library link is being resolved. Generation will resume automatically."
                : "The source library is already linked, so generation remains available while document details refresh."}
            </p>
          </div>
        )}

        {librarySyncFailed && (
          <div className="rounded-md border border-amber-300 bg-amber-50 p-3">
            <div className="text-xs font-medium text-amber-800">Library refresh timed out</div>
            <p className="mt-1 text-[10px] leading-relaxed text-amber-700">
              Existing linked documents remain available. You can continue generating or retry the
              refresh.
            </p>
            <button
              type="button"
              onClick={retryLibrarySync}
              disabled={retryingLibrarySync}
              className="mt-2 inline-flex items-center gap-1.5 rounded border border-amber-300 bg-white px-2 py-1 text-[11px] font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-60"
            >
              {retryingLibrarySync ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <RefreshCw className="h-3 w-3" />
              )}
              Retry library refresh
            </button>
          </div>
        )}

        {/* Draft All Card */}
        <div className="doc-card">
          <div className="p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-medium text-muted-foreground">
                {draftAllJob
                  ? `Draft All: ${draftAllJob.completed}/${draftAllJob.total} completed${draftAllJob.failed ? `, ${draftAllJob.failed} failed` : ""}`
                  : `Progress: ${readySections}/${totalSections} sections`}
              </div>
              <div className="text-xs font-mono text-muted-foreground">{draftProgressPercent}%</div>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted mb-3">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                style={{ width: `${draftProgressPercent}%` }}
              />
            </div>
            {draftAllJob && (
              <div className="mb-3 space-y-2 rounded-md border bg-muted/20 p-2.5">
                {liveDraftSections.length > 0 ? (
                  <div className="rounded-md border border-blue-200 bg-blue-50 px-2.5 py-2 text-xs text-blue-800">
                    <div className="mb-1 font-semibold">Currently running</div>
                    {liveDraftSections.map((section) => (
                      <div key={section.section_id} className="flex items-center gap-2 py-0.5">
                        <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
                        <span className="font-medium">{section.title}</span>
                        <span className="text-blue-600">— {section.stage}</span>
                      </div>
                    ))}
                  </div>
                ) : draftingAll ? (
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Loader2 className="h-3 w-3 animate-spin" />
                    Preparing the next sections…
                  </div>
                ) : null}
                <div className="max-h-48 space-y-1 overflow-y-auto">
                  {draftAllJob.sections.map((section) => (
                    <div
                      key={section.section_id}
                      className="flex items-center justify-between gap-2 rounded bg-background px-2 py-1.5 text-[11px]"
                    >
                      <span className="truncate font-medium">{section.title}</span>
                      <span
                        className={`flex shrink-0 items-center gap-1 ${
                          section.status === "completed"
                            ? "text-emerald-600"
                            : section.status === "failed"
                              ? "text-red-600"
                              : section.status === "running"
                                ? "text-blue-600"
                                : "text-muted-foreground"
                        }`}
                      >
                        {section.status === "completed" ? (
                          <CheckCircle2 className="h-3 w-3" />
                        ) : section.status === "failed" ? (
                          <TriangleAlert className="h-3 w-3" />
                        ) : section.status === "running" ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <Clock className="h-3 w-3" />
                        )}
                        {section.stage}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleDraftAll}
                disabled={draftingAll || draftingSelected || isSyncing}
                className="flex-1 inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary/10 px-3 text-xs font-medium text-primary hover:bg-primary/20 disabled:opacity-60 transition-colors"
              >
                {draftingAll ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {draftingAll ? "Drafting All…" : "Draft All"}
              </button>
              <button
                onClick={handleDraftSelected}
                disabled={
                  draftingAll || draftingSelected || selectedSectionIds.size === 0 || isSyncing
                }
                className="flex-1 inline-flex h-9 items-center justify-center gap-2 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60 transition-colors"
              >
                {draftingSelected ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                Draft Selected ({selectedSectionIds.size})
              </button>
            </div>
          </div>
        </div>

        {/* Section List */}
        <div className="doc-card">
          <div className="doc-section-header justify-between">
            <span>Sections</span>
            <button
              onClick={() => {
                if (selectedSectionIds.size === deal.sections.length) {
                  setSelectedSectionIds(new Set());
                } else {
                  setSelectedSectionIds(new Set(deal.sections.map((s) => s.id)));
                }
              }}
              className="text-[10px] font-medium text-primary hover:underline"
            >
              {selectedSectionIds.size === deal.sections.length ? "Deselect All" : "Select All"}
            </button>
          </div>
          <ul className="divide-y max-h-[500px] overflow-y-auto">
            {deal.sections.map((s, i) => (
              <li key={s.id} className="flex items-center">
                <div className="pl-3 py-2.5 shrink-0 flex items-center justify-center">
                  <input
                    type="checkbox"
                    checked={selectedSectionIds.has(s.id)}
                    onChange={(e) => {
                      const newSet = new Set(selectedSectionIds);
                      if (e.target.checked) newSet.add(s.id);
                      else newSet.delete(s.id);
                      setSelectedSectionIds(newSet);
                    }}
                    className="h-3.5 w-3.5 rounded border-muted-foreground/30 text-primary focus:ring-primary cursor-pointer"
                  />
                </div>
                <button
                  onClick={() => setActiveId(s.id)}
                  className={`flex flex-1 items-center justify-between pr-3 py-2.5 text-left text-sm transition-colors ${
                    activeId === s.id ? "bg-primary/5" : "hover:bg-surface"
                  }`}
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="font-mono text-[10px] text-muted-foreground shrink-0 w-5 text-right">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span
                      className={`font-medium truncate ${activeId === s.id ? "text-primary" : ""}`}
                    >
                      {s.title}
                    </span>
                  </span>
                  <span className="flex items-center gap-1.5 shrink-0 ml-2">
                    {s.output_template && (
                      <span
                        className="rounded-full bg-violet-100 px-1 py-0.5 text-[9px] text-violet-700"
                        title="Has template"
                      >
                        📋
                      </span>
                    )}
                    <span className={`section-status-badge ${s.state}`}>
                      {s.state === "ready" ? <CheckCircle2 className="h-3 w-3" /> : null}
                      {s.state}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* ── Right Panel: Section Detail ── */}
      <div className="space-y-4">
        {/* Section Header Card */}
        <div className={`doc-card ${active.generated_content ? "narrative-ready-glow" : ""}`}>
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              <span className="font-mono text-xs opacity-70">
                {String(deal.sections.indexOf(active) + 1).padStart(2, "0")}
              </span>
              {active.title}
            </span>
            <div className="flex items-center gap-2">
              {/* Mode badges */}
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                  isFewShot
                    ? "bg-amber-100 text-amber-800 border border-amber-200"
                    : "bg-slate-100 text-slate-600 border border-slate-200"
                }`}
              >
                {isFewShot ? "Few-shot" : "Zero-shot"}
              </span>
              {hasTemplate && (
                <span className="rounded-full bg-violet-100 text-violet-800 border border-violet-200 px-2 py-0.5 text-[10px] font-semibold">
                  Template
                </span>
              )}
              {/* Moderation badge */}
              {isFlagged && (
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-red-100 text-red-700 border border-red-200 px-2 py-0.5 text-[10px] font-semibold"
                  title={`Flagged: ${flaggedCategories.join(", ")}`}
                >
                  <ShieldAlert className="h-3 w-3" />
                  Flagged
                </span>
              )}
              {isModerationSafe && (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-700 border border-emerald-200 px-2 py-0.5 text-[10px] font-semibold">
                  <ShieldCheck className="h-3 w-3" />
                  Safe
                </span>
              )}
              <span className={`section-status-badge ${active.state}`}>
                {active.state === "ready" ? <CheckCircle2 className="h-3 w-3" /> : null}
                {active.state}
              </span>
            </div>
          </div>
          <div className="p-4">
            <p className="text-sm text-muted-foreground">{active.description}</p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <div className="rounded-md bg-surface p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                  Data Sources
                </div>
                <textarea
                  value={dataSources}
                  onChange={(event) => setDataSources(event.target.value)}
                  rows={3}
                  className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
              <div className="rounded-md bg-surface p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                  Expected Output
                </div>
                <textarea
                  value={expected}
                  onChange={(event) => setExpected(event.target.value)}
                  rows={3}
                  className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-xs outline-none focus:ring-1 focus:ring-ring"
                />
              </div>
            </div>
            <div className="mt-2 flex justify-end">
              <button
                onClick={handleSaveSectionDetails}
                disabled={
                  savingSectionDetails ||
                  (dataSources === active.sources && expected === active.expected_output)
                }
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground disabled:opacity-40"
              >
                {savingSectionDetails ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}{" "}
                Save Section Details
              </button>
            </div>
          </div>
        </div>

        {/* ── Custom Instructions (Few-shot) ── */}
        <div className="doc-card">
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              <LinkIcon className="h-4 w-4 shrink-0" />
              Add URLs
              {(active.source_urls?.length || 0) > 0 && (
                <span className="rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-700">
                  {active.source_urls.length} saved
                </span>
              )}
            </span>
          </div>
          <div className="space-y-3 p-4">
            <p className="text-xs text-muted-foreground">
              Add public webpages to use as evidence for this section’s narration draft.
            </p>
            {sourceUrls.map((url, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  type="url"
                  value={url}
                  onChange={(event) => {
                    const next = [...sourceUrls];
                    next[index] = event.target.value;
                    setSourceUrls(next);
                    setUrlMessage(null);
                    setUrlError(null);
                  }}
                  placeholder="https://example.com/relevant-page"
                  className="h-9 min-w-0 flex-1 rounded-md border border-input bg-background px-3 text-sm outline-none focus:ring-1 focus:ring-ring"
                />
                {sourceUrls.length > 1 && (
                  <button
                    type="button"
                    onClick={() =>
                      setSourceUrls((current) =>
                        current.filter((_, itemIndex) => itemIndex !== index),
                      )
                    }
                    className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border text-red-600 hover:bg-red-50"
                    title="Remove URL"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                )}
              </div>
            ))}
            {sourceUrls[sourceUrls.length - 1]?.trim() && sourceUrls.length < 10 && (
              <button
                type="button"
                onClick={() => setSourceUrls((current) => [...current, ""])}
                className="inline-flex h-8 items-center gap-1.5 rounded-md border px-3 text-xs font-medium hover:bg-muted"
              >
                <Plus className="h-3.5 w-3.5" /> Add Another
              </button>
            )}
            {active.url_scrape_details?.length ? (
              <div className="space-y-1 rounded-md bg-muted/40 p-3">
                {active.url_scrape_details.map((detail) => (
                  <div key={detail.url} className="flex items-start gap-2 text-[11px]">
                    <span
                      className={
                        detail.status === "completed" ? "text-emerald-700" : "text-red-700"
                      }
                    >
                      {detail.status === "completed" ? "Scraped" : "Failed"}
                    </span>
                    <span
                      className="min-w-0 truncate text-muted-foreground"
                      title={detail.error || detail.url}
                    >
                      {detail.title || detail.url}
                      {detail.error ? ` — ${detail.error}` : ""}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="flex items-center justify-between gap-3 border-t pt-3">
              <div className="text-xs">
                {urlMessage && <span className="text-emerald-700">{urlMessage}</span>}
                {urlError && <span className="text-red-700">{urlError}</span>}
              </div>
              <button
                type="button"
                onClick={handleSaveUrls}
                disabled={savingUrls}
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-primary px-3 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {savingUrls ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Save className="h-3.5 w-3.5" />
                )}
                Save URLs
              </button>
            </div>
          </div>
        </div>

        <div className="doc-card">
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              Custom Instructions for AI
              <span
                className={`rounded-full px-2 py-0.5 text-[9px] font-semibold ${
                  customInstructions.trim()
                    ? "bg-amber-100 text-amber-800"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {customInstructions.trim() ? "Few-shot" : "Zero-shot"}
              </span>
            </span>
          </div>
          <div className="p-4">
            <textarea
              value={customInstructions}
              onChange={(e) => setCustomInstructions(e.target.value)}
              rows={3}
              placeholder={`Provide example output patterns for the AI to follow (few-shot approach).\n\nExample:\n"For the executive summary, start with a recommendation paragraph, then use bullet points for key highlights. Include a risk summary table at the end."`}
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <div className="flex items-center justify-between mt-2">
              <p className="text-[10px] text-muted-foreground">
                {customInstructions.trim()
                  ? "✨ Few-shot mode — the agent will use your instructions as example patterns."
                  : "No instructions set — the agent will run in zero-shot mode."}
              </p>
              <button
                onClick={handleSaveInstructions}
                disabled={
                  savingInstructions || customInstructions === (active.custom_instructions || "")
                }
                className="inline-flex h-8 items-center gap-1.5 rounded-md bg-amber-600 px-3 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-40 transition-colors"
              >
                {savingInstructions ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Save className="h-3 w-3" />
                )}
                Save Instructions
              </button>
            </div>
          </div>
        </div>

        {/* ── Output Template ── */}
        <div className="doc-card">
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              <FileType className="h-4 w-4 shrink-0" />
              Output Template
              {hasTemplate && (
                <span className="rounded-full bg-violet-100 text-violet-700 px-2 py-0.5 text-[10px] font-bold">
                  Active
                </span>
              )}
            </span>
            <div className="flex items-center gap-1">
              {hasTemplate && (
                <>
                  <button
                    onClick={() => setShowTemplatePreview(!showTemplatePreview)}
                    className="inline-flex h-6 items-center gap-1 rounded px-2 text-[11px] font-medium bg-primary-foreground/10 hover:bg-primary-foreground/20 transition-colors"
                    title={showTemplatePreview ? "Hide preview" : "Show preview"}
                  >
                    {showTemplatePreview ? (
                      <EyeOff className="h-3 w-3" />
                    ) : (
                      <Eye className="h-3 w-3" />
                    )}
                  </button>
                  <button
                    onClick={handleDeleteTemplate}
                    className="inline-flex h-6 items-center gap-1 rounded px-2 text-[11px] font-medium text-destructive hover:bg-destructive/10 transition-colors"
                    title="Remove template"
                  >
                    <Trash2 className="h-3 w-3" />
                  </button>
                </>
              )}
            </div>
          </div>
          <div className="p-4 space-y-3">
            {/* Template text preview */}
            {hasTemplate && showTemplatePreview && (
              <div className="rounded-md bg-violet-50 border border-violet-200 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-violet-600 mb-2">
                  Current Template Preview
                </div>
                <pre className="text-xs text-violet-900 whitespace-pre-wrap font-mono max-h-48 overflow-y-auto">
                  {active.output_template}
                </pre>
              </div>
            )}

            {/* Template textarea */}
            <div>
              <label className="text-xs font-medium text-muted-foreground block mb-1.5">
                Paste or edit markdown template
              </label>
              <textarea
                value={outputTemplate}
                onChange={(e) => setOutputTemplate(e.target.value)}
                rows={4}
                placeholder={`# Section Heading\n\n## Sub-section 1\n- Key point 1\n- Key point 2\n\n## Sub-section 2\n| Column A | Column B |\n|----------|----------|\n| ...      | ...      |`}
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm font-mono focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              />
              <button
                onClick={handleSaveTemplate}
                disabled={savingTemplate || outputTemplate === (active.output_template || "")}
                className="mt-2 inline-flex h-8 items-center gap-1.5 rounded-md bg-violet-600 px-3 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-40 transition-colors"
              >
                {savingTemplate ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Save className="h-3 w-3" />
                )}
                Save Template
              </button>
            </div>

            {/* Divider */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-[10px] uppercase">
                <span className="bg-card px-2 text-muted-foreground">or upload file</span>
              </div>
            </div>

            {/* Template file upload */}
            <div className="rounded-lg border-2 border-dashed border-violet-200 p-3 hover:border-violet-400 transition-colors">
              <div className="flex items-center gap-3">
                <FileType className="h-5 w-5 text-violet-400 shrink-0" />
                <div className="flex-1 min-w-0">
                  <input
                    type="file"
                    id="template-file-input"
                    accept=".md,.txt,.docx,.doc"
                    className="text-xs w-full"
                    onChange={handleUploadTemplate}
                  />
                  <p className="text-[10px] text-muted-foreground mt-0.5">
                    Supports .md, .txt, .docx files
                  </p>
                </div>
                {uploadingTemplate && <Loader2 className="h-4 w-4 animate-spin text-violet-500" />}
              </div>
              {active.template_file_path && (
                <div className="mt-2 flex items-center gap-2 text-[10px] text-violet-600">
                  <CheckCircle2 className="h-3 w-3" />
                  Template loaded from file
                </div>
              )}
            </div>

            <p className="text-[10px] text-muted-foreground">
              The AI agent will follow this template's exact structure (headings, tables, bullet
              format) when generating the narrative.
            </p>
          </div>
        </div>

        {/* ── Generated Narrative — The Star of the Show ── */}
        <div className={`doc-card ${active.generated_content ? "narrative-ready-glow" : ""}`}>
          <div className="doc-section-header justify-between">
            <span className="flex items-center gap-2">
              <Sparkles className="h-4 w-4" />
              Generated Narrative
              {active.generated_content && (
                <span className="rounded-full bg-primary-foreground/20 px-2 py-0.5 text-[10px] font-semibold">
                  {wordCount} words
                </span>
              )}
            </span>
            <div className="flex items-center gap-2">
              {active.generated_content &&
                !editingContent &&
                active.original_generated_content &&
                active.original_generated_content !== active.generated_content && (
                  <button
                    onClick={() => setShowEdits(!showEdits)}
                    className={`inline-flex h-7 items-center gap-1 rounded-md border px-2 text-xs font-medium transition-colors ${showEdits ? "border-emerald-500/50 bg-emerald-50 text-emerald-700" : "border-primary-foreground/30 bg-primary-foreground/10 hover:bg-primary-foreground/20"}`}
                  >
                    <Eye className="h-3.5 w-3.5" />
                    {showEdits ? "Hide Edits" : "Show Edits"}
                  </button>
                )}
              {active.generated_content && !editingContent && (
                <button
                  onClick={() => setShowCitations((value) => !value)}
                  className="inline-flex h-7 items-center gap-1 rounded-md border border-primary-foreground/30 bg-primary-foreground/10 px-2 text-xs font-medium hover:bg-primary-foreground/20"
                >
                  {showCitations ? (
                    <EyeOff className="h-3.5 w-3.5" />
                  ) : (
                    <Eye className="h-3.5 w-3.5" />
                  )}
                  {showCitations ? "Hide Citations" : "Show Citations"}
                </button>
              )}
              {active.generated_content && !editingContent && (
                <button
                  onClick={handleToggleVersionHistory}
                  disabled={loadingVersions}
                  className={`inline-flex h-7 items-center gap-1 rounded-md border px-2 text-xs font-medium transition-colors ${
                    showVersionHistory
                      ? "border-primary-foreground/60 bg-primary-foreground/25"
                      : "border-primary-foreground/30 bg-primary-foreground/10 hover:bg-primary-foreground/20"
                  }`}
                >
                  {loadingVersions ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <History className="h-3.5 w-3.5" />
                  )}
                  Version History
                </button>
              )}
              {active.generated_content && !editingContent && (
                <button
                  onClick={handleStartEditing}
                  disabled={generating || acquiringEditLock}
                  className="inline-flex h-7 items-center gap-1 rounded-md border border-primary-foreground/30 bg-primary-foreground/10 px-2 text-xs font-medium disabled:opacity-60 hover:bg-primary-foreground/20 transition-colors"
                >
                  {acquiringEditLock ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Type className="h-3.5 w-3.5" />
                  )}
                  {acquiringEditLock ? "Opening" : "Edit"}
                </button>
              )}
              {editingContent && (
                <button
                  onClick={handleCancelEditing}
                  disabled={savingContent}
                  className="inline-flex h-7 items-center gap-1 rounded-md border border-primary-foreground/30 bg-transparent px-2 text-xs font-medium text-primary-foreground disabled:opacity-60 hover:bg-primary-foreground/10 transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                  Cancel
                </button>
              )}
              <button
                onClick={handleGenerate}
                disabled={generating || editingContent || isFlagged || isSyncing}
                title={
                  isFlagged
                    ? `Blocked: content flagged (${flaggedCategories.join(", ")})`
                    : isSyncing
                      ? "Blocked: Library sync in progress"
                      : undefined
                }
                className="inline-flex h-7 items-center gap-1 rounded-md border border-primary-foreground/30 bg-primary-foreground/10 px-2 text-xs font-medium disabled:opacity-60 hover:bg-primary-foreground/20 transition-colors"
              >
                {generating ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : isFlagged ? (
                  <ShieldAlert className="h-3.5 w-3.5" />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                {generating
                  ? "Generating…"
                  : isFlagged
                    ? "Blocked"
                    : isSyncing
                      ? "Syncing..."
                      : "Generate"}
              </button>
            </div>
          </div>

          {showVersionHistory && (
            <div className="border-b bg-slate-50 p-4 text-foreground">
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wide text-slate-700">
                    All Generated and Edited Versions
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    The latest version is used as the default final until you explicitly mark
                    another version. Only the final version is used in exports.
                  </p>
                </div>
                <button
                  onClick={() => setShowVersionHistory(false)}
                  className="rounded-md border bg-background p-1.5 text-muted-foreground hover:text-foreground"
                  title="Close version history"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>

              {loadingVersions ? (
                <div className="flex items-center justify-center gap-2 rounded-md border bg-background p-8 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading versions…
                </div>
              ) : narrativeVersions.length === 0 ? (
                <div className="rounded-md border border-dashed bg-background p-8 text-center text-sm text-muted-foreground">
                  No saved narrative versions yet.
                </div>
              ) : (
                <div className="max-h-[520px] space-y-3 overflow-y-auto pr-1">
                  {narrativeVersions.map((version, index) => {
                    const hasExplicitFinal = narrativeVersions.some((item) => item.is_final);
                    const isDefaultFinal = !hasExplicitFinal && index === 0;
                    const expanded = expandedVersionIds.has(version.id);
                    const lines = version.content.split("\n");
                    const shortContent = lines.slice(0, 5).join("\n");
                    const preview =
                      expanded || version.content.length <= 650
                        ? version.content
                        : `${shortContent.slice(0, 650)}…`;
                    const canExpand = version.content.length > 650 || lines.length > 5;
                    const badgeClass =
                      version.version_type === "edited"
                        ? "bg-pink-100 text-pink-700"
                        : "bg-blue-100 text-blue-700";
                    const previousVersion = version.parent_version_id
                      ? narrativeVersions.find((item) => item.id === version.parent_version_id)
                      : narrativeVersions[index + 1];

                    return (
                      <div
                        key={version.id}
                        className="rounded-lg border bg-background p-3 shadow-sm"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold">
                              Version {narrativeVersions.length - index}
                            </span>
                            <span
                              className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${badgeClass}`}
                            >
                              {version.version_type}
                            </span>
                            {index === 0 && (
                              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-700">
                                Latest
                              </span>
                            )}
                            {version.is_final && (
                              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-700">
                                Final
                              </span>
                            )}
                            {isDefaultFinal && (
                              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-700">
                                Default Final
                              </span>
                            )}
                          </div>
                          <span className="text-[11px] text-muted-foreground">
                            {new Date(version.created_at).toLocaleString()}
                          </span>
                        </div>
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {version.created_by}
                        </p>
                        <pre
                          className={`mt-3 whitespace-pre-wrap rounded-md border p-3 font-sans text-xs leading-5 text-slate-700 ${
                            version.version_type === "edited"
                              ? "border-amber-200 bg-amber-50/60"
                              : "bg-muted/30"
                          }`}
                        >
                          {version.version_type === "edited" ? (
                            <VersionHistoryContent
                              previous={previousVersion?.content || ""}
                              current={preview}
                            />
                          ) : (
                            preview
                          )}
                        </pre>
                        <div className="mt-3 flex flex-wrap items-center gap-2">
                          {canExpand && (
                            <button
                              onClick={() =>
                                setExpandedVersionIds((current) => {
                                  const next = new Set(current);
                                  if (next.has(version.id)) next.delete(version.id);
                                  else next.add(version.id);
                                  return next;
                                })
                              }
                              className="rounded-md border px-2.5 py-1 text-xs font-medium hover:bg-muted"
                            >
                              {expanded ? "Show less" : "Show more"}
                            </button>
                          )}
                          <button
                            onClick={() => handleMarkNarrativeVersionFinal(version.id)}
                            disabled={version.is_final || markingFinalVersionId !== null}
                            className="inline-flex items-center gap-1.5 rounded-md border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {markingFinalVersionId === version.id ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <CheckCircle2 className="h-3 w-3" />
                            )}
                            {version.is_final ? "Marked as Final" : "Mark as Final"}
                          </button>
                          <button
                            onClick={() => handleDeleteNarrativeVersion(version)}
                            disabled={
                              deletingNarrativeVersionId !== null || markingFinalVersionId !== null
                            }
                            className="inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {deletingNarrativeVersionId === version.id ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <Trash2 className="h-3 w-3" />
                            )}
                            Delete Version
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Moderation Warning Banner */}
          {(isFlagged || moderationError) && (
            <div className="px-5 py-4 bg-red-50 border-b border-red-200 space-y-3">
              <div className="flex items-center gap-2">
                <ShieldAlert className="h-5 w-5 text-red-600 shrink-0" />
                <span className="text-xs font-bold text-red-800 uppercase tracking-wide">
                  Content Moderation — Generation Blocked
                </span>
              </div>

              {moderationError && !isFlagged && (
                <div className="text-xs text-red-700 bg-red-100 rounded-md px-3 py-2">
                  {moderationError}
                </div>
              )}

              {/* Per-field breakdown */}
              {active.moderation_details?.details &&
                (() => {
                  const details = active.moderation_details.details as Record<
                    string,
                    {
                      is_safe?: boolean;
                      flagged_categories?: string[];
                      details?: Record<string, { flagged: boolean; score: number }>;
                    }
                  >;
                  const instructionsFlagged =
                    details.custom_instructions && !details.custom_instructions.is_safe;
                  const templateFlagged =
                    details.output_template && !details.output_template.is_safe;

                  const renderCategoryBreakdown = (
                    label: string,
                    fieldDetails:
                      | {
                          is_safe?: boolean;
                          flagged_categories?: string[];
                          details?: Record<string, { flagged: boolean; score: number }>;
                        }
                      | undefined,
                  ) => {
                    if (!fieldDetails || (!showMoreModeration && fieldDetails.is_safe)) return null;

                    const allCats = fieldDetails.details || {};
                    const displayedCats = showMoreModeration
                      ? Object.keys(allCats)
                      : fieldDetails.flagged_categories || [];

                    if (displayedCats.length === 0) return null;

                    return (
                      <div className="rounded-md border border-red-200 bg-white/60 p-3 space-y-2 mb-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-[10px] font-bold uppercase ${label === "Custom Instructions" ? "bg-amber-100 text-amber-800 border-amber-200" : "bg-violet-100 text-violet-800 border-violet-200"}`}
                          >
                            {label}
                          </span>
                          {!fieldDetails.is_safe && (
                            <span className="text-[10px] text-red-600 font-medium">— Flagged</span>
                          )}
                        </div>
                        <div className="space-y-1.5">
                          {displayedCats.map((cat) => {
                            const info = MODERATION_CATEGORY_INFO[cat] || {
                              label: cat.replace(/_/g, " "),
                              fix: "Review and edit this content.",
                            };
                            const catData = allCats[cat];
                            const scoreValue = catData ? catData.score : 0;
                            const scorePercent = (scoreValue * 100).toFixed(2);
                            const isFlagged = catData
                              ? catData.flagged
                              : fieldDetails.flagged_categories?.includes(cat);

                            const scoreColor = isFlagged
                              ? "bg-red-500"
                              : scoreValue > 0.5
                                ? "bg-amber-500"
                                : "bg-emerald-400";

                            return (
                              <div
                                key={cat}
                                className="flex flex-col gap-2 text-xs border-b border-gray-100 last:border-0 pb-2.5 last:pb-0 pt-1"
                              >
                                <div className="flex items-center gap-2">
                                  <span
                                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold shrink-0 ${isFlagged ? "bg-red-200/60 text-red-800" : "bg-slate-100 text-slate-600"}`}
                                  >
                                    {info.label}
                                  </span>
                                  {isFlagged ? (
                                    <span className="text-red-700">{info.fix}</span>
                                  ) : (
                                    <span className="text-slate-500">Passed</span>
                                  )}
                                </div>
                                {catData && (
                                  <div className="flex items-center gap-3 w-full max-w-[200px] pl-1 opacity-90 hover:opacity-100 transition-opacity">
                                    <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden shrink-0">
                                      <div
                                        className={`h-full ${scoreColor} rounded-full transition-all duration-500`}
                                        style={{ width: `${Math.max(scoreValue * 100, 2)}%` }}
                                      />
                                    </div>
                                    <span className="text-[10px] font-mono font-medium text-slate-500 shrink-0 w-10 text-right">
                                      {scorePercent}%
                                    </span>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    );
                  };

                  return (
                    <div>
                      {renderCategoryBreakdown("Custom Instructions", details.custom_instructions)}
                      {renderCategoryBreakdown("Output Template", details.output_template)}

                      {/* Fallback */}
                      {!instructionsFlagged &&
                        !templateFlagged &&
                        flaggedCategories.length > 0 &&
                        !showMoreModeration && (
                          <div className="rounded-md border border-red-200 bg-white/60 p-3 space-y-1.5">
                            {flaggedCategories.map((cat: string) => {
                              const info = MODERATION_CATEGORY_INFO[cat] || {
                                label: cat.replace(/_/g, " "),
                                fix: "Review and edit this content.",
                              };
                              return (
                                <div key={cat} className="flex items-start gap-2 text-xs">
                                  <span className="rounded-full bg-red-200/60 text-red-800 px-2 py-0.5 text-[10px] font-semibold shrink-0 mt-0.5">
                                    {info.label}
                                  </span>
                                  <span className="text-red-700">{info.fix}</span>
                                </div>
                              );
                            })}
                          </div>
                        )}
                    </div>
                  );
                })()}

              <div className="flex items-center justify-between mt-2 pt-2 border-t border-red-200/50">
                <p className="text-[10px] text-red-600 italic">
                  Fix the flagged content above, then save again. The moderation check will re-run
                  automatically.
                </p>
                <button
                  onClick={() => setShowMoreModeration(!showMoreModeration)}
                  className="inline-flex items-center gap-1 text-[10px] font-medium text-red-700 hover:text-red-900 transition-colors bg-red-100 hover:bg-red-200 rounded-md px-2 py-1"
                >
                  {showMoreModeration ? (
                    <ChevronUp className="h-3 w-3" />
                  ) : (
                    <ChevronDown className="h-3 w-3" />
                  )}
                  {showMoreModeration ? "Show Less" : "Show More"}
                </button>
              </div>
            </div>
          )}

          {active.generated_content ? (
            <div className="narrative-content-enter">
              {/* Success banner */}
              <div className="flex items-center gap-2 px-5 py-2.5 bg-emerald-50 border-b border-emerald-100">
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                <span className="text-xs font-semibold text-emerald-700 uppercase tracking-wide">
                  AI Draft Ready
                </span>
                <div className="ml-auto flex items-center gap-2">
                  {isFewShot && (
                    <span className="text-[9px] font-medium text-amber-700 bg-amber-50 rounded-full px-2 py-0.5 border border-amber-200">
                      Few-shot
                    </span>
                  )}
                  {hasTemplate && (
                    <span className="text-[9px] font-medium text-violet-700 bg-violet-50 rounded-full px-2 py-0.5 border border-violet-200">
                      Templated
                    </span>
                  )}
                  <span className="text-[10px] text-emerald-600">
                    {libDocCount > 0 ? `${libDocCount} library doc(s)` : "No docs"} · Mistral Agent
                  </span>
                </div>
              </div>
              {/* Accuracy Panel */}
              <AccuracyPanel section={active} />
              {/* References Panel */}
              <ReferencesPanel section={active} deal={deal} />
              {/* Rendered markdown content */}
              <div className="narrative-prose px-6 py-5">
                {editingContent ? (
                  <div className="space-y-3">
                    <textarea
                      value={editedContent}
                      onChange={(e) => setEditedContent(e.target.value)}
                      rows={15}
                      className="w-full rounded-md border border-input bg-background/50 px-3 py-2 text-sm font-mono focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                    />
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={handleSaveContent}
                        disabled={savingContent}
                        className="inline-flex h-8 items-center gap-1.5 rounded-md bg-emerald-600 px-3 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-60 transition-colors"
                      >
                        {savingContent ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Save className="h-3.5 w-3.5" />
                        )}
                        Save Changes
                      </button>
                    </div>
                  </div>
                ) : showEdits && active.original_generated_content ? (
                  <DiffViewer
                    original={
                      showCitations
                        ? active.original_generated_content
                        : withoutCitations(active.original_generated_content)
                    }
                    current={visibleNarrativeContent}
                    primaryColor={deal.primary_color}
                    secondaryColor={deal.secondary_color}
                    documents={deal.documents}
                  />
                ) : (
                  <MarkdownRenderer
                    content={visibleNarrativeContent}
                    primaryColor={deal.primary_color}
                    secondaryColor={deal.secondary_color}
                    documents={deal.documents}
                  />
                )}
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-4 p-12 text-center">
              <div className="rounded-full bg-muted p-4">
                <Sparkles className="h-8 w-8 text-muted-foreground" />
              </div>
              <div>
                <div className="font-semibold text-foreground">No AI draft yet</div>
                <div className="text-sm text-muted-foreground mt-1 max-w-sm">
                  Upload documents to the library, add custom instructions (few-shot), and
                  optionally set an output template. Then generate the draft.
                </div>
              </div>
              <button
                onClick={handleGenerate}
                disabled={generating || isFlagged || isSyncing}
                title={
                  isFlagged
                    ? `Blocked: content flagged (${flaggedCategories.join(", ")})`
                    : isSyncing
                      ? "Blocked: Library sync in progress"
                      : undefined
                }
                className={`inline-flex h-10 items-center gap-2 rounded-md px-5 text-sm font-medium shadow disabled:opacity-60 transition-colors ${
                  isFlagged || isSyncing
                    ? "bg-red-600 text-white hover:bg-red-700"
                    : "bg-primary text-primary-foreground hover:bg-primary/90"
                }`}
              >
                {generating ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : isFlagged || isSyncing ? (
                  <ShieldAlert className="h-4 w-4" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {generating
                  ? "Generating…"
                  : isFlagged
                    ? "Generation Blocked"
                    : isSyncing
                      ? "Syncing Documents..."
                      : "Generate Draft"}
              </button>
              {isFlagged && (
                <p className="text-xs text-red-600 mt-2 max-w-sm">
                  Edit your custom instructions or output template to resolve moderation flags.
                </p>
              )}
              {isSyncing && !isFlagged && (
                <p className="text-xs text-red-600 mt-2 max-w-sm">
                  Please wait until all documents are uploaded to the library before generating.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ── Accuracy Panel Component ──────────────────────────────────── */

function AccuracyPanel({ section }: { section: Section }) {
  const [expanded, setExpanded] = useState(false);

  // No accuracy assessment available
  if (section.accuracy_score === null && !section.accuracy_details) {
    return (
      <div className="flex items-center gap-2 px-5 py-2 bg-slate-50 border-b border-slate-100">
        <Info className="h-3.5 w-3.5 text-slate-400" />
        <span className="text-[10px] text-slate-500 italic">
          Accuracy not assessed — no library documents available
        </span>
      </div>
    );
  }

  const score = section.accuracy_score ?? 0;
  const details = section.accuracy_details;

  // Color theming based on score
  const getScoreColor = (s: number) => {
    if (s >= 80)
      return {
        bg: "bg-emerald-50",
        border: "border-emerald-200",
        text: "text-emerald-700",
        ring: "stroke-emerald-500",
        fill: "bg-emerald-500",
        label: "High Confidence",
      };
    if (s >= 60)
      return {
        bg: "bg-amber-50",
        border: "border-amber-200",
        text: "text-amber-700",
        ring: "stroke-amber-500",
        fill: "bg-amber-500",
        label: "Moderate Confidence",
      };
    return {
      bg: "bg-red-50",
      border: "border-red-200",
      text: "text-red-700",
      ring: "stroke-red-500",
      fill: "bg-red-500",
      label: "Low Confidence",
    };
  };

  const colors = getScoreColor(score);

  // SVG circular gauge
  const radius = 28;
  const circumference = 2 * Math.PI * radius;
  const strokeDashoffset = circumference - (score / 100) * circumference;

  // Claims total for percentage bar
  const grounded = details?.grounded_claims ?? 0;
  const inferred = details?.inferred_claims ?? 0;
  const unsupported = details?.unsupported_claims ?? 0;
  const totalClaims = grounded + inferred + unsupported;

  return (
    <div className={`border-b ${colors.border} ${colors.bg} transition-all duration-300`}>
      {/* Collapsed summary bar */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-3 px-5 py-2.5 hover:brightness-95 transition-all"
      >
        {/* Circular gauge */}
        <div className="relative shrink-0" style={{ width: 40, height: 40 }}>
          <svg width="40" height="40" viewBox="0 0 64 64" className="-rotate-90">
            {/* Background circle */}
            <circle
              cx="32"
              cy="32"
              r={radius}
              fill="none"
              stroke="currentColor"
              className="text-black/5"
              strokeWidth="5"
            />
            {/* Score arc */}
            <circle
              cx="32"
              cy="32"
              r={radius}
              fill="none"
              className={colors.ring}
              strokeWidth="5"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={strokeDashoffset}
              style={{ transition: "stroke-dashoffset 0.8s ease-out" }}
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className={`text-[11px] font-bold ${colors.text}`}>{score}%</span>
          </div>
        </div>

        {/* Label */}
        <div className="flex-1 min-w-0 text-left">
          <div className="flex items-center gap-1.5">
            <ShieldCheck className={`h-3.5 w-3.5 ${colors.text}`} />
            <span className={`text-xs font-semibold ${colors.text}`}>{colors.label}</span>
          </div>
          {details?.summary && (
            <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{details.summary}</p>
          )}
        </div>

        {/* Claims mini-bar */}
        {totalClaims > 0 && (
          <div className="hidden sm:flex items-center gap-3 shrink-0">
            <div className="flex items-center gap-1">
              <div className="w-16 h-1.5 rounded-full bg-black/5 overflow-hidden flex">
                <div
                  className="h-full bg-emerald-500 transition-all"
                  style={{ width: `${(grounded / totalClaims) * 100}%` }}
                />
                <div
                  className="h-full bg-amber-400 transition-all"
                  style={{ width: `${(inferred / totalClaims) * 100}%` }}
                />
                <div
                  className="h-full bg-red-400 transition-all"
                  style={{ width: `${(unsupported / totalClaims) * 100}%` }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Expand/collapse */}
        <div className={`shrink-0 ${colors.text}`}>
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </div>
      </button>

      {/* Expanded details */}
      {expanded && details && (
        <div className="px-5 pb-4 pt-1 space-y-3 animate-in slide-in-from-top-1 duration-200">
          {/* Claims breakdown */}
          <div className="grid grid-cols-3 gap-2">
            <div className="rounded-lg bg-white/70 border border-emerald-200/60 p-2.5 text-center">
              <div className="text-lg font-bold text-emerald-700">{grounded}</div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-emerald-600 mt-0.5">
                Grounded
              </div>
              <div className="text-[9px] text-emerald-500 mt-0.5">Direct from docs</div>
            </div>
            <div className="rounded-lg bg-white/70 border border-amber-200/60 p-2.5 text-center">
              <div className="text-lg font-bold text-amber-700">{inferred}</div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-amber-600 mt-0.5">
                Inferred
              </div>
              <div className="text-[9px] text-amber-500 mt-0.5">Reasoned from data</div>
            </div>
            <div className="rounded-lg bg-white/70 border border-red-200/60 p-2.5 text-center">
              <div className="text-lg font-bold text-red-700">{unsupported}</div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-red-600 mt-0.5">
                Unsupported
              </div>
              <div className="text-[9px] text-red-500 mt-0.5">No doc evidence</div>
            </div>
          </div>

          {/* Full-width claims bar */}
          {totalClaims > 0 && (
            <div>
              <div className="flex justify-between text-[9px] text-muted-foreground mb-1">
                <span>Claims Distribution</span>
                <span>{totalClaims} total claims</span>
              </div>
              <div className="h-2.5 rounded-full bg-black/5 overflow-hidden flex">
                <div
                  className="h-full bg-emerald-500 transition-all duration-500"
                  style={{ width: `${(grounded / totalClaims) * 100}%` }}
                  title={`${grounded} grounded claims`}
                />
                <div
                  className="h-full bg-amber-400 transition-all duration-500"
                  style={{ width: `${(inferred / totalClaims) * 100}%` }}
                  title={`${inferred} inferred claims`}
                />
                <div
                  className="h-full bg-red-400 transition-all duration-500"
                  style={{ width: `${(unsupported / totalClaims) * 100}%` }}
                  title={`${unsupported} unsupported claims`}
                />
              </div>
              <div className="flex justify-between mt-1">
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-emerald-500" />
                  <span className="text-[9px] text-muted-foreground">
                    Grounded ({Math.round((grounded / totalClaims) * 100)}%)
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-amber-400" />
                  <span className="text-[9px] text-muted-foreground">
                    Inferred ({Math.round((inferred / totalClaims) * 100)}%)
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <div className="w-2 h-2 rounded-full bg-red-400" />
                  <span className="text-[9px] text-muted-foreground">
                    Unsupported ({Math.round((unsupported / totalClaims) * 100)}%)
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Evaluator summary */}
          {details.summary && (
            <div className="rounded-md bg-white/60 border border-black/5 p-3">
              <div className="flex items-start gap-2">
                <Info className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  {details.summary}
                </p>
              </div>
            </div>
          )}

          {/* Disclaimer */}
          <p className="text-[9px] text-muted-foreground/60 italic text-center">
            Accuracy is an AI self-assessment and may not reflect ground truth. Always verify
            critical data points.
          </p>
        </div>
      )}
    </div>
  );
}

function ReferencesPanel({ section, deal }: { section: Section; deal: Deal }) {
  const [expanded, setExpanded] = useState(false);

  const timing = section.timing;
  const timingStr = timing
    ? `(Orch: ${timing.orchestration_ms}ms, Gen: ${timing.generation_ms}ms)`
    : "";

  return (
    <div className="border-b border-blue-100 bg-blue-50/30 transition-all duration-300">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between px-5 py-2 hover:bg-blue-50/60 transition-all"
      >
        <div className="flex items-center gap-2">
          <RefreshCw className="h-3.5 w-3.5 text-blue-500" />
          <span className="text-xs font-semibold text-blue-700">References {timingStr}</span>
        </div>
        <div className="text-blue-500">
          {expanded ? (
            <ChevronUp className="h-3.5 w-3.5" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-5 pb-4 pt-1 animate-in slide-in-from-top-1 duration-200">
          <div className="rounded-md bg-white border border-blue-200 p-4 shadow-sm prose prose-sm prose-blue max-w-none text-sm text-blue-900 overflow-y-auto max-h-[400px]">
            {section.orchestration_strategy ? (
              <MarkdownRenderer
                content={section.orchestration_strategy}
                primaryColor={deal.primary_color}
                secondaryColor={deal.secondary_color}
                documents={deal.documents}
              />
            ) : (
              <p className="text-muted-foreground italic m-0">
                No orchestration references available yet. Generate a draft to view the agent's
                research strategy and sources.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const MODERATION_CATEGORY_INFO: Record<string, { label: string; fix: string }> = {
  sexual: { label: "Sexual Content", fix: "Remove any sexually explicit or suggestive language." },
  hate_and_discrimination: {
    label: "Hate & Discrimination",
    fix: "Remove language targeting specific groups based on race, religion, gender, or other protected characteristics.",
  },
  violence_and_threats: {
    label: "Violence & Threats",
    fix: "Remove any references to physical harm, threats, or violent actions.",
  },
  dangerous_and_criminal_content: {
    label: "Dangerous & Criminal",
    fix: "Remove instructions related to illegal activities, fraud, or dangerous actions.",
  },
  selfharm: { label: "Self-Harm", fix: "Remove any references to self-harm or suicide." },
  health: { label: "Health Advice", fix: "Remove unqualified medical or health advice." },
  financial: {
    label: "Financial Advice",
    fix: "Remove specific investment recommendations or financial advice outside the credit analysis scope.",
  },
  pii: {
    label: "Personal Information (PII)",
    fix: "Remove personal identifiable information such as phone numbers, addresses, or ID numbers.",
  },
  law: { label: "Legal Advice", fix: "Remove specific legal counsel or recommendations." },
};

/* ── Markdown Renderer Component ───────────────────────────────── */

// Helper to extract plain text from React children
function extractText(node: any): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (!node) return "";
  if (Array.isArray(node)) return node.map(extractText).join("");
  if (node.props && node.props.children) return extractText(node.props.children);
  return "";
}

function CustomTable({ children, primaryColor, secondaryColor, node, ...props }: any) {
  const [viewMode, setViewMode] = useState<"table" | "chart">("table");

  // Parse the table data from the React children
  const parseTable = () => {
    try {
      const headers: string[] = [];
      const rows: any[] = [];

      const childrenArray = React.Children.toArray(children);
      const thead: any = childrenArray.find(
        (c: any) => React.isValidElement(c) && c.type === "thead",
      );
      const tbody: any = childrenArray.find(
        (c: any) => React.isValidElement(c) && c.type === "tbody",
      );

      if (thead && thead.props && thead.props.children) {
        const trs = React.Children.toArray(thead.props.children);
        const tr = trs.find((c: any) => React.isValidElement(c) && c.type === "tr") as any;
        if (tr && tr.props && tr.props.children) {
          React.Children.forEach((tr.props as any).children, (th: any) => {
            headers.push(extractText(th).trim());
          });
        }
      }

      if (tbody && tbody.props && tbody.props.children) {
        React.Children.forEach(tbody.props.children, (tr: any) => {
          if (!React.isValidElement(tr) || tr.type !== "tr" || !tr.props) return;
          const rowData: any = {};
          React.Children.forEach((tr.props as any).children, (td: any, idx: number) => {
            const valStr = extractText(td).trim();
            // Try to parse as number
            const numVal = Number(valStr.replace(/[^0-9.-]+/g, ""));
            const header = headers[idx] || `Col${idx}`;
            rowData[header] = !isNaN(numVal) && valStr.match(/[0-9]/) ? numVal : valStr;
          });
          rows.push(rowData);
        });
      }

      return { headers, rows };
    } catch (err) {
      console.error("Failed to parse table", err);
      return { headers: [], rows: [] };
    }
  };

  const { headers, rows } = parseTable();

  // Heuristic for numeric table: must have >1 columns, and at least some rows where column 2+ is a number
  const isNumeric = headers.length > 1 && rows.some((r) => typeof r[headers[1]] === "number");

  if (!isNumeric) {
    return (
      <div className="my-6 overflow-x-auto rounded-lg border border-slate-200 shadow-sm bg-white">
        <table className="w-full text-left text-sm" {...props}>
          {children}
        </table>
      </div>
    );
  }

  const yKeys = headers.slice(1);
  const xKey = headers[0];
  const chartColors = [
    primaryColor || "#0f172a",
    secondaryColor || "#334155",
    "#64748b",
    "#94a3b8",
    "#cbd5e1",
  ];

  return (
    <div className="my-6 rounded-md border bg-card text-card-foreground shadow-sm overflow-hidden">
      <div className="flex items-center justify-between border-b px-4 py-2 bg-muted/30">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {viewMode === "table" ? "Data Table" : "Chart View"}
        </div>
        <div className="flex bg-muted rounded-md p-0.5">
          <button
            onClick={() => setViewMode("table")}
            className={`flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium transition-colors ${viewMode === "table" ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
          >
            <TableIcon className="h-3.5 w-3.5" /> Table
          </button>
          <button
            onClick={() => setViewMode("chart")}
            className={`flex items-center gap-1.5 rounded-sm px-2.5 py-1 text-xs font-medium transition-colors ${viewMode === "chart" ? "bg-background shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
          >
            <BarChart3 className="h-3.5 w-3.5" /> Chart
          </button>
        </div>
      </div>

      <div className="p-4">
        {viewMode === "table" ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm" {...props}>
              {children}
            </table>
          </div>
        ) : (
          <div className="h-[300px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={rows} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e5e7eb" />
                <XAxis
                  dataKey={xKey}
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 12, fill: "#6b7280" }}
                  dy={10}
                />
                <YAxis
                  axisLine={false}
                  tickLine={false}
                  tick={{ fontSize: 12, fill: "#6b7280" }}
                  dx={-10}
                />
                <RechartsTooltip
                  contentStyle={{
                    borderRadius: "8px",
                    border: "none",
                    boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
                  }}
                  cursor={{ fill: "#f3f4f6" }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: "12px", paddingTop: "20px" }} />
                {yKeys.map((key, i) => (
                  <Bar
                    key={key}
                    dataKey={key}
                    fill={chartColors[i % chartColors.length]}
                    radius={[4, 4, 0, 0]}
                    maxBarSize={50}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

function VersionHistoryContent({ previous, current }: { previous: string; current: string }) {
  if (!previous) {
    return <mark className="rounded-sm bg-amber-200/80 px-0.5 text-amber-950">{current}</mark>;
  }

  const comparisonBase = previous.slice(0, Math.max(current.length, 650));
  return (
    <>
      {diffWords(comparisonBase, current).map((part, index) => {
        if (part.removed) return null;
        if (part.added) {
          return (
            <mark
              key={index}
              className="rounded-sm bg-amber-300 px-0.5 text-amber-950"
              title="Edited text"
            >
              {part.value}
            </mark>
          );
        }
        return <React.Fragment key={index}>{part.value}</React.Fragment>;
      })}
    </>
  );
}

function DiffViewer({
  original,
  current,
  primaryColor,
  secondaryColor,
  documents,
}: {
  original: string;
  current: string;
  primaryColor?: string;
  secondaryColor?: string;
  documents?: DealDocument[];
}) {
  const diffs = diffWords(original, current);

  const htmlContent = diffs
    .map((part) => {
      if (part.added) {
        return `<mark class="bg-emerald-200/70 text-emerald-900 px-0.5 rounded-sm">${part.value}</mark>`;
      }
      if (part.removed) {
        return `<del class="bg-red-200/70 text-red-900 px-0.5 rounded-sm decoration-red-900/50">${part.value}</del>`;
      }
      return part.value;
    })
    .join("");

  return (
    <MarkdownRenderer
      content={htmlContent}
      primaryColor={primaryColor}
      secondaryColor={secondaryColor}
      documents={documents}
    />
  );
}

function MarkdownRenderer({
  content,
  primaryColor,
  secondaryColor,
  documents,
}: {
  content: string;
  primaryColor?: string;
  secondaryColor?: string;
  documents?: DealDocument[];
}) {
  // Lazy import react-markdown
  const [ReactMarkdown, setReactMarkdown] = useState<any>(null);
  const [remarkGfm, setRemarkGfm] = useState<any>(null);

  useEffect(() => {
    Promise.all([import("react-markdown"), import("remark-gfm")]).then(
      ([md, gfm]) => {
        setReactMarkdown(() => md.default);
        setRemarkGfm(() => gfm.default);
      },
    );
  }, []);

  let processedContent = content;
  if (documents && documents.length > 0) {
    processedContent = processedContent.replace(/\[\[(.*?)\]\]/g, (match, filename) => {
      const doc = documents.find((d) => d.filename === filename);
      if (doc && doc.url) {
        return `[${filename}](${doc.url})`;
      }
      return match;
    });
  }

  if (!ReactMarkdown) {
    // Fallback: show pre-formatted text while markdown loads
    return <div className="whitespace-pre-wrap text-sm leading-relaxed">{processedContent}</div>;
  }

  return (
    <ReactMarkdown
      remarkPlugins={remarkGfm ? [remarkGfm] : []}
      skipHtml
      components={{
        table: (props: any) => (
          <CustomTable {...props} primaryColor={primaryColor} secondaryColor={secondaryColor} />
        ),
        a: (props: any) => (
          <a
            {...props}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 underline hover:text-blue-800 font-medium transition-colors"
          />
        ),
        h1: (props: any) => (
          <h1 {...props} className="text-2xl font-bold mt-6 mb-3 text-slate-900 tracking-tight" />
        ),
        h2: (props: any) => (
          <h2 {...props} className="text-xl font-bold mt-5 mb-3 text-slate-800 tracking-tight" />
        ),
        h3: (props: any) => (
          <h3 {...props} className="text-lg font-semibold mt-5 mb-2 text-slate-800" />
        ),
        h4: (props: any) => (
          <h4 {...props} className="text-base font-semibold mt-4 mb-2 text-slate-800" />
        ),
        p: (props: any) => <p {...props} className="text-sm text-slate-600 mb-3 leading-relaxed" />,
        ul: (props: any) => (
          <ul
            {...props}
            className="list-disc pl-5 mb-4 space-y-1.5 text-sm text-slate-600 marker:text-slate-400"
          />
        ),
        ol: (props: any) => (
          <ol
            {...props}
            className="list-decimal pl-5 mb-4 space-y-1.5 text-sm text-slate-600 marker:text-slate-400"
          />
        ),
        li: (props: any) => <li {...props} className="leading-relaxed" />,
        strong: (props: any) => <strong {...props} className="font-semibold text-slate-800" />,
        blockquote: (props: any) => (
          <blockquote
            {...props}
            className="border-l-4 border-slate-200 pl-4 py-1 my-4 italic text-slate-600 bg-slate-50 rounded-r-md"
          />
        ),
        code: (props: any) => (
          <code
            {...props}
            className="bg-slate-100 text-pink-600 px-1.5 py-0.5 rounded text-xs font-mono"
          />
        ),
        pre: (props: any) => (
          <pre
            {...props}
            className="bg-slate-900 text-slate-50 p-4 rounded-lg overflow-x-auto mb-4 text-sm font-mono shadow-sm"
          />
        ),
        thead: (props: any) => (
          <thead {...props} className="bg-slate-100/80 border-b border-slate-200" />
        ),
        tbody: (props: any) => <tbody {...props} className="divide-y divide-slate-100 bg-white" />,
        tr: (props: any) => <tr {...props} className="hover:bg-slate-50/80 transition-colors" />,
        th: (props: any) => (
          <th
            {...props}
            className="px-4 py-3 text-left text-xs font-semibold text-slate-700 uppercase tracking-wider"
          />
        ),
        td: (props: any) => (
          <td {...props} className="px-4 py-3 text-sm text-slate-600 align-top" />
        ),
      }}
    >
      {processedContent}
    </ReactMarkdown>
  );
}

/* ── Versions Tab ───────────────────────────────────────────── */

function VersionsTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const { user } = useAuth();
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [reviewComments, setReviewComments] = useState<Record<string, string>>({});
  const [reviewingVersionId, setReviewingVersionId] = useState<string | null>(null);
  const [downloadingVersionId, setDownloadingVersionId] = useState<string | null>(null);
  const ready = deal.sections.filter((s) => !s.optional && s.state === "ready").length;
  const total = deal.sections.filter((s) => !s.optional).length;
  const pending = deal.sections.filter((s) => !s.optional && s.state === "pending");

  const submit = async () => {
    if (submitting) return;
    if (!validateTextInput("Reviewer notes", notes, 4000)) return;
    setSubmitting(true);
    try {
      await api.versions.submit(deal.id, notes);
      setNotes("");
      refresh();
    } catch (err) {
      console.error("Submit failed:", err);
    } finally {
      setSubmitting(false);
    }
  };

  const approve = async (versionId: string) => {
    if (reviewingVersionId) return;
    if (!validateTextInput("Review comments", reviewComments[versionId] || "", 4000)) return;
    setReviewingVersionId(versionId);
    try {
      await api.versions.approve(deal.id, versionId, reviewComments[versionId] || "");
      refresh();
    } catch (err) {
      console.error("Approve failed:", err);
      alert(err instanceof Error ? err.message : "Approval failed.");
    } finally {
      setReviewingVersionId(null);
    }
  };

  const deny = async (versionId: string) => {
    const comments = (reviewComments[versionId] || "").trim();
    if (!validateTextInput("Review comments", comments, 4000)) return;
    if (!comments) {
      alert("Enter review comments before denying this version.");
      return;
    }
    if (reviewingVersionId) return;
    setReviewingVersionId(versionId);
    try {
      await api.versions.deny(deal.id, versionId, comments);
      refresh();
    } catch (err) {
      console.error("Deny failed:", err);
      alert(err instanceof Error ? err.message : "Denial failed.");
    } finally {
      setReviewingVersionId(null);
    }
  };

  const download = async (versionId: string) => {
    if (downloadingVersionId) return;
    setDownloadingVersionId(versionId);
    try {
      await api.versions.download(deal.id, versionId);
    } catch (err) {
      console.error("Version download failed:", err);
      alert(err instanceof Error ? err.message : "Version download failed.");
    } finally {
      setDownloadingVersionId(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="doc-card">
        <div className="doc-section-header">
          <span>Validation Summary</span>
        </div>
        <div className="p-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <div className="text-sm">
                Mandatory sections ready{" "}
                <span className="ml-2 font-mono text-muted-foreground">
                  {ready}/{total}
                </span>
              </div>
              <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary"
                  style={{ width: `${total > 0 ? (ready / total) * 100 : 0}%` }}
                />
              </div>
            </div>
            <div>
              <div className="text-sm">Approved version</div>
              <div
                className={`mt-1 inline-block rounded-full px-3 py-0.5 text-xs font-semibold ${
                  deal.versions.some((v) => v.status === "approved")
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {deal.versions.some((v) => v.status === "approved") ? "Yes" : "No"}
              </div>
            </div>
            <div>
              <div className="text-sm">Total versions</div>
              <div className="mt-1 inline-block rounded-full bg-muted px-3 py-0.5 text-xs font-semibold text-muted-foreground">
                {deal.versions.length}
              </div>
            </div>
          </div>
          {pending.length > 0 && (
            <div className="mt-4 rounded-md border bg-surface p-3">
              <div className="text-xs font-semibold text-muted-foreground">
                Pending mandatory sections:
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {pending.map((s) => (
                  <span
                    key={s.id}
                    className="rounded-full border border-warning/40 bg-warning/15 px-2 py-0.5 text-[11px] font-medium text-warning-foreground"
                  >
                    {s.title}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {user?.role === "relationship_manager" && (
        <div className="doc-card">
          <div className="doc-section-header">
            <span>Submit for Review</span>
          </div>
          <div className="space-y-3 p-4">
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Reviewer notes (optional)"
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <button
              onClick={submit}
              disabled={submitting}
              className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60"
            >
              {submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FileText className="h-4 w-4" />
              )}
              {submitting ? "Submitting…" : "Submit version for review"}
            </button>
          </div>
        </div>
      )}

      <div className="doc-card">
        <div className="doc-section-header">
          <Clock className="h-4 w-4 shrink-0" />
          <span>Versions ({deal.versions.length})</span>
        </div>
        {deal.versions.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            {user?.role === "relationship_manager"
              ? "No versions yet. Submit the draft for review above."
              : "No versions have been submitted for review."}
          </div>
        ) : (
          <ul className="divide-y">
            {deal.versions.map((v) => (
              <li key={v.id} className="p-4 text-sm">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{v.id}</span>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${
                          v.status === "approved"
                            ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                            : v.status === "denied"
                              ? "border-red-300 bg-red-50 text-red-700"
                              : "border-border bg-muted text-muted-foreground"
                        }`}
                      >
                        {v.status}
                      </span>
                    </div>
                    <div className="text-xs text-muted-foreground">{v.notes || "—"}</div>
                  </div>
                  <div className="flex items-center gap-3">
                    <div className="text-xs text-muted-foreground">
                      {new Date(v.created_at).toLocaleString()}
                    </div>
                    <button
                      type="button"
                      onClick={() => download(v.id)}
                      disabled={downloadingVersionId !== null}
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md border bg-background text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
                      title={`Download ${v.id} as PDF`}
                      aria-label={`Download ${v.id} as PDF`}
                    >
                      {downloadingVersionId === v.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>
                {v.review_comments && (
                  <div
                    className={`mt-3 rounded-md border p-3 ${v.status === "denied" ? "border-red-200 bg-red-50" : "border-emerald-200 bg-emerald-50"}`}
                  >
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Credit Analyst comments
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-sm">{v.review_comments}</p>
                    <div className="mt-2 text-[10px] text-muted-foreground">
                      Reviewed by {v.reviewed_by || "Credit Analyst"}
                      {v.reviewed_at ? ` on ${new Date(v.reviewed_at).toLocaleString()}` : ""}
                    </div>
                  </div>
                )}
                {v.status === "submitted" && user?.role === "credit_analyst" && (
                  <div className="mt-3 rounded-md border bg-surface p-3">
                    <label className="text-xs font-semibold">Review comments</label>
                    <textarea
                      value={reviewComments[v.id] || ""}
                      onChange={(event) =>
                        setReviewComments((current) => ({ ...current, [v.id]: event.target.value }))
                      }
                      maxLength={4000}
                      rows={3}
                      placeholder="Add comments for the Relationship Manager. Comments are required when denying."
                      className="mt-1.5 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-1 focus:ring-ring"
                    />
                    <div className="mt-2 flex justify-end gap-2">
                      <button
                        onClick={() => deny(v.id)}
                        disabled={reviewingVersionId !== null}
                        className="inline-flex h-8 items-center gap-1.5 rounded-md bg-red-600 px-3 text-xs font-medium text-white hover:bg-red-700 disabled:opacity-50"
                      >
                        <X className="h-3.5 w-3.5" /> Deny
                      </button>
                      <button
                        onClick={() => approve(v.id)}
                        disabled={reviewingVersionId !== null}
                        className="inline-flex h-8 items-center gap-1.5 rounded-md bg-emerald-600 px-3 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                      >
                        <CheckCircle2 className="h-3.5 w-3.5" /> Approve
                      </button>
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

/* ── Export Tab ──────────────────────────────────────────────── */

function ExportTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const ready = deal.sections.filter((s) => !s.optional && s.state === "ready").length;
  const total = deal.sections.filter((s) => !s.optional).length;
  const pending = total - ready;
  const [exporting, setExporting] = useState<string | null>(null);
  const [generatingReport, setGeneratingReport] = useState(false);

  const handleExport = async (format: string) => {
    setExporting(format);
    try {
      await api.exports.download(deal.id, format);
      refresh();
    } catch (err) {
      console.error(`Export ${format} failed:`, err);
      alert(err instanceof Error ? err.message : `Export ${format.toUpperCase()} failed.`);
    } finally {
      setExporting(null);
    }
  };

  const handleGenerateReport = async () => {
    setGeneratingReport(true);
    try {
      await api.exports.generateReport(deal.id);
      refresh();
    } catch (err) {
      console.error("Report generation failed:", err);
      alert(err instanceof Error ? err.message : "Report generation failed.");
    } finally {
      setGeneratingReport(false);
    }
  };

  const [extractingTheme, setExtractingTheme] = useState(false);

  const handleExtractTheme = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setExtractingTheme(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch(`/api/deals/${deal.id}/theme/extract`, {
        method: "POST",
        // CSRF mitigation is enforced server-side with same-origin validation.
        credentials: "same-origin",
        body: formData,
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Theme extraction failed.");
      refresh();
    } catch (err) {
      console.error("Theme extraction failed:", err);
      alert("Failed to extract theme. Try a different file.");
    } finally {
      setExtractingTheme(false);
      e.target.value = "";
    }
  };

  const handlePaletteChange = async (index: number, value: string) => {
    try {
      const currentPalette = deal.theme_palette || [
        "#002060",
        "#800020",
        "#1e293b",
        "#3b82f6",
        "#f59e0b",
      ];
      const newPalette = [...currentPalette];
      newPalette[index] = value;

      const payload: any = {
        theme_palette: JSON.stringify(newPalette),
      };

      // Keep primary/secondary in sync with first two colors
      if (index === 0) payload.primary_color = value;
      if (index === 1) payload.secondary_color = value;

      const res = await fetch(`/api/deals/${deal.id}`, {
        method: "PATCH",
        // CSRF mitigation is enforced server-side with same-origin validation.
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Palette update failed.");
      refresh();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-4">
      <div className="doc-card">
        <div className="doc-section-header">
          <Sparkles className="h-4 w-4 shrink-0 text-primary" />
          <span>Brand &amp; Theme Extraction</span>
        </div>
        <div className="p-5">
          <p className="mb-4 text-sm text-muted-foreground">
            Upload an Annual Report or corporate presentation to let the AI automatically extract
            the company's brand colors. Or, manually set your preferred hex codes.
          </p>
          <div className="flex flex-wrap items-center gap-6">
            <div>
              <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Extract Theme
              </label>
              <label className="btn-primary inline-flex cursor-pointer items-center gap-2">
                {extractingTheme ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                {extractingTheme ? "Extracting..." : "Upload Document"}
                <input
                  type="file"
                  className="hidden"
                  accept=".pdf,.txt"
                  onChange={handleExtractTheme}
                  disabled={extractingTheme}
                />
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-4">
              {(deal.theme_palette || ["#002060", "#800020", "#1e293b", "#3b82f6", "#f59e0b"]).map(
                (color, idx) => (
                  <div key={idx}>
                    <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                      {idx === 0 ? "Primary" : idx === 1 ? "Secondary" : `Color ${idx + 1}`}
                    </label>
                    <div className="flex items-center gap-2 rounded-md border p-1 shadow-sm">
                      <input
                        type="color"
                        value={color}
                        onChange={(e) => handlePaletteChange(idx, e.target.value)}
                        className="h-8 w-8 cursor-pointer rounded border-none p-0 outline-none"
                      />
                      <span className="font-mono text-xs font-medium w-16 text-center">
                        {color}
                      </span>
                    </div>
                  </div>
                ),
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Generate Combined Report */}
      <div className="doc-card">
        <div className="doc-section-header">
          <BookOpenCheck className="h-4 w-4 shrink-0" />
          <span>Generate Combined Report</span>
        </div>
        <div className="p-5">
          <p className="text-sm text-muted-foreground mb-4">
            Generate a comprehensive PDF report combining all section narratives into a single
            credit pitch book document.
          </p>
          <button
            onClick={handleGenerateReport}
            disabled={generatingReport}
            className="inline-flex h-10 items-center gap-2 rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-60"
          >
            {generatingReport ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <FileDown className="h-4 w-4" />
            )}
            {generatingReport ? "Generating report…" : "Generate Report (PDF)"}
          </button>
        </div>
      </div>

      <div className="doc-card">
        <div className="doc-section-header">
          <Download className="h-4 w-4 shrink-0" />
          <span>Export Pitch Book</span>
        </div>
        <div className="space-y-4 p-5">
          <div className="grid gap-3 sm:grid-cols-3">
            {["pptx", "pdf", "docx"].map((fmt) => (
              <button
                key={fmt}
                onClick={() => handleExport(fmt)}
                disabled={exporting !== null}
                className="flex items-start gap-3 rounded-md border bg-card p-4 text-left hover:bg-surface disabled:opacity-60"
              >
                {exporting === fmt ? (
                  <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
                ) : (
                  <FileText className="h-5 w-5 text-muted-foreground" />
                )}
                <div>
                  <div className="font-medium">Export as {fmt.toUpperCase()}</div>
                  <div className="text-xs text-muted-foreground">Download pitch book</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Documents Tab ───────────────────────────────────────────── */

function DocumentsTab({ deal, refresh }: { deal: Deal; refresh: () => void }) {
  const [showLibUpload, setShowLibUpload] = useState(false);
  const [libUploadType, setLibUploadType] = useState<"file" | "url" | "text">("file");
  const [libUploading, setLibUploading] = useState(false);
  const [libUploadNote, setLibUploadNote] = useState("");
  const [libUrlInput, setLibUrlInput] = useState("");
  const [libTextInput, setLibTextInput] = useState("");
  const [libSelectedFileName, setLibSelectedFileName] = useState("");
  const [triggeringSync, setTriggeringSync] = useState(false);

  // Poll for updates if sync is in progress
  useEffect(() => {
    if (deal.library_sync_status !== "syncing") return;
    const interval = setInterval(() => {
      refresh();
    }, 3000);
    return () => clearInterval(interval);
  }, [deal.library_sync_status, refresh]);

  const handleTriggerSync = async () => {
    if (triggeringSync) return;
    setTriggeringSync(true);
    try {
      await api.library.triggerSync(deal.id);
      refresh();
    } catch (err) {
      console.error("Failed to trigger sync:", err);
    } finally {
      setTriggeringSync(false);
    }
  };

  const handleLibUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (libUploading) return;
    setLibUploading(true);
    try {
      const formData = new FormData();
      formData.append("source_type", libUploadType);
      if (libUploadNote) formData.append("note", libUploadNote);

      if (libUploadType === "file") {
        const fileInput = document.getElementById("lib-file-input") as HTMLInputElement;
        if (!fileInput?.files?.[0]) return;
        formData.append("file", fileInput.files[0]);
      } else if (libUploadType === "url") {
        formData.append("url", libUrlInput);
      } else {
        formData.append("text_content", libTextInput);
      }

      await api.library.upload(deal.id, formData);

      setLibUploadNote("");
      setLibUrlInput("");
      setLibTextInput("");
      setLibSelectedFileName("");
      setShowLibUpload(false);
      refresh();
    } catch (err) {
      console.error("Library upload failed:", err);
    } finally {
      setLibUploading(false);
    }
  };

  const handleDeleteLibFile = async (fileId: string) => {
    try {
      await api.library.delete(deal.id, fileId);
      refresh();
    } catch (err) {
      console.error("Delete library file failed:", err);
    }
  };

  const libDocCount = deal.library_files?.length || 0;
  const latestSyncLogs = Array.from(
    (deal.sync_logs || []).reduce((latestByDocument, log) => {
      const current = latestByDocument.get(log.doc_title);
      if (
        !current ||
        new Date(log.created_at).getTime() >= new Date(current.created_at).getTime()
      ) {
        latestByDocument.set(log.doc_title, log);
      }
      return latestByDocument;
    }, new Map<string, Deal["sync_logs"][number]>()),
  ).map(([, log]) => log);

  // Try to find matching library files for MCP docs to show status
  const getMcpDocStatus = (filename: string) => {
    return deal.library_files?.some((f) => f.filename === filename || f.note?.includes(filename))
      ? "In Library"
      : "Available";
  };

  return (
    <div className="space-y-6">
      {/* ── Auto-Fetched from MCP (Timeline) ── */}
      <div className="doc-card">
        <div className="doc-section-header justify-between">
          <div className="flex items-center gap-2">
            <Library className="h-4 w-4 shrink-0" />
            <span>Company Source Library</span>
            {deal.company_document_count > 0 && (
              <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-bold text-emerald-700">
                {deal.company_document_count} documents
              </span>
            )}
          </div>
          <button
            onClick={handleTriggerSync}
            disabled={triggeringSync || deal.library_sync_status === "syncing"}
            className="inline-flex h-6 items-center gap-1.5 rounded bg-primary/10 px-2 text-[11px] font-medium text-primary hover:bg-primary/20 disabled:opacity-50 transition-colors"
          >
            {triggeringSync || deal.library_sync_status === "syncing" ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              <RefreshCw className="h-3 w-3" />
            )}
            {deal.library_sync_status === "syncing" ? "Refreshing..." : "Refresh"}
          </button>
        </div>
        <div className="p-4">
          <p className="text-sm text-muted-foreground mb-4">
            Documents for <strong>{deal.customer}</strong> are read directly from the existing
            Mistral Library. No files are downloaded or uploaded again.
          </p>

          {latestSyncLogs.length > 0 ? (
            <div className="space-y-3">
              {latestSyncLogs.map((log) => {
                let statusConfig = {
                  icon: "⏳",
                  color: "text-slate-500",
                  bg: "bg-slate-100",
                  label: "Queued",
                };
                if (log.status === "downloading")
                  statusConfig = {
                    icon: "⬇️",
                    color: "text-blue-600",
                    bg: "bg-blue-50",
                    label: "Downloading from MCP...",
                  };
                if (log.status === "uploading")
                  statusConfig = {
                    icon: "⬆️",
                    color: "text-indigo-600",
                    bg: "bg-indigo-50",
                    label: "Uploading to Mistral Library...",
                  };
                if (log.status === "completed")
                  statusConfig = {
                    icon: "✅",
                    color: "text-emerald-600",
                    bg: "bg-emerald-50",
                    label: "Completed",
                  };
                if (log.status === "linked")
                  statusConfig = {
                    icon: "✅",
                    color: "text-emerald-600",
                    bg: "bg-emerald-50",
                    label: "Referenced directly",
                  };
                if (log.status === "removed")
                  statusConfig = {
                    icon: "➖",
                    color: "text-slate-500",
                    bg: "bg-slate-50",
                    label: "No longer available",
                  };
                if (log.status === "failed")
                  statusConfig = {
                    icon: "❌",
                    color: "text-red-600",
                    bg: "bg-red-50",
                    label: "Failed",
                  };

                return (
                  <div
                    key={log.id}
                    className={`flex items-start gap-3 rounded-lg border p-3 transition-colors ${statusConfig.bg}`}
                  >
                    <div className="flex items-center justify-center h-6 w-6 rounded-full bg-white shadow-sm shrink-0 mt-0.5 text-xs">
                      {statusConfig.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-4">
                        <div className="text-sm font-semibold truncate">{log.doc_title}</div>
                        <div
                          className={`text-[10px] font-bold uppercase tracking-wider ${statusConfig.color} shrink-0`}
                        >
                          {statusConfig.label}
                        </div>
                      </div>
                      <div className="text-[10px] text-muted-foreground flex items-center gap-3 mt-1">
                        {log.file_size && <span>{(log.file_size / 1024).toFixed(0)} KB</span>}
                        <span>Queued: {new Date(log.created_at).toLocaleTimeString()}</span>
                        {log.completed_at && (
                          <span>Finished: {new Date(log.completed_at).toLocaleTimeString()}</span>
                        )}
                      </div>
                      {log.error && (
                        <div className="text-xs text-red-600 mt-2 bg-red-100/50 p-2 rounded border border-red-200">
                          {log.error}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-sm text-muted-foreground bg-muted/30 p-6 rounded-lg text-center border border-dashed">
              <Library className="h-8 w-8 mx-auto mb-2 text-muted-foreground/40" />
              <div>No company documents are currently linked for {deal.customer}.</div>
              <div className="text-[10px] mt-1">
                Click "Refresh" to check the registered Mistral Library.
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Manual Upload & Deal Library ── */}
      <div className="doc-card">
        <div className="doc-section-header justify-between">
          <span className="flex items-center gap-2">
            <Library className="h-4 w-4 shrink-0" />
            Deal-Specific Uploads
            {libDocCount > 0 && (
              <span className="rounded-full bg-blue-500/20 text-blue-700 px-2 py-0.5 text-[10px] font-bold">
                {libDocCount} file{libDocCount !== 1 ? "s" : ""}
              </span>
            )}
          </span>
          <button
            onClick={() => setShowLibUpload(!showLibUpload)}
            className={`inline-flex h-7 items-center gap-1.5 rounded-md border px-2.5 text-[11px] font-medium transition-colors ${
              showLibUpload
                ? "border-red-300/50 bg-red-500/20 text-white hover:bg-red-500/30"
                : "border-primary-foreground/30 bg-primary-foreground/15 text-primary-foreground hover:bg-primary-foreground/25"
            }`}
          >
            {showLibUpload ? <X className="h-3 w-3" /> : <Plus className="h-3 w-3" />}
            {showLibUpload ? "Cancel" : "Add Document"}
          </button>
        </div>

        <div className="px-4 py-2 bg-blue-50/50 border-b border-blue-100/50 flex items-center gap-2">
          <Info className="h-3.5 w-3.5 text-blue-500 shrink-0" />
          <span className="text-[10px] text-blue-700">
            Add only documents specific to this deal. AI generation searches these uploads together
            with the shared company source library.
          </span>
        </div>

        {showLibUpload && (
          <div className="p-4 bg-surface/50 border-b space-y-3">
            <form onSubmit={handleLibUpload} className="space-y-3">
              <div className="flex gap-1 rounded-lg bg-muted p-0.5">
                {[
                  { type: "file" as const, label: "File", Icon: FileIcon },
                  { type: "url" as const, label: "URL", Icon: LinkIcon },
                  { type: "text" as const, label: "Text", Icon: Type },
                ].map(({ type, label, Icon }) => (
                  <button
                    key={type}
                    type="button"
                    onClick={() => setLibUploadType(type)}
                    className={`flex-1 inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                      libUploadType === type
                        ? "bg-background text-foreground shadow-sm"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <Icon className="h-3 w-3" /> {label}
                  </button>
                ))}
              </div>

              {libUploadType === "file" && (
                <div className="relative rounded-lg border-2 border-dashed border-muted-foreground/30 bg-muted/20 p-6 text-center hover:bg-muted/40 hover:border-primary/40 transition-colors cursor-pointer">
                  <input
                    type="file"
                    id="lib-file-input"
                    className="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10"
                    accept=".pdf,.docx,.doc,.xlsx,.xls,.pptx,.csv,.txt,.md,.json"
                    onChange={(e) => setLibSelectedFileName(e.target.files?.[0]?.name || "")}
                  />
                  <FileIcon
                    className={`h-8 w-8 mx-auto mb-3 ${libSelectedFileName ? "text-primary" : "text-muted-foreground/60"}`}
                  />
                  {libSelectedFileName ? (
                    <div className="text-sm font-semibold text-primary break-all px-4">
                      {libSelectedFileName}
                    </div>
                  ) : (
                    <>
                      <div className="text-sm font-medium text-foreground mb-1">
                        Click to browse or drag and drop
                      </div>
                      <div className="text-[10px] text-muted-foreground">
                        PDF, DOCX, XLSX, PPTX, CSV, TXT, MD
                      </div>
                    </>
                  )}
                </div>
              )}
              {libUploadType === "url" && (
                <input
                  placeholder="https://example.com/document.pdf"
                  value={libUrlInput}
                  onChange={(e) => setLibUrlInput(e.target.value)}
                  className="w-full h-9 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              )}
              {libUploadType === "text" && (
                <textarea
                  placeholder="Paste document content here…"
                  value={libTextInput}
                  onChange={(e) => setLibTextInput(e.target.value)}
                  rows={4}
                  className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
              )}

              <div className="flex gap-2">
                <input
                  placeholder="Note (optional)"
                  value={libUploadNote}
                  onChange={(e) => setLibUploadNote(e.target.value)}
                  className="flex-1 h-9 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                />
                <button
                  type="submit"
                  disabled={libUploading}
                  className="inline-flex h-9 items-center gap-1.5 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-60 transition-colors"
                >
                  {libUploading ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Upload className="h-3.5 w-3.5" />
                  )}
                  Upload to Library
                </button>
              </div>
            </form>
          </div>
        )}

        {libDocCount > 0 ? (
          <ul className="divide-y">
            {deal.library_files.map((lf) => {
              const typeConfig: Record<string, { color: string; icon: string }> = {
                file: { color: "bg-blue-100 text-blue-700 border-blue-200", icon: "📄" },
                url: { color: "bg-green-100 text-green-700 border-green-200", icon: "🔗" },
                text: { color: "bg-orange-100 text-orange-700 border-orange-200", icon: "📝" },
                mcp_auto: {
                  color: "bg-emerald-100 text-emerald-700 border-emerald-200",
                  icon: "🤖",
                },
              };
              const cfg = typeConfig[lf.source_type] || typeConfig.file;
              const sizeStr = lf.file_size ? `${(lf.file_size / 1024).toFixed(0)} KB` : "";

              return (
                <li
                  key={lf.id}
                  className="flex items-center justify-between px-4 py-2.5 hover:bg-surface/50 transition-colors group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span
                      className={`rounded-md border px-1.5 py-0.5 text-[9px] font-bold uppercase shrink-0 ${cfg.color}`}
                    >
                      {cfg.icon} {lf.source_type === "mcp_auto" ? "MCP" : lf.source_type}
                    </span>
                    <div className="min-w-0">
                      <div className="text-xs font-medium truncate">{lf.filename}</div>
                      <div className="text-[10px] text-muted-foreground flex gap-2 items-center">
                        <span className="text-emerald-600 font-semibold">⚡ Mistral Library</span>
                        {sizeStr && <span>{sizeStr}</span>}
                        {lf.note && <span className="truncate max-w-[150px]">• {lf.note}</span>}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => handleDeleteLibFile(lf.id)}
                    className="rounded-md p-1.5 text-muted-foreground opacity-0 group-hover:opacity-100 hover:bg-destructive/10 hover:text-destructive transition-all"
                    title="Remove from library"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        ) : !showLibUpload ? (
          <div className="px-4 py-6 text-center">
            <Library className="h-6 w-6 mx-auto mb-2 text-muted-foreground/40" />
            <div className="text-xs text-muted-foreground">No documents in the library yet.</div>
            <div className="text-[10px] text-muted-foreground/60 mt-1">
              Upload files to enable AI agents to use real data for grounding.
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
