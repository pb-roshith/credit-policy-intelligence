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
import { AuthField, Badge, Bars, Card, DataTable, DEFAULT_PASSWORD_POLICY, Heading, Insight, LineChart, Metric, NO_CLIPBOARD, PasswordPolicy, SecretInput, money, passwordRules } from "../components/ui";

export default function UserProfile({ session, onLogout }) {
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState([]);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);
  const [passwordPolicy, setPasswordPolicy] = useState(DEFAULT_PASSWORD_POLICY);
  const displayRole = session.user.role
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

  useEffect(() => {
    apiRequest(`/api/auth/recovery/${encodeURIComponent(session.user.user_id)}`)
      .then((data) => {
        setQuestions(data.questions);
        setAnswers(data.questions.map(() => ""));
      })
      .catch((error) => setMessage({ type: "error", text: error.message }));
    apiRequest("/api/auth/password-policy")
      .then(setPasswordPolicy)
      .catch(() => setPasswordPolicy(DEFAULT_PASSWORD_POLICY));
  }, [session.user.user_id]);

  const changePassword = async (event) => {
    event.preventDefault();
    setMessage(null);
    if (password !== confirm) {
      setMessage({ type: "error", text: "Passwords do not match" });
      return;
    }
    if (!passwordRules(passwordPolicy, session.user.user_id).every(([, test]) => test(password))) {
      setMessage({ type: "error", text: "Please satisfy every password requirement" });
      return;
    }
    setBusy(true);
    try {
      const data = await apiRequest("/api/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({
          user_id: session.user.user_id,
          password,
          security_answers: questions.map((question, index) => ({ question, answer: answers[index] })),
        }),
      });
      setPassword("");
      setConfirm("");
      setAnswers(questions.map(() => ""));
      setMessage({ type: "success", text: data.message });
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <Heading page="profile" />
      <div className="profile-layout">
        <Card title="Account details" className="profile-summary">
          <div className="profile-avatar">{session.user.user_id.slice(0, 2).toUpperCase()}</div>
          <dl>
            <div><dt>User ID</dt><dd>{session.user.user_id}</dd></div>
            <div><dt>Role</dt><dd>{displayRole}</dd></div>
            <div><dt>Account status</dt><dd><Badge tone="approved">Approved</Badge></dd></div>
          </dl>
        </Card>
        <Card title="Set a new password" sub="Answer your three saved security questions to verify your identity.">
          <form className="profile-password-form" onSubmit={changePassword}>
            {message && <div className={`auth-message ${message.type}`}>{message.text}</div>}
            <div className="profile-security-list">
              {questions.map((question, index) => (
                <AuthField key={question} label={`${index + 1}. ${question}`}>
                  <SecretInput
                    required
                    autoComplete="off"
                    value={answers[index] || ""}
                    onChange={(event) => setAnswers((current) => current.map((answer, i) => i === index ? event.target.value : answer))}
                    placeholder="Enter your security answer"
                  />
                </AuthField>
              ))}
            </div>
            <div className="auth-grid">
              <AuthField label="New password"><SecretInput required maxLength={passwordPolicy.maximum_length} autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter a new password" /></AuthField>
              <AuthField label="Confirm new password"><SecretInput required maxLength={passwordPolicy.maximum_length} autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} placeholder="Re-enter the new password" /></AuthField>
            </div>
            <PasswordPolicy password={password} userId={session.user.user_id} policy={passwordPolicy} />
            <button className="btn primary profile-save" disabled={busy || questions.length !== 3}>
              <KeyRound size={16} />{busy ? "Updating..." : "Update password"}
            </button>
          </form>
        </Card>
      </div>
      <div className="profile-footer">
        <div><strong>Finished with your session?</strong><span>Sign out securely from this device.</span></div>
        <button className="btn profile-logout" type="button" onClick={onLogout}><LogOut size={16} />Log out</button>
      </div>
    </>
  );
}
