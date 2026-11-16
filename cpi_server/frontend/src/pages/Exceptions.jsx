import React, { useEffect, useRef, useState } from "react";
import "./Exceptions.css";
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
  Trash2,
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
  const [deleteTarget, setDeleteTarget] = useState(null), [deleting, setDeleting] = useState(false), [deleteError, setDeleteError] = useState("");
  const deleteDialog = useRef(null);
  useEffect(() => {
    if (deleteTarget) deleteDialog.current?.showModal();
    else deleteDialog.current?.close();
  }, [deleteTarget]);
  const canApprove = session.user.role === "credit_analyst";
  const canCreate = session.user.role === "relationship_manager";
  const creation = <Heading page="exceptions">{session.user.role==='relationship_manager'&&<button className="btn primary" onClick={()=>{location.hash='compliance'}}><Plus size={14}/>Create Exception</button>}</Heading>;
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
  const confirmDelete = async () => {
    if (!deleteTarget || deleting) return;
    setDeleting(true);
    setDeleteError("");
    try {
      const target = deleteTarget;
      const accountQuery = target.account_user_id ? `?account_user_id=${encodeURIComponent(target.account_user_id)}` : "";
      await apiRequest(`/api/exceptions/${encodeURIComponent(target.id)}${accountQuery}`, { method: "DELETE" });
      setExceptions(current => current.filter(item => !(item.id === target.id && item.account_user_id === target.account_user_id)));
      setSelected(null);
      setDeleteTarget(null);
      notify(`${target.id} deleted`);
    } catch (error) {
      setDeleteError(error.message);
    } finally {
      setDeleting(false);
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
            render={(v, i, tableRow) =>
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
          <Rationale title="Exception description">{row.rationale?.synthetic?row.description.replace(/^Manufactured /,''):row.description}</Rationale>
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
          <h3>{row.rationale.generation_status === "pending" ? "AI Exception Rationale — Pending" : "AI Exception Rationale"}</h3>
          {row.rationale.generation_status === "pending" && <p className="exception-rationale-notice" role="status">{row.rationale.generation_notice}</p>}
          <Rationale title="Why detected">
            {row.rationale.synthetic?row.rationale.why_detected.replace(/a synthetic /g,'a '):row.rationale.why_detected}
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
          {(canApprove || (canCreate && row.account_user_id === session.user.user_id)) && <div className="exception-delete-actions">
            <button type="button" className="btn exception-delete-trigger" disabled={acting || deleting} onClick={() => { setDeleteError(""); setDeleteTarget(row); }}><Trash2 size={16} />Delete exception</button>
          </div>}
        </Card>}
      </div>
      <dialog ref={deleteDialog} className="exception-delete-dialog" aria-labelledby="exception-delete-title" aria-describedby="exception-delete-description" onCancel={event => { event.preventDefault(); if (!deleting) setDeleteTarget(null); }}>
        <div className="exception-delete-dialog-header">
          <span className="exception-delete-icon"><Trash2 size={21} aria-hidden="true" /></span>
          <h2 id="exception-delete-title">Delete exception?</h2>
          <button type="button" className="exception-delete-close" aria-label="Close delete confirmation" disabled={deleting} onClick={() => setDeleteTarget(null)}><X size={18} /></button>
        </div>
        <div className="exception-delete-dialog-body">
          <p id="exception-delete-description">Are you sure you want to delete this exception? The exception and its workflow history will be permanently removed.</p>
          <dl className="exception-delete-summary">
            <div><dt>Exception</dt><dd>{deleteTarget?.id}</dd></div>
            <div><dt>Credit request</dt><dd>{deleteTarget?.credit_request_number}</dd></div>
          </dl>
          <p className="exception-delete-warning"><AlertTriangle size={15} aria-hidden="true" />This action cannot be undone.</p>
          {deleteError && <p role="alert" className="data-message error">{deleteError}</p>}
        </div>
        <div className="exception-delete-dialog-footer">
          <button type="button" className="btn secondary" autoFocus disabled={deleting} onClick={() => setDeleteTarget(null)}>Cancel</button>
          <button type="button" className="btn exception-delete-button" disabled={deleting} onClick={confirmDelete}><Trash2 size={15} />{deleting ? "Deleting..." : "Delete exception"}</button>
        </div>
      </dialog>
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
