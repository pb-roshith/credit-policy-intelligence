import React, { useEffect, useState } from "react";
import {
  LayoutDashboard,
  FileText,
  BookOpen,
  ShieldCheck,
  AlertTriangle,
  SlidersHorizontal,
  BarChart3,
  Search,
  PanelLeftClose,
  Download,
  Plus,
  ArrowRight,
  Sparkles,
  TrendingUp,
  TrendingDown,
  CircleDollarSign,
  Activity,
  ShieldAlert,
  CheckCircle2,
  ChevronRight,
  Play,
  Save,
  GitCompareArrows,
  Filter,
  X,
  Database,
  Clock3,
  ExternalLink,
  Send,
  Building2,
  Menu,
  UserPlus,
  KeyRound,
  LockKeyhole,
  UserCheck,
  LogOut,
  CircleX,
  Eye,
  EyeOff,
  Factory,
} from "lucide-react";
import { API, apiRequest } from "../api/client";
import { META, POLICY_TYPE_ORDER, policyDisplayName } from "../config";
import { AuthField, Badge, Bars, Card, DataTable, Heading, Insight, LineChart, Metric, NO_CLIPBOARD, PasswordPolicy, SecretInput, money } from "../components/ui";

const GEOGRAPHIES = [
  "US Northeast", "US Southeast", "US Midwest", "US West", "Canada",
  "United Kingdom", "Europe", "Middle East & Africa", "Asia Pacific", "Latin America",
];

function StageExposure({ label, value, percent, tone }) {
  return (
    <div className="stage-item">
      <div>
        <span>{label}</span>
        <Badge tone={tone}>{value}</Badge>
      </div>
      <div className="stage-track">
        <i className={tone} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
function Legend() {
  return (
    <div className="legend">
      <i />
      Detected <i className="green-dot" />
      Remediated
    </div>
  );
}

function formatMillions(value) {
  const millions = Number(value) / 1_000_000;
  return `$${Number.isInteger(millions) ? millions : millions.toFixed(1)}M`;
}

function creditRequestRow(row) {
  return [
    row.borrower_name,
    row.credit_request_number,
    row.industry,
    formatMillions(row.exposure),
    `${Number(row.collateral_coverage).toFixed(0)}%`,
    row.facility,
    row.rating,
    formatMillions(row.requested_amount),
    row.status,
    row.compliance_score,
    row.recommended_pricing_bps,
    row.recommended_tenor_years,
    row.geography,
  ];
}

function RequestAssistant({ request }) {
  const score = Number(request[9] || 0);
  const attention = score < 70
    ? "Material policy deviations require escalation."
    : score < 85
      ? "Review the highlighted policy conditions before approval."
      : "The request is broadly aligned with current policy.";
  return (
    <Card className="assistant-panel" title="AI Credit Assistant">
      <div className="borrower">
        <span><Building2 size={17} /></span>
        <div>
          <strong>{request[0]}</strong>
          <small>{request[1]} - {request[2]}</small>
        </div>
      </div>
      <h3>Request overview</h3>
      <p>{request[5]} request for {request[7]} in {request[12]}, with current exposure of {request[3]}, collateral coverage of {request[4]}, and rating {request[6]}.</p>
      <h3>Recommended structure</h3>
      <p>{request[10]} basis points pricing with a {request[11]}-year tenor.</p>
      <h3>Policy assessment</h3>
      <div className="tag-row">
        <Badge>{request[8]}</Badge>
        <Badge tone={score < 70 ? "danger" : score < 85 ? "warning" : "pass"}>
          Compliance {score}
        </Badge>
      </div>
      <h3>Recommended attention</h3>
      <p>{attention}</p>
      <div className="button-row">
        <button className="btn primary" type="button">
          <Sparkles size={14} />Review request<ArrowRight size={14} />
        </button>
      </div>
      <small className="disclaimer">AI assistance supports, but does not replace, delegated credit approval.</small>
    </Card>
  );
}

export default function Requests({ session, notify }) {
  const [requests, setRequests] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [filter, setFilter] = useState("All Statuses");
  const [query, setQuery] = useState("");
  const [requestPage, setRequestPage] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState("");
  const [complianceResult, setComplianceResult] = useState(null);
  const [documentStep, setDocumentStep] = useState(0);
  const [documentAnswer, setDocumentAnswer] = useState("");
  const [form, setForm] = useState({
    borrower_name: "",
    industry: "Manufacturing",
    geography: "US Northeast",
    facility: "Term Loan",
    rating: "BB",
    requested_amount: 1_000_000,
    status: "Pending",
    collateral_coverage: 100,
    total_required_documents: null,
    uploaded_required_documents: null,
  });
  useEffect(() => {
    let active = true;
    apiRequest("/api/requests", {}, session.token)
      .then((rows) => {
        if (!active) return;
        const mapped = rows.map(creditRequestRow);
        setRequests(mapped);
        setSelected(mapped[0] || null);
        setLoadError("");
      })
      .catch((error) => active && setLoadError(error.message));
    return () => { active = false; };
  }, [session.token]);
  const filtered = requests.filter(
    (row) =>
      (filter === "All Statuses" || row[8] === filter) &&
      `${row[0]} ${row[1]}`.toLowerCase().includes(query.toLowerCase()),
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / 10));
  const safePage = Math.min(requestPage, pageCount - 1);
  const shown = filtered.slice(safePage * 10, safePage * 10 + 10);
  const updateForm = (field, value) => setForm((current) => ({ ...current, [field]: value }));
  const answerDocumentQuestion = () => {
    const answer = Number(documentAnswer);
    if (!Number.isInteger(answer) || answer < 0) return;
    if (documentStep === 0 && answer < 1) return;
    if (documentStep === 1 && answer > Number(form.total_required_documents)) return;
    updateForm(documentStep === 0 ? "total_required_documents" : "uploaded_required_documents", answer);
    setDocumentStep((step) => step + 1);
    setDocumentAnswer("");
  };
  const submitCreditRequest = async (event) => {
    event.preventDefault();
    setSaving(true);
    setFormError("");
    try {
      const created = await apiRequest(
        "/api/requests",
        {
          method: "POST",
          body: JSON.stringify({
            ...form,
            requested_amount: Number(form.requested_amount),
            collateral_coverage: Number(form.collateral_coverage),
            total_required_documents: Number(form.total_required_documents),
            uploaded_required_documents: Number(form.uploaded_required_documents),
          }),
        },
        session.token,
      );
      const mapped = creditRequestRow(created);
      setRequests((current) => [...current, mapped]);
      setSelected(mapped);
      setComplianceResult(created.compliance);
      setShowForm(false);
      setQuery(created.credit_request_number);
      setRequestPage(0);
      notify(`Compliance score ${created.compliance.overallScore}: ${created.compliance.complianceStatus}`);
    } catch (error) {
      setFormError(error.message);
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <Heading page="requests">
        {session.user.role === "relationship_manager" && (
          <button className="btn primary" onClick={() => { setDocumentStep(0); setDocumentAnswer(""); setForm((current) => ({ ...current, total_required_documents: null, uploaded_required_documents: null })); setShowForm(true); }}>
            <Plus size={15} />
            New Credit Request
          </button>
        )}
      </Heading>
      {showForm && (
        <Card
          className="request-form-card"
          title="New Credit Request"
          action={<button type="button" className="icon-button" aria-label="Close form" onClick={() => setShowForm(false)}><X size={17} /></button>}
        >
          <form className="credit-request-form" onSubmit={submitCreditRequest}>
            <div className="credit-form-note form-wide"><Sparkles size={16} /><span>Exposure is calculated from borrower history. Applicable policy checks, approval authority, pricing, tenor, and the compliance score are derived automatically.</span></div>
            <label><span>Borrower name</span><input required autoComplete="off" value={form.borrower_name} onChange={(event) => updateForm("borrower_name", event.target.value)} /></label>
            <label><span>Industry</span><input required autoComplete="off" value={form.industry} onChange={(event) => updateForm("industry", event.target.value)} /></label>
            <label><span>Geography</span><select required value={form.geography} onChange={(event) => updateForm("geography", event.target.value)}>{GEOGRAPHIES.map((geography) => <option key={geography}>{geography}</option>)}</select></label>
            <label><span>Facility</span><input required autoComplete="off" value={form.facility} onChange={(event) => updateForm("facility", event.target.value)} /></label>
            <label><span>Rating</span><input required autoComplete="off" maxLength="12" value={form.rating} onChange={(event) => updateForm("rating", event.target.value)} /></label>
            <label><span>Requested amount ($)</span><input required type="number" min="1" step="1" value={form.requested_amount} onChange={(event) => updateForm("requested_amount", event.target.value)} /></label>
            <label><span>Collateral coverage (%)</span><input required type="number" min="0" max="500" step="0.01" value={form.collateral_coverage} onChange={(event) => updateForm("collateral_coverage", event.target.value)} /></label>
            <label><span>Status</span><select value={form.status} onChange={(event) => updateForm("status", event.target.value)}><option>Pending</option><option>In Review</option><option>Escalated</option><option>Approved</option><option>Declined</option></select></label>
            <div className="compliance-chat form-wide request-intake-chat">
              <div className="chat-ai"><Sparkles size={18} /><p>How many documents are required for this credit request?</p></div>
              {form.total_required_documents !== null && <div className="chat-user">{form.total_required_documents} documents are required.</div>}
              {documentStep >= 1 && <div className="chat-ai"><Sparkles size={18} /><p>How many of those required documents have been supplied?</p></div>}
              {form.uploaded_required_documents !== null && <div className="chat-user">{form.uploaded_required_documents} documents have been supplied.</div>}
              {documentStep >= 2 && <div className="chat-ai"><CheckCircle2 size={18} /><p>Thank you. I have enough information to calculate documentation completeness.</p></div>}
              {documentStep < 2 && <div className="chat-input"><input type="number" min="0" max={documentStep === 1 ? form.total_required_documents : 1000} value={documentAnswer} onChange={(event) => setDocumentAnswer(event.target.value)} placeholder="Enter a number..." aria-label="Answer the compliance question" /><button type="button" disabled={!documentAnswer} onClick={answerDocumentQuestion} aria-label="Send answer"><Send size={16} /></button></div>}
            </div>
            {formError && <div className="data-message error form-wide">{formError}</div>}
            <div className="credit-form-actions form-wide"><button type="button" className="btn secondary" onClick={() => setShowForm(false)}>Cancel</button><button className="btn primary" disabled={saving || documentStep < 2}><Save size={15} />{saving ? "Scoring request..." : "Create & Calculate Score"}</button></div>
          </form>
        </Card>
      )}
      {complianceResult && !showForm && (
        <Card className="compliance-result-card" title="Compliance Scoring Result" action={<Badge tone="rating">{complianceResult.complianceStatus}</Badge>}>
          <div className="compliance-result-summary">
            <strong>{complianceResult.overallScore}</strong>
            <span>Overall compliance score</span>
            <div>{Object.entries(complianceResult.categoryScores).map(([category, score]) => <p key={category}><span>{category.replace(/([A-Z])/g, " $1")}</span><b>{score}</b></p>)}</div>
          </div>
        </Card>
      )}
      <div className="request-layout">
        <Card
          className="table-card"
          title={`${filtered.length.toLocaleString()} Request${filtered.length === 1 ? "" : "s"}`}
          action={<Badge tone="rating">Sorted: Compliance (ascending)</Badge>}
        >
          <div className="request-tools">
            <label className="request-search">
              <Search size={16} />
              <input
                autoComplete="off"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setRequestPage(0);
                }}
                placeholder="Search borrower or ID..."
              />
            </label>
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setRequestPage(0);
              }}
            >
              <option>All Statuses</option>
              <option>In Review</option>
              <option>Escalated</option>
              <option>Approved</option>
              <option>Pending</option>
              <option>Declined</option>
            </select>
            <button className="filter-square" aria-label="Filter requests">
              <Filter size={16} />
            </button>
          </div>
          {loadError && <div className="data-message error">{loadError}</div>}
          {!loadError && requests.length === 0 && <div className="data-message">Loading credit requests...</div>}
          <DataTable
            headers={[
              "Borrower",
              "Industry",
              "Geography",
              "Exposure",
              "Collateral Coverage",
              "Facility",
              "Rating",
              "Requested",
              "Status",
              "Compliance",
            ]}
            rows={shown}
            selected={selected}
            onSelect={setSelected}
            render={(v, i, r) =>
              i === 0 ? (
                <>
                  <strong>{v}</strong>
                  <small>{r[1]}</small>
                </>
              ) : i === 1 ? (
                r[2]
              ) : i === 2 ? (
                r[12]
              ) : i === 3 ? (
                r[3]
              ) : i === 4 ? (
                r[4]
              ) : i === 5 ? (
                r[5]
              ) : i === 6 ? (
                <Badge tone="rating">{r[6]}</Badge>
              ) : i === 7 ? (
                r[7]
              ) : i === 8 ? (
                <Badge>{r[8]}</Badge>
              ) : (
                <span
                  className={`score ${r[9] < 70 ? "danger" : r[9] < 85 ? "warn" : ""}`}
                >
                  {r[9]}
                </span>
              )
            }
          />
          <div className="table-footer request-pagination">
            <span>
              Showing {filtered.length ? safePage * 10 + 1 : 0}-
              {Math.min((safePage + 1) * 10, filtered.length)} of{" "}
              {filtered.length.toLocaleString()}
            </span>
            <div>
              <button
                disabled={safePage === 0}
                onClick={() => setRequestPage((page) => Math.max(0, page - 1))}
                aria-label="Previous 10 requests"
              >
                &lt;
              </button>
              <button
                disabled={safePage >= pageCount - 1}
                onClick={() =>
                  setRequestPage((page) => Math.min(pageCount - 1, page + 1))
                }
                aria-label="Next 10 requests"
              >
                &gt;
              </button>
            </div>
          </div>
        </Card>
        {selected && <RequestAssistant request={selected} />}
      </div>
    </>
  );
}
