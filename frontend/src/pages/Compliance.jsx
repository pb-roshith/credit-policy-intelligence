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
      <span className={tone}><Icon size={20} /></span>
      <div><strong>{value}</strong><small>{label}</small></div>
    </div>
  );
}

export default function Compliance({ notify, session }) {
  const [requests, setRequests] = useState([]);
  const [selectedRequest, setSelectedRequest] = useState("");
  const [review, setReview] = useState(null);
  const [loadingRequests, setLoadingRequests] = useState(true);
  const [loadingStored, setLoadingStored] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [showExceptionForm, setShowExceptionForm] = useState(false);
  const [savingException, setSavingException] = useState(false);
  const [exceptionError, setExceptionError] = useState("");
  const [exceptionForm, setExceptionForm] = useState({ exception_type: "", clause_code: "", owner: session.user.user_id, due_date: "", status: "Active", description: "" });

  useEffect(() => {
    apiRequest("/api/requests", {}, session.token)
      .then((rows) => {
        setRequests(rows);
        const savedRequest = sessionStorage.getItem(`complianceReviewSelection:${session.user.user_id}`);
        const restoredRequest = rows.some((row) => row.credit_request_number === savedRequest)
          ? savedRequest
          : rows[0]?.credit_request_number || "";
        setSelectedRequest((current) => current || restoredRequest);
      })
      .catch((requestError) => setError(requestError.message))
      .finally(() => setLoadingRequests(false));
  }, [session.token, session.user.user_id]);

  useEffect(() => {
    if (!selectedRequest) return undefined;
    let active = true;
    sessionStorage.setItem(`complianceReviewSelection:${session.user.user_id}`, selectedRequest);
    setReview(null);
    setError("");
    setLoadingStored(true);
    apiRequest(`/api/compliance-review/${encodeURIComponent(selectedRequest)}/latest`, {}, session.token)
      .then((savedReview) => { if (active) setReview(savedReview); })
      .catch((requestError) => {
        if (active && requestError.status !== 404) setError(requestError.message);
      })
      .finally(() => { if (active) setLoadingStored(false); });
    return () => { active = false; };
  }, [selectedRequest, session.token, session.user.user_id]);

  const runAgent = async (event) => {
    event.preventDefault();
    if (!selectedRequest || running) return;
    setRunning(true);
    setError("");
    setReview(null);
    try {
      const result = await apiRequest(
        "/api/compliance-review/run",
        { method: "POST", body: JSON.stringify({ credit_request_number: selectedRequest }) },
        session.token,
      );
      setReview(result);
      notify(`${result.agent} completed ${selectedRequest}`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunning(false);
    }
  };

  const tracePolicy = (finding) => {
    if (!finding.policy_id) {
      notify(`No policy summary is mapped to ${finding.policy_clause}`);
      return;
    }
    sessionStorage.setItem("complianceTracePolicyId", String(finding.policy_id));
    sessionStorage.removeItem("policyExplorerTab");
    location.hash = "policy";
  };

  const openExceptionForm = () => {
    const finding = review?.findings?.find((item) => item.severity === "BREACH") || review?.findings?.find((item) => item.severity === "WARNING") || review?.findings?.[0];
    const clauseCode = finding?.policy_clause?.match(/[A-Z]+-\d+(?:\.\d+)*/)?.[0] || finding?.policy_clause?.slice(0, 40) || "";
    const due = new Date();
    due.setDate(due.getDate() + 30);
    setExceptionForm({
      exception_type: finding?.policy_type || "Policy",
      clause_code: clauseCode,
      owner: session.user.user_id,
      due_date: due.toISOString().slice(0, 10),
      status: "Active",
      description: "",
    });
    setExceptionError("");
    setShowExceptionForm(true);
  };
  const updateException = (field, value) => setExceptionForm((current) => ({ ...current, [field]: value }));
  const submitException = async (event) => {
    event.preventDefault();
    setSavingException(true);
    setExceptionError("");
    try {
      const created = await apiRequest("/api/exceptions", {
        method: "POST",
        body: JSON.stringify({ ...exceptionForm, credit_request_number: selectedRequest }),
      }, session.token);
      sessionStorage.setItem("exceptionRegistrySearch", selectedRequest);
      notify(`${created.id} created with Mistral-generated rationale`);
      location.hash = "exceptions";
    } catch (requestError) {
      setExceptionError(requestError.message);
    } finally {
      setSavingException(false);
    }
  };

  const selected = review?.credit_request;
  const findingRows = (review?.findings || []).map((finding) => [
    finding.policy_clause, finding.actual, finding.threshold, finding.variance,
    finding.severity, finding,
  ]);
  return (
    <>
      <Heading page="compliance">
        <button className="btn tertiary" onClick={() => (location.hash = "requests")}>Back to Requests</button>
        <button className="btn primary" disabled={!review} onClick={openExceptionForm}><Plus size={14} />Create Exception</button>
      </Heading>
      {showExceptionForm && (
        <Card className="request-form-card" title="Create Policy Exception" action={<button type="button" className="icon-button" aria-label="Close form" onClick={() => setShowExceptionForm(false)}><X size={17} /></button>}>
          <form className="credit-request-form" onSubmit={submitException}>
            <div className="credit-form-note form-wide"><Sparkles size={16} /><span>The exception ID, exposure, and severity are generated automatically. Mistral will create the business justification, risk implications, remediation, and escalation guidance from your description and this compliance review.</span></div>
            <label><span>Credit request ID</span><input autoComplete="off" value={selectedRequest} readOnly /></label>
            <label><span>Exception type</span><input required autoComplete="off" value={exceptionForm.exception_type} onChange={(event) => updateException("exception_type", event.target.value)} /></label>
            <label><span>Policy clause</span><input required autoComplete="off" value={exceptionForm.clause_code} onChange={(event) => updateException("clause_code", event.target.value)} /></label>
            <label><span>Owner</span><input required autoComplete="off" value={exceptionForm.owner} onChange={(event) => updateException("owner", event.target.value)} /></label>
            <label><span>Due date</span><input required type="date" min={new Date().toISOString().slice(0, 10)} value={exceptionForm.due_date} onChange={(event) => updateException("due_date", event.target.value)} /></label>
            <label><span>Status</span><select value={exceptionForm.status} onChange={(event) => updateException("status", event.target.value)}><option>Active</option><option>Pending Approval</option><option>Remediation</option><option>Closed</option></select></label>
            <label className="form-wide"><span>Exception description</span><textarea required minLength="10" rows="5" placeholder="Describe the policy exception and why it is being requested..." value={exceptionForm.description} onChange={(event) => updateException("description", event.target.value)} /></label>
            {exceptionError && <div className="data-message error form-wide">{exceptionError}</div>}
            <div className="credit-form-actions form-wide"><button type="button" className="btn secondary" onClick={() => setShowExceptionForm(false)}>Cancel</button><button className="btn primary" disabled={savingException}><Sparkles size={15} />{savingException ? "Generating rationale..." : "Create Exception"}</button></div>
          </form>
        </Card>
      )}
      <Card className="compliance-runner-card" title="Run Generative AI Compliance Agent" sub="The Mistral agent retrieves policy evidence and independently classifies the selected credit request.">
        <form className="compliance-runner" onSubmit={runAgent}>
          <label>
            <span>Credit request</span>
            <select value={selectedRequest} disabled={loadingRequests || loadingStored || running} onChange={(event) => setSelectedRequest(event.target.value)}>
              {requests.map((request) => <option key={request.credit_request_number} value={request.credit_request_number}>{request.credit_request_number} - {request.borrower_name} - {request.facility}</option>)}
            </select>
          </label>
          <button className="btn primary" type="submit" disabled={!selectedRequest || loadingStored || running}><Play size={15} />{running ? "Submitting..." : "Submit"}</button>
        </form>
        {error && <div className="data-message error">{error}</div>}
      </Card>
      {!review && !running && !loadingStored && <div className="compliance-empty"><ShieldCheck size={28} /><h3>Select a request and submit it</h3><p>The first submission generates and stores the review. Later visits load the saved result.</p></div>}
      {loadingStored && <div className="compliance-empty agent-running"><Database size={28} /><h3>Loading saved review</h3><p>Checking for an existing GenAI compliance review...</p></div>}
      {running && <div className="compliance-empty agent-running"><Sparkles size={28} /><h3>Generative AI Compliance Agent is active</h3><p>Retrieving policy documents and reasoning over the selected credit proposal...</p></div>}
      {review && <>
        <Card title="Credit Proposal Inputs" className="proposal-card">
          <div className="proposal-inputs">
            <ProposalInput label="Credit Request" value={selected.credit_request_number} />
            <ProposalInput label="Borrower" value={selected.borrower_name} />
            <ProposalInput label="Borrower Rating" value={selected.rating} />
            <ProposalInput label="Facility" value={selected.facility} />
            <ProposalInput label="Requested Amount" value={money(selected.requested_amount / 1_000_000)} />
          </div>
        </Card>
        <div className="compliance-counts">
          <ComplianceCount icon={CheckCircle2} label="Pass" value={review.counts.PASS} tone="pass" />
          <ComplianceCount icon={AlertTriangle} label="Warning" value={review.counts.WARNING} tone="warning" />
          <ComplianceCount icon={ShieldAlert} label="Breach" value={review.counts.BREACH} tone="breach" />
        </div>
        <div className="layout compliance-grid">
          <Card title="AI Compliance Findings" className="table-card">
            <DataTable
              className="findings-table"
              headers={["Policy Clause", "Actual", "Threshold", "Variance", "Severity", "Evidence"]}
              rows={findingRows}
              render={(value, index, row) => index === 0 ? <div className="finding-clause"><strong>{value}</strong><small>{row[5].rationale}</small></div> : index === 4 ? <Badge>{value}</Badge> : index === 5 ? <button className="trace" title={row[5].evidence} onClick={() => tracePolicy(row[5])}>Trace <ExternalLink size={12} /></button> : value}
            />
          </Card>
          <Card title="Compliance Heatmap">
            <div className="heatmap">{review.heatmap.map((item) => <div key={item.policy_type} className={item.severity.toLowerCase()}>{item.policy_type}</div>)}</div>
            <div className="heat-key"><span><i className="pass" />Pass</span><span><i className="warning" />Warning</span><span><i className="breach" />Breach</span></div>
          </Card>
        </div>
        <ComplianceCopilot session={session} requestNumber={selected.credit_request_number} />
      </>}
    </>
  );
}

function ComplianceCopilot({ session, requestNumber }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setMessages([]); setQuestion(""); setError(""); }, [requestNumber]);
  const ask = async (event, suggestion = "") => {
    event?.preventDefault();
    const prompt = (suggestion || question).trim();
    if (!prompt || sending) return;
    setQuestion(""); setError(""); setMessages((current) => [...current, { role: "user", content: prompt }]); setSending(true);
    try {
      const response = await apiRequest("/api/compliance-review/copilot", { method: "POST", body: JSON.stringify({ credit_request_number: requestNumber, question: prompt }) }, session.token);
      setMessages((current) => [...current, { role: "assistant", content: response.answer }]);
    } catch (requestError) { setError(requestError.message); } finally { setSending(false); }
  };
  return (
    <Card title="Compliance Copilot" sub={`Answers are grounded only in the AI Compliance Findings table for ${requestNumber}.`} className="compliance-copilot" action={<button type="button" className="text-btn" onClick={() => setMessages([])}>Clear</button>}>
      <div className="compliance-chat" aria-live="polite">
        {!messages.length && <div className="chat-ai"><Sparkles size={18} /><p>Ask which policies were breached, why a warning was raised, what passed, or how to remediate the findings.</p></div>}
        {messages.map((message, index) => message.role === "user" ? <div className="chat-user" key={index}>{message.content}</div> : <div className="chat-ai" key={index}><Sparkles size={18} /><div className="chat-answer">{message.content}</div></div>)}
        {sending && <div className="chat-ai"><Sparkles size={18} /><p>Reviewing the findings...</p></div>}
      </div>
      {error && <div className="data-message error">{error}</div>}
      <div className="suggestions">{["What policies are breached?", "Show warnings", "What should be remediated?"].map((text) => <button type="button" key={text} disabled={sending} onClick={(event) => ask(event, text)}>{text}</button>)}</div>
      <form className="chat-input" onSubmit={ask}><input autoComplete="off" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about these findings..." disabled={sending} aria-label="Ask Compliance Copilot" /><button type="submit" disabled={sending || !question.trim()} aria-label="Send question"><Send size={16} /></button></form>
    </Card>
  );
}
