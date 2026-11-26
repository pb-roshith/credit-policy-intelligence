import React, { useState } from 'react';
import SemanticOntology from './SemanticOntology';
import SemanticKnowledge from './SemanticKnowledge';
import { SampleAssessmentGraph } from '../../../components/AssessmentGraphViews';
export default function GraphStudio(props) {
 const [sample, setSample] = useState(false);
 if (props.ontology) return <SemanticOntology/>;
 return <>
  <button type="button" className="btn secondary" aria-expanded={sample} onClick={() => setSample(value => !value)}>
   {sample ? 'Return to policy knowledge' : 'Open assessment graph sample'}
  </button>
  {sample ? <SampleAssessmentGraph/> : <SemanticKnowledge {...props}/>}
 </>;
}
