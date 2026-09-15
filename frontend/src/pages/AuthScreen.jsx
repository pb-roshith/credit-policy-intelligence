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
import { EXCEPTIONS, META, POLICY_TYPE_ORDER, policyDisplayName } from "../config";
import { AuthField, Badge, Bars, Card, DataTable, DEFAULT_PASSWORD_POLICY, Heading, Insight, LineChart, Metric, NO_CLIPBOARD, PasswordPolicy, SecretInput, money, passwordRules } from "../components/ui";

export default function AuthScreen({ onAuthenticated }) {
  const [view, setView] = useState("login");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [recoveryQuestions, setRecoveryQuestions] = useState([]);
  const [passwordPolicy, setPasswordPolicy] = useState(DEFAULT_PASSWORD_POLICY);
  const [login, setLogin] = useState({ user_id: "", password: "" });
  const [registration, setRegistration] = useState({
    user_id: "",
    password: "",
    confirm: "",
    role: "relationship_manager",
    security_answers: Array.from({ length: 3 }, () => ({ selection: "", custom: "", answer: "" })),
  });
  const [reset, setReset] = useState({ user_id: "", password: "", confirm: "", answers: [] });

  useEffect(() => {
    apiRequest("/api/auth/security-questions")
      .then((data) => setQuestions(data.questions))
      .catch(() => setQuestions([]));
    apiRequest("/api/auth/password-policy")
      .then(setPasswordPolicy)
      .catch(() => setPasswordPolicy(DEFAULT_PASSWORD_POLICY));
  }, []);

  const changeView = (next) => {
    setView(next);
    setMessage(null);
    setRecoveryQuestions([]);
  };
  const submitLogin = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const data = await apiRequest("/api/auth/login", { method: "POST", body: JSON.stringify(login) });
      onAuthenticated(data);
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  };
  const updateSecurity = (index, key, value) => {
    setRegistration((current) => ({
      ...current,
      security_answers: current.security_answers.map((entry, i) => i === index ? { ...entry, [key]: value } : entry),
    }));
  };
  const submitRegistration = async (event) => {
    event.preventDefault();
    setMessage(null);
    if (registration.password !== registration.confirm) {
      return setMessage({ type: "error", text: "Passwords do not match" });
    }
    if (!passwordRules(passwordPolicy, registration.user_id).every(([, test]) => test(registration.password))) {
      return setMessage({ type: "error", text: "Please satisfy every password requirement" });
    }
    const security_answers = registration.security_answers.map((entry) => ({
      question: entry.selection === "custom" ? entry.custom.trim() : entry.selection,
      answer: entry.answer.trim(),
    }));
    if (security_answers.some((entry) => !entry.question || !entry.answer)) {
      return setMessage({ type: "error", text: "Complete all three security questions and answers" });
    }
    setBusy(true);
    try {
      const data = await apiRequest("/api/auth/register", {
        method: "POST",
        body: JSON.stringify({ user_id: registration.user_id, password: registration.password, role: registration.role, security_answers }),
      });
      setLogin({ user_id: registration.user_id, password: "" });
      changeView("login");
      setMessage({ type: "success", text: data.message });
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  };
  const loadRecoveryQuestions = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const data = await apiRequest(`/api/auth/recovery/${encodeURIComponent(reset.user_id)}`);
      setRecoveryQuestions(data.questions);
      setReset((current) => ({ ...current, answers: data.questions.map(() => "") }));
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  };
  const submitReset = async (event) => {
    event.preventDefault();
    setMessage(null);
    if (reset.password !== reset.confirm) return setMessage({ type: "error", text: "Passwords do not match" });
    if (!passwordRules(passwordPolicy, reset.user_id).every(([, test]) => test(reset.password))) return setMessage({ type: "error", text: "Please satisfy every password requirement" });
    setBusy(true);
    try {
      const data = await apiRequest("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({
          user_id: reset.user_id,
          password: reset.password,
          security_answers: recoveryQuestions.map((question, index) => ({ question, answer: reset.answers[index] })),
        }),
      });
      setLogin({ user_id: reset.user_id, password: "" });
      changeView("login");
      setMessage({ type: "success", text: data.message });
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <section className="auth-intro">
        <div className="auth-logo">tcs</div>
        <p>Credit Policy Intelligence</p>
        <h1>Decisions backed by policy, insight, and control.</h1>
        <span>Secure access for Relationship Managers and Credit Analysts.</span>
      </section>
      <section className="auth-panel">
        <div className={`auth-card ${view === "register" ? "wide" : ""}`}>
          <div className="auth-card-head">
            <span className="auth-icon">{view === "register" ? <UserPlus /> : view === "forgot" ? <KeyRound /> : <LockKeyhole />}</span>
            <div>
              <h2>{view === "register" ? "Create an account" : view === "forgot" ? "Reset your password" : "Welcome back"}</h2>
              <p>{view === "register" ? "Your account will require administrator approval." : view === "forgot" ? "Verify your three saved security answers." : "Sign in to your secure workspace."}</p>
            </div>
          </div>
          {message && <div className={`auth-message ${message.type}`}>{message.text}</div>}

          {view === "login" && (
            <form onSubmit={submitLogin} className="auth-form">
              <AuthField label="User ID"><input {...NO_CLIPBOARD} autoFocus required autoComplete="username" value={login.user_id} onChange={(e) => setLogin({ ...login, user_id: e.target.value })} placeholder="Enter your user ID" /></AuthField>
              <AuthField label="Password"><SecretInput required autoComplete="current-password" value={login.password} onChange={(e) => setLogin({ ...login, password: e.target.value })} placeholder="Enter your password" /></AuthField>
              <button className="auth-link forgot-link" type="button" onClick={() => changeView("forgot")}>Forgot password?</button>
              <button className="btn primary auth-submit" disabled={busy}>{busy ? "Signing in..." : "Sign in"}<ArrowRight size={16} /></button>
              <div className="auth-divider"><span>New to the platform?</span></div>
              <button className="btn secondary auth-submit" type="button" onClick={() => changeView("register")}><UserPlus size={16} />Create new user</button>
            </form>
          )}

          {view === "register" && (
            <form onSubmit={submitRegistration} className="auth-form">
              <div className="auth-grid">
                <AuthField label="User ID"><input {...NO_CLIPBOARD} required minLength="3" maxLength="64" value={registration.user_id} onChange={(e) => setRegistration({ ...registration, user_id: e.target.value })} placeholder="Choose a unique user ID" /></AuthField>
                <AuthField label="Role"><select required value={registration.role} onChange={(e) => setRegistration({ ...registration, role: e.target.value })}><option value="relationship_manager">Relationship Manager</option><option value="credit_analyst">Credit Analyst</option></select></AuthField>
                <AuthField label="Password"><SecretInput required maxLength={passwordPolicy.maximum_length} autoComplete="new-password" value={registration.password} onChange={(e) => setRegistration({ ...registration, password: e.target.value })} placeholder="Create a password" /></AuthField>
                <AuthField label="Confirm password"><SecretInput required maxLength={passwordPolicy.maximum_length} autoComplete="new-password" value={registration.confirm} onChange={(e) => setRegistration({ ...registration, confirm: e.target.value })} placeholder="Re-enter your password" /></AuthField>
              </div>
              <PasswordPolicy password={registration.password} userId={registration.user_id} policy={passwordPolicy} />
              <div className="security-section">
                <div><h3>Security questions</h3><p>All three answers are required for password recovery.</p></div>
                {registration.security_answers.map((entry, index) => (
                  <div className={`security-row ${entry.selection === "custom" ? "custom" : ""}`} key={index}>
                    <span>{index + 1}</span>
                    <select required value={entry.selection} onChange={(e) => updateSecurity(index, "selection", e.target.value)}><option value="">Select a question</option>{questions.map((question) => <option key={question} value={question}>{question}</option>)}<option value="custom">Custom question</option></select>
                    {entry.selection === "custom" && <input required maxLength="200" value={entry.custom} onChange={(e) => updateSecurity(index, "custom", e.target.value)} placeholder="Enter your custom question" />}
                    <SecretInput required maxLength="200" autoComplete="off" value={entry.answer} onChange={(e) => updateSecurity(index, "answer", e.target.value)} placeholder="Your answer" />
                  </div>
                ))}
              </div>
              <button className="btn primary auth-submit" disabled={busy}>{busy ? "Creating..." : "Create account"}</button>
              <button className="auth-link" type="button" onClick={() => changeView("login")}>Back to sign in</button>
            </form>
          )}

          {view === "forgot" && (
            <form onSubmit={recoveryQuestions.length ? submitReset : loadRecoveryQuestions} className="auth-form">
              <AuthField label="User ID"><input {...NO_CLIPBOARD} required disabled={recoveryQuestions.length > 0} value={reset.user_id} onChange={(e) => setReset({ ...reset, user_id: e.target.value })} placeholder="Enter your user ID" /></AuthField>
              {recoveryQuestions.map((question, index) => <AuthField label={question} key={question}><SecretInput required autoComplete="off" value={reset.answers[index] || ""} onChange={(e) => setReset({ ...reset, answers: reset.answers.map((answer, i) => i === index ? e.target.value : answer) })} placeholder="Your answer" /></AuthField>)}
              {recoveryQuestions.length > 0 && <><AuthField label="New password"><SecretInput required maxLength={passwordPolicy.maximum_length} autoComplete="new-password" value={reset.password} onChange={(e) => setReset({ ...reset, password: e.target.value })} /></AuthField><AuthField label="Confirm new password"><SecretInput required maxLength={passwordPolicy.maximum_length} autoComplete="new-password" value={reset.confirm} onChange={(e) => setReset({ ...reset, confirm: e.target.value })} /></AuthField><PasswordPolicy password={reset.password} userId={reset.user_id} policy={passwordPolicy} /></>}
              <button className="btn primary auth-submit" disabled={busy}>{busy ? "Please wait..." : recoveryQuestions.length ? "Reset password & unlock" : "Continue"}</button>
              <button className="auth-link" type="button" onClick={() => changeView("login")}>Back to sign in</button>
            </form>
          )}
        </div>
      </section>
    </div>
  );
}
