import React from 'react';
import SemanticOntology from './SemanticOntology';
import SemanticKnowledge from './SemanticKnowledge';
export default function GraphStudio(props) {
 return props.ontology?<SemanticOntology/>:<SemanticKnowledge {...props}/>;
}
