import React, { useState } from "react";
import {
  CheckCircle2,
  CircleX,
  Eye,
  EyeOff,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { META } from "../config";

export const slug = (v) => String(v).toLowerCase().replaceAll(" ", "-");
export const money = (v) =>
  `$${v.toLocaleString(undefined, { maximumFractionDigits: 1 })}M`;
export function Badge({ children, tone }) {
  return <span className={`badge ${tone || slug(children)}`}>{children}</span>;
}
export function Heading({ page, children }) {
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
export function Card({ title, sub, action, className = "", children }) {
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
export function Metric({
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
export function LineChart({ second = false }) {
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
export function Bars({ data, labels }) {
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
export function Insight({ children }) {
  return (
    <div className="insight">
      <Badge tone="ai">AI</Badge>
      <p>{children}</p>
    </div>
  );
}

export function Legend() {
  return (
    <div className="legend">
      <i />
      Detected <i className="green-dot" />
      Remediated
    </div>
  );
}

export function StageExposure({ label, value, percent, tone }) {
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


export function DataTable({ headers, rows, selected, onSelect, render, className = "" }) {
  return (
    <div className={`table-scroll ${className}`}>
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
              key={r[1] || r[0]}
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

export const DEFAULT_PASSWORD_POLICY = {
  minimum_length: 12,
  maximum_length: 128,
  minimum_uppercase: 1,
  minimum_lowercase: 1,
  minimum_digits: 1,
  minimum_special: 1,
};
export const passwordRules = (policy = DEFAULT_PASSWORD_POLICY, userId = "") => [
  [`At least ${policy.minimum_length} characters`, (value) => value.length >= policy.minimum_length],
  [`No more than ${policy.maximum_length} characters`, (value) => value.length > 0 && value.length <= policy.maximum_length],
  [`At least ${policy.minimum_uppercase} uppercase character(s)`, (value) => [...value].filter((character) => /[A-Z]/.test(character)).length >= policy.minimum_uppercase],
  [`At least ${policy.minimum_lowercase} lowercase character(s)`, (value) => [...value].filter((character) => /[a-z]/.test(character)).length >= policy.minimum_lowercase],
  [`At least ${policy.minimum_digits} digit(s)`, (value) => [...value].filter((character) => /[0-9]/.test(character)).length >= policy.minimum_digits],
  [`At least ${policy.minimum_special} special character(s)`, (value) => [...value].filter((character) => /[^A-Za-z0-9]/.test(character)).length >= policy.minimum_special],
  ["Does not contain your user ID", (value) => value.length > 0 && Boolean(userId.trim()) && !value.toLowerCase().includes(userId.trim().toLowerCase())],
];
export const preventClipboardAction = (event) => event.preventDefault();
export const NO_CLIPBOARD = {
  onCopy: preventClipboardAction,
  onCut: preventClipboardAction,
  onPaste: preventClipboardAction,
  onContextMenu: preventClipboardAction,
};


export function PasswordPolicy({ password, userId, policy = DEFAULT_PASSWORD_POLICY }) {
  return (
    <div className="password-policy" aria-live="polite">
      <strong>Password requirements</strong>
      {passwordRules(policy, userId).map(([label, test]) => {
        const passed = test(password);
        return (
          <span className={passed ? "met" : "unmet"} key={label}>
            {passed ? <CheckCircle2 size={15} /> : <CircleX size={15} />}
            {label}
          </span>
        );
      })}
    </div>
  );
}

export function AuthField({ label, children }) {
  return (
    <label className="auth-field">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function SecretInput(props) {
  const [visible, setVisible] = useState(false);
  return (
    <div className="secret-input">
      <input {...props} {...NO_CLIPBOARD} type={visible ? "text" : "password"} />
      <button
        type="button"
        onClick={() => setVisible((current) => !current)}
        aria-label={visible ? "Hide value" : "Show value"}
        title={visible ? "Hide" : "Show"}
      >
        {visible ? <EyeOff size={17} /> : <Eye size={17} />}
      </button>
    </div>
  );
}
