import React, { lazy, Suspense, useEffect, useState } from 'react';
import sample from './assessmentGraphSample.json';
import { apiRequest } from '../api/client';

const AssessmentGraph = lazy(() => import('./AssessmentGraph'));

function GraphView({ data }) {
  return <Suspense fallback={<p role="status">Loading graph...</p>}><AssessmentGraph data={data} /></Suspense>;
}

export function SampleAssessmentGraph() {
  return <GraphView data={sample} />;
}

export function SavedAssessmentGraph({ requestId, reviewId }) {
  const [state, setState] = useState({ data: null, error: '' });

  useEffect(() => {
    if (!reviewId || !requestId) return;
    const controller = new AbortController();
    setState({ data: null, error: '' });
    apiRequest(`/api/compliance-review/${encodeURIComponent(requestId)}/assessment-graph?review_id=${reviewId}`,
      { signal: controller.signal })
      .then(data => { if (!controller.signal.aborted) setState({ data, error: '' }); })
      .catch(error => { if (!controller.signal.aborted) setState({ data: null, error: error.message }); });
    return () => controller.abort();
  }, [requestId, reviewId]);

  if (!reviewId) return <p>Save an assessment to open its visual explanation.</p>;
  if (state.error) return <p role="alert">{state.error}</p>;
  if (!state.data) return <p role="status">Loading assessment paths…</p>;
  return <GraphView key={reviewId} data={state.data} />;
}
