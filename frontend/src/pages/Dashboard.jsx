import React, { useEffect, useMemo, useRef, useState } from "react";
import { FileText, ShieldCheck, AlertTriangle, CircleDollarSign, ShieldAlert, Clock3, Download, RefreshCw } from "lucide-react";
import { apiRequest } from "../api/client";
import { Card, Heading, Metric, StageExposure, Legend, money } from "../components/ui";

const amount = (value) => money(Number(value) / 1000000);
const colors = ["#20bad8", "#40bf91", "#efb75b", "#ac8ee8", "#e77991"];
const Empty = ({ children = "No records available." }) => <p className="dashboard-empty">{children}</p>;

function Trend({ data }) {
  const [hovered, setHovered] = useState(null);
  const max = Math.max(1, ...data.flatMap((row) => [row.detected, row.remediated]));
  const ticks = [0, Math.ceil(max / 2), max];
  const plotted = (key) => data.map((row, i) => ({ x: 55 + i * 615 / Math.max(1, data.length - 1), y: 185 - row[key] / max * 150 }));
  return <div className="line-chart">
    <svg viewBox="0 0 700 220" role="img" aria-label="Monthly detected and remediated exceptions">
      {ticks.map((value) => { const y = 185 - value / max * 150; return <g key={value}><line x1="55" x2="680" y1={y} y2={y} className="gridline" /><text x="47" y={y + 3} className="chart-tick" textAnchor="end">{value}</text></g>; })}
      <line x1="55" x2="55" y1="35" y2="185" className="chart-axis-line" />
      <line x1="55" x2="680" y1="185" y2="185" className="chart-axis-line" />
      {['detected', 'remediated'].map((key) => <React.Fragment key={key}>
        <polyline className={`line ${key === 'detected' ? 'aqua' : 'green'}`} points={plotted(key).map((point) => `${point.x},${point.y}`).join(" ")} />
        {plotted(key).map((point, index) => <circle key={data[index].label} className={`chart-point ${key === 'detected' ? 'aqua-point' : 'green-point'}`} cx={point.x} cy={point.y} r="5" tabIndex="0" onMouseEnter={() => setHovered({ index, key, ...point })} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered({ index, key, ...point })} onBlur={() => setHovered(null)}><title>{data[index].label}: {key} {data[index][key]}</title></circle>)}
      </React.Fragment>)}
      {data.map((row, index) => <text key={row.label} x={55 + index * 615 / Math.max(1, data.length - 1)} y="205" className="chart-tick" textAnchor="middle">{row.label}</text>)}
      <text x="14" y="110" className="chart-axis-title" textAnchor="middle" transform="rotate(-90 14 110)">Exceptions</text>
      <text x="365" y="219" className="chart-axis-title" textAnchor="middle">Month</text>
      {hovered && <g className="chart-tooltip" pointerEvents="none"><rect x={Math.min(hovered.x + 8, 570)} y={Math.max(hovered.y - 34, 4)} width="120" height="27" rx="4" /><text x={Math.min(hovered.x + 15, 577)} y={Math.max(hovered.y - 17, 21)}>{data[hovered.index].label}: {hovered.key} {data[hovered.index][hovered.key]}</text></g>}
    </svg>
  </div>;
}

function ifrsStages(payments) {
  const total = payments.reduce((sum, row) => sum + Number(row.value), 0);
  if (!total) return [];
  // Allocate in $0.1M units so the three displayed values exactly match the displayed total.
  const totalUnits = Math.max(3, Math.round(total / 100000));
  const minimum = Math.max(1, Math.floor(totalUnits * 0.1));
  const distributable = totalUnits - minimum * 3;
  const weights = [Math.random() + 0.35, Math.random() + 0.35, Math.random() + 0.35];
  const weightTotal = weights.reduce((sum, value) => sum + value, 0);
  const allocated = weights.map((weight) => Math.floor(distributable * weight / weightTotal));
  allocated[2] += distributable - allocated.reduce((sum, value) => sum + value, 0);
  const values = allocated.map((value) => (value + minimum) * 100000);
  return values.map((value, index) => ({ label: `Stage ${index + 1}`, value }));
}

function ExposureDonut({ data }) {
  const [hovered, setHovered] = useState(null);
  const total = data.reduce((sum, row) => sum + Number(row.value), 0);
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  let consumed = 0;
  return <>
    <div className="interactive-donut">
      <svg viewBox="0 0 160 160" role="img" aria-label="Exposure by exception type">
        <circle className="donut-base" cx="80" cy="80" r={radius} />
        {data.map((row, index) => {
          const share = total ? Number(row.value) / total : 0;
          const offset = consumed;
          consumed += share;
          return <circle key={row.label} className="donut-segment" cx="80" cy="80" r={radius} stroke={colors[index % colors.length]} strokeDasharray={`${share * circumference} ${circumference}`} strokeDashoffset={-offset * circumference} tabIndex="0" onMouseEnter={() => setHovered(index)} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered(index)} onBlur={() => setHovered(null)}><title>{row.label}: {amount(row.value)} ({(share * 100).toFixed(1)}%)</title></circle>;
        })}
        <text x="80" y="76" className="donut-total" textAnchor="middle">{hovered == null ? amount(total) : amount(data[hovered].value)}</text>
        <text x="80" y="91" className="donut-label" textAnchor="middle">{hovered == null ? "Total exposure" : data[hovered].label}</text>
      </svg>
    </div>
    <div className="donut-key">{data.map((row, i) => <span key={row.label} style={{ color: colors[i % colors.length] }}>{row.label} {amount(row.value)} ({total ? (Number(row.value) / total * 100).toFixed(1) : 0}%)</span>)}</div>
  </>;
}

export default function Dashboard({ session }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [insightError, setInsightError] = useState("");
  const generation = useRef(null);
  useEffect(() => () => { generation.current?.abort(); generation.current = null; }, [session.token]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      try {
        const result = await apiRequest("/api/dashboard", { signal: controller.signal }, session.token);
        if (active) { setData((previous) => previous?.insights_generated_at &&
          (!result.insights_generated_at || new Date(previous.insights_generated_at) > new Date(result.insights_generated_at))
          ? { ...result, insights: previous.insights, insights_generated_at: previous.insights_generated_at,
              insights_source_generated_at: previous.insights_source_generated_at } : result); setError(""); }
      } catch (err) {
        if (active) setError(err.message);
      } finally { if (active) setLoading(false); }
    }
    load();
    const interval = setInterval(load, 60000);
    return () => { active = false; controller.abort(); clearInterval(interval); };
  }, [session.token, refresh]);

  async function generateInsights() {
    if (generation.current) return;
    const controller = new AbortController();
    generation.current = controller;
    setGenerating(true);
    setInsightError("");
    try {
      const result = await apiRequest("/api/dashboard/insights", { method: "POST", signal: controller.signal }, session.token);
      if (!controller.signal.aborted) setData((previous) => ({ ...previous, ...result }));
    } catch (err) {
      if (!controller.signal.aborted) setInsightError(err.message);
    } finally {
      if (!controller.signal.aborted) { generation.current = null; setGenerating(false); }
    }
  }

  function exportReport() {
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "executive-dashboard.json";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  const insights = data?.insights || [];
  const metrics = data?.metrics;
  const stages = useMemo(() => ifrsStages(data?.payments || []), [data?.payments]);
  const stageTotal = stages.reduce((sum, row) => sum + row.value, 0);
  const maxPayment = Math.max(1, ...stages.map((row) => Number(row.value)));
  return <>
    <Heading page="dashboard">
      <button className="btn secondary" disabled={loading} onClick={() => setRefresh((value) => value + 1)}><RefreshCw size={15} />{loading ? "Refreshing…" : "Refresh"}</button>
      <button className="btn secondary" disabled={!data || !!error} onClick={exportReport}><Download size={15} />Export Report</button>
    </Heading>
    {error && <p role="alert" className="dashboard-empty">Could not refresh dashboard: {error}. <button className="text-btn" onClick={() => setRefresh((value) => value + 1)}>Retry</button></p>}
    {!data ? <Empty>{loading ? "Loading dashboard from PostgreSQL…" : "Dashboard data is unavailable."}</Empty> : <>
      <p className="dashboard-empty">Current portfolio · Updated {new Date(data.generated_at).toLocaleString()} · Refreshes every minute{error ? " · Showing last successful update" : ""}</p>
      <div className="metrics six">
        <Metric icon={FileText} label="Active Credit Requests" value={metrics.active_requests.toLocaleString()} />
        <Metric icon={ShieldCheck} label="Average Compliance Score" value={metrics.policy_compliance == null ? "—" : `${metrics.policy_compliance}%`} />
        <Metric icon={AlertTriangle} label="Active Exceptions" value={metrics.open_exceptions.toLocaleString()} />
        <Metric icon={CircleDollarSign} label="Exposure Under Exception" value={amount(metrics.exception_exposure)} />
        <Metric icon={ShieldAlert} label="High Severity Breaches" value={metrics.high_severity.toLocaleString()} />
        <Metric icon={Clock3} label="Overdue Remediation" value={metrics.overdue.toLocaleString()} />
      </div>
      <div className="layout two-one">
        <Card title="Exception Trend (last 6 months)" sub="Monthly counts: detected / remediated, including closed" action={<Legend />}><Trend data={data.trend} /></Card>
        <Card title="Portfolio Insights" sub="AI-generated from dashboard data" action={<button className="btn secondary" disabled={loading || !!error || generating} onClick={generateInsights}>{generating ? "Generating..." : "Get Insights"}</button>}>
          <div className="portfolio-insights-scroll" role="region" aria-label="Portfolio insights" tabIndex={0}>
            <div aria-live="polite" aria-busy={generating}>
              {insightError && <p role="alert" className="dashboard-empty">{insightError}</p>}
              {data.insights_generated_at && <p className="dashboard-empty">Saved {new Date(data.insights_generated_at).toLocaleString()} | Based on dashboard data from {new Date(data.insights_source_generated_at).toLocaleString()}</p>}
              {insights.length ? <ol className="portfolio-insights-list">{insights.map((text, index) => <li key={index}>{text}</li>)}</ol> : <Empty>Click Get Insights to generate 5 to 7 points from the latest dashboard data.</Empty>}
            </div>
          </div>
        </Card>
      </div>
      <div className="layout thirds">
        <Card title="Open Exceptions by Industry">{data.industries.length ? data.industries.map((row) => <div className="rank" key={row.label}><span>{row.label}</span><b>{row.value}</b></div>) : <Empty />}</Card>
        <Card title="Exposure by Exception Type" sub="Exception-level amounts; a request may have multiple exceptions">
          {data.types.length ? <ExposureDonut data={data.types} /> : <Empty />}
        </Card>
        <Card title="Top Violated Policies" sub="Open exceptions by clause">{data.policies.length ? data.policies.map((row) => <div className="rank" key={row.label}><span>{row.label}</span><b>{row.value}</b></div>) : <Empty />}</Card>
      </div>
      <Card title="IFRS 9 Stage Exposure Distribution ($M)" sub={stages.length ? `Random split of ${amount(stageTotal)} total exposure` : "Random allocation of latest total facility exposure"} className="ifrs-card">
        {stages.length ? <div className="stage-chart">{stages.map((row, i) => <StageExposure key={row.label} label={row.label} value={amount(row.value)} percent={Number(row.value) / maxPayment * 100} tone={["stage-one", "stage-two", "stage-three"][i]} />)}</div> : <Empty>No borrower exposure history available.</Empty>}
      </Card>
    </>}
  </>;
}
