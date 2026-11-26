import React, { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import { Crosshair, Minus, Plus } from 'lucide-react';
import './assessmentGraph.css';

const pageSize = 8;
const filters = [
  ['all', 'All rules'], ['Pass', 'Passed'], ['Breach', 'Breached'],
  ['exceptions', 'Exceptions'], ['policies', 'Applicable policies'],
];
const categories = {
  borrower: ['Borrower', '#dceafe', '#1c4b90'],
  attribute: ['Borrower attribute', '#ddf4e9', '#186247'],
  metric: ['Financial metric', '#fff0bd', '#775408'],
  policy: ['Policy', '#eee4fb', '#603c88'],
  rule: ['Policy rule', '#ffead9', '#8d460e'],
  pass: ['Pass', '#def4e5', '#17613b'],
  breach: ['Breach', '#fde4e4', '#9c2332'],
  review: ['Review needed', '#edf0f4', '#475568'],
  exception: ['Exception', '#ffe3d6', '#963b1e'],
};
const columns = { borrower: 0, attribute: 1, metric: 1, policy: 2, rule: 3, pass: 4, breach: 4, review: 4, exception: 5 };
const width = [164, 152, 160, 202, 140, 154];
const x = [105, 370, 640, 935, 1210, 1465];
const styles = [
  { selector: 'node', style: {
    shape: 'roundrectangle', width: 'data(width)', height: 64, label: 'data(canvasLabel)',
    'font-family': 'system-ui', 'font-size': 16, 'font-weight': 600,
    'text-wrap': 'wrap', 'text-max-width': 'data(textWidth)', 'text-valign': 'center',
    'text-halign': 'center', 'border-width': 1.4, 'background-color': 'data(fill)',
    'border-color': 'data(ink)', color: 'data(ink)',
  }},
  { selector: 'edge', style: {
    'curve-style': 'bezier', width: 1.6, 'line-color': '#8293a7', 'target-arrow-color': '#8293a7',
    'target-arrow-shape': 'triangle', label: 'data(label)', color: '#485a70',
    'font-size': 14, 'font-family': 'system-ui', 'text-background-opacity': 0.95,
    'text-background-color': '#f7fafd', 'text-background-padding': 3,
  }},
  { selector: 'edge[bent]', style: {
    'curve-style': 'unbundled-bezier', 'control-point-distances': -132, 'control-point-weights': 0.56,
  }},
  { selector: '.dimmed', style: { opacity: 0.18 }},
  { selector: 'edge.path-pass', style: { 'line-color': '#237a4b', 'target-arrow-color': '#237a4b', width: 3 }},
  { selector: 'edge.path-breach', style: { 'line-color': '#b33443', 'target-arrow-color': '#b33443', width: 3 }},
  { selector: 'edge.path-mixed', style: { 'line-color': '#6f557d', 'target-arrow-color': '#6f557d', width: 2.8 }},
  { selector: 'edge.path-review', style: { 'line-color': '#52657c', 'target-arrow-color': '#52657c', width: 2.6 }},
  { selector: 'node.focused', style: { 'border-width': 4 }},
];

function spaceEdgeLabels(graph) {
  const nodeBounds = graph.nodes().map(node => node.boundingBox({ includeLabels: false }));
  const labelBounds = [];
  const edges = graph.edges().sort((a, b) => Number(a.hasClass('dimmed')) - Number(b.hasClass('dimmed')));
  edges.removeStyle('text-margin-y text-opacity');
  for (const edge of edges) {
    const box = edge.boundingBox({ includeEdges: false, includeLabels: true, useCache: false });
    const offset = [0, -18, 18, -34, 34, -52, 52].find(dy =>
      !nodeBounds.some(rect => intersectsLabel(box, dy, rect)) &&
      !labelBounds.some(rect => intersectsLabel(box, dy, rect)));
    if (offset === undefined) {
      edge.style('text-opacity', 0);
    } else {
      if (offset) edge.style('text-margin-y', offset);
      labelBounds.push({ ...box, y1: box.y1 + offset, y2: box.y2 + offset });
    }
  }
}

function intersectsLabel(box, dy, rect) {
  const gap = 4;
  return box.x1 < rect.x2 + gap && box.x2 > rect.x1 - gap &&
    box.y1 + dy < rect.y2 + gap && box.y2 + dy > rect.y1 - gap;
}

function getView(data, paths, filter) {
  const ids = new Set(paths.flatMap(path => path.nodes));
  const edgeIds = new Set(paths.flatMap(path => path.edges));
  ids.add('borrower');
  if (filter === 'policies') {
    for (const node of data.nodes) {
      if (!['borrower', 'policy', 'attribute'].includes(node.kind)) ids.delete(node.id);
    }
  }
  if (['all', 'policies'].includes(filter)) {
    for (const edge of data.edges) {
      if (edge.source === 'borrower' && edge.label !== 'Has metric' &&
          edge.label !== 'Applicable policy') {
        ids.add(edge.target);
        edgeIds.add(edge.id);
      }
      if (filter === 'policies' && edge.label === 'Applicable policy') edgeIds.add(edge.id);
    }
  }
  const rank = new Map();
  paths.forEach((path, index) => path.nodes.forEach(id => {
    if (!rank.has(id)) rank.set(id, index);
  }));
  const lanes = x.map(() => []);
  for (const node of data.nodes) if (ids.has(node.id)) lanes[columns[node.kind]].push(node);
  const nodes = lanes.flatMap((lane, col) => lane
    .sort((a, b) => (rank.get(a.id) ?? Infinity) - (rank.get(b.id) ?? Infinity))
    .map((node, index) => ({
      data: { ...node, canvasLabel: data.sample && col === 3
        ? node.label + '\n' + node.finding.threshold.replace('<=', '≤') : node.label,
        width: width[col], textWidth: width[col] - 20,
        fill: categories[node.kind][1], ink: categories[node.kind][2] },
      position: { x: x[col], y: (index - (lane.length - 1) / 2) * 104 + 240 },
    })));
  const positions = new Map(nodes.map(node => [node.data.id, node.position.y]));
  return [...nodes, ...data.edges.filter(e => edgeIds.has(e.id) && ids.has(e.source) && ids.has(e.target))
    .map(edge => ({ data: edge.label === 'Tested against' &&
      Math.abs(positions.get(edge.source) - positions.get(edge.target)) < 65
      ? { ...edge, bent: true } : edge }))];
}

function AssessmentCanvas({ elements, paths, selection, onSelect }) {
  const container = useRef(null);
  const canvas = useRef(null);
  const [hover, setHover] = useState(null);
  useEffect(() => {
    setHover(null);
    const graph = cytoscape({
      container: container.current, elements, style: styles,
      layout: { name: 'preset', fit: true, padding: 25 },
      minZoom: 0.12, maxZoom: 2.5, pixelRatio: 'auto',
    });
    canvas.current = graph;
    const observer = new ResizeObserver(() => graph.resize());
    observer.observe(container.current);
    graph.on('tap', event => onSelect(event.target === graph ? null : event.target.isNode() ? event.target.id() : event.target.target().id()));
    graph.on('mouseover', 'node', event => {
      const node = event.target.data();
      setHover({ title: node.label, detail: node.detail, type: categories[node.kind][0] });
    });
    graph.on('mouseover', 'edge', event => {
      const edge = event.target;
      setHover({ title: edge.data('label'), detail: `${edge.source().data('label')} → ${edge.target().data('label')}`, type: 'Relationship' });
    });
    graph.on('dragfree', 'node', () => spaceEdgeLabels(graph));
    graph.on('mouseout drag pan zoom', () => setHover(null));
    return () => { observer.disconnect(); graph.destroy(); canvas.current = null; };
  }, [elements, onSelect]);

  useEffect(() => {
    const graph = canvas.current;
    if (!graph) return;
    const connected = paths.filter(path => path.nodes.includes(selection));
    const nodes = new Set(connected.flatMap(path => path.nodes));
    const edgeTones = new Map();
    for (const path of connected) {
      const tone = path.outcome === 'Pass' ? 'pass' : path.outcome === 'Breach' ? 'breach' : 'review';
      for (const id of path.edges) {
        const previous = edgeTones.get(id);
        edgeTones.set(id, previous && previous !== tone ? 'mixed' : tone);
      }
    }
    if (!connected.length && selection) {
      graph.getElementById(selection).closedNeighborhood().nodes().forEach(node => nodes.add(node.id()));
      graph.getElementById(selection).connectedEdges().forEach(edge => edgeTones.set(edge.id(), 'review'));
    }
    graph.batch(() => {
      graph.nodes().forEach(node => {
        node.toggleClass('focused', node.id() === selection);
        node.toggleClass('dimmed', Boolean(selection) && !nodes.has(node.id()));
      });
      graph.edges().forEach(edge => {
        edge.removeClass('path-pass path-breach path-mixed path-review');
        const tone = edgeTones.get(edge.id());
        edge.toggleClass('dimmed', Boolean(selection) && !tone);
        if (tone) edge.addClass('path-' + tone);
      });
    });
    spaceEdgeLabels(graph);
  }, [elements, paths, selection]);

  function zoom(factor) {
    const graph = canvas.current;
    graph?.zoom({ level: graph.zoom() * factor, renderedPosition: { x: graph.width() / 2, y: graph.height() / 2 } });
  }

  return <div className="assessment-canvas-wrap">
    <div className="assessment-canvas" ref={container} role="img" aria-label="Interactive map of borrower facts, policies, rules and outcomes. Use the rule list to select a path by keyboard." />
    <div className="assessment-zoom">
      <button type="button" aria-label="Zoom in" onClick={() => zoom(1.2)}><Plus size={17}/></button>
      <button type="button" aria-label="Zoom out" onClick={() => zoom(1 / 1.2)}><Minus size={17}/></button>
      <button type="button" aria-label="Fit graph" onClick={() => canvas.current?.fit(undefined, 25)}><Crosshair size={17}/></button>
    </div>
    {hover && <div className="assessment-hover"><small>{hover.type}</small><strong>{hover.title}</strong><span>{hover.detail}</span></div>}
  </div>;
}

function NodeDetails({ node, policy }) {
  const finding = node?.finding;
  if (finding) return <>
    <span className={'assessment-result ' + (finding.result === 'Pass' ? 'is-pass' : finding.result === 'Breach' ? 'is-breach' : '')}>{finding.result}</span>
    <h3>{node.label}</h3>
    <p>{finding.description}</p>
    <dl>
      <dt>Policy source</dt><dd>{[finding.policy, finding.clause && 'Clause ' + finding.clause, finding.page && 'Page ' + finding.page, finding.version].filter(Boolean).join(' · ')}</dd>
      <dt>Why this rule applies</dt><dd>{finding.scope.join(' ')}</dd>
      <dt>Threshold</dt><dd>{finding.threshold || 'Manual verification'}</dd>
      <dt>Borrower value</dt><dd>{finding.observed || 'Unavailable'}{finding.synthetic && ' · Manufactured data'}</dd>
      <dt>Assessment rationale</dt><dd>{finding.rationale || finding.reason}</dd>
    </dl>
  </>;
  if (policy) return <><h3>{policy.name}</h3><p>{policy.rules} applicable {policy.rules === 1 ? 'rule' : 'rules'}</p><ul>{policy.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></>;
  return <><h3>{node?.label || 'Trace an assessment'}</h3><p>{node?.detail || 'Select a rule to see why it applied, the value tested, and the recorded outcome.'}</p></>;
}

export default function AssessmentGraph({ data }) {
  const [filter, setFilter] = useState('all');
  const [policy, setPolicy] = useState('');
  const [page, setPage] = useState(0);
  const [selection, setSelection] = useState(null);
  const nodes = useMemo(() => new Map(data.nodes.map(node => [node.id, node])), [data]);
  const matching = useMemo(() => data.paths.filter(path =>
    (!policy || path.policy === policy) &&
    (filter === 'all' || filter === 'policies' || filter === path.outcome || (filter === 'exceptions' && path.exceptions))),
  [data, policy, filter]);
  const paths = useMemo(() => filter === 'policies' ? matching :
    matching.slice(page * pageSize, (page + 1) * pageSize), [matching, filter, page]);
  const elements = useMemo(() => getView(data, paths, filter), [data, paths, filter]);
  const selected = nodes.get(selection);
  const associated = paths.find(path => path.nodes.includes(selection));
  const detail = selected && ['pass', 'breach', 'review', 'exception'].includes(selected.kind) ? nodes.get(associated?.rule) : selected;
  const numExceptions = data.paths.reduce((total, path) => total + path.exceptions, 0);
  const otherOutcomes = data.paths.length - (data.counts.Pass || 0) - (data.counts.Breach || 0);

  function changeFilter(next) { setFilter(next); setPage(0); setSelection(null); }
  return <section className="assessment-map" aria-label="Credit policy assessment graph">
    <header className="assessment-map-head">
      <div><small>{data.sample ? 'Illustrative credit request' : data.request}</small><h2>{data.borrower}</h2></div>
      <div className="assessment-map-totals">
        <span>{data.policies.length} applicable {data.policies.length === 1 ? 'policy' : 'policies'}</span>
        <span className="is-pass">{data.counts.Pass || 0} passed</span>
        <span className="is-breach">{data.counts.Breach || 0} breached</span>
        <span>{numExceptions} {numExceptions === 1 ? 'exception' : 'exceptions'}</span>
        {otherOutcomes > 0 && <span>{otherOutcomes} other outcomes</span>}
      </div>
    </header>
    <div className="assessment-map-tools">
      <div className="assessment-map-filters" aria-label="Path filters">
        {filters.map(([id, label]) => <button type="button" key={id} aria-pressed={filter === id} onClick={() => changeFilter(id)}>{label}</button>)}
      </div>
      <label>Policy <select value={policy} onChange={event => { setPolicy(event.target.value); setPage(0); setSelection(null); }}>
        <option value="">All applicable policies</option>
        {data.policies.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
    </div>
    <div className="assessment-map-body">
      <div className="assessment-map-diagram">
        <AssessmentCanvas elements={elements} paths={paths} selection={selection} onSelect={setSelection}/>
        {!matching.length && <p className="assessment-map-empty">No paths match the selected filters.</p>}
        <div className="assessment-map-legend">{Object.entries(categories).map(([key, [label, fill, ink]]) =>
          <span key={key}><i style={{ background: fill, borderColor: ink }} />{label}</span>)}</div>
      </div>
      <div className="assessment-map-aside" role="complementary" aria-label="Assessment details">
        <div className="assessment-map-detail" aria-live="polite">
          <NodeDetails node={detail} policy={data.policies.find(item => item.id === selection)} />
          {selected?.kind === 'exception' && <p><strong>{selected.label}</strong> · {selected.detail}</p>}
        </div>
        <div className="assessment-map-list">
          <h3>{['all', 'policies'].includes(filter) && !policy ? 'Applicable policies' : 'Policy rules'}</h3>
          {['all', 'policies'].includes(filter) && !policy && data.policies.map(item => <button type="button" key={item.id}
            aria-pressed={selection === item.id} onClick={() => { setPolicy(item.id); setPage(0); setSelection(item.id); }}>
            <strong>{item.name}</strong><small>{item.reasons[0]} · {item.rules} {item.rules === 1 ? 'rule' : 'rules'}</small>
          </button>)}
          {filter !== 'policies' && paths.map(path => <button type="button" key={path.rule}
            aria-pressed={selection === path.rule} onClick={() => setSelection(path.rule)}>
            <strong>{nodes.get(path.rule).label}</strong><small>{path.outcome}{path.exceptions ? ' · Registered exception' : ''}</small>
          </button>)}
        </div>
      </div>
    </div>
    {filter !== 'policies' && matching.length > pageSize && <div className="assessment-map-pagination">
      <span>{page * pageSize + 1}–{Math.min((page + 1) * pageSize, matching.length)} of {matching.length} rule paths</span>
      <button type="button" disabled={!page} onClick={() => { setPage(page - 1); setSelection(null); }}>Previous</button>
      <button type="button" disabled={(page + 1) * pageSize >= matching.length} onClick={() => { setPage(page + 1); setSelection(null); }}>Next</button>
    </div>}
  </section>;
}
