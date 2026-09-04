import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
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
  Bot,
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
  Target,
  Menu,
} from "lucide-react";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://localhost:8000";
const NAV = [
  ["dashboard", "Executive Dashboard", LayoutDashboard],
  ["requests", "Credit Requests", FileText],
  ["policy", "Policy Intelligence", BookOpen],
  ["compliance", "Compliance Review", ShieldCheck],
  ["exceptions", "Exception Management", AlertTriangle],
  ["simulator", "Decision Simulator", SlidersHorizontal],
  ["portfolio", "Portfolio Analytics", BarChart3],
];
const META = {
  dashboard: [
    "Executive Dashboard",
    "Consolidated view of credit policy compliance & exceptions.",
  ],
  requests: [
    "Credit Request Workbench",
    "Review incoming credit requests with AI-assisted insights.",
  ],
  policy: [
    "Policy Intelligence",
    "Enterprise policy knowledge center with AI copilot.",
  ],
  compliance: [
    "Compliance Review",
    "CR-10242 · Harbor Point Realty · Construction Facility",
  ],
  exceptions: [
    "Exception Management",
    "Central registry of policy exceptions and remediation workflow.",
  ],
  simulator: [
    "Decision Simulator",
    "Interactive credit scenario analysis with real-time risk outputs.",
  ],
  portfolio: [
    "Portfolio Analytics",
    "Enterprise-wide policy breach, exception, and risk analytics.",
  ],
};
const REQUESTS = [
  [
    "Meridian Steel Holdings",
    "CR-10241",
    "Manufacturing",
    "$120M",
    "Term Loan",
    "BB",
    "$45M",
    "In Review",
    78,
  ],
  [
    "Harbor Point Realty",
    "CR-10242",
    "Commercial RE",
    "$340M",
    "Construction",
    "BB-",
    "$85M",
    "Escalated",
    62,
  ],
  [
    "Northwind Logistics",
    "CR-10243",
    "Transportation",
    "$78M",
    "Revolver",
    "BBB",
    "$25M",
    "Approved",
    94,
  ],
  [
    "Solstice Renewables",
    "CR-10244",
    "Energy",
    "$210M",
    "Project Finance",
    "BB+",
    "$110M",
    "In Review",
    84,
  ],
  [
    "Ashford Health Systems",
    "CR-10245",
    "Healthcare",
    "$95M",
    "Term Loan",
    "A-",
    "$30M",
    "Approved",
    96,
  ],
  [
    "Cascade Foods Group",
    "CR-10246",
    "Consumer",
    "$65M",
    "Revolver",
    "BB",
    "$20M",
    "Pending",
    81,
  ],
  [
    "Vantage Semi Corp",
    "CR-10247",
    "Technology",
    "$180M",
    "Bridge",
    "B+",
    "$60M",
    "Escalated",
    58,
  ],
  [
    "Crestline Aviation",
    "CR-10248",
    "Aviation",
    "$240M",
    "Aircraft Finance",
    "BB",
    "$95M",
    "In Review",
    72,
  ],
  [
    "Riverstone Chemicals",
    "CR-10249",
    "Chemicals",
    "$130M",
    "Term Loan",
    "BB-",
    "$40M",
    "Pending",
    68,
  ],
  [
    "Bluepeak Mining",
    "CR-10250",
    "Mining",
    "$155M",
    "Reserve Based",
    "B+",
    "$55M",
    "Declined",
    45,
  ],
];
const CREDIT_REQUESTS = Array.from({ length: 1245 }, (_, index) => {
  const source = REQUESTS[index % REQUESTS.length];
  if (index < REQUESTS.length) return source;
  const batch = Math.floor(index / REQUESTS.length) + 1;
  return [
    `${source[0]} · Portfolio ${batch}`,
    `CR-${String(10241 + index).padStart(5, "0")}`,
    ...source.slice(2),
  ];
});
const EXCEPTIONS = [
  [
    "EX-8821",
    "Leverage",
    "CP-4.2",
    "High",
    "$85M",
    "S. Chen",
    "2026-08-05",
    "Pending Approval",
  ],
  [
    "EX-8822",
    "Collateral",
    "COL-2.1",
    "High",
    "$62M",
    "M. Ruiz",
    "2026-07-28",
    "Active",
  ],
  [
    "EX-8823",
    "Concentration",
    "RAF-3.5",
    "Medium",
    "$140M",
    "A. Patel",
    "2026-08-12",
    "Remediation",
  ],
  [
    "EX-8824",
    "Covenant",
    "CP-6.4",
    "Low",
    "$18M",
    "J. Okafor",
    "2026-07-22",
    "Active",
  ],
  [
    "EX-8825",
    "Delegation",
    "DEL-3.1",
    "High",
    "$95M",
    "R. Kim",
    "2026-07-25",
    "Pending Approval",
  ],
  [
    "EX-8826",
    "Pricing",
    "PRC-1.1",
    "Low",
    "$12M",
    "L. Novak",
    "2026-08-30",
    "Closed",
  ],
  [
    "EX-8827",
    "Tenor",
    "CP-4.3",
    "Medium",
    "$40M",
    "T. Alvarez",
    "2026-08-18",
    "Remediation",
  ],
  [
    "EX-8828",
    "Leverage",
    "CP-4.2",
    "High",
    "$110M",
    "S. Chen",
    "2026-07-30",
    "Active",
  ],
];
const FINDINGS = [
  ["CP-4.2 Leverage Limit (CRE)", "5.5x", "4.5x", "+22%", "BREACH"],
  ["COL-2.1 Collateral Coverage", "85%", "100%", "-15%", "BREACH"],
  ["PRC-1.1 RAROC Floor", "12.4%", "12.0%", "+3%", "PASS"],
  ["CP-4.3 Tenor Limit", "7yr", "7yr", "0%", "PASS"],
  ["CP-6.4 Covenant Package", "Partial", "Full", "—", "WARNING"],
  ["RAF-3.5 Sector Concentration", "9.2%", "10%", "-8%", "WARNING"],
  [
    "DEL-3.1 Approval Authority",
    "RVP",
    "Credit Committee",
    "Below Auth",
    "BREACH",
  ],
];

const slug = (v) => String(v).toLowerCase().replaceAll(" ", "-");
const money = (v) =>
  `$${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}M`;
function Badge({ children, tone }) {
  return <span className={`badge ${tone || slug(children)}`}>{children}</span>;
}
function Heading({ page, children }) {
  return (
    <div className="page-heading">
      <div>
        <h1>{META[page][0]}</h1>
        <p>{META[page][1]}</p>
      </div>
      <div className="heading-actions">{children}</div>
    </div>
  );
}
function Card({ title, sub, action, className = "", children }) {
  return (
    <section className={`card ${className}`}>
      <div className="card-head">
        <div>
          {title && <h2>{title}</h2>}
          {sub && <p>{sub}</p>}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}
function Metric({
  icon: Icon,
  label,
  value,
  change,
  good = true,
  down = false,
}) {
  return (
    <div className="card metric">
      <div className="metric-label">
        <span>{label}</span>
        <span className="metric-icon">
          <Icon size={16} />
        </span>
      </div>
      <strong>{value}</strong>
      <small className={good ? "positive" : "negative"}>
        {down ? <TrendingDown size={12} /> : <TrendingUp size={12} />} {change}
      </small>
    </div>
  );
}
function LineChart({ second = false }) {
  return (
    <div className="line-chart">
      <svg viewBox="0 0 700 220" preserveAspectRatio="none">
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#20bad8" stopOpacity=".32" />
            <stop offset="1" stopColor="#20bad8" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[40, 85, 130, 175].map((y) => (
          <line key={y} x1="20" x2="680" y1={y} y2={y} className="gridline" />
        ))}
        <path
          className="area"
          d="M20 168 C110 160 120 125 210 132 S340 82 430 94 S550 45 680 50 L680 205 L20 205Z"
        />
        <path
          className="line aqua"
          d="M20 168 C110 160 120 125 210 132 S340 82 430 94 S550 45 680 50"
        />
        {second && (
          <path
            className="line green"
            d="M20 190 C120 174 170 164 245 150 S385 145 455 112 S590 116 680 82"
          />
        )}
      </svg>
      <div className="axis">
        <span>Mar</span>
        <span>Apr</span>
        <span>May</span>
        <span>Jun</span>
        <span>Jul</span>
        <span>Aug</span>
      </div>
    </div>
  );
}
function Bars({ data, labels }) {
  return (
    <div className="bar-chart">
      <div className="bar-grid">
        {data.map((v, i) => (
          <div className="bar-slot" key={labels[i]}>
            <i style={{ height: `${v}%` }} />
            <b>{v}</b>
          </div>
        ))}
      </div>
      <div className="axis">
        {labels.map((x) => (
          <span key={x}>{x}</span>
        ))}
      </div>
    </div>
  );
}
function Insight({ children }) {
  return (
    <div className="insight">
      <Badge tone="ai">AI</Badge>
      <p>{children}</p>
    </div>
  );
}

function Dashboard({ notify, summary }) {
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
            Construction contributes 34% of exceptions — concentration
            approaching RAF ceiling.
          </Insight>
          <Insight>
            Five large exceptions account for 48% of exposure under exception.
          </Insight>
          <Insight>
            Delegation matrix bypass detected on 6 deals — recommend escalation.
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
function StageExposure({ label, value, percent, tone }) {
  return (
    <div className="stage-item">
      <div>
        <span>{label}</span>
        <Badge tone={tone}>{value}</Badge>
      </div>
      <div className="stage-track">
        <i className={tone} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
function Legend() {
  return (
    <div className="legend">
      <i />
      Detected <i className="green-dot" />
      Remediated
    </div>
  );
}

function Requests() {
  const [selected, setSelected] = useState(CREDIT_REQUESTS[1]);
  const [filter, setFilter] = useState("All Statuses");
  const [query, setQuery] = useState("");
  const [requestPage, setRequestPage] = useState(0);
  const filtered = CREDIT_REQUESTS.filter(
    (row) =>
      (filter === "All Statuses" || row[7] === filter) &&
      `${row[0]} ${row[1]}`.toLowerCase().includes(query.toLowerCase()),
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / 10));
  const safePage = Math.min(requestPage, pageCount - 1);
  const shown = filtered.slice(safePage * 10, safePage * 10 + 10);
  return (
    <>
      <Heading page="requests">
        <button className="btn primary">
          <Plus size={15} />
          New Credit Request
        </button>
      </Heading>
      <div className="request-layout">
        <Card
          className="table-card"
          title="10 Requests"
          action={<Badge tone="rating">Sorted: Compliance ↑</Badge>}
        >
          <div className="request-tools">
            <label className="request-search">
              <Search size={16} />
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setRequestPage(0);
                }}
                placeholder="Search borrower or ID…"
              />
            </label>
            <select
              value={filter}
              onChange={(e) => {
                setFilter(e.target.value);
                setRequestPage(0);
              }}
            >
              <option>All Statuses</option>
              <option>In Review</option>
              <option>Escalated</option>
              <option>Approved</option>
              <option>Pending</option>
              <option>Declined</option>
            </select>
            <button className="filter-square" aria-label="Filter requests">
              <Filter size={16} />
            </button>
          </div>
          <DataTable
            headers={[
              "Borrower",
              "Industry",
              "Exposure",
              "Facility",
              "Rating",
              "Requested",
              "Status",
              "Compliance",
            ]}
            rows={shown}
            selected={selected}
            onSelect={setSelected}
            render={(v, i, r) =>
              i === 0 ? (
                <>
                  <strong>{v}</strong>
                  <small>{r[1]}</small>
                </>
              ) : i === 1 ? (
                r[2]
              ) : i === 2 ? (
                r[3]
              ) : i === 3 ? (
                r[4]
              ) : i === 4 ? (
                <Badge tone="rating">{r[5]}</Badge>
              ) : i === 5 ? (
                r[6]
              ) : i === 6 ? (
                <Badge>{r[7]}</Badge>
              ) : (
                <span
                  className={`score ${r[8] < 70 ? "danger" : r[8] < 85 ? "warn" : ""}`}
                >
                  {r[8]}
                </span>
              )
            }
          />
          <div className="table-footer request-pagination">
            <span>
              Showing {filtered.length ? safePage * 10 + 1 : 0}–
              {Math.min((safePage + 1) * 10, filtered.length)} of{" "}
              {filtered.length.toLocaleString()}
            </span>
            <div>
              <button
                disabled={safePage === 0}
                onClick={() => setRequestPage((page) => Math.max(0, page - 1))}
                aria-label="Previous 10 requests"
              >
                &lt;
              </button>
              <button
                disabled={safePage >= pageCount - 1}
                onClick={() =>
                  setRequestPage((page) => Math.min(pageCount - 1, page + 1))
                }
                aria-label="Next 10 requests"
              >
                &gt;
              </button>
            </div>
          </div>
        </Card>
        <RequestAssistant request={selected} />
      </div>
    </>
  );
}
function DataTable({ headers, rows, selected, onSelect, render }) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, ri) => (
            <tr
              key={r[0]}
              className={r === selected ? "selected" : ""}
              onClick={() => onSelect?.(r)}
            >
              {headers.map((_, i) => (
                <td key={i}>{render ? render(r[i], i, r) : r[i]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function RequestAssistant({ request }) {
  return (
    <Card
      className="assistant-panel"
      title="AI Credit Assistant"
      action={<Sparkles size={16} />}
    >
      <div className="borrower">
        <span>
          <Building2 size={18} />
        </span>
        <div>
          <strong>{request[0]}</strong>
          <small>
            {request[1]} · {request[4]} · {request[5]}
          </small>
        </div>
      </div>
      <h3>Summary</h3>
      <p>
        Borrower requests {request[6]} of funding. Total exposure would rise to{" "}
        {request[3]}. Rating {request[5]} requires enhanced policy review.
      </p>
      <h3>Risk Factors</h3>
      <ul>
        <li>Leverage of 5.5x exceeds policy limit of 4.5x</li>
        <li>Collateral coverage is 15pp below policy floor</li>
        <li>Sector concentration approaches RAF ceiling</li>
      </ul>
      <h3>Policy Concerns</h3>
      <div className="tag-row">
        <Badge tone="clause">CP-4.2</Badge>
        <Badge tone="clause">COL-2.1</Badge>
        <Badge tone="clause">RAF-3.5</Badge>
      </div>
      <h3>Recommended Actions</h3>
      <ol>
        <li>Escalate to Credit Committee</li>
        <li>Request additional collateral</li>
        <li>Add cash-sweep covenant</li>
      </ol>
      <div className="button-row">
        <button
          className="btn primary"
          onClick={() => (location.hash = "compliance")}
        >
          Open Compliance
        </button>
        <button
          className="btn secondary"
          onClick={() => (location.hash = "simulator")}
        >
          Simulate
        </button>
      </div>
      <small className="disclaimer">
        AI-generated. Recommendations require human approval.
      </small>
    </Card>
  );
}

function Policy({ notify }) {
  const [section, setSection] = useState("§ 4.2 Leverage Limits"),
    [message, setMessage] = useState(""),
    [explorerTab, setExplorerTab] = useState("library");
  const ask = () => {
    if (message.trim()) {
      setMessage("");
      notify("Policy copilot response generated");
    }
  };
  return (
    <>
      <Heading page="policy" />
      <div
        className="policy-view-toggle"
        role="tablist"
        aria-label="Policy Intelligence views"
      >
        <button
          type="button"
          role="tab"
          aria-selected={explorerTab === "library"}
          className={explorerTab === "library" ? "active" : ""}
          onClick={() => setExplorerTab("library")}
        >
          Policy Explorer
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={explorerTab === "controls"}
          className={explorerTab === "controls" ? "active" : ""}
          onClick={() => setExplorerTab("controls")}
        >
          Controls
        </button>
      </div>
      <div
        className={`policy-layout ${
          explorerTab === "controls" ? "controls-view" : ""
        }`}
      >
        {explorerTab === "library" && (
          <Card title="Policy Explorer" action={<Search size={15} />}>
            <div className="tree">
              <strong>Credit Policy</strong>
              <p>CP-Wholesale-v4.2</p>
              {[
                "§ 4.1 Underwriting Standards",
                "§ 4.2 Leverage Limits",
                "§ 4.3 Tenor Limits",
                "§ 4.4 Covenant Package",
              ].map((x) => (
                <button
                  className={section === x ? "active" : ""}
                  onClick={() => setSection(x)}
                  key={x}
                >
                  {x}
                </button>
              ))}
              <p>CP-Retail-v3.1</p>
              <button>§ 3.1 DSCR Minimums</button>
              <button>§ 3.2 LTV Ceilings</button>
              {[
                "Risk Appetite Framework",
                "Collateral Standards",
                "Pricing Policy",
                "Sector Policy",
                "Delegation Matrix",
                "Regulatory Guidance",
              ].map((x) => (
                <strong key={x}>{x}</strong>
              ))}
            </div>
          </Card>
        )}
        {explorerTab === "library" ? (
          <>
            <div className="policy-main">
              <Card
                title="CP-Wholesale-v4.2"
                action={
                  <>
                    <Badge tone="effective">v4.2</Badge>
                    <small className="effective-date">
                      Effective 2026-01-15
                    </small>
                  </>
                }
              >
                <div className="document">
                  <small>CREDIT POLICY · SECTION 4.2 LEVERAGE LIMITS</small>
                  <h2>{section}</h2>
                  <p>
                    Maximum Debt/EBITDA leverage for Commercial Real Estate
                    exposures shall not exceed <mark>4.5x at origination</mark>,
                    measured on a trailing twelve-month basis. Speculative
                    construction exposures are further constrained by sector
                    policy SEC-CRE-v2.0.
                  </p>
                  <p>
                    Any deal above the threshold must be escalated to the Credit
                    Committee under delegation matrix DEL-3.1, with a documented
                    business justification and remediation path.
                  </p>
                  <p>
                    For borrowers rated below BB, the effective ceiling drops to
                    4.0x. Exceptions shall be logged in the Exception Registry
                    with severity classification per §7.4.
                  </p>
                  <h3>Related Policies</h3>
                  <div className="tag-row">
                    <Badge tone="clause">SEC-CRE-v2.0 §2.1</Badge>
                    <Badge tone="clause">DEL-3.1</Badge>
                    <Badge tone="clause">RAF-3.5</Badge>
                  </div>
                </div>
              </Card>
              <Card
                className="policy-controls-card"
                title={
                  <>
                    <ShieldCheck size={18} />
                    Controls Against This Policy
                    <span className="policy-control-count">1</span>
                  </>
                }
                action={
                  <button className="btn secondary policy-add-control">
                    <Plus size={16} />
                    Add Control
                  </button>
                }
              >
                <div className="policy-control-content">
                  <article className="policy-control-item">
                    <div className="policy-control-summary">
                      <div>
                        <h3>Leverage Ceiling Check</h3>
                        <p>
                          CTL-101 · Preventive · Automated · Credit Risk · Per
                          Deal
                        </p>
                      </div>
                      <Badge tone="effective">Effective</Badge>
                    </div>
                    <p className="policy-control-description">
                      Blocks submission of any wholesale deal with Debt/EBITDA
                      above the policy ceiling without a logged exception.
                    </p>
                    <div className="policy-control-progress">
                      <div>
                        <i style={{ width: "96%" }} />
                      </div>
                      <span>96%</span>
                    </div>
                  </article>
                  <dl className="policy-control-review">
                    <div>
                      <dt>Owner:</dt>
                      <dd>Chief Credit Officer</dd>
                    </div>
                    <div>
                      <dt>Last Reviewed:</dt>
                      <dd>2026-06-01</dd>
                    </div>
                    <div>
                      <dt>Next Review:</dt>
                      <dd>2026-12-01</dd>
                    </div>
                    <div>
                      <dt>Status:</dt>
                      <dd>
                        <Badge tone="effective">Active</Badge>
                      </dd>
                    </div>
                  </dl>
                </div>
              </Card>
            </div>
            <Card
              className="copilot"
              title="Policy Copilot"
              action={<Bot size={17} />}
            >
              <div className="chat">
                <div className="chat-user">
                  Show leverage limits for Commercial Real Estate.
                </div>
                <div className="chat-ai">
                  <Sparkles size={14} />
                  <p>
                    Per CP-Wholesale-v4.2 §4.2, the maximum leverage for CRE is{" "}
                    <strong>4.5x Debt/EBITDA</strong>. Sector overlays tighten
                    this to 4.0x for speculative construction.
                  </p>
                  <div className="citations">
                    <small>CITATIONS</small>
                    <button>CP-Wholesale-v4.2 · §4.2</button>
                    <button>SEC-CRE-v2.0 · §2.1</button>
                  </div>
                </div>
              </div>
              <div className="suggestions">
                <button onClick={() => setMessage("Approvals for BB rated")}>
                  Approvals for BB rated
                </button>
                <button onClick={() => setMessage("Policy version changes")}>
                  Policy version changes
                </button>
              </div>
              <div className="chat-input">
                <input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && ask()}
                  placeholder="Ask about any policy..."
                />
                <button onClick={ask}>
                  <Send size={15} />
                </button>
              </div>
            </Card>
          </>
        ) : (
          <ControlsWorkspace />
        )}
      </div>
    </>
  );
}

const CONTROLS = [
  {
    id: "CTL-101",
    name: "Leverage Ceiling Check",
    owner: "Credit Risk",
    clause: "CP-4.2",
    type: "Preventive",
    automation: "Automated",
    frequency: "Per Deal",
    effectiveness: "96%",
    status: "Effective",
  },
  {
    id: "CTL-204",
    name: "Collateral Coverage Check",
    owner: "Collateral Risk",
    clause: "COL-2.1",
    type: "Preventive",
    automation: "Automated",
    frequency: "Per Deal",
    effectiveness: "92%",
    status: "Effective",
  },
  {
    id: "CTL-305",
    name: "RAROC Floor Validation",
    owner: "Credit Risk",
    clause: "PRC-3.2",
    type: "Detective",
    automation: "Automated",
    frequency: "Per Deal",
    effectiveness: "88%",
    status: "Effective",
  },
  {
    id: "CTL-410",
    name: "Tenor Limit Check",
    owner: "Credit Risk",
    clause: "CP-4.3",
    type: "Preventive",
    automation: "Manual",
    frequency: "Per Deal",
    effectiveness: "84%",
    status: "Effective",
  },
  {
    id: "CTL-512",
    name: "Covenant Package Review",
    owner: "Credit Risk",
    clause: "CP-4.4",
    type: "Detective",
    automation: "Manual",
    frequency: "Quarterly",
    effectiveness: "74%",
    status: "Review Due",
  },
  {
    id: "CTL-618",
    name: "Sector Concentration Monitor",
    owner: "Portfolio Risk",
    clause: "RAF-3.5",
    type: "Preventive",
    automation: "Automated",
    frequency: "Daily",
    effectiveness: "90%",
    status: "Effective",
  },
];

const CONTROL_ROWS = CONTROLS.map((control) => [
  control.id,
  control.clause,
  control.type,
  control.frequency,
  control.effectiveness,
  control.status,
]);

function ControlsWorkspace() {
  const [selectedControl, setSelectedControl] = useState(CONTROLS[0]);
  const selectedRow = CONTROL_ROWS.find(
    ([id]) => id === selectedControl.id,
  );
  return (
    <div className="controls-workspace">
      <div className="control-metrics">
        <ControlMetric
          label="Total Controls"
          value="10"
          detail="Mapped to policy clauses"
        />
        <ControlMetric
          label="Effective"
          value="5/10"
          detail="Latest test cycle"
          tone="success"
        />
        <ControlMetric
          label="Avg Effectiveness"
          value="80%"
          detail="Weighted across controls"
        />
        <ControlMetric
          label="Automated"
          value="6"
          detail="Machine-executed checks"
        />
      </div>
      <div className="controls-layout">
        <Card title="Controls Register" className="controls-register">
          <DataTable
            headers={[
              "Control",
              "Clause",
              "Type",
              "Frequency",
              "Effectiveness",
              "Status",
            ]}
            rows={CONTROL_ROWS}
            selected={selectedRow}
            onSelect={(row) =>
              setSelectedControl(
                CONTROLS.find((control) => control.id === row[0]),
              )
            }
            render={(value, index, row) => {
              const control = CONTROLS.find(
                (item) => item.id === row[0],
              );
              if (index === 0) {
                return (
                  <div className="control-name-cell">
                    <strong>{control.name}</strong>
                    <small>
                      {control.id} · {control.owner}
                    </small>
                  </div>
                );
              }
              return index === 5 ? <Badge>{value}</Badge> : value;
            }}
          />
        </Card>
        <Card title="Control Detail" className="control-detail">
          <div className="detail-title">
            <div>
              <h3>{selectedControl.name}</h3>
              <small>
                {selectedControl.id} · linked to § {selectedControl.clause}
              </small>
            </div>
          </div>
          <div className="control-facts">
            <p>
              <span>Type:</span> <strong>{selectedControl.type}</strong>
            </p>
            <p>
              <span>Automation:</span>{" "}
              <strong>{selectedControl.automation}</strong>
            </p>
            <p>
              <span>Owner:</span> <strong>{selectedControl.owner}</strong>
            </p>
            <p>
              <span>Frequency:</span> <strong>{selectedControl.frequency}</strong>
            </p>
            <p>
              <span>Last Tested:</span> <strong>2026-07-14</strong>
            </p>
            <p>
              <span>Failures (90d):</span> <strong>2</strong>
            </p>
          </div>
          <div className="effectiveness-score">
            <span>Effectiveness Score</span>
            <strong>{selectedControl.effectiveness}</strong>
            <div>
              <i style={{ width: selectedControl.effectiveness }} />
            </div>
          </div>
          <div className="control-assessment">
            <h4>
              <Sparkles size={14} /> AI Control Assessment
            </h4>
            <p>
              {selectedControl.id} is operating as designed with 2 exceptions
              in the last 90 days. No remediation required; continue per deal
              testing.
            </p>
          </div>
          <div className="control-actions">
            <button className="btn primary">
              <Play size={14} />
              Run Test
            </button>
            <button className="btn secondary">
              <FileText size={14} />
              View Evidence
            </button>
          </div>
        </Card>
      </div>
    </div>
  );
}

function ControlMetric({ label, value, detail, tone = "" }) {
  return (
    <div className={`card control-metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function Compliance({ notify }) {
  const heat = [
    "Leverage",
    "Collateral",
    "Pricing",
    "Tenor",
    "Covenant",
    "Sector",
    "Delegation",
    "Rating",
    "Country",
    "Industry",
    "LTV",
    "DSCR",
    "Concentration",
    "Currency",
    "Duration",
    "Liquidity",
  ];
  return (
    <>
      <Heading page="compliance">
        <button
          className="btn tertiary"
          onClick={() => (location.hash = "requests")}
        >
          Back to Requests
        </button>
        <button
          className="btn primary"
          onClick={() => notify("Exception EX-8829 created")}
        >
          <Plus size={14} />
          Create Exception
        </button>
      </Heading>
      <Card title="Credit Proposal Inputs" className="proposal-card">
        <div className="proposal-inputs">
          <ProposalInput label="Borrower Rating" value="BB-" />
          <ProposalInput label="Leverage" value="5.5x" alert />
          <ProposalInput label="Policy Limit" value="4.5x" />
          <ProposalInput label="Collateral Coverage" value="85%" alert />
          <ProposalInput label="Required Coverage" value="100%" />
        </div>
      </Card>
      <div className="compliance-counts">
        <ComplianceCount
          icon={CheckCircle2}
          label="Pass"
          value="2"
          tone="pass"
        />
        <ComplianceCount
          icon={AlertTriangle}
          label="Warning"
          value="2"
          tone="warning"
        />
        <ComplianceCount
          icon={ShieldAlert}
          label="Breach"
          value="3"
          tone="breach"
        />
      </div>
      <div className="layout compliance-grid">
        <Card title="AI Compliance Findings" className="table-card">
          <DataTable
            headers={[
              "Policy Clause",
              "Actual",
              "Threshold",
              "Variance",
              "Severity",
              "Evidence",
            ]}
            rows={FINDINGS}
            render={(v, i, r) =>
              i === 0 ? (
                <strong>{v}</strong>
              ) : i === 4 ? (
                <Badge>{v}</Badge>
              ) : i === 5 ? (
                <button
                  className="trace"
                  onClick={() => notify(`Evidence opened for ${r[0]}`)}
                >
                  Trace <ExternalLink size={12} />
                </button>
              ) : (
                v
              )
            }
          />
        </Card>
        <Card title="Compliance Heatmap">
          <div className="heatmap">
            {heat.map((x, i) => (
              <div
                key={x}
                className={
                  [0, 5, 10, 15].includes(i)
                    ? "breach"
                    : [1, 2, 6, 7, 11, 12].includes(i)
                      ? "warning"
                      : "pass"
                }
              >
                {x}
              </div>
            ))}
          </div>
          <div className="heat-key">
            <span>
              <i className="pass" />
              Pass
            </span>
            <span>
              <i className="warning" />
              Warning
            </span>
            <span>
              <i className="breach" />
              Breach
            </span>
          </div>
        </Card>
      </div>
      <Card title="Evidence Traceability" className="evidence-card">
        <div className="evidence-grid">
          <Evidence
            icon={Database}
            label="Source Data"
            value="Financials FY25 Q2"
            sub="S3://credit-docs/harbor-fy25.xlsx"
          />
          <Evidence
            icon={FileText}
            label="Credit Proposal"
            value="CR-10242 v2"
            sub="Proposal Memo"
          />
          <Evidence
            icon={BookOpen}
            label="Policy Document"
            value="CP-Wholesale-v4.2"
            sub="Policy Library"
          />
          <Evidence
            icon={Target}
            label="Policy Clause"
            value="§ 4.2 Leverage Limits"
            sub="Clause Detail"
          />
        </div>
      </Card>
    </>
  );
}
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
      <span className={tone}>
        <Icon size={20} />
      </span>
      <div>
        <strong>{value}</strong>
        <small>{label}</small>
      </div>
    </div>
  );
}
function Evidence({ icon: Icon, label, value, sub }) {
  return (
    <div className="evidence">
      <span>
        <Icon size={16} />
      </span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <p>{sub}</p>
      </div>
      <ChevronRight size={14} />
    </div>
  );
}

function Exceptions({ notify }) {
  const [tab, setTab] = useState("All"),
    [selected, setSelected] = useState(0);
  const row = EXCEPTIONS[selected],
    rows = tab === "All" ? EXCEPTIONS : EXCEPTIONS.filter((x) => x[7] === tab);
  return (
    <>
      <Heading page="exceptions" />
      <div className="tabs">
        {["All", "Active", "Pending Approval", "Remediation", "Closed"].map(
          (x) => (
            <button
              className={tab === x ? "active" : ""}
              onClick={() => setTab(x)}
              key={x}
            >
              {x}
              {x === "All" ? " (8)" : ""}
            </button>
          ),
        )}
      </div>
      <div className="exception-layout">
        <Card title="Exception Registry">
          <DataTable
            headers={[
              "ID",
              "Type",
              "Clause",
              "Severity",
              "Exposure",
              "Owner",
              "Due",
              "Status",
            ]}
            rows={rows}
            selected={row}
            onSelect={(r) => setSelected(EXCEPTIONS.indexOf(r))}
            render={(v, i) =>
              i === 0 ? (
                <strong>{v}</strong>
              ) : i === 3 || i === 7 ? (
                <Badge>{v}</Badge>
              ) : (
                v
              )
            }
          />
        </Card>
        <Card
          className="exception-detail"
          title={row[0]}
          action={<Badge>{row[3]}</Badge>}
        >
          <h3>
            {row[1]} exception · {row[2]}
          </h3>
          <div className="workflow">
            {["Detected", "Reviewed", "Approved", "Remediated", "Closed"].map(
              (x, i) => (
                <div className={i < 2 ? "done" : ""} key={x}>
                  <i>{i < 2 ? "✓" : "○"}</i>
                  <span>{x}</span>
                  {i === 1 && <Badge tone="clause">Current</Badge>}
                </div>
              ),
            )}
          </div>
          <h3>AI Exception Rationale</h3>
          <Rationale title="Why detected">
            Actual leverage of 5.5x exceeds the CRE ceiling by 22%.
          </Rationale>
          <Rationale title="Business justification">
            Bridge financing pending stabilization; sponsor commits to
            de-leverage within 18 months.
          </Rationale>
          <Rationale title="Risk implication">
            Elevated Expected Loss; +$1.4M ECL; concentration approaches the RAF
            ceiling.
          </Rationale>
          <Rationale title="Recommended remediation">
            Add cash-sweep covenant; require quarterly leverage attestation.
          </Rationale>
          <div className="button-row">
            <button
              className="btn primary"
              onClick={() => notify(`${row[0]} approved`)}
            >
              Approve
            </button>
            <button
              className="btn secondary"
              onClick={() => notify(`${row[0]} escalated`)}
            >
              Escalate
            </button>
          </div>
          <h3>Workflow History</h3>
          <div className="history">
            <p>2026-07-18 · Detected by AI Compliance Agent</p>
            <p>2026-07-19 · Reviewed by S. Chen</p>
            <p>2026-07-20 · Awaiting approver</p>
          </div>
        </Card>
      </div>
    </>
  );
}
function Rationale({ title, children }) {
  return (
    <div className="rationale">
      <strong>{title}:</strong>
      <p>{children}</p>
    </div>
  );
}

function Simulator({ notify }) {
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
          <Card title="Sensitivity Analysis · Facility Amount">
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
            <b>↓ 31%</b> Expected loss
            <br />
            <b>↓ $24M</b> RWA impact
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

function Portfolio() {
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
              Exp {exp}% · {breaches} breaches
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
}

function Shell() {
  const initial = location.hash.slice(1) || "dashboard";
  const [page, setPage] = useState(
      NAV.some((n) => n[0] === initial) ? initial : "dashboard",
    ),
    [collapsed, setCollapsed] = useState(false),
    [mobile, setMobile] = useState(false),
    [toast, setToast] = useState(""),
    [summary, setSummary] = useState({});
  useEffect(() => {
    const handler = () => setPage(location.hash.slice(1) || "dashboard");
    addEventListener("hashchange", handler);
    fetch(`${API}/api/summary`)
      .then((r) => (r.ok ? r.json() : {}))
      .then(setSummary)
      .catch(() => {});
    return () => removeEventListener("hashchange", handler);
  }, []);
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
    policy: Policy,
    compliance: Compliance,
    exceptions: Exceptions,
    simulator: Simulator,
    portfolio: Portfolio,
  }[page];
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
        <div className="side-user">
          <div>SC</div>
          {!collapsed && (
            <span>
              <strong>Sarah Chen</strong>
              <small>Credit Risk Manager</small>
            </span>
          )}
          <ChevronRight size={14} />
        </div>
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
        </header>
        <main>
          <Page notify={notify} summary={summary} />
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
createRoot(document.getElementById("root")).render(<Shell />);
