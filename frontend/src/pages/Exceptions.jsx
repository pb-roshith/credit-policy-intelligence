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

function ProposalInput({ label, value, alert = false }) {
  return (
    <div>
      <span>{label}</span>
      <strong className={alert ? "alert-value" : ""}>{value}</strong>
    </div>
  );
}
function ComplianceCount({ icon: Icon, label, value, tone }) {
  return (
    <div className="card compliance-count">
      <span className={tone}>
        <Icon size={20} />
      </span>
      <div>
        <strong>{value}</strong>
        <small>{label}</small>
      </div>
    </div>
  );
}
export default function Exceptions({ session, notify }) {
  const [tab, setTab] = useState("All"), [selected, setSelected] = useState(null), [exceptions, setExceptions] = useState([]), [loading, setLoading] = useState(true), [loadError, setLoadError] = useState(""), [query, setQuery] = useState(() => sessionStorage.getItem("exceptionRegistrySearch") || "");
  useEffect(() => {
    apiRequest("/api/exceptions", {}, session.token)
      .then((data) => {
        setExceptions(data);
        const searched = sessionStorage.getItem("exceptionRegistrySearch");
        setSelected(data.find((item) => item.credit_request_number === searched) || data[0] || null);
        sessionStorage.removeItem("exceptionRegistrySearch");
      })
      .catch((error) => { setLoadError(error.message); notify(`Could not load exception registry: ${error.message}`); })
      .finally(() => setLoading(false));
  }, [session.token]);
  const filtered = exceptions.filter((item) => (tab === "All" || item.status === tab) && item.credit_request_number.toLowerCase().includes(query.trim().toLowerCase()));
  const rows = filtered.map((x) => [x.id, x.credit_request_number, x.type, x.clause, x.severity, `$${Math.round(x.exposure / 1000000)}M`, x.owner, String(x.due), x.status]);
  const row = selected || exceptions[0];
  if (loading) return <><Heading page="exceptions" /><div className="compliance-empty"><Database size={28} /><h3>Loading exception registry</h3><p>Reading exceptions and workflow details from PostgreSQL...</p></div></>;
  if (!row) return <><Heading page="exceptions" /><div className="compliance-empty"><Database size={28} /><h3>{loadError ? "Could not load exception registry" : "No exceptions found"}</h3><p>{loadError || "Create credit requests to populate the exception registry."}</p></div></>;
  return (
    <>
      <Heading page="exceptions" />
      <div className="tabs">
        {["All", "Active", "Pending Approval", "Remediation", "Closed"].map(
          (x) => (
            <button
              className={tab === x ? "active" : ""}
              onClick={() => setTab(x)}
              key={x}
            >
              {x}
              {x === "All" ? ` (${exceptions.length})` : ""}
            </button>
          ),
        )}
      </div>
      <div className="exception-layout">
        <Card title="Exception Registry">
          <div className="request-tools">
            <label className="request-search"><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search credit request ID..." /></label>
            {query && <button type="button" className="text-btn" onClick={() => setQuery("")}>Clear</button>}
          </div>
          <DataTable
            headers={[
              "ID",
              "Credit Request ID",
              "Type",
              "Clause",
              "Severity",
              "Exposure",
              "Owner",
              "Due",
              "Status",
            ]}
            rows={rows}
            selected={rows.find((item) => item[0] === row.id)}
            onSelect={(r) => setSelected(exceptions.find((x) => x.id === r[0]))}
            render={(v, i) =>
              i === 0 ? (
                <strong>{v}</strong>
              ) : i === 4 || i === 8 ? (
                <Badge>{v}</Badge>
              ) : (
                v
              )
            }
          />
        </Card>
        <Card
          className="exception-detail"
          title={row.id}
          action={<Badge>{row.severity}</Badge>}
        >
          <h3>{row.type} exception - {row.clause} · {row.credit_request_number}</h3>
          <Rationale title="Exception description">{row.description}</Rationale>
          <div className="workflow">
            {row.workflow.map(
              (x, i) => (
                <div className={x.status === "Done" ? "done" : ""} key={x.name}>
                  <i>{x.status}</i>
                  <span>{x.name}</span>
                  {x.status === "Current" && <Badge tone="clause">Current</Badge>}
                </div>
              ),
            )}
          </div>
          <h3>AI Exception Rationale</h3>
          <Rationale title="Why detected">
            {row.rationale.why_detected}
          </Rationale>
          <Rationale title="Business justification">
            {row.rationale.business_justification}
          </Rationale>
          <Rationale title="Risk implication">
            {row.rationale.risk_implication}
          </Rationale>
          <Rationale title="Recommended remediation">
            {row.rationale.recommended_remediation}
          </Rationale>
          <Rationale title="Escalation requirement">
            {row.rationale.escalation_required}
          </Rationale>
          <div className="button-row">
            <button
              className="btn primary"
              onClick={async () => { await apiRequest(`/api/exceptions/${row.id}/action`, { method: "POST", body: JSON.stringify({ action: "approve" }) }, session.token); notify(`${row.id} approved`); setExceptions(await apiRequest("/api/exceptions", {}, session.token)); }}
            >
              Approve
            </button>
            <button
              className="btn secondary"
              onClick={async () => { await apiRequest(`/api/exceptions/${row.id}/action`, { method: "POST", body: JSON.stringify({ action: "escalate" }) }, session.token); notify(`${row.id} escalated`); setExceptions(await apiRequest("/api/exceptions", {}, session.token)); }}
            >
              Escalate
            </button>
          </div>
          <h3>Workflow History</h3>
          <div className="history">
            {row.history.map((event, index) => <p key={`${event.date}-${index}`}>{event.date} - {event.event} ({event.actor})</p>)}
          </div>
        </Card>
      </div>
    </>
  );
}
function Rationale({ title, children }) {
  return (
    <div className="rationale">
      <strong>{title}:</strong>
      <p>{children}</p>
    </div>
  );
}
