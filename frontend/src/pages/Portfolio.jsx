import React, { useEffect, useState } from "react";
import { RefreshCw, Send, Sparkles } from "lucide-react";
import { apiRequest } from "../api/client";
import { Card, Heading, Legend, money } from "../components/ui";

const Empty = ({ children = "No records available." }) => <p className="dashboard-empty">{children}</p>;
const inMillions = (value) => money(Number(value || 0) / 1000000);

function InteractiveLine({ data, series, yTitle, currency = false, ariaLabel }) {
  const [hovered, setHovered] = useState(null);
  const max = Math.max(1, ...data.flatMap((row) => series.map(({ key }) => Number(row[key]))));
  const ticks = [0, max / 2, max];
  const plot = (key) => data.map((row, index) => ({
    x: 58 + index * 612 / Math.max(1, data.length - 1),
    y: 180 - Number(row[key]) / max * 145,
  }));
  const format = (value) => currency ? `$${Number(value).toFixed(2)}M` : Number(value).toFixed(0);
  return <div className="line-chart">
    <svg viewBox="0 0 700 220" role="img" aria-label={ariaLabel}>
      {ticks.map((value) => { const y = 180 - value / max * 145; return <g key={value}><line x1="58" x2="670" y1={y} y2={y} className="gridline" /><text x="50" y={y + 3} className="chart-tick" textAnchor="end">{format(value)}</text></g>; })}
      <line x1="58" x2="58" y1="35" y2="180" className="chart-axis-line" />
      <line x1="58" x2="670" y1="180" y2="180" className="chart-axis-line" />
      {series.map(({ key, label, tone }) => <React.Fragment key={key}>
        <polyline className={`line ${tone}`} points={plot(key).map((point) => `${point.x},${point.y}`).join(" ")} />
        {plot(key).map((point, index) => <circle key={data[index].label} cx={point.x} cy={point.y} r="5" className={`chart-point ${tone}-point`} tabIndex="0" onMouseEnter={() => setHovered({ index, key, label, ...point })} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered({ index, key, label, ...point })} onBlur={() => setHovered(null)}><title>{data[index].label}: {label} {format(data[index][key])}</title></circle>)}
      </React.Fragment>)}
      {data.map((row, index) => <text key={row.label} x={58 + index * 612 / Math.max(1, data.length - 1)} y="199" className="chart-tick" textAnchor="middle">{row.label}</text>)}
      <text x="14" y="108" className="chart-axis-title" textAnchor="middle" transform="rotate(-90 14 108)">{yTitle}</text>
      <text x="365" y="216" className="chart-axis-title" textAnchor="middle">Month</text>
      {hovered && <g className="chart-tooltip" pointerEvents="none"><rect x={Math.min(hovered.x + 8, 545)} y={Math.max(hovered.y - 34, 4)} width="145" height="27" rx="4" /><text x={Math.min(hovered.x + 15, 552)} y={Math.max(hovered.y - 17, 21)}>{hovered.label}: {format(data[hovered.index][hovered.key])}</text></g>}
    </svg>
  </div>;
}

const Trend = ({ data }) => <InteractiveLine data={data} series={[{ key: "detected", label: "Detected", tone: "aqua" }, { key: "remediated", label: "Remediated", tone: "green" }]} yTitle="Exceptions" ariaLabel="Monthly detected and remediated exceptions" />;
const EclTrend = ({ data }) => <InteractiveLine data={data} series={[{ key: "value", label: "ECL", tone: "aqua" }]} yTitle="ECL (USD millions)" currency ariaLabel="Monthly estimated ECL in millions" />;

function ImpactBars({ data }) {
  const max = Math.max(1, ...data.map((row) => Number(row.value)));
  return <div className="bar-chart portfolio-bars">
    <div className="bar-y-axis"><span>${max.toFixed(1)}M</span><span>${(max / 2).toFixed(1)}M</span><span>$0</span></div>
    <div className="bar-grid">{data.map((row) => <div className="bar-slot" key={row.label} tabIndex="0" data-tooltip={`${row.label}: $${Number(row.value).toFixed(1)}M`} aria-label={`${row.label}: $${Number(row.value).toFixed(1)}M`}>
      <i style={{ height: `${(Number(row.value) / max) * 100}%` }} /><b>${Number(row.value).toFixed(1)}M</b>
    </div>)}</div>
    <div className="bar-axis-title">Estimated RWA (USD millions)</div>
  </div>;
}

function Heat({ title, data }) {
  const maxExposure = Math.max(1, ...data.map((row) => Number(row.exposure_percent)));
  return <Card title={title}>
    {data.length ? <div className="heat-grid">{data.map((row) => {
      const intensity = Number(row.exposure_percent) / maxExposure;
      const tone = intensity >= 0.67 ? "heat-high" : intensity >= 0.34 ? "heat-medium" : "heat-low";
      return <div key={row.label} className={tone} title={`${inMillions(row.exposure)} exposure`}>
        <strong>{row.label}</strong>
        <span>{Number(row.exposure_percent).toFixed(1)}% exposure - {row.breaches} breach{Number(row.breaches) === 1 ? "" : "es"}</span>
      </div>;
    })}</div> : <Empty />}
  </Card>;
}

export default function Portfolio({ session }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);
  const [chatError, setChatError] = useState("");

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      try {
        const result = await apiRequest("/api/portfolio", { signal: controller.signal }, session.token);
        if (active) { setData(result); setError(""); }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        if (active) setLoading(false);
      }
    }
    load();
    const interval = setInterval(load, 60000);
    return () => { active = false; controller.abort(); clearInterval(interval); };
  }, [session.token, refresh]);

  async function ask(event) {
    event.preventDefault();
    const text = question.trim();
    if (!data || !text || asking) return;
    const history = messages.slice(-20);
    setQuestion("");
    setMessages((current) => [...current, { role: "user", content: text }]);
    setAsking(true);
    setChatError("");
    try {
      const result = await apiRequest("/api/portfolio/chat", {
        method: "POST",
        body: JSON.stringify({ question: text, history }),
      }, session.token);
      setMessages((current) => [...current, { role: "assistant", content: result.answer }]);
    } catch (err) {
      setChatError(err.message);
    } finally {
      setAsking(false);
    }
  }

  return <>
    <Heading page="portfolio">
      <button className="btn secondary" disabled={loading} onClick={() => setRefresh((value) => value + 1)}><RefreshCw size={15} />{loading ? "Refreshing…" : "Refresh from tables"}</button>
    </Heading>
    {error && <p role="alert" className="dashboard-empty">Could not refresh portfolio analytics: {error}. <button className="text-btn" onClick={() => setRefresh((value) => value + 1)}>Retry</button></p>}
    {!data ? <Empty>{loading ? "Loading portfolio analytics from PostgreSQL…" : "Portfolio analytics are unavailable."}</Empty> : <>
      <p className="dashboard-empty">Current account portfolio · Updated {new Date(data.generated_at).toLocaleString()} · Refreshes every minute{error ? " · Showing last successful update" : ""}</p>
      <div className="layout two-one">
        <Card title="Exception & Remediation Trends" sub="Monthly detected / remediated counts" action={<Legend />}><Trend data={data.trend} /></Card>
        <Card title="Ask Portfolio Data" sub="Mistral Portfolio Analytics Agent" action={<Sparkles size={15} />}>
          <div className="portfolio-chat" aria-live="polite" aria-busy={asking}>
            {messages.map((message, index) => <div className={`portfolio-message ${message.role}`} key={index}>{message.content}</div>)}
            {asking && <div className="portfolio-message assistant">Analyzing the current portfolio…</div>}
            {chatError && <p role="alert" className="data-message error">{chatError}</p>}
          </div>
          <form className="chat-input" onSubmit={ask}>
            <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about this portfolio…" aria-label="Ask a portfolio question" />
            <button type="submit" disabled={asking || !question.trim()} aria-label="Ask"><Send size={14} /></button>
          </form>
        </Card>
      </div>
      <div className="layout two">
        <Heat title="Sector Concentration" data={data.sectors} />
        <Heat title="Geography Concentration" data={data.geographies} />
      </div>
      <div className="layout two">
        <Card title="Estimated RWA by Sector ($M)" sub="Table exposure weighted by borrower rating">{data.rwa.length ? <ImpactBars data={data.rwa} /> : <Empty>No credit requests available.</Empty>}</Card>
        <Card title="Estimated ECL Trend ($M)" sub="Monthly exposure history weighted by payment status"><EclTrend data={data.ecl} /></Card>
      </div>
    </>}
  </>;
}
