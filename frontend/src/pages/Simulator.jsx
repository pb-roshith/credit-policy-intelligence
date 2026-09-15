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
import { AuthField, Badge, Bars, Card, DataTable, Heading, Insight, LineChart, Metric, NO_CLIPBOARD, PasswordPolicy, SecretInput, money } from "../components/ui";

export default function Simulator({ notify }) {
  const [amount, setAmount] = useState(85),
    [coverage, setCoverage] = useState(85),
    [rating, setRating] = useState("BB-"),
    [pricing, setPricing] = useState(325),
    [tenor, setTenor] = useState(7),
    [running, setRunning] = useState(false);
  const risk = Math.max(
    18,
    Math.min(
      96,
      Math.round(
        100 -
          (amount - 50) * 0.35 -
          (100 - coverage) * 0.65 -
          (tenor - 5) * 2 +
          (pricing - 250) * 0.03 -
          (rating === "B+" ? 14 : rating === "BBB" ? 12 : 0),
      ),
    ),
  );
  const run = () => {
    setRunning(true);
    setTimeout(() => {
      setRunning(false);
      notify("Scenario recalculated");
    }, 500);
  };
  return (
    <>
      <Heading page="simulator">
        <button
          className="btn tertiary"
          onClick={() => notify("Scenario saved")}
        >
          <Save size={14} />
          Save Scenario
        </button>
        <button className="btn secondary">
          <GitCompareArrows size={14} />
          Compare
        </button>
      </Heading>
      <div className="sim-layout">
        <Card title="Scenario Inputs">
          <Slider
            label="Facility Amount"
            value={amount}
            set={setAmount}
            min={25}
            max={150}
            display={`$${amount}M`}
          />
          <Slider
            label="Collateral Coverage"
            value={coverage}
            set={setCoverage}
            min={50}
            max={130}
            display={`${coverage}%`}
          />
          <div className="form-row single-field">
            <label>
              Risk Rating
              <select
                value={rating}
                onChange={(e) => setRating(e.target.value)}
              >
                <option>BBB</option>
                <option>BB+</option>
                <option>BB-</option>
                <option>B+</option>
              </select>
            </label>
          </div>
          <Slider
            label="Pricing (bps)"
            value={pricing}
            set={setPricing}
            min={100}
            max={600}
            display={`${pricing}`}
          />
          <Slider
            label="Tenor (years)"
            value={tenor}
            set={setTenor}
            min={1}
            max={12}
            display={`${tenor}yr`}
          />
          <label className="field">
            Covenants
            <select>
              <option>Partial</option>
              <option>Full</option>
              <option>None</option>
            </select>
          </label>
          <button className="btn primary run" onClick={run}>
            <Play size={15} />
            {running ? "Running..." : "Run Scenario"}
          </button>
        </Card>
        <div>
          <div className="output-grid">
            <Output
              label="Expected Loss"
              value={money((amount * (100 - coverage)) / 2650 + 0.08)}
              tone="warn"
            />
            <Output
              label="ECL Impact"
              value={money((amount * (100 - coverage)) / 1875 + 0.1)}
              tone="warn"
            />
            <Output label="RWA Impact" value={money(amount * 1.2)} />
            <Output label="Capital Impact" value={money(amount * 0.126)} />
            <Output
              label="Concentration Impact"
              value={`${(amount / 10).toFixed(1)}%`}
              tone="warn"
            />
            <Output
              label="Risk Appetite Score"
              value={risk}
              tone={risk < 70 ? "danger" : "good"}
            />
          </div>
          <Card title="Sensitivity Analysis - Facility Amount">
            <LineChart second />
          </Card>
        </div>
        <Card
          className="recommendations"
          title="AI Recommendations"
          action={<Sparkles size={16} />}
        >
          {[
            "Increase collateral to 100% to bring COL-2.1 into compliance",
            "Reduce facility size to $65M to meet CP-4.2 leverage ceiling",
            "Add cash-sweep covenant to mitigate leverage exposure",
            "Escalate to Credit Committee per DEL-3.1 delegation matrix",
          ].map((x) => (
            <div className="recommend" key={x}>
              <CheckCircle2 size={15} />
              <p>{x}</p>
              <ChevronRight size={14} />
            </div>
          ))}
          <small className="disclaimer">
            AI-generated recommendations. Require human approval to enact.
          </small>
        </Card>
      </div>
      <Card title="Scenario Comparison">
        <div className="comparison">
          <div>
            <small>BASE CASE</small>
            <strong>$85M / 85%</strong>
            <Badge tone="warning">Score {risk}</Badge>
          </div>
          <ArrowRight />
          <div>
            <small>RECOMMENDED</small>
            <strong>$65M / 100%</strong>
            <Badge tone="pass">Score 86</Badge>
          </div>
          <span>
            <b>31%</b> Expected loss
            <br />
            <b>$24M</b> RWA impact
          </span>
        </div>
      </Card>
    </>
  );
}
function Slider({ label, value, set, min, max, display }) {
  return (
    <label className="slider">
      <span>
        {label}
        <b>{display}</b>
      </span>
      <input
        type="range"
        min={min}
        max={max}
        value={value}
        onChange={(e) => set(+e.target.value)}
      />
      <div>
        <small>{min}</small>
        <small>{max}</small>
      </div>
    </label>
  );
}
function Output({ label, value, tone = "" }) {
  return (
    <div className={`card output ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <div className="mini-bars">
        {[35, 48, 42, 57, 53, 69, 65, 78].map((v, i) => (
          <i key={i} style={{ height: `${v}%` }} />
        ))}
      </div>
    </div>
  );
}

