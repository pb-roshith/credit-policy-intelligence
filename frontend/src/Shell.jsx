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
import { API, apiRequest } from "./api/client";
import { META } from "./config";
import AuthScreen from "./pages/AuthScreen";
import AdminDashboard from "./pages/AdminDashboard";
import Compliance from "./pages/Compliance";
import Dashboard from "./pages/Dashboard";
import DataManufacturing from "./pages/DataManufacturing";
import Exceptions from "./pages/Exceptions";
import Policy from "./pages/Policy";
import Portfolio from "./pages/Portfolio";
import Requests from "./pages/Requests";
import Simulator from "./pages/Simulator";
import UserProfile from "./pages/UserProfile";

const NAV = [
  ["dashboard", "Executive Dashboard", LayoutDashboard],
  ["requests", "Credit Requests", FileText],
  ["policy", "Policy Intelligence", BookOpen],
  ["compliance", "Compliance Review", ShieldCheck],
  ["exceptions", "Exception Management", AlertTriangle],
  ["simulator", "Decision Simulator", SlidersHorizontal],
  ["portfolio", "Portfolio Analytics", BarChart3],
  ["manufacturing", "Data Manufacturing", Factory],
];

export default function Shell() {
  const [session, setSession] = useState(() => {
    try {
      const saved = JSON.parse(sessionStorage.getItem("cpi-session"));
      return saved?.token && saved?.user?.role ? saved : null;
    } catch {
      return null;
    }
  });
  const initial = location.hash.slice(1) || "dashboard";
  const validPage = (id) => NAV.some((item) => item[0] === id) || id === "profile";
  const returnToLogin = () => {
    sessionStorage.removeItem("cpi-session");
    const loginUrl = `${window.location.origin}${window.location.pathname}${window.location.search}`;
    window.location.replace(loginUrl);
  };
  const [page, setPage] = useState(
      validPage(initial) ? initial : "dashboard",
    ),
    [collapsed, setCollapsed] = useState(false),
    [mobile, setMobile] = useState(false),
    [toast, setToast] = useState(""),
    [summary, setSummary] = useState({});
  useEffect(() => {
    const handler = () => {
      const next = location.hash.slice(1) || "dashboard";
      setPage(validPage(next) ? next : "dashboard");
    };
    addEventListener("hashchange", handler);
    if (session?.token) {
      apiRequest("/api/summary", {}, session.token)
        .then(setSummary)
        .catch(returnToLogin);
    }
    return () => removeEventListener("hashchange", handler);
  }, [session?.token]);
  useEffect(() => {
    if (!session?.expires_at) return undefined;
    const remaining = new Date(session.expires_at).getTime() - Date.now();
    if (remaining <= 0) {
      returnToLogin();
      return undefined;
    }
    const timer = setTimeout(returnToLogin, remaining);
    return () => clearTimeout(timer);
  }, [session?.expires_at]);
  const notify = (message) => {
      setToast(message);
      setTimeout(() => setToast(""), 2600);
    },
    go = (id) => {
      location.hash = id;
      setMobile(false);
    };
  const Page = {
    dashboard: Dashboard,
    requests: Requests,
    manufacturing: DataManufacturing,
    policy: Policy,
    compliance: Compliance,
    exceptions: Exceptions,
    simulator: Simulator,
    portfolio: Portfolio,
    profile: UserProfile,
  }[page];
  const authenticated = (data) => {
    sessionStorage.setItem("cpi-session", JSON.stringify(data));
    setSession(data);
  };
  const logout = () => {
    const token = session?.token;
    if (token) {
      fetch(`${API}/api/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        keepalive: true,
      }).catch(() => {});
    }
    returnToLogin();
  };
  if (!session) return <AuthScreen key="login" onAuthenticated={authenticated} />;
  if (session.user.role === "admin") return <AdminDashboard session={session} onLogout={logout} />;
  const displayRole = session.user.role.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  return (
    <div className={`app ${collapsed ? "collapsed" : ""}`}>
      <aside className={mobile ? "mobile-open" : ""}>
        <div className="brand">
          <div className="tcs-mark">tcs</div>
          {!collapsed && (
            <div>
              <strong>TCS CPI</strong>
              <small>POLICY INTELLIGENCE</small>
            </div>
          )}
          <button className="close-mobile" onClick={() => setMobile(false)}>
            <X />
          </button>
        </div>
        {!collapsed && <div className="nav-label">WORKSPACE</div>}
        <nav>
          {NAV.map(([id, label, Icon]) => (
            <button
              key={id}
              title={label}
              className={page === id ? "active" : ""}
              onClick={() => go(id)}
            >
              <Icon size={18} />
              {!collapsed && <span>{label}</span>}
            </button>
          ))}
        </nav>
        <button className={`side-user ${page === "profile" ? "active" : ""}`} type="button" onClick={() => go("profile")} title="Open my profile">
          <div>{session.user.user_id.slice(0, 2).toUpperCase()}</div>
          {!collapsed && (
            <span>
              <strong>{session.user.user_id}</strong>
              <small>{displayRole}</small>
            </span>
          )}
          <ChevronRight size={14} />
        </button>
      </aside>
      <div className="main">
        <header>
          <div className="header-left">
            <button className="menu-mobile" onClick={() => setMobile(true)}>
              <Menu size={19} />
            </button>
            <button
              className="collapse"
              onClick={() => setCollapsed((x) => !x)}
            >
              <PanelLeftClose size={18} />
            </button>
            <span>Home</span>
            <ChevronRight size={13} />
            <strong>{META[page][0]}</strong>
          </div>
          <button className="header-logout" onClick={logout} title="Sign out"><LogOut size={17} /></button>
        </header>
        <main>
          <Page notify={notify} summary={summary} session={session} onLogout={logout} />
        </main>
      </div>
      {toast && (
        <div className="toast">
          <CheckCircle2 size={17} />
          {toast}
        </div>
      )}
    </div>
  );
}

