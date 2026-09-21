import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Activity, CheckCircle2, Clock3, Download, Gauge, RefreshCw, Search, Sparkles, XCircle, Zap } from "lucide-react";
import { apiRequest } from "../api/client";
import { Card, Heading } from "../components/ui";

const number = (value) => Number(value || 0).toLocaleString();
const latency = (value) => value == null ? "Not recorded" : value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`;
const dateTime = (value) => value ? new Date(value).toLocaleString() : "No requests recorded";
const title = (value = "") => value.split("_").map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(" ");

function Stat({ icon: Icon, label, value, tone = "" }) {
  return <div className={`obs-stat ${tone}`}><span><Icon size={17} /></span><small>{label}</small><strong>{value}</strong></div>;
}

export default function Observability({ session, notify }) {
  const [data, setData] = useState(null), [loading, setLoading] = useState(true), [error, setError] = useState("");
  const [query, setQuery] = useState(""), [feature, setFeature] = useState("All AI features"), [selectedId, setSelectedId] = useState(null);
  const load = useCallback(async (announce = false) => {
    setError("");
    try {
      const snapshot = await apiRequest("/api/observability", {}, session.token);
      setData(snapshot);
      setSelectedId((current) => current && snapshot.traces.some((item) => item.span_id === current) ? current : snapshot.traces[0]?.span_id || null);
      if (announce) notify("AI telemetry refreshed.");
    } catch (requestError) { setError(requestError.message); }
    finally { setLoading(false); }
  }, [session.token, notify]);
  useEffect(() => { load(); const timer = setInterval(() => load(), 30000); return () => clearInterval(timer); }, [load]);

  const featureNames = useMemo(() => ["All AI features", ...new Set((data?.features || []).map((item) => item.feature))], [data]);
  const traces = useMemo(() => (data?.traces || []).filter((item) => {
    const matchesFeature = feature === "All AI features" || item.feature === feature;
    return matchesFeature && `${item.feature} ${item.operation} ${item.target || ""} ${item.status} ${item.trace_id}`.toLowerCase().includes(query.trim().toLowerCase());
  }), [data, feature, query]);
  const selected = (data?.traces || []).find((item) => item.span_id === selectedId) || traces[0];
  const overview = data?.overview || {};
  const exportJson = () => {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `cpi-ai-telemetry-${new Date().toISOString()}.json`; link.click(); URL.revokeObjectURL(url);
    notify("Current AI telemetry exported.");
  };

  return <>
    <Heading page="observability"><button className="btn secondary" onClick={exportJson} disabled={!data}><Download size={15} />Export JSON</button><button className="btn primary" onClick={() => load(true)} disabled={loading}><RefreshCw size={15} className={loading ? "obs-spin" : ""} />Refresh</button></Heading>
    {error && <div className="data-message error">{error}</div>}
    {loading && !data ? <Card><div className="obs-loading"><RefreshCw className="obs-spin" />Loading OpenTelemetry spans…</div></Card> : data && <>
      <div className="obs-live"><i />OpenTelemetry live snapshot <span>Updated {dateTime(data.generated_at)} · Auto-refreshes every 30 seconds</span></div>
      <Card title="AI Executive Overview" sub="Aggregated telemetry for user-facing AI requests in this account." className="obs-overview"><div className="obs-kpis obs-kpis-seven">
        <Stat icon={Activity} label="Total requests" value={number(overview.total_requests)} /><Stat icon={CheckCircle2} label="Successful" value={number(overview.successful)} tone="good" /><Stat icon={XCircle} label="Failed" value={number(overview.failed)} tone={Number(overview.failed) ? "bad" : "good"} /><Stat icon={Clock3} label="Average latency" value={latency(overview.average_latency_ms)} /><Stat icon={Zap} label="Input tokens" value={number(overview.input_tokens)} /><Stat icon={Sparkles} label="Output tokens" value={number(overview.output_tokens)} /><Stat icon={Gauge} label="Total tokens" value={number(overview.total_tokens)} />
      </div></Card>

      <div className="obs-agent-grid">{data.features.map((item, index) => <Card className="obs-agent" key={item.operation}>
        <div className="obs-agent-title"><span>{index + 1}</span><div><h3>{item.display_name}</h3><small>Mistral AI feature</small></div></div>
        <div className="obs-agent-section"><small>Application section</small><strong>{item.feature}</strong></div>
        <div className="obs-agent-metrics"><div><small>Total requests</small><b>{number(item.total_requests)}</b></div><div><small>Successful</small><b className="success">{number(item.successful)}</b></div><div><small>Failed</small><b className={Number(item.failed) ? "failure" : ""}>{number(item.failed)}</b></div><div><small>Average latency</small><b>{latency(item.average_latency_ms)}</b></div><div><small>Input tokens</small><b>{number(item.input_tokens)}</b></div><div><small>Output tokens</small><b>{number(item.output_tokens)}</b></div><div><small>Total tokens</small><b>{number(item.total_tokens)}</b></div><div><small>Last request</small><b>{dateTime(item.last_request_at)}</b></div></div>
      </Card>)}</div>

      <Card title="AI Trace Explorer" sub="Inspect persisted OpenTelemetry spans for individual AI requests." className="obs-traces" action={<span className="obs-count">{traces.length} spans</span>}>
        <div className="obs-tools"><div className="obs-search"><Search size={16} /><input autoComplete="off" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search operation, target, status, or trace ID" /></div><select value={feature} onChange={(event) => setFeature(event.target.value)}>{featureNames.map((item) => <option key={item}>{item}</option>)}</select></div>
        {!traces.length ? <div className="obs-empty">No AI spans have been recorded for these filters. Run an AI feature to create the first trace.</div> : <div className="obs-trace-layout"><div className="obs-trace-list">{traces.map((item) => <button key={item.span_id} className={selected?.span_id === item.span_id ? "active" : ""} onClick={() => setSelectedId(item.span_id)}><strong>{title(item.operation)}</strong><span><i className={item.status === "failed" ? "failed" : ""}>{item.status}</i>{item.feature}</span><small>{item.target || "Application request"} · {dateTime(item.started_at)}</small></button>)}</div>{selected && <div className="obs-selected"><span className="eyebrow">Selected OpenTelemetry span</span><h3>{title(selected.operation)}</h3><span className={selected.status === "failed" ? "status-failed" : "status-success"}>{selected.status}</span><div className="obs-detail-grid"><div><small>Feature</small><b>{selected.feature}</b></div><div><small>Model</small><b>{selected.model || "Not reported"}</b></div><div><small>Latency</small><b>{latency(selected.latency_ms)}</b></div><div><small>Input tokens</small><b>{selected.input_tokens == null ? "Not provided by API" : number(selected.input_tokens)}</b></div><div><small>Output tokens</small><b>{selected.output_tokens == null ? "Not provided by API" : number(selected.output_tokens)}</b></div><div><small>Total tokens</small><b>{selected.total_tokens == null ? "Not provided by API" : number(selected.total_tokens)}</b></div><div><small>Trace ID</small><b>{selected.trace_id}</b></div><div><small>Span ID</small><b>{selected.span_id}</b></div><div><small>Started</small><b>{dateTime(selected.started_at)}</b></div>{selected.status === "failed" && <div className="obs-error-detail"><small>Failure</small><b>The request could not be completed.</b></div>}</div></div>}</div>}
      </Card>
    </>}
  </>;
}
