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
import { AuthField, Badge, Bars, Card, DataTable, Heading, Insight, Legend, LineChart, Metric, NO_CLIPBOARD, PasswordPolicy, SecretInput, money } from "../components/ui";

export default function Portfolio() {
  const sectors = [
      ["CRE", 78, 34],
      ["Energy", 62, 22],
      ["Manufacturing", 54, 18],
      ["Tech", 48, 14],
      ["Healthcare", 32, 6],
      ["Transport", 41, 11],
      ["Retail", 28, 8],
      ["Chemicals", 36, 12],
      ["Mining", 44, 19],
    ],
    geo = [
      ["US Northeast", 62, 24],
      ["US Southeast", 45, 18],
      ["US Midwest", 34, 9],
      ["US West", 58, 22],
      ["EMEA", 41, 14],
      ["APAC", 38, 11],
      ["LATAM", 22, 7],
      ["UK", 29, 8],
      ["Canada", 18, 4],
    ];
  return (
    <>
      <Heading page="portfolio">
        <select>
          <option>Enterprise</option>
          <option>Corporate Banking</option>
        </select>
        <button className="btn secondary">
          Drill to Business Unit <ChevronRight size={14} />
        </button>
      </Heading>
      <div className="layout two-one">
        <Card title="Exception & Policy Breach Trends" action={<Legend />}>
          <LineChart second />
        </Card>
        <Card title="Ask AI" action={<Sparkles size={15} />}>
          {[
            "Top 10 concentration risks",
            "Clauses causing most exceptions",
            "Highest capital impact",
          ].map((x) => (
            <button className="ai-query" key={x}>
              {x}
              <ArrowRight size={13} />
            </button>
          ))}
          <div className="chat-input">
            <input placeholder="Ask a portfolio question..." />
            <button>
              <Send size={14} />
            </button>
          </div>
        </Card>
      </div>
      <div className="layout two">
        <Heat title="Sector Heatmap" data={sectors} />
        <Heat title="Geography Heatmap" data={geo} />
      </div>
      <div className="layout two">
        <Card title="RWA Impact Distribution ($M)">
          <Bars
            data={[40, 62, 83, 55, 72, 46]}
            labels={["CRE", "Energy", "Mfg", "Tech", "Health", "Other"]}
          />
        </Card>
        <Card title="ECL Impact Trend ($M)">
          <LineChart />
        </Card>
      </div>
    </>
  );
}
function Heat({ title, data }) {
  return (
    <Card title={title}>
      <div className="heat-grid">
        {data.map(([name, exp, breaches]) => (
          <div
            key={name}
            className={
              exp >= 58 ? "heat-high" : exp >= 38 ? "heat-medium" : "heat-low"
            }
          >
            <strong>{name}</strong>
            <span>
              Exp {exp}% - {breaches} breaches
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}
