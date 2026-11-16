import React, { useEffect, useRef, useState } from "react";
import { CheckCircle2, Play, Sparkles } from "lucide-react";
import { apiRequest } from "../api/client";
import {scenarioListPath,scenarioContextPath,scenarioDetailPath,scenarioRequestNumber,scenarioInputs,scenarioPayload} from "../api/scenarioRequests";
import { Card, Heading } from "../components/ui";

const EMPTY_INPUTS={facility_amount:'',collateral_coverage:'',risk_rating:'',pricing_bps:'',tenor_years:'',covenants:'Partial'};
const displayNumber=value=>Number(value).toLocaleString(undefined,{maximumFractionDigits:6});
const money=(value,currency='USD')=>`${currency} ${displayNumber(value)}M`;

export default function Simulator({ notify, session }) {
 const [requests,setRequests]=useState([]),[requestId,setRequestId]=useState(''),[loadingRequests,setLoadingRequests]=useState(true),[requestError,setRequestError]=useState('');
 const [requestNotice,setRequestNotice]=useState(''),[requestRefresh,setRequestRefresh]=useState(0);
 const [baseline,setBaseline]=useState(null),[loadingContext,setLoadingContext]=useState(false);
 const [scenarioName,setScenarioName]=useState(''),[inputs,setInputs]=useState(EMPTY_INPUTS),[scenario,setScenario]=useState(null);
 const [savedScenarios,setSavedScenarios]=useState([]),[selectedScenario,setSelectedScenario]=useState('');
 const [running,setRunning]=useState(false),[loadingScenario,setLoadingScenario]=useState(false),[error,setError]=useState(''),[loadError,setLoadError]=useState('');
 const activeSelection=useRef('');activeSelection.current=session.user.user_id+':'+requestId;
 useEffect(()=>{
  let active=true;setRequests([]);setRequestId('');setLoadingRequests(true);setRequestError('');setRequestNotice('');setRunning(false);setLoadingScenario(false);
  apiRequest('/api/decision-scenarios/requests',{},session.token).then(({requests:rows,notices=[]})=>{
   if(!active)return;setRequests(rows);setRequestNotice(notices.join(' '));
   const saved=sessionStorage.getItem('simulatorRequestSelection:'+session.user.user_id)||sessionStorage.getItem('complianceReviewSelection:'+session.user.user_id);
   setRequestId(rows.some(r=>r.credit_request_number===saved)?saved:'');
   if(saved&&!rows.some(r=>r.credit_request_number===saved))setRequestNotice('Choose an available credit request from the list below. '+notices.join(' '));
  }).catch(e=>{if(active)setRequestError(e.message)}).finally(()=>{if(active)setLoadingRequests(false)});
  return()=>{active=false};
 },[session.token,session.user.user_id,requestRefresh]);
 useEffect(()=>{
  let active=true;setBaseline(null);setInputs(EMPTY_INPUTS);setScenario(null);setScenarioName('');setSavedScenarios([]);setSelectedScenario('');setError('');setLoadError('');
  if(!requestId){setLoadingContext(false);return()=>{active=false}}
  setLoadingContext(true);sessionStorage.setItem('simulatorRequestSelection:'+session.user.user_id,requestId);
  Promise.all([apiRequest(scenarioContextPath(requestId),{},session.token),apiRequest(scenarioListPath(requestId),{},session.token)]).then(([context,items])=>{
   if(!active)return;
   if(context.credit_request_number!==scenarioRequestNumber(requestId))throw new Error('The request context did not match the selected request.');
   setBaseline(context);setInputs(scenarioInputs(context));setSavedScenarios(items.filter(item=>item.credit_request_number===scenarioRequestNumber(requestId)));
  }).catch(async e=>{if(!active)return;if([403,404,503].includes(e.status))await recoverSelection(()=>active);else setError(e.message)}).finally(()=>{if(active)setLoadingContext(false)});
  return()=>{active=false};
 },[requestId,session.token,session.user.user_id]);
 async function recoverSelection(isActive=()=>true){
  const selection=activeSelection.current;
  try{
   const {requests:rows,notices=[]}=await apiRequest('/api/decision-scenarios/requests',{},session.token);
   if(!isActive()||selection!==activeSelection.current)return;
   setRequests(rows.filter(r=>r.credit_request_number!==requestId));setRequestId('');setError('');setLoadError('');setRunning(false);setLoadingScenario(false);
   sessionStorage.removeItem('simulatorRequestSelection:'+session.user.user_id);
   setRequestNotice('Choose another available credit request from the list. '+notices.join(' '));
  }catch(e){if(isActive()&&selection===activeSelection.current)setRequestError(e.message)}
 }
 function setInput(field,value){setInputs(current=>({...current,[field]:value}));setScenario(null);setSelectedScenario('')}
 function resetInputs(){if(baseline){setInputs(scenarioInputs(baseline));setScenario(null);setSelectedScenario('');setScenarioName('');setError('')}}
 async function run(){
  if(!requestId||!baseline){setError('Select a credit request first.');return}
  if(!scenarioName.trim()){setError('Enter a scenario name before running the scenario.');return}
  if(!inputs.risk_rating||!inputs.facility_amount){setError('Provide a facility amount and supported scenario risk rating.');return}
  const selection=activeSelection.current;setRunning(true);setError('');setScenario(null);
  try{
   const result=await apiRequest('/api/decision-scenarios',{method:'POST',body:JSON.stringify(scenarioPayload(requestId,scenarioName,inputs))},session.token);
   if(selection!==activeSelection.current)return;
   if(result.credit_request_number!==scenarioRequestNumber(requestId))throw new Error('The saved scenario did not match the selected request.');
   setScenario(result);setSelectedScenario(String(result.scenario_id));
   setSavedScenarios(current=>[{scenario_id:result.scenario_id,scenario_name:result.scenario_name,credit_request_number:result.credit_request_number,created_at:result.created_at},...current.filter(item=>item.scenario_id!==result.scenario_id)]);
   notify(`Scenario "${result.scenario_name}" saved for ${requestId}`);
  }catch(e){if(selection===activeSelection.current){if([403,404].includes(e.status))await recoverSelection();else setError(e.message)}}
  finally{if(selection===activeSelection.current)setRunning(false)}
 }
 async function loadScenario(){
  if(!requestId||!selectedScenario)return;
  const selection=activeSelection.current;setLoadingScenario(true);setLoadError('');
  try{
   const result=await apiRequest(scenarioDetailPath(selectedScenario,requestId),{},session.token);
   if(selection!==activeSelection.current)return;
   if(result.credit_request_number!==scenarioRequestNumber(requestId))throw new Error('This scenario belongs to another credit request.');
   setScenario(result);setScenarioName(result.scenario_name);setInputs(result.inputs);setError('');
   notify(`Scenario "${result.scenario_name}" loaded for ${requestId}`);
  }catch(e){if(selection===activeSelection.current){if([403,404].includes(e.status)&&/credit request|account/i.test(e.message))await recoverSelection();else setLoadError(e.message)}}
  finally{if(selection===activeSelection.current)setLoadingScenario(false)}
 }
 const results=scenario?.results,currency=inputs.currency||baseline?.currency||'USD';
 const disabled=!baseline||loadingContext||running||loadingScenario;
 return <>
  <Heading page="simulator"/>
  <Card className="simulator-request" title="Credit request" sub="Choose a request to load its baseline and saved scenarios.">
   <label className="field">Available credit requests ({requests.length})<select aria-label="Simulator credit request" value={requestId} disabled={loadingRequests||running||loadingScenario} onChange={e=>setRequestId(e.target.value)}>
    <option value="">{loadingRequests?'Loading requests...':requests.length?'Select an available credit request':'No credit requests available'}</option>
    {requests.map(r=><option key={r.credit_request_number} value={r.credit_request_number}>{r.credit_request_number} - {r.borrower_name} - {r.facility}</option>)}
   </select></label>
   <button className="btn secondary" disabled={loadingRequests||running||loadingScenario} onClick={()=>setRequestRefresh(n=>n+1)}>Refresh request list</button>
   {requestNotice&&<p role="status" className="data-message">{requestNotice}</p>}
   {!loadingRequests&&!requests.length&&!requestError&&<p>No credit requests are currently available for simulation in this account.</p>}
   {requestError&&<p role="alert" className="data-message error">{requestError}</p>}
   {loadingContext&&<p role="status">Loading request baseline and saved scenarios...</p>}
   {baseline&&<><p><strong>{baseline.credit_request_number}</strong> - {baseline.borrower_name} - {baseline.facility} - Currency: {baseline.currency}</p>
    <p>Baseline facility: {baseline.inputs.facility_amount==null?'Not supplied':money(baseline.inputs.facility_amount,baseline.currency)}. Source rating: {baseline.request_facts.rating||'Not supplied'}. Scenario amounts are in millions of {baseline.currency}.</p>
    {!!baseline.assumptions.length&&<details><summary>Scenario assumptions and required choices ({baseline.assumptions.length})</summary>{baseline.assumptions.map((a,i)=><p key={i}><strong>{a.field.replaceAll('_',' ')}</strong>: {a.value??'Choose a scenario value'} - {a.reason}</p>)}</details>}
   </>}
  </Card>
  <div className="sim-layout">
   <Card title="Scenario Inputs" sub={requestId?`Scenarios are saved against ${requestId}. Use a new name for each scenario.`:'Select a credit request to begin.'}>
    <fieldset disabled={disabled} style={{border:0,padding:0,margin:0,minWidth:0}}>
     <label className="field scenario-name-field">Scenario Name<input type="text" autoComplete="off" value={scenarioName} maxLength={120} placeholder="e.g. FY27 downside case" onChange={e=>{setScenarioName(e.target.value);setScenario(null);setError('')}}/></label>
     <Slider label="Facility Amount" value={inputs.facility_amount} set={v=>setInput('facility_amount',v)} min={0.000001} max={Math.min(1e9,Math.max(150,Number(baseline?.inputs.facility_amount)*2||0))} inputMax={1e9} display={inputs.facility_amount===''?'Required':money(inputs.facility_amount,currency)}/>
     <Slider label="Collateral Coverage" value={inputs.collateral_coverage} set={v=>setInput('collateral_coverage',v)} min={0} max={1000} display={`${inputs.collateral_coverage}%`}/>
     <div className="form-row single-field"><label>Risk Rating<select value={inputs.risk_rating} onChange={e=>setInput('risk_rating',e.target.value)}><option value="">Choose a scenario rating</option><option>BBB</option><option>BB+</option><option>BB-</option><option>B+</option></select></label></div>
     <Slider label="Pricing (bps)" value={inputs.pricing_bps} set={v=>setInput('pricing_bps',v)} min={0} max={10000} display={`${inputs.pricing_bps}`}/>
     <Slider label="Tenor (years)" value={inputs.tenor_years} set={v=>setInput('tenor_years',v)} min={0.01} max={50} display={`${displayNumber(inputs.tenor_years)}yr`}/>
     <label className="field">Covenants<select value={inputs.covenants} onChange={e=>setInput('covenants',e.target.value)}><option>Partial</option><option>Full</option><option>None</option></select></label>
     <button className="btn secondary" type="button" onClick={resetInputs}>Reset to request baseline</button>
     <button className="btn primary run" onClick={run}><Play size={15}/>{running?'Calculating & saving...':'Run Scenario'}</button>
    </fieldset>
    {error&&<p className="data-message error simulator-error" role="alert">{error}</p>}
   </Card>
   <div className="simulator-workspace"><div className="simulator-results-row"><div className="scenario-results">
    <div className="card scenario-loader"><label>Saved scenarios for {requestId||'selected request'}<select value={selectedScenario} disabled={disabled} onChange={e=>setSelectedScenario(e.target.value)}><option value="">Select a saved scenario</option>{savedScenarios.map(item=><option key={item.scenario_id} value={item.scenario_id}>{item.scenario_name}</option>)}</select></label>
     <button className="btn secondary" type="button" disabled={!selectedScenario||disabled} onClick={loadScenario}>{loadingScenario?'Loading...':'Display Scenario'}</button>
     {loadError&&<p className="data-message error" role="alert">{loadError}</p>}
     {baseline&&!savedScenarios.length&&<p>No scenarios saved for this request yet.</p>}
     {scenario&&<small>{scenario.scenario_name} - {scenario.credit_request_number} - saved {new Date(scenario.created_at).toLocaleString()}</small>}

     {scenario?.request_snapshot?.original_inputs_not_request_derived&&<small>This earlier scenario was linked manually; its original inputs and results are preserved.</small>}
    </div>
    <div className="output-grid">
     <Output label="Expected Loss" value={results?money(results.expected_loss,currency):'--'} numeric={results?.expected_loss} tone="warn"/>
     <Output label="ECL Impact" value={results?money(results.ecl_impact,currency):'--'} numeric={results?.ecl_impact} tone="warn"/>
     <Output label="RWA Impact" value={results?money(results.rwa_impact,currency):'--'} numeric={results?.rwa_impact}/>
     <Output label="Capital Impact" value={results?money(results.capital_impact,currency):'--'} numeric={results?.capital_impact}/>
     <Output label="Concentration Impact" value={results?`${results.concentration_impact.toFixed(1)}%`:'--'} numeric={results?.concentration_impact} tone="warn"/>
     <Output label="Risk Appetite Score" value={results?.risk_appetite_score??'--'} numeric={results?.risk_appetite_score} tone={!results?'':results.risk_appetite_score<70?'danger':'good'}/>
    </div>
   </div><Card className="recommendations" title="AI Recommendations" action={<Sparkles size={16}/>}>
    <div className="recommendations-scroll" tabIndex={0} role="region" aria-label="AI recommendations">
     {!scenario&&<p className="simulator-placeholder">Choose a request and run a named scenario to generate recommendations.</p>}
     {scenario?.recommendations.map((recommendation,i)=><div className="recommend" key={i}><CheckCircle2 size={15}/><p>{recommendation}</p></div>)}
     <small className="disclaimer">Scenario simulation. AI recommendations require human approval to enact.</small>
    </div>
   </Card></div>
   <Card className="sensitivity-card" title="Sensitivity Analysis - Facility Amount" sub={`EL and ECL by facility size (${currency} millions)`} action={<div className="legend"><i/>EL <i className="green-dot"/>ECL</div>}><SensitivityChart points={results?.sensitivity||[]} currency={currency}/></Card>
  </div></div>
 </>;
}

function Slider({ label, value, set, min, max, display,inputMax=max }) {
  return (
    <label className="slider">
      <span>{label}<b>{display}</b></span>
      <input aria-label={`${label} value`} type="number" step="any" min={min} max={inputMax} value={value} onChange={event=>set(event.target.value===''?'':+event.target.value)}/>
      <input aria-label={`${label} slider`} type="range" step="any" min={min} max={max} value={value===''?min:value} onChange={(event) => set(+event.target.value)} />
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

function SensitivityChart({ points,currency='USD' }) {
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
        {ticks.map((value) => { const y = 180 - value / maxLoss * 145; return <g key={value}><line x1="62" x2="670" y1={y} y2={y} className="gridline" /><text x="54" y={y + 3} className="chart-tick" textAnchor="end">{displayNumber(value)}M</text></g>; })}
        <line x1="62" x2="62" y1="35" y2="180" className="chart-axis-line" />
        <line x1="62" x2="670" y1="180" y2="180" className="chart-axis-line" />
        {[['expected_loss', 'aqua', 'EL'], ['ecl_impact', 'green', 'ECL']].map(([key, tone, label]) => <React.Fragment key={key}>
          <polyline className={`line ${tone}`} points={plotted(key).map((point) => `${point.x},${point.y}`).join(" ")} />
          {plotted(key).map((point, index) => <circle key={point.facility_amount} cx={point.x} cy={point.y} r="5" className={`chart-point ${tone}-point`} tabIndex="0" onMouseEnter={() => setHovered({ index, key, label, x: point.x, y: point.y })} onMouseLeave={() => setHovered(null)} onFocus={() => setHovered({ index, key, label, x: point.x, y: point.y })} onBlur={() => setHovered(null)}><title>{money(point.facility_amount,currency)}: {label} {money(point[key],currency)}</title></circle>)}
        </React.Fragment>)}
        {points.map((point, index) => <text key={point.facility_amount} x={62 + index * 608 / Math.max(1, points.length - 1)} y="198" className="chart-tick" textAnchor="middle">{displayNumber(point.facility_amount)}M</text>)}
        <text x="14" y="108" className="chart-axis-title" textAnchor="middle" transform="rotate(-90 14 108)">Loss ({currency} millions)</text>
        <text x="366" y="216" className="chart-axis-title" textAnchor="middle">Facility amount ({currency} millions)</text>
        {hovered && <g className="chart-tooltip" pointerEvents="none"><rect x={Math.min(hovered.x + 8, 548)} y={Math.max(hovered.y - 34, 4)} width="142" height="27" rx="4" /><text x={Math.min(hovered.x + 15, 555)} y={Math.max(hovered.y - 17, 21)}>{hovered.label}: {money(points[hovered.index][hovered.key],currency)}</text></g>}
      </svg>
    </div>
  );
}
