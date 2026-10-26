import React, { useEffect, useRef, useState } from "react";
import { loadRequestList } from "../api/requestList";
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

function formatMillions(value, currency = "USD") {
  const millions = Number(value) / 1_000_000;
  return `${currency === "USD" ? "$" : currency + " "}${Number.isInteger(millions) ? millions : millions.toFixed(1)}M`;
}

function creditRequestRow(row) {
  return [
    row.borrower_name,
    row.credit_request_number,
    row.industry,
    formatMillions(row.exposure, row.currency),
    `${Number(row.collateral_coverage).toFixed(0)}%`,
    row.facility,
    row.rating,
    formatMillions(row.requested_amount, row.currency),
    row.status,
    row.compliance_score,
    row.recommended_pricing_bps,
    row.recommended_tenor_years,
    row.geography,
    row.assistant || null,
  ];
}

function RequestAssistant({ request, session }) {
  const details = request[13];
  const [mapping, setMapping] = useState(null);
  const [mappingError, setMappingError] = useState("");
  useEffect(() => {
    let active = true;
    setMapping(null);
    setMappingError("");
    apiRequest(`/api/compliance-review/${encodeURIComponent(request[1])}/policy-mapping`, {}, session.token)
      .then(result => { if (active) setMapping(result); })
      .catch(error => { if (active) setMappingError(error.message); });
    return () => { active = false; };
  }, [request[1], session.token]);
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
      <p>{details?.summary || `${request[5]} request for ${request[7]} in ${request[12]}, with current exposure of ${request[3]}, collateral coverage of ${request[4]}, and rating ${request[6]}.`}</p>
      <h3>Risk factors</h3>
      {(details?.risks || [attention]).map((risk, index) => <p key={index}>{risk}</p>)}
      <h3>Recommended structure</h3>
      <p>{request[10]} basis points pricing with a {request[11]}-year tenor.</p>
      <h3>Applicable policies to review</h3>
      {mappingError ? <p>{mappingError}</p> : !mapping ? <p>Checking policy scope...</p> : <>
        {mapping.policy_mappings.map(policy => <p key={policy.policy_id}>{policy.policy_name} <small>({policy.rule_count} applicable rules)</small></p>)}
      </>}
    </Card>
  );
}

export default function Requests({ session, notify }) {
  const currentOwner = useRef(session.user.user_id);
  currentOwner.current = session.user.user_id;
  const [requests, setRequests] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [filter, setFilter] = useState("All Active");
  const [query, setQuery] = useState("");
  const [requestPage, setRequestPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const filtered = requests.filter(
    (row) =>
      (filter === "All Active" ? ["In Review", "Escalated", "Pending"].includes(row[8]) : row[8] === filter) &&
      `${row[0]} ${row[1]}`.toLowerCase().includes(query.toLowerCase()),
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / 10));
  const safePage = Math.min(requestPage, pageCount - 1);
  const shown = filtered.slice(safePage * 10, safePage * 10 + 10);
  const refreshRequests = async () => {
    const owner = session.user.user_id;
    setLoading(true);
    const list = await loadRequestList(session.token, apiRequest);
    if (currentOwner.current !== owner) return;
    const mapped = list.rows.map(creditRequestRow);
    setRequests(mapped);
    setSelected(current => mapped.find(row => row[1] === current?.[1]) || mapped[0] || null);
    setLoadError(list.error);
    setLoading(false);
  };
  useEffect(() => {
    setRequests([]);
    setSelected(null);
    refreshRequests();
    const refreshWhenVisible = () => { if (document.visibilityState === "visible") refreshRequests(); };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    window.addEventListener("focus", refreshWhenVisible);
    return () => {
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.removeEventListener("focus", refreshWhenVisible);
    };
  }, [session.user.user_id]);
  return (
    <>
      <Heading page="requests" />
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
              <option>All Active</option>
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
          {!loadError && requests.length === 0 && <div className="data-message">{loading ? "Loading credit requests..." : "No credit requests found."}</div>}
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
        {selected && <RequestAssistant request={selected} session={session} />}
      </div>
    </>
  );
}
