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
import { loadRequestList } from "../api/requestList";
import { filterExceptions } from "../api/exceptionSearch.js";
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
  const [acting, setActing] = useState(false);
  const [creating, setCreating] = useState(false), [saving, setSaving] = useState(false), [createError, setCreateError] = useState("");
  const [requests, setRequests] = useState([]);
  const [form, setForm] = useState({ credit_request_number: "", exception_type: "Policy", clause_code: "", owner: session.user.user_id, due_date: "", status: "Active", description: "" });
  const canApprove = session.user.role === "credit_analyst";
  const canCreate = session.user.role === "relationship_manager";
  const changeField = event => setForm(current => ({ ...current, [event.target.name]: event.target.value }));
  const openCreate = async () => {
    setCreating(true);
    setCreateError("");
    const result = await loadRequestList(session.token, apiRequest);
    setRequests(result.rows);
    if (result.error) setCreateError(result.error);
  };
  const submitCreate = async event => {
    event.preventDefault();
    setSaving(true);
    setCreateError("");
    try {
      const created = await apiRequest("/api/exceptions", { method: "POST", body: JSON.stringify(form) });
      const updated = await apiRequest("/api/exceptions");
      setExceptions(updated);
      setSelected(created);
      setTab("Active");
      setQuery("");
      setCreating(false);
      notify(`${created.id} created as Active`);
    } catch (error) { setCreateError(error.message); }
    finally { setSaving(false); }
  };
  const creation = <>
    <Heading page="exceptions">{canCreate && <button className="btn primary" onClick={openCreate}><Plus size={14} />Create Exception</button>}</Heading>
    {canCreate && creating && <Card title="Create Exception"><form className="credit-request-form" onSubmit={submitCreate}>
      <label><span>Credit request</span><select name="credit_request_number" required value={form.credit_request_number} onChange={changeField}><option value="">Select a credit request</option>{requests.map(request => <option key={request.credit_request_number} value={request.credit_request_number}>{request.borrower_name} ({request.credit_request_number})</option>)}</select></label>
      <label><span>Exception type</span><input name="exception_type" required minLength={2} maxLength={80} value={form.exception_type} onChange={changeField} /></label>
      <label><span>Policy clause</span><input name="clause_code" required maxLength={40} value={form.clause_code} onChange={changeField} /></label>
      <label><span>Owner</span><input name="owner" required minLength={2} maxLength={120} value={form.owner} onChange={changeField} /></label>
      <label><span>Due date</span><input name="due_date" type="date" required value={form.due_date} onChange={changeField} /></label>
      <label className="form-wide"><span>Description</span><textarea name="description" required minLength={10} maxLength={4000} value={form.description} onChange={changeField} /></label>
      {createError && <p role="alert" className="data-message error">{createError}</p>}
      <div className="button-row"><button className="btn primary" disabled={saving || !requests.length}>{saving ? "Creating..." : "Create Exception"}</button><button type="button" className="btn secondary" disabled={saving} onClick={() => setCreating(false)}>Cancel</button></div>
    </form></Card>}
  </>;
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
  const filtered = filterExceptions(exceptions, tab, query);
  const rows = filtered.map((x) => [x.id, x.credit_request_number, x.type, x.clause, x.severity, `$${Math.round(x.exposure / 1000000)}M`, x.owner, String(x.due), x.status, x.account_user_id]);
  const row = filtered.find((item) => item.id === selected?.id && item.account_user_id === selected?.account_user_id) || filtered[0] || null;
  const chooseTab = (nextTab) => {
    setTab(nextTab);
    const next = exceptions.find((item) => nextTab === "All" || item.status === nextTab) || null;
    setSelected(next);
  };
  const runAction = async (action) => {
    if (!row || acting) return;
    setActing(true);
    try {
      await apiRequest(`/api/exceptions/${row.id}/action`, { method: "POST", body: JSON.stringify({ action, account_user_id: row.account_user_id }) }, session.token);
      const updated = await apiRequest("/api/exceptions", {}, session.token);
      setExceptions(updated);
      setSelected(updated.find((item) => item.id === row.id && item.account_user_id === row.account_user_id) || null);
      setTab(action === "approve" ? "Remediation" : action === "remediate" ? "Closed" : action === "escalate" ? "Pending Approval" : tab);
      notify(`${row.id} ${action === "remediate" ? "remediated and closed" : `${action}d`}`);
    } catch (error) {
      notify(`Could not ${action} ${row.id}: ${error.message}`);
    } finally {
      setActing(false);
    }
  };
  if (loading) return <><Heading page="exceptions" /><div className="compliance-empty"><Database size={28} /><h3>Loading exception registry</h3><p>Reading exceptions and workflow details from PostgreSQL...</p></div></>;
  if (!exceptions.length) return <>{creation}<div className="compliance-empty"><Database size={28} /><h3>{loadError ? "Could not load exception registry" : "No exceptions found"}</h3><p>{loadError || "Create an exception for a credit request to submit it for analyst approval."}</p></div></>;
  return (
    <>
      {creation}
      <div className="tabs">
        {["All", "Active", "Pending Approval", "Remediation", "Closed"].map(
          (x) => (
            <button
              className={tab === x ? "active" : ""}
              onClick={() => chooseTab(x)}
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
            <label className="request-search"><Search size={16} /><input autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} aria-label="Search exceptions" placeholder="Search ID, request, type, owner..." /></label>
            {query && <button type="button" className="text-btn" onClick={() => setQuery("")}>Clear</button>}
          </div>
          <DataTable
            rowKey={r => `${r[9]}:${r[0]}`}
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
            selected={row ? rows.find((item) => item[0] === row.id && item[9] === row.account_user_id) : null}
            onSelect={(r) => setSelected(exceptions.find((x) => x.id === r[0] && x.account_user_id === r[9]))}
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
        {!row ? <Card className="exception-detail" title="No matching exceptions"><div className="compliance-empty"><Filter size={26} /><p>No records match the selected status and search.</p></div></Card> : <Card
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
            {canApprove && (row.status === "Active" || row.status === "Pending Approval") && <button className="btn primary" disabled={acting} onClick={() => runAction("approve")}>{acting ? "Updating..." : "Approve"}</button>}
            {row.status === "Remediation" && <button className="btn primary" disabled={acting} onClick={() => runAction("remediate")}>{acting ? "Updating..." : "Remediate"}</button>}
            {row.status === "Active" && <button className="btn secondary" disabled={acting} onClick={() => runAction("escalate")}>Escalate</button>}
            {row.status === "Closed" && <span className="workflow-complete"><CheckCircle2 size={15} /> Workflow complete</span>}
          </div>
          <h3>Workflow History</h3>
          <div className="history">
            {row.history.map((event, index) => <p key={`${event.date}-${index}`}>{event.date} - {event.event} ({event.actor})</p>)}
          </div>
        </Card>}
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
