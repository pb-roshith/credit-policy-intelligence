import React, { useEffect, useState } from "react";
import { CheckCircle2, Play, Sparkles } from "lucide-react";

import { apiRequest } from "../api/client";
import { Card, Heading, money } from "../components/ui";

const INITIAL_INPUTS = {
  facility_amount: 85,
  collateral_coverage: 85,
  risk_rating: "BB-",
  pricing_bps: 325,
  tenor_years: 7,
  covenants: "Partial",
};

export default function Simulator({ notify, session }) {
  const [scenarioName, setScenarioName] = useState("");
  const [inputs, setInputs] = useState(INITIAL_INPUTS);
  const [scenario, setScenario] = useState(null);
  const [savedScenarios, setSavedScenarios] = useState([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [running, setRunning] = useState(false);
  const [loadingScenario, setLoadingScenario] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  useEffect(() => {
    let active = true;
    apiRequest("/api/decision-scenarios", {}, session.token)
      .then((items) => { if (active) setSavedScenarios(items); })
      .catch((requestError) => { if (active) setLoadError(requestError.message); });
    return () => { active = false; };
  }, [session.token]);
  const setInput = (field, value) => {
    setInputs((current) => ({ ...current, [field]: value }));
    setScenario(null);
  };

  const run = async () => {
    if (!scenarioName.trim()) {
      setError("Enter a scenario name before running the scenario.");
      return;
    }
    setRunning(true);
    setError("");
    setScenario(null);
    try {
      const result = await apiRequest(
        "/api/decision-scenarios",
        { method: "POST", body: JSON.stringify({ scenario_name: scenarioName, ...inputs }) },
        session.token,
      );
      setScenario(result);
      setSelectedScenario(String(result.scenario_id));
      setSavedScenarios((current) => [
        { scenario_id: result.scenario_id, scenario_name: result.scenario_name, created_at: result.created_at },
        ...current.filter((item) => item.scenario_id !== result.scenario_id),
      ]);
      notify(`Scenario “${result.scenario_name}” calculated and saved`);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setRunning(false);
    }
  };

  const loadScenario = async () => {
    if (!selectedScenario) return;
    setLoadingScenario(true);
    setLoadError("");
    try {
      const result = await apiRequest(`/api/decision-scenarios/${selectedScenario}`, {}, session.token);
      setScenario(result);
      setScenarioName(result.scenario_name);
      setInputs(result.inputs);
      setError("");
      notify(`Scenario “${result.scenario_name}” loaded`);
    } catch (requestError) {
      setLoadError(requestError.message);
    } finally {
      setLoadingScenario(false);
    }
  };

  const results = scenario?.results;
  return (
    <>
      <Heading page="simulator" />
      <div className="sim-layout">
        <Card title="Scenario Inputs" sub="Running a scenario automatically saves it">
          <label className="field scenario-name-field">
            Scenario Name
            <input
              type="text"
              autoComplete="off"
              value={scenarioName}
              maxLength={120}
              onChange={(event) => {
                setScenarioName(event.target.value);
                setScenario(null);
                if (error) setError("");
              }}
              placeholder="e.g. FY27 downside case"
              disabled={running}
            />
          </label>
          <Slider label="Facility Amount" value={inputs.facility_amount} set={(value) => setInput("facility_amount", value)} min={25} max={150} display={`$${inputs.facility_amount}M`} />
          <Slider label="Collateral Coverage" value={inputs.collateral_coverage} set={(value) => setInput("collateral_coverage", value)} min={50} max={130} display={`${inputs.collateral_coverage}%`} />
          <div className="form-row single-field">
            <label>
              Risk Rating
              <select value={inputs.risk_rating} onChange={(event) => setInput("risk_rating", event.target.value)}>
                <option>BBB</option><option>BB+</option><option>BB-</option><option>B+</option>
              </select>
            </label>
          </div>
          <Slider label="Pricing (bps)" value={inputs.pricing_bps} set={(value) => setInput("pricing_bps", value)} min={100} max={600} display={`${inputs.pricing_bps}`} />
          <Slider label="Tenor (years)" value={inputs.tenor_years} set={(value) => setInput("tenor_years", value)} min={1} max={12} display={`${inputs.tenor_years}yr`} />
          <label className="field">
            Covenants
            <select value={inputs.covenants} onChange={(event) => setInput("covenants", event.target.value)}>
              <option>Partial</option><option>Full</option><option>None</option>
            </select>
          </label>
          {error && <div className="data-message error simulator-error" role="alert">{error}</div>}
          <button className="btn primary run" onClick={run} disabled={running}>
            <Play size={15} />{running ? "Calculating & saving..." : "Run Scenario"}
          </button>
        </Card>
        <div className="simulator-workspace">
          <div className="simulator-results-row">
            <div className="scenario-results">
              <div className="card scenario-loader">
            <label>
              Existing Scenario
              <select value={selectedScenario} onChange={(event) => setSelectedScenario(event.target.value)}>
                <option value="">Select a saved scenario</option>
                {savedScenarios.map((item) => <option key={item.scenario_id} value={item.scenario_id}>{item.scenario_name}</option>)}
              </select>
            </label>
            <button className="btn secondary" type="button" disabled={!selectedScenario || loadingScenario} onClick={loadScenario}>
              {loadingScenario ? "Loading..." : "Display Scenario"}
            </button>
            {loadError && <div className="data-message error" role="alert">{loadError}</div>}
          </div>
              <div className="output-grid">
            <Output label="Expected Loss" value={results ? money(results.expected_loss) : "—"} numeric={results?.expected_loss} tone="warn" />
            <Output label="ECL Impact" value={results ? money(results.ecl_impact) : "—"} numeric={results?.ecl_impact} tone="warn" />
            <Output label="RWA Impact" value={results ? money(results.rwa_impact) : "—"} numeric={results?.rwa_impact} />
            <Output label="Capital Impact" value={results ? money(results.capital_impact) : "—"} numeric={results?.capital_impact} />
            <Output label="Concentration Impact" value={results ? `${results.concentration_impact.toFixed(1)}%` : "—"} numeric={results?.concentration_impact} tone="warn" />
            <Output label="Risk Appetite Score" value={results?.risk_appetite_score ?? "—"} numeric={results?.risk_appetite_score} tone={!results ? "" : results.risk_appetite_score < 70 ? "danger" : "good"} />
          </div>
        </div>
        <Card className="recommendations" title="AI Recommendations" action={<Sparkles size={16} />}>
          <div className="recommendations-scroll" tabIndex={0} role="region" aria-label="AI recommendations">
          {!scenario && <p className="simulator-placeholder">Run a named scenario to generate 3–5 recommendations.</p>}
          {scenario?.recommendations.map((recommendation) => (
            <div className="recommend" key={recommendation}>
              <CheckCircle2 size={15} /><p>{recommendation}</p>
            </div>
          ))}
          <small className="disclaimer">AI-generated recommendations. Require human approval to enact.</small>
          </div>
        </Card>
        </div>
        <Card className="sensitivity-card" title="Sensitivity Analysis - Facility Amount" sub="EL and ECL by facility size (USD millions)" action={<div className="legend"><i />EL <i className="green-dot" />ECL</div>}>
          <SensitivityChart points={results?.sensitivity || []} />
        </Card>
      </div>
      </div>
    </>
  );
}

function Slider({ label, value, set, min, max, display }) {
  return (
    <label className="slider">
      <span>{label}<b>{display}</b></span>
      <input type="range" min={min} max={max} value={value} onChange={(event) => set(+event.target.value)} />
      <div><small>{min}</small><small>{max}</small></div>
    </label>
  );
}

function Output({ label, value, numeric = 0, tone = "" }) {
  const intensity = Math.max(18, Math.min(90, Number(numeric) || 0));
  return (
    <div className={`card output ${tone}`}>
      <span>{label}</span><strong>{value}</strong>
      <div className="mini-bars" aria-hidden="true">
        {[0.55, 0.7, 0.62, 0.82, 0.76, 1].map((factor, index) => <i key={index} style={{ height: `${Math.max(8, intensity * factor)}%` }} />)}
      </div>
    </div>
  );
}

function SensitivityChart({ points }) {
  const [hovered, setHovered] = useState(null);
  if (!points.length) return <div className="simulator-chart-empty">Run a scenario to calculate sensitivity.</div>;
  const width = 700;
  const height = 220;
  const maxLoss = Math.max(...points.flatMap((point) => [point.expected_loss, point.ecl_impact]), 0.001);
  const ticks = [0, maxLoss / 2, maxLoss];
  const plotted = (key) => points.map((point, index) => ({
    ...point,
    x: 62 + index * 608 / Math.max(1, points.length - 1),
    y: 180 - point[key] / maxLoss * 145,
  }));
  return (
    <div className="line-chart simulator-sensitivity">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Expected loss and ECL sensitivity by facility amount">
        {ticks.map((value) => { const y = 180 - value / maxLoss * 145; return <g key={value}><line x1="62" x2="670" y1={y} y2={y} className="gridline" /><text x="54" y={y + 3} className="chart-tick" textAnchor="end">${value.toFixed(2)}M</text></g>; })}
        <line x1="62" x2="62" y1="35" y2="180" className="chart-axis-line" />
        <line x1="62" x2="670" y1="180" y2="180" className="chart-axis-line" />
        {[['expected_loss', 'aqua', 'EL'], ['ecl_impact', 'green', 'ECL']].map(([key, tone, label]) => <React.Fragment key={key}>
          <polyline className={`line ${tone}`} points={plotted(key).map((point) => `${point.x},${point.y}`).join(" ")} />
          {plotted(key).map((point, index) => <circle key={point.facility_amount} cx={point.x} cy={point.y} r="5" className={`chart-point ${tone}-point`} tabIndex="0" onMouseEnter={() => setHovered({ index, key, label, x: point.x, y: point.y })} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered({ index, key, label, x: point.x, y: point.y })} onBlur={() => setHovered(null)}><title>${point.facility_amount}M: {label} {money(point[key])}</title></circle>)}
        </React.Fragment>)}
        {points.map((point, index) => <text key={point.facility_amount} x={62 + index * 608 / Math.max(1, points.length - 1)} y="198" className="chart-tick" textAnchor="middle">${point.facility_amount}M</text>)}
        <text x="14" y="108" className="chart-axis-title" textAnchor="middle" transform="rotate(-90 14 108)">Loss (USD millions)</text>
        <text x="366" y="216" className="chart-axis-title" textAnchor="middle">Facility amount</text>
        {hovered && <g className="chart-tooltip" pointerEvents="none"><rect x={Math.min(hovered.x + 8, 548)} y={Math.max(hovered.y - 34, 4)} width="142" height="27" rx="4" /><text x={Math.min(hovered.x + 15, 555)} y={Math.max(hovered.y - 17, 21)}>{hovered.label}: {money(points[hovered.index][hovered.key])}</text></g>}
      </svg>
    </div>
  );
}
