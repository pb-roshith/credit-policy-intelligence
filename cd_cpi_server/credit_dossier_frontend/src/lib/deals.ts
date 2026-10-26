/**
 * API client for Credit Dossier backend.
 * Supports Mistral Library + Agents architecture.
 */

import { apiErrorFromResponse } from "@/lib/api-error";

const API_BASE = "/api";

// ── Types ──────────────────────────────────────────────────────

export type Status =
  | "Draft"
  | "In Progress"
  | "In Review"
  | "Changes Requested"
  | "Approved"
  | "Exported";
export type DealType = "Existing" | "New-to-bank";

export type UploadBrief = {
  id: string;
  source_type: string;
  filename: string | null;
  url: string | null;
  note: string | null;
  created_at: string;
};

export type DealDocument = {
  id: string;
  source_type: string;
  filename: string | null;
  url: string | null;
  note: string | null;
  extraction_method: string | null;
  page_count: number | null;
  created_at: string;
};

export type SectionDocumentLink = {
  id: string;
  document: DealDocument;
  created_at: string;
};

export type LibraryFile = {
  id: string;
  mistral_file_id: string;
  filename: string;
  source_type: string;
  file_size: number | null;
  note: string | null;
  created_at: string;
};

export type LibrarySyncLog = {
  id: string;
  doc_title: string;
  doc_url: string | null;
  status: "queued" | "downloading" | "uploading" | "completed" | "failed" | "linked" | "removed";
  error: string | null;
  file_size: number | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
};

export type Section = {
  id: string;
  section_key: string;
  title: string;
  description: string;
  sources: string;
  expected_output: string;
  optional: boolean;
  state: "pending" | "ready";
  order_index: number;
  generated_content: string | null;
  original_generated_content: string | null;
  custom_instructions: string | null;
  accuracy_score: number | null;
  accuracy_details: {
    score: number;
    grounded_claims: number;
    inferred_claims: number;
    unsupported_claims: number;
    summary: string;
  } | null;
  output_template: string | null;
  template_file_path: string | null;
  orchestration_strategy?: string | null;
  timing?: {
    orchestration_ms: number;
    generation_ms: number;
    accuracy_ms: number;
    total_ms: number;
  } | null;
  moderation_status: "safe" | "flagged" | null;
  moderation_details: {
    is_safe: boolean;
    flagged_categories: string[];
    details: Record<string, unknown>;
  } | null;
  observability_details: {
    moderation?: AgentMetrics;
    orchestration?: AgentMetrics;
    section_agent?: AgentMetrics;
    judge?: AgentMetrics;
    claim_evaluator?: AgentMetrics;
  } | null;
  source_urls: string[];
  url_scrape_details: Array<{
    url: string;
    final_url: string | null;
    title: string;
    status: "completed" | "failed";
    characters: number;
    error: string | null;
  }> | null;
  uploads: UploadBrief[]; // Legacy
  document_links: SectionDocumentLink[]; // Legacy
};

export type AuditEntry = {
  id: string;
  action: string;
  subject: string;
  user: string;
  created_at: string;
};

export type Version = {
  id: string;
  notes: string;
  status: string;
  review_comments: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
};

export type Deal = {
  id: string;
  customer: string;
  customer_type: DealType;
  industry: string;
  segment: string;
  geography: string;
  city: string;
  sector: string;
  kyc: "verified" | "pending";
  facility: string;
  currency: string;
  amount: number;
  tenure: number;
  pricing: string;
  repayment: string;
  collateral: boolean;
  due: string;
  owner: string;
  status: Status;
  library_sync_status: "not_started" | "syncing" | "ready" | "partial" | "error";
  mistral_library_id: string | null;
  company_mistral_library_id: string | null;
  company_document_count: number;
  created_at: string;
  updated_at: string;
  primary_color: string;
  secondary_color: string;
  theme_palette: string[];

  sections: Section[];
  documents: DealDocument[];
  library_files: LibraryFile[];
  sync_logs: LibrarySyncLog[];
  audit_entries: AuditEntry[];
  versions: Version[];
};

export type DealListItem = Omit<
  Deal,
  "sections" | "audit_entries" | "versions" | "documents" | "library_files" | "sync_logs"
> & {
  sections_ready: number;
  sections_total: number;
  versions_count: number;
};

export type DealCreate = {
  customer: string;
  customer_type?: string;
  industry?: string;
  segment?: string;
  geography?: string;
  kyc?: string;
  facility?: string;
  currency?: string;
  amount?: number;
  tenure?: number;
  pricing?: string;
  repayment?: string;
  collateral?: boolean;
  due?: string;
};

export type NarrativeResponse = {
  section_id: string;
  section_key: string;
  title: string;
  generated_content: string;
  state: string;
  accuracy_score: number | null;
  accuracy_details: {
    score: number;
    grounded_claims: number;
    inferred_claims: number;
    unsupported_claims: number;
    summary: string;
  } | null;
};

export type DraftAllResponse = {
  results: NarrativeResponse[];
  total: number;
  succeeded: number;
  failed: number;
};

export type AgentMetrics = {
  name: string;
  model: string;
  status: string;
  latency_ms: number | null;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  token_usage_available?: boolean;
};

export type DraftSectionProgress = {
  section_id: string;
  title: string;
  status: "queued" | "waiting" | "running" | "completed" | "failed";
  stage: string;
};

export type DraftAllJob = {
  job_id: string;
  deal_id: string;
  status: "queued" | "running" | "completed" | "failed";
  percent: number;
  completed: number;
  failed: number;
  total: number;
  sections: DraftSectionProgress[];
  error: string | null;
};

export type NarrativeVersion = {
  id: string;
  deal_id: string;
  section_id: string;
  content: string;
  version_type: "generated" | "edited";
  parent_version_id: string | null;
  created_by: string;
  is_final: boolean;
  created_at: string;
};

export type ManufactureResult = {
  companyName: string;
  industry: string;
  geography: string;
  databaseName: string;
  mcpUrl: string;
  pdfCount: number;
  generatedPdfCount: number;
  uploadedPdfCount: number;
  tableCount: number;
  seededRowCount: number;
  mistralLibraryId: string | null;
  uploadError: string | null;
  generatorVersion: number;
  aiDetailedGeneration: boolean;
  syntheticData: boolean;
};

export type ManufactureJob = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  percent: number;
  stage: string;
  result: ManufactureResult | null;
  error: string | null;
  phase: string;
  generated_pdfs: string[];
  uploaded_pdfs: string[];
  completed_tables: string[];
  pdf_total: number;
  table_total: number;
};

export type NarrativeEditLock = {
  section_id: string;
  locked_by: string;
  expires_at: string;
};

// ── Fetch helpers ──────────────────────────────────────────────

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers as Record<string, string>),
    },
    ...options,
  });
  if (!res.ok) {
    if (res.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new Event("auth:unauthorized"));
    }
    throw await apiErrorFromResponse(res);
  }
  // Handle 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── API Methods ────────────────────────────────────────────────

export const api = {
  // Health
  health: () => request<{ status: string }>(`${API_BASE}/health`),

  // Deals
  deals: {
    list: (params?: { status?: string; search?: string }) => {
      const filters = {
        status: params?.status && params.status !== "all" ? params.status : null,
        search: params?.search || null,
      };
      if (!filters.status && !filters.search) {
        return request<DealListItem[]>(`${API_BASE}/deals`);
      }
      return request<DealListItem[]>(`${API_BASE}/deals/search`, {
        method: "POST",
        body: JSON.stringify(filters),
      });
    },
    get: (id: string) => request<Deal>(`${API_BASE}/deals/${id}`),
    create: (data: DealCreate) =>
      request<Deal>(`${API_BASE}/deals`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    update: (id: string, data: Partial<Deal>) =>
      request<Deal>(`${API_BASE}/deals/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    delete: (id: string) => request<void>(`${API_BASE}/deals/${id}`, { method: "DELETE" }),
  },

  // Sections
  sections: {
    list: (dealId: string) => request<Section[]>(`${API_BASE}/deals/${dealId}/sections`),
    update: (
      dealId: string,
      sectionId: string,
      data: {
        sources?: string;
        expected_output?: string;
        custom_instructions?: string | null;
        state?: string;
        output_template?: string | null;
        generated_content?: string;
        source_urls?: string[];
      },
    ) =>
      request<Section>(`${API_BASE}/deals/${dealId}/sections/${sectionId}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    acquireEditLock: (dealId: string, sectionId: string) =>
      request<NarrativeEditLock>(
        `${API_BASE}/deals/${dealId}/sections/${sectionId}/edit-lock`,
        { method: "POST" },
      ),
    releaseEditLock: (dealId: string, sectionId: string) =>
      request<void>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/edit-lock`, {
        method: "DELETE",
      }),
    generate: (dealId: string, sectionId: string, customInstructions?: string) =>
      request<NarrativeResponse>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/generate`, {
        method: "POST",
        body: JSON.stringify({ custom_instructions: customInstructions || null }),
      }),
    generateAll: (dealId: string) =>
      request<DraftAllResponse>(`${API_BASE}/deals/${dealId}/sections/generate-all`, {
        method: "POST",
      }),
    startGenerateAll: (dealId: string) =>
      request<DraftAllJob>(`${API_BASE}/deals/${dealId}/sections/generate-all/start`, {
        method: "POST",
      }),
    generateAllStatus: (dealId: string, jobId: string) =>
      request<DraftAllJob>(`${API_BASE}/deals/${dealId}/sections/generate-all/jobs/${jobId}`),
    uploadTemplate: async (dealId: string, sectionId: string, formData: FormData) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/sections/${sectionId}/template`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Template upload failed.");
      return res.json() as Promise<Section>;
    },
    deleteTemplate: (dealId: string, sectionId: string) =>
      request<Section>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/template`, {
        method: "DELETE",
      }),
    moderate: (dealId: string, sectionId: string) =>
      request<{
        moderation_status: string | null;
        is_safe: boolean;
        flagged_categories: string[];
        details: Record<string, unknown>;
        message: string;
      }>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/moderate`, {
        method: "POST",
      }),
    versions: (dealId: string, sectionId: string) =>
      request<NarrativeVersion[]>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/versions`),
    markVersionFinal: (dealId: string, sectionId: string, versionId: string) =>
      request<NarrativeVersion>(
        `${API_BASE}/deals/${dealId}/sections/${sectionId}/versions/${versionId}/mark-final`,
        { method: "POST" },
      ),
    deleteVersion: (dealId: string, sectionId: string, versionId: string) =>
      request<{
        deleted: boolean;
        deleted_version_id: string;
        remaining_count: number;
        current_version_id: string | null;
        uses_default_final: boolean;
      }>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/versions/${versionId}`, {
        method: "DELETE",
      }),
  },

  // Mistral Document Library (NEW)
  library: {
    list: (dealId: string) => request<LibraryFile[]>(`${API_BASE}/deals/${dealId}/library`),
    upload: async (dealId: string, formData: FormData) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/library`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Library upload failed.");
      return res.json();
    },
    delete: async (dealId: string, fileId: string) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/library/${fileId}`, {
        method: "DELETE",
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Library file deletion failed.");
      return res.json();
    },
    syncStatus: async (dealId: string) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/library/sync-status`);
      if (!res.ok) throw await apiErrorFromResponse(res, "Library status retrieval failed.");
      return res.json();
    },
    triggerSync: async (dealId: string) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/library/sync`, { method: "POST" });
      if (!res.ok) throw await apiErrorFromResponse(res, "Library synchronization failed.");
      return res.json();
    },
    initialize: (dealId: string) =>
      request<{ library_id: string; agents_created: number; agent_keys: string[] }>(
        `${API_BASE}/deals/${dealId}/library/initialize`,
        { method: "POST" },
      ),
  },

  // Versions
  versions: {
    submit: (dealId: string, notes: string) =>
      request<Version>(`${API_BASE}/deals/${dealId}/versions`, {
        method: "POST",
        body: JSON.stringify({ notes }),
      }),
    approve: (dealId: string, versionId: string, comments: string) =>
      request<Version>(`${API_BASE}/deals/${dealId}/versions/${versionId}/approve`, {
        method: "PATCH",
        body: JSON.stringify({ comments }),
      }),
    deny: (dealId: string, versionId: string, comments: string) =>
      request<Version>(`${API_BASE}/deals/${dealId}/versions/${versionId}/deny`, {
        method: "PATCH",
        body: JSON.stringify({ comments }),
      }),
    download: async (dealId: string, versionId: string) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/versions/${versionId}/download`, {
        method: "POST",
      });
      if (!res.ok) {
        throw await apiErrorFromResponse(res, "Version download failed.");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const contentDisposition = res.headers.get("content-disposition");
      const filename = contentDisposition?.match(/filename="(.+)"/)?.[1] || `${versionId}.pdf`;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
  },

  // Deal Documents (Legacy — kept for backward compat)
  documents: {
    list: (dealId: string) => request<DealDocument[]>(`${API_BASE}/deals/${dealId}/documents`),
    upload: async (dealId: string, formData: FormData) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/documents`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Document upload failed.");
      return res.json() as Promise<DealDocument>;
    },
    delete: (dealId: string, docId: string) =>
      request<void>(`${API_BASE}/deals/${dealId}/documents/${docId}`, { method: "DELETE" }),
    linkToSection: (dealId: string, sectionId: string, documentIds: string[]) =>
      request<SectionDocumentLink[]>(
        `${API_BASE}/deals/${dealId}/sections/${sectionId}/documents/link`,
        {
          method: "POST",
          body: JSON.stringify({ document_ids: documentIds }),
        },
      ),
    unlinkFromSection: (dealId: string, sectionId: string, docId: string) =>
      request<void>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/documents/${docId}/unlink`, {
        method: "DELETE",
      }),
  },

  // Uploads (Legacy)
  uploads: {
    list: (dealId: string, sectionId: string) =>
      request<UploadBrief[]>(`${API_BASE}/deals/${dealId}/sections/${sectionId}/uploads`),
    create: async (dealId: string, sectionId: string, formData: FormData) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/sections/${sectionId}/uploads`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Upload failed.");
      return res.json() as Promise<UploadBrief>;
    },
    delete: (uploadId: string) =>
      request<void>(`${API_BASE}/uploads/${uploadId}`, { method: "DELETE" }),
  },

  // Exports
  exports: {
    download: async (dealId: string, format: string) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/export/${format}`, {
        method: "POST",
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Export failed.");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const contentDisposition = res.headers.get("content-disposition");
      const filename = contentDisposition?.match(/filename="(.+)"/)?.[1] || `PitchBook.${format}`;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
    generateReport: async (dealId: string) => {
      const res = await fetch(`${API_BASE}/deals/${dealId}/report`, {
        method: "POST",
      });
      if (!res.ok) throw await apiErrorFromResponse(res, "Report generation failed.");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const contentDisposition = res.headers.get("content-disposition");
      const filename =
        contentDisposition?.match(/filename="(.+)"/)?.[1] || "CreditReport.pdf";
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    },
  },

  // MCP Companies
  companies: {
    list: () =>
      request<Array<{ name: string; blob_url: string; document_count: number }>>(
        `${API_BASE}/companies`,
      ),
    documents: (companyName: string) =>
      request<
        Array<{
          document_name: string;
          document_url: string;
          summary?: string;
          size?: number;
          type?: string;
        }>
      >(`${API_BASE}/companies/${encodeURIComponent(companyName)}/documents`),
    details: (companyName: string) =>
      request<{ industry?: string; geography?: string; segment?: string; kyc_status?: string }>(
        `${API_BASE}/companies/${encodeURIComponent(companyName)}/details`,
      ),
  },

  // Local MCP synthetic-data manufacturing
  manufacture: {
    start: (data: { company_name: string; industry: string; geography: string }) =>
      request<ManufactureJob>(`${API_BASE}/manufacture`, {
        method: "POST",
        body: JSON.stringify(data),
      }),
    status: (jobId: string) => request<ManufactureJob>(`${API_BASE}/manufacture/${jobId}`),
  },
};

// ── Utility ────────────────────────────────────────────────────

export function formatAmount(n: number, currency: string) {
  if (currency === "INR") {
    const cr = n / 10000000;
    return `INR ${cr.toFixed(2)} Cr`;
  }
  return `${currency} ${n.toLocaleString()}`;
}
