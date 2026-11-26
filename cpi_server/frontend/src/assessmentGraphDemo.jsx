import React from 'react';
import { createRoot } from 'react-dom/client';
import AssessmentGraph from './components/AssessmentGraph';
import sample from './components/assessmentGraphSample.json';

createRoot(document.getElementById('root')).render(
  <main className="assessment-demo">
    <h1>Credit policy assessment</h1>
    <AssessmentGraph data={sample} />
  </main>,
);
