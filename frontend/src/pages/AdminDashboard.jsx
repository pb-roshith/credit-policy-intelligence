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
import { AuthField, Badge, Bars, Card, DataTable, DEFAULT_PASSWORD_POLICY, Heading, Insight, LineChart, Metric, NO_CLIPBOARD, PasswordPolicy, SecretInput, money } from "../components/ui";

export default function AdminDashboard({ session, onLogout }) {
  const [users, setUsers] = useState([]);
  const [message, setMessage] = useState(null);
  const [policy, setPolicy] = useState(DEFAULT_PASSWORD_POLICY);
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [userPages, setUserPages] = useState({ pending: 1, locked: 1, active: 1 });
  const [logs, setLogs] = useState({ logs: [], page: 1, pages: 1, total: 0 });
  const loadUsers = () => apiRequest("/api/admin/users", {}, session.token)
    .then((data) => setUsers(data.users))
    .catch((error) => setMessage({ type: "error", text: error.message }));
  const loadPolicy = () => apiRequest("/api/admin/password-policy", {}, session.token)
    .then((data) => setPolicy(data))
    .catch((error) => setMessage({ type: "error", text: error.message }));
  const loadLogs = (page = 1) => apiRequest(`/api/admin/logs?page=${page}`, {}, session.token)
    .then(setLogs)
    .catch((error) => setMessage({ type: "error", text: error.message }));
  useEffect(() => {
    loadUsers();
    loadPolicy();
    loadLogs(1);
  }, []);
  const perform = async (userId, action) => {
    try {
      const data = await apiRequest(`/api/admin/users/${encodeURIComponent(userId)}/${action}`, { method: "POST" }, session.token);
      setMessage({ type: "success", text: data.message });
      loadUsers();
      loadLogs(1);
    } catch (error) { setMessage({ type: "error", text: error.message }); }
  };
  const savePolicy = async (event) => {
    event.preventDefault();
    setSavingPolicy(true);
    setMessage(null);
    try {
      const data = await apiRequest("/api/admin/password-policy", {
        method: "PUT",
        body: JSON.stringify({
          minimum_length: Number(policy.minimum_length),
          maximum_length: Number(policy.maximum_length),
          minimum_uppercase: Number(policy.minimum_uppercase),
          minimum_lowercase: Number(policy.minimum_lowercase),
          minimum_digits: Number(policy.minimum_digits),
          minimum_special: Number(policy.minimum_special),
        }),
      }, session.token);
      setPolicy(data);
      setMessage({ type: "success", text: data.message });
      loadLogs(1);
    } catch (error) {
      setMessage({ type: "error", text: error.message });
    } finally {
      setSavingPolicy(false);
    }
  };
  const updatePolicy = (field, value) => setPolicy((current) => ({ ...current, [field]: value }));
  const pending = users.filter((user) => user.status === "pending");
  const locked = users.filter((user) => user.locked);
  const approved = users.filter((user) => user.status === "approved" && !user.locked);
  const UserTable = ({ rows, action, section }) => {
    if (!rows.length) return <div className="admin-empty">No accounts in this section.</div>;
    const pages = Math.max(1, Math.ceil(rows.length / 10));
    const page = Math.min(userPages[section], pages);
    const visibleRows = rows.slice((page - 1) * 10, page * 10);
    const setPage = (nextPage) => setUserPages((current) => ({ ...current, [section]: nextPage }));
    return (
      <div className="admin-table-wrap">
        <table><thead><tr><th>User ID</th><th>Role</th><th>Status</th><th>Created</th><th>Action</th></tr></thead><tbody>{visibleRows.map((user) => <tr key={user.user_id}><td><strong>{user.user_id}</strong></td><td>{user.role.replaceAll("_", " ")}</td><td><Badge tone={user.locked ? "high" : user.status === "pending" ? "warning" : "approved"}>{user.locked ? "Locked" : user.status}</Badge></td><td>{new Date(user.created_at).toLocaleDateString()}</td><td>{action && <button className="btn primary admin-action" onClick={() => perform(user.user_id, action)}>{action === "approve" ? <UserCheck size={14} /> : <KeyRound size={14} />}{action === "approve" ? "Approve" : "Unlock"}</button>}</td></tr>)}</tbody></table>
        <div className="admin-pagination">
          <button type="button" aria-label={`Previous 10 ${section} users`} title="Previous 10" disabled={page <= 1} onClick={() => setPage(page - 1)}>&lt;</button>
          <span>Page {page} of {pages}</span>
          <button type="button" aria-label={`Next 10 ${section} users`} title="Next 10" disabled={page >= pages} onClick={() => setPage(page + 1)}>&gt;</button>
        </div>
      </div>
    );
  };
  return (
    <div className="admin-page">
      <header className="admin-header"><div className="brand"><div className="tcs-mark">tcs</div><div><strong>TCS CPI</strong><small>ADMINISTRATION</small></div></div><div><span>Signed in as <strong>{session.user.user_id}</strong></span><button className="btn secondary" type="button" onClick={onLogout}><LogOut size={15} />Sign out</button></div></header>
      <main className="admin-main">
        <div className="admin-title"><div><h1>Admin Dashboard</h1><p>Manage users, password controls, and administrative activity.</p></div><button className="btn secondary" onClick={() => { loadUsers(); loadPolicy(); loadLogs(logs.page); }}>Refresh</button></div>
        {message && <div className={`auth-message ${message.type}`}>{message.text}</div>}
        <div className="admin-metrics"><div className="card"><UserPlus /><span>Pending approval</span><strong>{pending.length}</strong></div><div className="card"><LockKeyhole /><span>Locked accounts</span><strong>{locked.length}</strong></div><div className="card"><UserCheck /><span>Active users</span><strong>{approved.length}</strong></div></div>
        <Card title="Password policy" sub="These requirements apply immediately to registration and every password reset.">
          <form className="admin-policy-form" onSubmit={savePolicy}>
            <label><span>Minimum length</span><input type="number" min="1" max="128" required value={policy.minimum_length} onChange={(event) => updatePolicy("minimum_length", event.target.value)} /></label>
            <label><span>Maximum length</span><input type="number" min="1" max="128" required value={policy.maximum_length} onChange={(event) => updatePolicy("maximum_length", event.target.value)} /></label>
            <label><span>Uppercase characters</span><input type="number" min="0" max="128" required value={policy.minimum_uppercase} onChange={(event) => updatePolicy("minimum_uppercase", event.target.value)} /></label>
            <label><span>Lowercase characters</span><input type="number" min="0" max="128" required value={policy.minimum_lowercase} onChange={(event) => updatePolicy("minimum_lowercase", event.target.value)} /></label>
            <label><span>Digits</span><input type="number" min="0" max="128" required value={policy.minimum_digits} onChange={(event) => updatePolicy("minimum_digits", event.target.value)} /></label>
            <label><span>Special characters</span><input type="number" min="0" max="128" required value={policy.minimum_special} onChange={(event) => updatePolicy("minimum_special", event.target.value)} /></label>
            <button className="btn primary admin-policy-save" disabled={savingPolicy}><Save size={15} />{savingPolicy ? "Saving..." : "Save policy"}</button>
          </form>
        </Card>
        <Card title="Pending user approvals" sub="New users cannot sign in until you approve them."><UserTable rows={pending} action="approve" section="pending" /></Card>
        <Card title="Locked accounts" sub="Accounts lock after three incorrect password attempts."><UserTable rows={locked} action="unlock" section="locked" /></Card>
        <Card title="Active users"><UserTable rows={approved} section="active" /></Card>
        <Card title="Administrative logs" sub={`Audit history - ${logs.total} recorded event${logs.total === 1 ? "" : "s"}`}>
          {logs.logs.length ? (
            <div className="admin-table-wrap audit-log-table">
              <table><thead><tr><th>Date & time</th><th>Administrator</th><th>Action</th><th>Target</th><th>Details</th></tr></thead><tbody>{logs.logs.map((entry) => (
                <tr key={entry.id}><td>{new Date(entry.created_at).toLocaleString()}</td><td><strong>{entry.actor}</strong></td><td>{entry.action.replaceAll("_", " ")}</td><td>{entry.target || "-"}</td><td>{entry.details || "-"}</td></tr>
              ))}</tbody></table>
              <div className="admin-pagination">
                <button type="button" aria-label="Previous 10 logs" title="Previous 10" disabled={logs.page <= 1} onClick={() => loadLogs(logs.page - 1)}>&lt;</button>
                <span>Page {logs.page} of {logs.pages}</span>
                <button type="button" aria-label="Next 10 logs" title="Next 10" disabled={logs.page >= logs.pages} onClick={() => loadLogs(logs.page + 1)}>&gt;</button>
              </div>
            </div>
          ) : <div className="admin-empty">No administrative activity recorded yet.</div>}
        </Card>
      </main>
    </div>
  );
}
