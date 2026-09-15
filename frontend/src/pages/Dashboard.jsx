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
import { AuthField, Badge, Bars, Card, DataTable, Heading, Insight, Legend, LineChart, Metric, NO_CLIPBOARD, PasswordPolicy, SecretInput, StageExposure, money } from "../components/ui";

export default function Dashboard({ notify, summary }) {
  return (
    <>
      <Heading page="dashboard">
        <select>
          <option>Last 30 days</option>
          <option>Last quarter</option>
        </select>
        <button
          className="btn secondary"
          onClick={() => notify("Dashboard report exported")}
        >
          <Download size={15} />
          Export Report
        </button>
      </Heading>
      <div className="metrics six">
        <Metric
          icon={FileText}
          label="Active Credit Requests"
          value="1,245"
          change="+8%"
        />
        <Metric
          icon={ShieldCheck}
          label="Policy Compliance Rate"
          value={`${summary.policy_compliance || 92}%`}
          change="+1.2%"
        />
        <Metric
          icon={AlertTriangle}
          label="Active Exceptions"
          value={summary.open_exceptions || 148}
          change="+11%"
          good={false}
        />
        <Metric
          icon={CircleDollarSign}
          label="Exposure Under Exception"
          value="$4.2B"
          change="+$0.4B"
          good={false}
        />
        <Metric
          icon={ShieldAlert}
          label="High Severity Breaches"
          value="23"
          change="+4"
          good={false}
        />
        <Metric
          icon={Clock3}
          label="Overdue Remediation"
          value="87"
          change="-5"
          down
        />
      </div>
      <div className="layout two-one">
        <Card
          title="Exception Trend (last 6 months)"
          sub="Detected vs Remediated"
          action={<Legend />}
        >
          <LineChart second />
        </Card>
        <Card title="AI Insights">
          <Insight>
            Leverage threshold violations increased 18% this month across
            Commercial Real Estate.
          </Insight>
          <Insight>
            Construction contributes 34% of exceptions - concentration
            approaching RAF ceiling.
          </Insight>
          <Insight>
            Five large exceptions account for 48% of exposure under exception.
          </Insight>
          <Insight>
            Delegation matrix bypass detected on 6 deals - recommend escalation.
          </Insight>
          <button
            className="text-btn"
            onClick={() => (location.hash = "portfolio")}
          >
            View all insights <ArrowRight size={14} />
          </button>
        </Card>
      </div>
      <div className="layout thirds">
        <Card title="Policy Breaches by Business Unit">
          <Bars
            data={[72, 56, 38, 27]}
            labels={["Corporate", "SME", "Retail", "Public"]}
          />
        </Card>
        <Card title="Exposure by Exception Type ($M)">
          <div className="donut">
            <div>
              <strong>$4.2B</strong>
              <small>Total exposure</small>
            </div>
          </div>
          <div className="donut-key">
            <span>Leverage 42%</span>
            <span>Collateral 31%</span>
            <span>Other 27%</span>
          </div>
        </Card>
        <Card title="Top Violated Policies">
          {[
            ["CP-4.2 Leverage Limit CRE", 34],
            ["COL-2.1 Collateral Coverage", 28],
            ["RAF-3.5 Sector Concentration", 22],
            ["CP-6.4 Covenant Package", 19],
            ["CP-1.7 Delegation Threshold", 15],
          ].map((x) => (
            <div className="rank" key={x[0]}>
              <span>{x[0]}</span>
              <b>{x[1]}</b>
            </div>
          ))}
        </Card>
      </div>
      <Card
        title="IFRS 9 Stage Exposure Distribution ($M)"
        className="ifrs-card"
      >
        <div className="stage-chart">
          <StageExposure
            label="Stage 1"
            value="$18,400M"
            percent={100}
            tone="stage-one"
          />
          <StageExposure
            label="Stage 2"
            value="$3,200M"
            percent={17.4}
            tone="stage-two"
          />
          <StageExposure
            label="Stage 3"
            value="$820M"
            percent={4.5}
            tone="stage-three"
          />
        </div>
      </Card>
    </>
  );
}
