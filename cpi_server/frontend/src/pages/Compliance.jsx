import React, { useEffect, useRef, useState } from "react";
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
  ChevronDown,
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
import {assessmentText,displayProvenance} from '../api/displayText';
import { loadRequestList } from "../api/requestList";
import { assessmentFindings } from "../api/assessmentResult";
import GraphAssessmentTrace from "../components/GraphAssessmentTrace";
import { SavedAssessmentGraph } from "../components/AssessmentGraphViews";
import ComplianceFindingsTable from "../components/ComplianceFindingsTable";
import {filterByRuleCategory} from "../api/policyRuleCategory";
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
  const canCreateException = session.user.role === "relationship_manager";
  const agentRequest = useRef(null);
  const [requests, setRequests] = useState([]);
  const [selectedRequest, setSelectedRequest] = useState("");
  const [review, setReview] = useState(null);
  const [policiesExpanded, setPoliciesExpanded] = useState(false);
  useEffect(() => { setPoliciesExpanded(false); }, [selectedRequest]);
  const [assessmentPage,setAssessmentPage]=useState(1);
  const [assessmentGraphOpen, setAssessmentGraphOpen] = useState(false);
  const [policyFilter,setPolicyFilter]=useState("");
  const [ruleCategory,setRuleCategory]=useState("ALL");
  useEffect(()=>{setRuleCategory("ALL");},[selectedRequest]);
  useEffect(()=>{setPolicyFilter("");},[review,selectedRequest]);
  useEffect(()=>{setAssessmentPage(1);},[policyFilter,ruleCategory]);
  useEffect(()=>{setAssessmentPage(1);},[review,selectedRequest]);
  const [listError, setListError] = useState("");
  const [loadingRequests, setLoadingRequests] = useState(true);
  const [loadingStored, setLoadingStored] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [evidenceFinding, setEvidenceFinding] = useState(null);
  useEffect(()=>{setEvidenceFinding(null);},[selectedRequest,review]);
  useEffect(() => () => agentRequest.current?.abort(), []);
  const [showExceptionForm, setShowExceptionForm] = useState(false);
  const [savingException, setSavingException] = useState(false);
  const [exceptionError, setExceptionError] = useState("");
  const [exceptionForm, setExceptionForm] = useState({ exception_type: "", clause_code: "", owner: session.user.user_id, due_date: "", status: "Active", description: "" });

  useEffect(() => {
    let active = true;
    let generation = 0;
    setRequests([]);
    setSelectedRequest("");
    const refresh = async () => {
      const currentGeneration = ++generation;
      setLoadingRequests(true);
      try {
        const { rows, error: sourceError } = await loadRequestList(session.token, apiRequest);
        if (!active || currentGeneration !== generation) return;
        setRequests(rows);
        setListError(sourceError);
        const savedRequest = sessionStorage.getItem(`complianceReviewSelection:${session.user.user_id}`);
        setSelectedRequest(current =>
          rows.some(row => row.credit_request_number === current) ? current
          : rows.some(row => row.credit_request_number === savedRequest) ? savedRequest
          : rows[0]?.credit_request_number || "");
      } catch (requestError) {
        if (active && currentGeneration === generation) setListError(requestError.message);
      } finally {
        if (active && currentGeneration === generation) setLoadingRequests(false);
      }
    };
    refresh();
    const refreshWhenVisible = () => { if (document.visibilityState === "visible") refresh(); };
    document.addEventListener("visibilitychange", refreshWhenVisible);
    window.addEventListener("focus", refreshWhenVisible);
    return () => {
      active = false;
      document.removeEventListener("visibilitychange", refreshWhenVisible);
      window.removeEventListener("focus", refreshWhenVisible);
    };
  }, [session.token, session.user.user_id]);

  useEffect(() => {
    if (!selectedRequest) return undefined;
    let active = true;
    sessionStorage.setItem(`complianceReviewSelection:${session.user.user_id}`, selectedRequest);
    setReview(null);
    setError("");
    setLoadingStored(true);
    const tracedReview = sessionStorage.getItem("complianceTraceReviewId");
    sessionStorage.removeItem("complianceTraceReviewId");
    apiRequest(tracedReview ? `/api/compliance-review/history/${encodeURIComponent(tracedReview)}` : `/api/compliance-review/${encodeURIComponent(selectedRequest)}/latest`, {}, session.token)
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
    const controller = new AbortController();
    agentRequest.current = controller;
    try {
      const result = await apiRequest(
        "/api/compliance-review/run",
        { method: "POST", signal: controller.signal, body: JSON.stringify({ credit_request_number: selectedRequest }) },
        session.token,
      );
      if (controller.signal.aborted) return;
      setReview(result);
      notify(`${result.agent} completed ${selectedRequest}`);
    } catch (requestError) {
      if (!controller.signal.aborted) setError(requestError.message);
    } finally {
      if (!controller.signal.aborted) setRunning(false);
      if (agentRequest.current === controller) agentRequest.current = null;
    }
  };

  const tracePolicy = (finding) => {
    if (!finding.policy_id) {
      notify(`No policy summary is mapped to ${finding.policy_clause}`);
      return;
    }
    if (finding.matching_trace) {
      sessionStorage.setItem("policyEvidencePolicy", String(finding.policy_id));
      sessionStorage.setItem("policyEvidenceClause", String(finding.clause_id));
      sessionStorage.setItem("riskKnowledgeView", "Policy Evidence");
      sessionStorage.setItem("policyExplorerTab", "knowledge");
      location.hash = "policy";
      return;
    }
    sessionStorage.setItem("complianceTracePolicyId", String(finding.policy_id));
    sessionStorage.removeItem("policyExplorerTab");
    location.hash = "policy";
  };

  const openExceptionForm = () => {
    const finding = review?.findings?.find((item) => item.severity === "BREACH") || review?.findings?.find((item) => item.severity === "WARNING") || review?.findings?.[0];
    const clauseCode = finding?.policy_clause?.match(/[A-Z]+-\d+(?:\.\d+)*/)?.[0] || String(finding?.source_clause||finding?.policy_clause||'').slice(0, 40) || "";
    const due = new Date();
    due.setDate(due.getDate() + 30);
    setExceptionForm({
      semantic_rule_id: finding?.rule_id,
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
      notify(created.rationale?.generation_notice || `${created.id} created with AI provider-generated rationale`);
      location.hash = "exceptions";
    } catch (requestError) {
      setExceptionError(requestError.message);
    } finally {
      setSavingException(false);
    }
  };

  const selected = review?.credit_request;
  const displayedFindings = assessmentFindings(review);
  const resultCount = status => displayedFindings.filter(finding => finding.displayResult === status).length;
  const findingRows = filterByRuleCategory(displayedFindings,ruleCategory).filter(finding =>
    (!policyFilter || String(finding.policy_id) === policyFilter)).map((finding) => [
    finding.rule_name || finding.policy_clause, finding.actual, finding.expected_condition || finding.threshold || "Source requirement needs correction", finding.variance,
    finding.displayResult, finding,
  ]);
  const assessmentPages=Math.max(1,Math.ceil(findingRows.length/10));
  const currentAssessmentPage=Math.min(assessmentPage,assessmentPages);
  return (
    <>
      <Heading page="compliance">
        <button className="btn tertiary" onClick={() => (location.hash = "requests")}>Back to Requests</button>
        {selectedRequest && <button className="btn secondary" onClick={() => {
          sessionStorage.setItem("exceptionRegistrySearch", selectedRequest);
          location.hash = "exceptions";
        }}>View Request Exceptions</button>}
        {selectedRequest && <button className="btn secondary" onClick={() => {
          sessionStorage.setItem(`simulatorRequestSelection:${session.user.user_id}`, selectedRequest);
          location.hash = "simulator";
        }}>Simulate Request</button>}
        {canCreateException && <button className="btn primary" disabled={!review} onClick={openExceptionForm}><Plus size={14} />Create Exception</button>}
      </Heading>

      {canCreateException && showExceptionForm && (
        <Card className="request-form-card" title="Create Policy Exception" action={<button type="button" className="icon-button" aria-label="Close form" onClick={() => setShowExceptionForm(false)}><X size={17} /></button>}>
          <form autoComplete="off" className="credit-request-form" onSubmit={submitException}>
            <div className="credit-form-note form-wide"><Sparkles size={16} /><span>The exception ID, exposure, and severity are generated automatically. AI provider will create the business justification, risk implications, remediation, and escalation guidance from your description and this compliance review.</span></div>
            <label><span>Credit request ID</span><input autoComplete="off" value={selectedRequest} readOnly /></label>
            <label><span>Exception type</span><input required autoComplete="off" value={exceptionForm.exception_type} onChange={(event) => updateException("exception_type", event.target.value)} /></label>
            <label className="form-wide"><span>Matched policy rule</span><select required value={exceptionForm.semantic_rule_id||''} onChange={event=>{const f=review.findings.find(item=>item.rule_id===event.target.value);setExceptionForm(current=>({...current,semantic_rule_id:f.rule_id,clause_code:String(f.source_clause||f.policy_clause).slice(0,40),exception_type:f.policy_type||'Policy'}))}}>{review.findings.map(f=><option key={f.rule_id} value={f.rule_id}>{f.policy_name}: {f.rule_name}</option>)}</select></label>
            <label><span>Source policy clause</span><input required readOnly value={exceptionForm.clause_code}/></label>
            <label><span>Owner</span><input required autoComplete="off" value={exceptionForm.owner} onChange={(event) => updateException("owner", event.target.value)} /></label>
            <label><span>Due date</span><input required type="date" min={new Date().toISOString().slice(0, 10)} value={exceptionForm.due_date} onChange={(event) => updateException("due_date", event.target.value)} /></label>
            <label><span>Status</span><select value={exceptionForm.status} onChange={(event) => updateException("status", event.target.value)}><option>Active</option><option>Pending Approval</option></select></label>
            <label className="form-wide"><span>Exception description</span><textarea required minLength="10" rows="5" placeholder="Describe the policy exception and why it is being requested..." value={exceptionForm.description} onChange={(event) => updateException("description", event.target.value)} /></label>
            {exceptionError && <div className="data-message error form-wide">{exceptionError}</div>}
            <div className="credit-form-actions form-wide"><button type="button" className="btn secondary" onClick={() => setShowExceptionForm(false)}>Cancel</button><button className="btn primary" disabled={savingException}><Sparkles size={15} />{savingException ? "Generating rationale..." : "Create Exception"}</button></div>
          </form>
        </Card>
      )}
      <Card className="compliance-runner-card" title="Run Policy Rule Assessment">
        <form autoComplete="off" className="compliance-runner" onSubmit={runAgent}>
          <label>
            <span>Credit request</span>
            <select value={selectedRequest} disabled={loadingRequests || loadingStored || running} onChange={(event) => setSelectedRequest(event.target.value)}>
              {!requests.length && <option value="">{loadingRequests ? "Loading credit requests..." : "No credit requests available"}</option>}
              {requests.map((request) => <option key={request.credit_request_number} value={request.credit_request_number}>{request.credit_request_number} - {request.borrower_name} - {request.facility}</option>)}
            </select>
          </label>
          <div className="compliance-runner-footer">
          <div className="compliance-runner-actions">
          <button className="btn primary" type="submit" disabled={!selectedRequest || loadingRequests || loadingStored || running}><Play size={15} />{running ? "Submitting..." : "Run assessment"}</button>
          </div>
          </div>
        </form>
        {listError && <div className="data-message error">{listError}</div>}
        {error && <div className="data-message error">{error}</div>}
      </Card>
      {!review && !running && !loadingStored && <div className="compliance-empty"><ShieldCheck size={28} /><h3>Select a request and submit it</h3><p>The first submission evaluates current rules and stores the review. Later visits load the saved result.</p></div>}
      {loadingStored && <div className="compliance-empty agent-running"><Database size={28} /><h3>Loading saved review</h3><p>Checking for an existing GenAI compliance review...</p></div>}
      {running && <div className="compliance-empty agent-running"><Sparkles size={28} /><h3>Policy assessment is running</h3><p>Traversing the current knowledge graph, matching request facts, then explaining the retrieved rules...</p></div>}
      {review&&<div className="compliance-counts">
        <ComplianceCount icon={CheckCircle2} label="Pass" value={resultCount("Pass")} tone="pass" />
        <ComplianceCount icon={AlertTriangle} label="Warning" value={resultCount("Warning")} tone="warning" />
        <ComplianceCount icon={ShieldAlert} label="Breach" value={resultCount("Breach")} tone="breach" />
        <ComplianceCount icon={AlertTriangle} label="Needs data / review" value={resultCount("Unable to Assess")+resultCount("Manual Review Required")} tone="unable-to-assess" />
      </div>}
      {review?.assessment_scope === 'current-semantic-graph' && <>
        <Card title="Assessment graph" sub="Follow the request facts through applicable policies, rule outcomes, and registered exceptions." action={
          <button type="button" className="btn secondary" aria-expanded={assessmentGraphOpen} onClick={() => setAssessmentGraphOpen(value => !value)}>
            {assessmentGraphOpen ? 'Close graph' : 'Open graph'}
          </button>
        }>
          {assessmentGraphOpen && <SavedAssessmentGraph key={review.review_id} requestId={selectedRequest} reviewId={review.review_id} />}
        </Card>
        <GraphAssessmentTrace key={`matching:${review.review_id||selectedRequest}`} review={review} onEvidence={tracePolicy}/>
      </>}
      {review&&review.assessment_scope!=='current-semantic-graph'&&<p>This saved review uses the earlier rule inventory. Run assessment to match this request against the current knowledge graph.</p>}
      {review?.applicability_report?.policy_mappings && <Card className="compliance-applicable-policies" title="Applicable policies" sub={`${review.applicability_report.policy_mappings.length} policies mapped to this credit request`} action={
        <button type="button" className="btn secondary" aria-expanded={policiesExpanded} aria-controls="applicable-policy-list" onClick={() => setPoliciesExpanded(value => !value)}>
          {policiesExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}{policiesExpanded ? "Collapse" : "Expand"}
        </button>
      }>
        <div id="applicable-policy-list" className="applicable-policy-list" hidden={!policiesExpanded}>
          {review.applicability_report.policy_mappings.map(policy => <div className="applicable-policy-row" key={policy.policy_id}>
            <span className="applicable-policy-icon"><BookOpen size={18} /></span>
            <strong>{policy.policy_name}</strong>
            <span className="applicable-policy-rule-count">{policy.rule_count} {Number(policy.rule_count) === 1 ? "rule" : "rules"}</span>
          </div>)}
          {!review.applicability_report.policy_mappings.length && <p className="applicable-policy-empty">No policies confirmed applicable.</p>}
          {!!review.applicability_report.unresolved_policy_count && <p className="applicable-policy-empty">{review.applicability_report.unresolved_policy_count} policies need scope review or request information. This assessment is incomplete until their applicability is resolved.</p>}
        </div>
      </Card>}
      {review&&<Card title="Applicable policy rule findings" className="table-card assessment-results">
        {review.assessment_scope!=="current-semantic-graph" && review.cached && !review.actual_generator_version && review.findings?.some(finding => finding.actual === "Unavailable") && <p>This saved assessment does not contain actual values. Click Run assessment to generate actual values and compare them with the thresholds.</p>}

        <div className="button-row assessment-filters">
          <label>Rule category<select aria-label="Filter findings by rule category" value={ruleCategory} onChange={event=>setRuleCategory(event.target.value)}><option value="ALL">All rules</option><option value="QUALITATIVE">Qualitative</option><option value="QUANTITATIVE">Quantitative</option></select></label>
          <select aria-label="Filter findings by policy" value={policyFilter} onChange={event=>setPolicyFilter(event.target.value)}>
            <option value="">All applicable policies</option>
            {(review.applicability_report?.policy_mappings || []).map(policy=><option key={policy.policy_id} value={policy.policy_id}>{policy.policy_name} ({policy.rule_count})</option>)}
          </select>
        </div>
        <ComplianceFindingsTable rows={findingRows.slice((currentAssessmentPage-1)*10,currentAssessmentPage*10)} onPolicy={tracePolicy} onEvidence={setEvidenceFinding}/>
        {!findingRows.length&&<p className="assessment-empty">No applicable rules match the selected filters.</p>}
        <div className="applicability-pagination assessment-pagination"><span>{findingRows.length?`${(currentAssessmentPage-1)*10+1}-${Math.min(currentAssessmentPage*10,findingRows.length)} of ${findingRows.length} findings`:"0 findings"} | Page {currentAssessmentPage} of {assessmentPages}</span><button type="button" className="btn secondary" disabled={currentAssessmentPage<=1} onClick={()=>setAssessmentPage(currentAssessmentPage-1)}>Previous</button><button type="button" className="btn secondary" disabled={currentAssessmentPage>=assessmentPages} onClick={()=>setAssessmentPage(currentAssessmentPage+1)}>Next</button></div>
      </Card>}
      {evidenceFinding&&<Card title="Rule evidence and matching trace" action={<button className="btn secondary" onClick={()=>setEvidenceFinding(null)}>Close</button>}>
        {evidenceFinding.matching_trace&&<><p>{assessmentText(evidenceFinding.explanation)}</p><blockquote>{evidenceFinding.evidence}</blockquote><p>Graph path: {evidenceFinding.matching_trace.graph_path.join(' -> ')}</p>{evidenceFinding.metric_checks.map((c,i)=><p key={i}>{c.metric}: {c.actual??'Unavailable'} {c.unit} ? {c.operator} {c.threshold} {c.unit}</p>)}{!!evidenceFinding.missing_inputs.length&&<p>Needs verification: {evidenceFinding.missing_inputs.join('; ')}</p>}</>}
        <p>{evidenceFinding.rule_name} · {evidenceFinding.actual_data_resolution?.resolution_status || (evidenceFinding.matching_trace?"Knowledge graph assessment":"Legacy assessment")}</p>
        {evidenceFinding.matching_trace&&<details><summary>Request fact sources</summary>{evidenceFinding.evidence_references.filter(e=>e.key!=='policy_clause').map((e,i)=><div key={i}><strong>{e.key}: {JSON.stringify(e.value)}</strong><p>{assessmentText(e.source)} - {e.reference}</p>{e.provenance?.as_of_date&&<p>As of {e.provenance.as_of_date}</p>}</div>)}</details>}
        {(evidenceFinding.actual_data_resolution?.resolved_fields || []).map((field,index)=><div key={index}>
          <strong>{field.attribute_name}: {JSON.stringify(field.value)} {field.unit}</strong>
          <p>{assessmentText(field.provenance.source_type)} · As of {field.as_of_date} · {assessmentText(field.provenance.verification_status)} · Confidence {field.provenance.confidence ?? "Not applicable"}</p>
          <p>Reference: {field.provenance.source_identifier || "See calculation inputs"}{field.provenance.source_document_id?` · Document ${field.provenance.source_document_id}`:""}{field.provenance.source_page?` · Page ${field.provenance.source_page}`:""}{field.provenance.source_section?` · ${field.provenance.source_section}`:""}</p>
          <details><summary>Evidence and provenance</summary><pre>{JSON.stringify(displayProvenance(field.provenance),null,2)}</pre></details>
        </div>)}
        {!evidenceFinding.actual_data_resolution&&<pre>{JSON.stringify(displayProvenance(evidenceFinding.evidence_references),null,2)}</pre>}
        {evidenceFinding.actual_data_resolution?.actual_provenance&&<details><summary>Observed value calculation and input lineage</summary><pre>{JSON.stringify(displayProvenance(evidenceFinding.actual_data_resolution.actual_provenance),null,2)}</pre></details>}
      </Card>}
      {review&&<ComplianceCopilot key={`copilot:${review.review_id||selectedRequest}`} session={session} requestNumber={selectedRequest} />}
    </>
  );
}

function ComplianceCopilot({ session, requestNumber }) {
  const activeRequest = useRef(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    activeRequest.current?.abort();
    setMessages([]); setQuestion(""); setError("");
    return () => activeRequest.current?.abort();
  }, [requestNumber]);
  const ask = async (event, suggestion = "") => {
    event?.preventDefault();
    const prompt = (suggestion || question).trim();
    if (!prompt || sending) return;
    setQuestion(""); setError(""); setMessages((current) => [...current, { role: "user", content: prompt }]); setSending(true);
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      const response = await apiRequest("/api/compliance-review/copilot", { method: "POST", signal: controller.signal, body: JSON.stringify({ credit_request_number: requestNumber, question: prompt }) }, session.token);
      if (!controller.signal.aborted) setMessages((current) => [...current, { role: "assistant", content: response.answer }]);
    } catch (requestError) {
      if (!controller.signal.aborted) {
        setError(requestError.status >= 500
          ? "Compliance Copilot could not complete the AI request. Please try again shortly."
          : requestError.message);
        setQuestion(prompt);
      }
    } finally {
      if (!controller.signal.aborted) setSending(false);
      if (activeRequest.current === controller) activeRequest.current = null;
    }
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
      <form autoComplete="off" className="chat-input" onSubmit={ask}><input autoComplete="off" minLength={2} maxLength={1000} value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about these findings..." disabled={sending} aria-label="Ask Compliance Copilot" /><button type="submit" disabled={sending || question.trim().length < 2} aria-label="Send question"><Send size={16} /></button></form>
    </Card>
  );
}
