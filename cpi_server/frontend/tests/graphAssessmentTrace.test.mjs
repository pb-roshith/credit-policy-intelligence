import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';

test('matching summary shows one count summary without repeating the executive paragraph',async()=>{
 const server=await createServer({cacheDir:'node_modules/.vite-tests/'+process.pid,optimizeDeps:{noDiscovery:true,include:[]},server:{middlewareMode:true,hmr:false,ws:false},appType:'custom'});
 try {
  const {default:Trace}=await server.ssrLoadModule('/src/components/GraphAssessmentTrace.jsx');
  const review={review_id:7,executive_summary:'Graph traversal checked 863 published rules across 35 policies.',
   demonstration_data_used:true,compliance_status:'BREACH',applicability_report:{decisions:[],graph_rule_count:863,
    applicable_rule_count:96,excluded_rule_count:317,unresolved_rule_count:450}};
  const html=renderToStaticMarkup(React.createElement(Trace,{review,onEvidence:()=>{}}));
  assert.equal((html.match(/Knowledge graph matching/g)||[]).length,1);
  assert.ok(!html.includes('(demonstration)'));
  assert.equal((html.match(/Published rules checked/g)||[]).length,1);
  assert.equal((html.match(/Graph traversal checked/g)||[]).length,0);
  assert.ok(html.includes('AI explanation')===false);
  assert.ok(html.includes('Inspect matched, excluded and unresolved rules'));
  assert.equal((html.match(/role="listitem"/g)||[]).length,4);
  assert.ok(html.includes('graph-matching-content'));
  assert.ok(html.includes('Overall status'));
  assert.ok(html.includes('Needs information'));
  assert.ok(html.startsWith('<details class="card graph-matching-card graph-matching-collapsible"><summary'));
  assert.ok(!/^<details[^>]*\sopen[\s=>]/.test(html));
 } finally {await server.close()}
});
