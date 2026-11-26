import React, { useEffect, useRef, useState } from "react";
import { RefreshCw, Send, Sparkles } from "lucide-react";
import { apiRequest } from "../api/client";
import { Card, Heading, Legend, money } from "../components/ui";

const Empty = ({ children = "No records available." }) => <p className="dashboard-empty">{children}</p>;
const inMillions = (value) => money(Number(value || 0) / 1000000);

function InteractiveLine({ data, series, yTitle, currency = false, ariaLabel, tall = false }) {
  const height = tall ? 360 : 220;
  const left = tall ? 100 : 58;
  const right = tall ? 680 : 670;
  const top = tall ? 28 : 35;
  const bottom = height - (tall ? 65 : 40);
  const plotHeight = bottom - top;
  const [hovered, setHovered] = useState(null);
  const max = Math.max(1, ...data.flatMap((row) => series.map(({ key }) => Number(row[key]))));
  const ticks = [0, max / 2, max];
  const plot = (key) => data.map((row, index) => ({
    x: left + index * (right - left) / Math.max(1, data.length - 1),
    y: bottom - Number(row[key]) / max * plotHeight,
  }));
  const format = (value) => currency ? `$${Number(value).toFixed(2)}M` : Number(value).toFixed(0);
  return <div className={`line-chart${tall ? " portfolio-risk-chart" : ""}`}>
    <svg viewBox={`0 0 700 ${height}`} role="img" aria-label={ariaLabel}>
      {ticks.map((value) => { const y = bottom - value / max * plotHeight; return <g key={value}><line x1={left} x2={right} y1={y} y2={y} className="gridline" /><text x={left - 10} y={y + 3} className="chart-tick" textAnchor="end">{format(value)}</text></g>; })}
      <line x1={left} x2={left} y1={top} y2={bottom} className="chart-axis-line" />
      <line x1={left} x2={right} y1={bottom} y2={bottom} className="chart-axis-line" />
      {series.map(({ key, label, tone }) => <React.Fragment key={key}>
        <polyline className={`line ${tone}`} points={plot(key).map((point) => `${point.x},${point.y}`).join(" ")} />
        {plot(key).map((point, index) => <circle key={data[index].label} cx={point.x} cy={point.y} r="5" className={`chart-point ${tone}-point`} tabIndex="0" onMouseEnter={() => setHovered({ index, key, label, ...point })} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered({ index, key, label, ...point })} onBlur={() => setHovered(null)}><title>{data[index].label}: {label} {format(data[index][key])}</title></circle>)}
      </React.Fragment>)}
      {data.map((row, index) => <text key={row.label} x={left + index * (right - left) / Math.max(1, data.length - 1)} y={bottom + 24} className="chart-tick" textAnchor="middle">{row.label}</text>)}
      <text x="14" y={height / 2} className="chart-axis-title" textAnchor="middle" transform={`rotate(-90 14 ${height / 2})`}>{yTitle}</text>
      <text x={(left + right) / 2} y={height - 4} className="chart-axis-title" textAnchor="middle">Month</text>
      {hovered && <g className="chart-tooltip" pointerEvents="none"><rect x={Math.min(hovered.x + 8, 545)} y={Math.max(hovered.y - 34, 4)} width="145" height="27" rx="4" /><text x={Math.min(hovered.x + 15, 552)} y={Math.max(hovered.y - 17, 21)}>{hovered.label}: {format(data[hovered.index][hovered.key])}</text></g>}
    </svg>
  </div>;
}

const Trend = ({ data }) => <InteractiveLine data={data} series={[{ key: "detected", label: "Detected", tone: "aqua" }, { key: "remediated", label: "Remediated", tone: "green" }]} yTitle="Exceptions" ariaLabel="Monthly detected and remediated exceptions" />;
const EclTrend = ({ data }) => <InteractiveLine data={data} series={[{ key: "value", label: "ECL", tone: "aqua" }]} yTitle="ECL (USD millions)" currency tall ariaLabel="Monthly estimated ECL in millions" />;

function ImpactBars({ data }) {
  const [hovered, setHovered] = useState(null);
  const max = Math.max(1, ...data.map(row => Number(row.value)));
  const left = 100, right = 680, top = 28, bottom = 295;
  const slot = (right - left) / Math.max(1, data.length);
  const barWidth = Math.min(38, slot * 0.65);
  const format = value => `$${Number(value).toFixed(1)}M`;
  return <div className="line-chart portfolio-risk-chart">
    <svg viewBox="0 0 700 360" role="img" aria-label="Estimated RWA by sector in USD millions">
      {[0, max / 2, max].map(value => {
        const y = bottom - value / max * (bottom - top);
        return <g key={value}><line x1={left} x2={right} y1={y} y2={y} className="gridline"/><text x={left - 10} y={y + 3} textAnchor="end" className="chart-tick">{format(value)}</text></g>;
      })}
      <line x1={left} x2={left} y1={top} y2={bottom} className="chart-axis-line"/>
      <line x1={left} x2={right} y1={bottom} y2={bottom} className="chart-axis-line"/>
      {data.map((row, index) => {
        const x = left + (index + 0.5) * slot;
        const height = Number(row.value) / max * (bottom - top);
        return <g key={row.label} tabIndex="0" onMouseEnter={()=>setHovered(index)} onMouseLeave={()=>setHovered(null)} onFocus={()=>setHovered(index)} onBlur={()=>setHovered(null)} aria-label={`${row.label}: ${format(row.value)}`}>
          <title>{row.label}: {format(row.value)}</title>
          <rect x={x - barWidth / 2} y={bottom - height} width={barWidth} height={height} rx="5" className="portfolio-rwa-bar"/>
          <text x={x} y={bottom + 18} transform={`rotate(-30 ${x} ${bottom + 18})`} textAnchor="end" className="chart-tick">{row.label.length>11?`${row.label.slice(0,10)}...`:row.label}</text>
          {hovered===index&&<g className="chart-tooltip" pointerEvents="none"><rect x={Math.min(x - 62, 555)} y={Math.max(top, bottom - height - 34)} width="125" height="27" rx="4"/><text x={Math.min(x - 55, 562)} y={Math.max(top, bottom - height - 34) + 18}>{format(row.value)}</text></g>}
        </g>;
      })}
      <text x="14" y="180" transform="rotate(-90 14 180)" textAnchor="middle" className="chart-axis-title">RWA (USD millions)</text>
      <text x="390" y="356" textAnchor="middle" className="chart-axis-title">Sector</text>
    </svg>
  </div>;
}

function Heat({ title, data }) {
  const maxExposure = Math.max(1, ...data.map((row) => Number(row.exposure_percent)));
  return <Card title={title}>
    {data.length ? <div className="heat-grid">{data.map((row) => {
      const intensity = Number(row.exposure_percent) / maxExposure;
      const tone = intensity >= 0.67 ? "heat-high" : intensity >= 0.34 ? "heat-medium" : "heat-low";
      return <div key={`${row.currency}-${row.label}`} className={tone} title={`${row.currency || "USD"} ${(Number(row.exposure)/1000000).toFixed(2)}M exposure / deal amount`}>
        <strong>{row.label} ({row.currency || "USD"})</strong>
        <span>{Number(row.exposure_percent).toFixed(1)}% exposure · {row.breaches} open exception{Number(row.breaches) === 1 ? "" : "s"}</span>
      </div>;
    })}</div> : <Empty />}
  </Card>;
}

export default function Portfolio({ session }) {
  const chatRequest = useRef(null);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([]);
  const [asking, setAsking] = useState(false);
  const [chatError, setChatError] = useState("");
  useEffect(() => () => chatRequest.current?.abort(), []);

  useEffect(() => {
    let active = true;
    let requestInFlight = false;
    const controller = new AbortController();
    async function load() {
      if (requestInFlight) return;
      requestInFlight = true;
      setLoading(true);
      try {
        const result = await apiRequest("/api/portfolio", { signal: controller.signal }, session.token);
        if (active) { setData(result); setError(""); }
      } catch (err) {
        if (active) setError(err.message);
      } finally {
        requestInFlight = false;
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
    const controller = new AbortController();
    chatRequest.current = controller;
    try {
      const result = await apiRequest("/api/portfolio/chat", {
        method: "POST",
        signal: controller.signal,
        body: JSON.stringify({ question: text, history }),
      }, session.token);
      if (!controller.signal.aborted) setMessages((current) => [...current, { role: "assistant", content: result.answer }]);
    } catch (err) {
      if (!controller.signal.aborted) setChatError(err.message);
    } finally {
      if (!controller.signal.aborted) setAsking(false);
      if (chatRequest.current === controller) chatRequest.current = null;
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
        <Card title="Ask Portfolio Data" sub="AI provider Portfolio Analytics Agent" action={<Sparkles size={15} />}>
          <div className="portfolio-chat" aria-live="polite" aria-busy={asking}>
            {messages.map((message, index) => <div className={`portfolio-message ${message.role}`} key={index}>{message.content}</div>)}
            {asking && <div className="portfolio-message assistant">Analyzing the current portfolio…</div>}
            {chatError && <p role="alert" className="data-message error">{chatError}</p>}
          </div>
          <form autoComplete="off" className="chat-input" onSubmit={ask}>
            <input autoComplete="off" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask about this portfolio…" aria-label="Ask a portfolio question" />
            <button type="submit" disabled={asking || !question.trim()} aria-label="Ask"><Send size={14} /></button>
          </form>
        </Card>
      </div>
      {data.source_warning && <p role="status" className="data-message">{data.source_warning}</p>}
      <div className="layout two">
        <Heat title="Sector Concentration" data={data.sectors} />
        <Heat title="Geography Concentration" data={data.geographies} />
      </div>
      <div className="layout two portfolio-risk-charts">
        <Card title="Estimated RWA by Sector ($M)" sub="Table exposure weighted by borrower rating">{data.rwa.length ? <ImpactBars data={data.rwa} /> : <Empty>No credit requests available.</Empty>}</Card>
        <Card title="Estimated ECL Trend ($M)" sub="Monthly exposure history weighted by payment status"><EclTrend data={data.ecl} /></Card>
      </div>
    </>}
  </>;
}
