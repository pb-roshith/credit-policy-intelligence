import React from 'react';
import SemanticKnowledge from '../features/riskKnowledge/pages/SemanticKnowledge';
export default function RuleLibrary({session,policies,onOpenEvidence}) {
 return <SemanticKnowledge policies={policies} onOpenEvidence={onOpenEvidence} canReview={['admin','credit_analyst'].includes(session.user.role)} canExtract={['relationship_manager','admin','credit_analyst'].includes(session.user.role)} initialView="rules" initialPolicy={sessionStorage.getItem('ruleLibraryPolicy')||''} title="Policy Rule Library"/>;
}
