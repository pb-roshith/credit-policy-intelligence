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

export default function DataManufacturing({ session, notify }) {
  const [menuItem, setMenuItem] = useState("credit-requests");
  const [count, setCount] = useState(10);
  const [generating, setGenerating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [policyJob, setPolicyJob] = useState(null);
  const [creditRequests, setCreditRequests] = useState([]);
  const [selectedRequests, setSelectedRequests] = useState([]);
  const [loadingRequests, setLoadingRequests] = useState(false);

  useEffect(() => {
    apiRequest("/api/data-manufacturing/policy-pdfs/status", {}, session.token)
      .then(setPolicyJob)
      .catch(() => {});
  }, [session.token]);

  useEffect(() => {
    if (!policyJob || !["queued", "running"].includes(policyJob.status)) return undefined;
    const timer = setInterval(() => {
      const path = policyJob.job_id
        ? `/api/data-manufacturing/policy-pdfs/${policyJob.job_id}`
        : "/api/data-manufacturing/policy-pdfs/status";
      apiRequest(path, {}, session.token)
        .then((job) => {
          setPolicyJob(job);
          if (job.status === "completed") notify(job.message);
        })
        .catch((requestError) => setError(requestError.message));
    }, 2500);
    return () => clearInterval(timer);
  }, [policyJob?.job_id, policyJob?.status, session.token]);

  useEffect(() => {
    if (menuItem !== "exceptions") return undefined;
    let active = true;
    const controller = new AbortController();
    setLoadingRequests(true);
    setError("");
    apiRequest("/api/requests", { signal: controller.signal }, session.token)
      .then((items) => { if (active) setCreditRequests(items); })
      .catch((requestError) => { if (active) setError(requestError.message); })
      .finally(() => { if (active) setLoadingRequests(false); });
    return () => { active = false; controller.abort(); };
  }, [menuItem, session.token]);

  const generate = async (event) => {
    event.preventDefault();
    if (menuItem === "exceptions") {
      if (!selectedRequests.length) {
        setError("Select at least one credit request.");
        return;
      }
      setGenerating(true);
      setError("");
      try {
        const response = await apiRequest(
          "/api/data-manufacturing/exceptions",
          { method: "POST", body: JSON.stringify({ credit_request_numbers: selectedRequests }) },
          session.token,
        );
        setResult(response);
        setSelectedRequests([]);
        notify(response.message);
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setGenerating(false);
      }
      return;
    }
    if (menuItem === "policy-pdfs") {
      setGenerating(true);
      setError("");
      try {
        const job = await apiRequest(
          "/api/data-manufacturing/policy-pdfs",
          { method: "POST" },
          session.token,
        );
        setPolicyJob(job);
        setResult(job);
        notify(job.message);
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setGenerating(false);
      }
      return;
    }
    if (menuItem === "policy-controls") {
      const safeCount = Math.max(1, Math.min(5, Number(count) || 5));
      setCount(safeCount);
      setGenerating(true);
      setError("");
      try {
        const response = await apiRequest(
          "/api/data-manufacturing/policy-controls",
          {
            method: "POST",
            body: JSON.stringify({ controls_per_policy: safeCount }),
          },
          session.token,
        );
        setResult(response);
        notify(response.message);
      } catch (requestError) {
        setError(requestError.message);
      } finally {
        setGenerating(false);
      }
      return;
    }
    const maximum = menuItem === "credit-requests" ? 100 : 10;
    const safeCount = Math.max(1, Math.min(maximum, Number(count) || 1));
    setCount(safeCount);
    setGenerating(true);
    setError("");
    try {
      const response = await apiRequest(
        menuItem === "credit-requests"
          ? "/api/data-manufacturing/credit-requests"
          : "/api/data-manufacturing/borrower-exposure-history",
        {
          method: "POST",
          body: JSON.stringify(
            menuItem === "credit-requests"
              ? { count: safeCount }
              : { records_per_borrower: safeCount },
          ),
        },
        session.token,
      );
      setResult(response);
      notify(response.message);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setGenerating(false);
    }
  };
  return (
    <>
      <Heading page="manufacturing" />
      <div className="manufacturing-layout">
        <Card className="manufacturing-menu" title="Menu">
          <button
            type="button"
            className={menuItem === "credit-requests" ? "active" : ""}
            onClick={() => {
              setMenuItem("credit-requests");
              setResult(null);
              setError("");
            }}
          >
            <Database size={17} />
            <span>Generate Credit Requests</span>
            <ChevronRight size={15} />
          </button>
          <button
            type="button"
            className={menuItem === "borrower-history" ? "active" : ""}
            onClick={() => {
              setMenuItem("borrower-history");
              setCount((value) => Math.min(10, Number(value) || 10));
              setResult(null);
              setError("");
            }}
          >
            <BarChart3 size={17} />
            <span>Generate Borrower Exposure History</span>
            <ChevronRight size={15} />
          </button>
          <button
            type="button"
            className={menuItem === "exceptions" ? "active" : ""}
            onClick={() => {
              setMenuItem("exceptions");
              setSelectedRequests([]);
              setResult(null);
              setError("");
            }}
          >
            <AlertTriangle size={17} />
            <span>Generate Exceptions</span>
            <ChevronRight size={15} />
          </button>
          <button
            type="button"
            className={menuItem === "policy-controls" ? "active" : ""}
            onClick={() => {
              setMenuItem("policy-controls");
              setCount((value) => Math.min(5, Number(value) || 5));
              setResult(null);
              setError("");
            }}
          >
            <ShieldCheck size={17} />
            <span>Generate Policy Controls</span>
            <ChevronRight size={15} />
          </button>
          <button
            type="button"
            className={menuItem === "policy-pdfs" ? "active" : ""}
            onClick={() => {
              setMenuItem("policy-pdfs");
              setResult(null);
              setError("");
            }}
          >
            <BookOpen size={17} />
            <span>Generate Policy PDFs</span>
            <ChevronRight size={15} />
          </button>
        </Card>
        {menuItem === "credit-requests" && (
          <Card title="Generate Credit Requests" action={<Factory size={17} />}>
            <form className="manufacturing-form" onSubmit={generate}>
              <p>Create synthetic credit requests with geography assigned across supported regions. Records are inserted directly into the account's <code>credit_requests</code> table.</p>
              <label>
                <span>Number of credit requests</span>
                <input
                  type="number"
                  min="1"
                  max="100"
                  step="1"
                  value={count}
                  onChange={(event) => setCount(event.target.value)}
                  required
                />
                <small>Choose any value from 1 to 100.</small>
              </label>
              {error && <div className="data-message error">{error}</div>}
              {result && !error && (
                <div className="generation-result">
                  <CheckCircle2 size={18} />
                  <span>{result.message}. The Credit Requests tab will show them immediately.</span>
                </div>
              )}
              <div className="manufacturing-actions">
                <button className="btn primary" type="submit" disabled={generating}>
                  <Play size={15} />
                  {generating ? "Generating..." : "Generate Credit Requests"}
                </button>
                {result && (
                  <button className="btn secondary" type="button" onClick={() => { location.hash = "requests"; }}>
                    View Credit Requests
                    <ArrowRight size={15} />
                  </button>
                )}
              </div>
            </form>
          </Card>
        )}
        {menuItem === "borrower-history" && (
          <Card title="Generate Borrower Exposure History" action={<BarChart3 size={17} />}>
            <form className="manufacturing-form" onSubmit={generate}>
              <p>
                Create monthly facility-exposure records for every borrower in the Credit Requests table. The simulation assigns borrowers as current, delayed, or defaulted and stores changing outstanding balances in <code>credit_data.borrower_exposure_history</code>.
              </p>
              <label>
                <span>Records per borrower</span>
                <input
                  type="number"
                  min="1"
                  max="10"
                  step="1"
                  value={count}
                  onChange={(event) => setCount(event.target.value)}
                  required
                />
                <small>Choose 1-10 monthly records for each borrower.</small>
              </label>
              {error && <div className="data-message error">{error}</div>}
              {result && !error && (
                <div className="generation-result">
                  <CheckCircle2 size={18} />
                  <span>{result.message} across {result.borrower_count} borrowers.</span>
                </div>
              )}
              <div className="manufacturing-actions">
                <button className="btn primary" type="submit" disabled={generating}>
                  <Play size={15} />
                  {generating ? "Generating..." : "Generate Exposure History"}
                </button>
              </div>
            </form>
          </Card>
        )}
        {menuItem === "exceptions" && (
          <Card title="Generate Exceptions" action={<AlertTriangle size={17} />}>
            <form className="manufacturing-form exception-generator" onSubmit={generate}>
              <p>Select one or more existing credit requests. One account-scoped exception will be generated for each selection and displayed in Exception Management.</p>
              <div className="exception-selection-head">
                <label>
                  <input
                    type="checkbox"
                    checked={creditRequests.length > 0 && selectedRequests.length === creditRequests.length}
                    onChange={(event) => setSelectedRequests(event.target.checked ? creditRequests.map((item) => item.credit_request_number) : [])}
                    disabled={!creditRequests.length || loadingRequests || generating}
                  />
                  <span>Select all credit requests</span>
                </label>
                <strong>{selectedRequests.length} selected</strong>
              </div>
              <div className="exception-request-list" role="group" aria-label="Credit requests available for exception generation">
                {loadingRequests && <div className="data-message">Loading credit requests...</div>}
                {!loadingRequests && !creditRequests.length && !error && <div className="data-message">No credit requests are available. Generate credit requests first.</div>}
                {!loadingRequests && creditRequests.map((item) => {
                  const checked = selectedRequests.includes(item.credit_request_number);
                  return (
                    <label className={checked ? "selected" : ""} key={item.credit_request_number}>
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={generating}
                        onChange={() => setSelectedRequests((current) => checked
                          ? current.filter((number) => number !== item.credit_request_number)
                          : [...current, item.credit_request_number])}
                      />
                      <span>
                        <strong>{item.credit_request_number}</strong>
                        <small>{item.borrower_name}</small>
                      </span>
                      <span>{item.industry}</span>
                      <span>{money(Number(item.exposure) / 1000000)}</span>
                      <Badge>{item.status}</Badge>
                    </label>
                  );
                })}
              </div>
              {error && <div className="data-message error">{error}</div>}
              {result && !error && (
                <div className="generation-result">
                  <CheckCircle2 size={18} />
                  <span>{result.message}. They are now available in Exception Management.</span>
                </div>
              )}
              <div className="manufacturing-actions">
                <button className="btn primary" type="submit" disabled={generating || loadingRequests || !selectedRequests.length}>
                  <Play size={15} />
                  {generating ? "Generating..." : `Generate Exceptions (${selectedRequests.length})`}
                </button>
                {result && (
                  <button className="btn secondary" type="button" onClick={() => { location.hash = "exceptions"; }}>
                    View Exception Management
                    <ArrowRight size={15} />
                  </button>
                )}
              </div>
            </form>
          </Card>
        )}
        {menuItem === "policy-controls" && (
          <Card title="Generate Policy Controls" action={<ShieldCheck size={17} />}>
            <form className="manufacturing-form" onSubmit={generate}>
              <p>
                Manufacture controls for every policy document in the Policy Library and store
                their policy mapping, ownership, type, automation, frequency, effectiveness,
                status, testing, and assessment data in <code>credit_data.policy_controls</code>.
              </p>
              <label>
                <span>Controls per policy document</span>
                <input
                  type="number"
                  min="1"
                  max="5"
                  step="1"
                  value={count}
                  onChange={(event) => setCount(event.target.value)}
                  required
                />
                <small>Choose 1-5 controls for each available policy document.</small>
              </label>
              {error && <div className="data-message error">{error}</div>}
              {result && !error && (
                <div className="generation-result">
                  <CheckCircle2 size={18} />
                  <span>{result.message}. {result.control_count} controls are stored.</span>
                </div>
              )}
              <div className="manufacturing-actions">
                <button className="btn primary" type="submit" disabled={generating}>
                  <Play size={15} />
                  {generating ? "Generating..." : "Generate Policy Controls"}
                </button>
                {result && (
                  <button className="btn secondary" type="button" onClick={() => { sessionStorage.setItem("policyExplorerTab", "controls"); location.hash = "policy"; }}>
                    View Controls Register
                    <ArrowRight size={15} />
                  </button>
                )}
              </div>
            </form>
          </Card>
        )}
        {menuItem === "policy-pdfs" && (
          <Card title="Generate Policy PDFs" action={<BookOpen size={17} />}>
            <form className="manufacturing-form" onSubmit={generate}>
              <p>
                Generate 25 synthetic credit policy PDFs and add the 10 documents from
                the policy document folder to one shared Mistral library. The resulting
                35-file Policy Intelligence library is available to every user role.
              </p>
              <div className="policy-generation-facts">
                <span><strong>25</strong> generated PDFs</span>
                <span><strong>10</strong> imported documents</span>
                <span><strong>10+</strong> pages each</span>
                <span><strong>Sequential</strong> processing</span>
              </div>
              {policyJob && policyJob.status !== "idle" && (
                <div className={`policy-job-status ${policyJob.status}`}>
                  <div>
                    <strong>{policyJob.message}</strong>
                    {policyJob.current_policy && <small>{policyJob.current_policy}</small>}
                  </div>
                  <span>{policyJob.completed_documents || 0} / {policyJob.total_documents || 35}</span>
                  <progress
                    max={policyJob.total_documents || 35}
                    value={policyJob.completed_documents || 0}
                  />
                </div>
              )}
              {policyJob?.error && <div className="data-message error">{policyJob.error}</div>}
              {error && <div className="data-message error">{error}</div>}
              <div className="manufacturing-actions">
                <button
                  className="btn primary"
                  type="submit"
                  disabled={generating || ["queued", "running"].includes(policyJob?.status)}
                >
                  <Play size={15} />
                  {["queued", "running"].includes(policyJob?.status)
                    ? "Generating Policies..."
                    : policyJob?.completed_documents >= 35
                      ? "Policies Already Generated"
                      : "Generate 25 PDFs + Add 10 Documents"}
                </button>
                {policyJob?.completed_documents >= 35 && (
                  <button className="btn secondary" type="button" onClick={() => { location.hash = "policy"; }}>
                    View Policy Library
                    <ArrowRight size={15} />
                  </button>
                )}
              </div>
            </form>
          </Card>
        )}
      </div>
    </>
  );
}
