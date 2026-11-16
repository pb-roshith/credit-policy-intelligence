const labels={property_type:'Property type',loan_program:'Loan programme',vehicle_condition:'Vehicle condition',facility:'Facility',borrower_credit_rating:'Borrower credit rating',industry:'Industry',currency:'Currency'};
const comparisons={equals:'is',not_equals:'is not',in_list:'is one of',not_in_list:'is not one of',greater_than_or_equal:'is at least',less_than_or_equal:'is at most',greater_than:'is above',less_than:'is below',exists:'is present',does_not_exist:'is absent'};
export function formatPolicyCondition(condition){
 if(!condition)return 'No additional rule-level restrictions (policy scope still applies)';
 const group=condition.all||condition.any;
 if(group)return '('+group.map(formatPolicyCondition).join(condition.all?' AND ':' OR ')+')';
 const value=Array.isArray(condition.value)?condition.value.join(', '):String(condition.value??'');
 return `${labels[condition.field]||condition.field} ${comparisons[condition.operator]||condition.operator}${['exists','does_not_exist'].includes(condition.operator)?'':' '+value}`;
}
export function describePolicyRequirement(frame){
 const metric={ltv:'LTV',tenor:'Tenor',dscr:'DSCR',leverage:'Debt / EBITDA',interest_coverage:'Interest coverage',exposure:'Exposure',requested_amount:'Requested amount'}[frame.metric]||frame.metric;
 const op={less_than_or_equal:'≤',greater_than_or_equal:'≥',less_than:'<',greater_than:'>',equals:'='}[frame.operator]||frame.operator;
 return frame.document?`Provide ${frame.document.replaceAll('_',' ')}`:`${metric} ${op} ${frame.threshold}${frame.unit==='%'?'%':frame.unit?' '+frame.unit:''}`;
}
export function filterPolicyCoverage(coverage,filter){
 return coverage.filter(row=>filter==='REQUIREMENTS'?['VALIDATED','REVIEWED'].includes(row.status):filter==='ATTENTION'?['UNRESOLVED','LLM_PROPOSED'].includes(row.status):!filter||row.status===filter);
}

export function filterSemanticPassages(passages,filter='ALL',query=''){
 const text=query.trim().toLowerCase();
 return passages.filter(p=>(filter==='ALL'||(filter==='RULES'?(p.primary_rule_ids.length>0||p.supporting_rule_ids.length>0):p.disposition===filter))&&
  (!text||[p.source.passage,p.source.section,p.source.clause,p.clause_id].join(' ').toLowerCase().includes(text)));
}
export function formatExtractedConditions(group){
 if(!group)return 'Not stated in this extraction';
 const items=[...(group.conditions||[]).map(c=>`${c.field.replaceAll('_',' ')} ${({LTE:'≤',GTE:'≥',GT:'>',LT:'<',EQ:'=',NE:'≠',IN:'in',NOT_IN:'not in',EXISTS:'is present'})[c.operator]||c.operator}${c.operator==='EXISTS'?'':' '+(Array.isArray(c.value)?c.value.join(', '):String(c.value))}${c.unit?' '+c.unit:''}`),
  ...(group.groups||[]).map(g=>'('+formatExtractedConditions(g)+')')];
 return group.logic==='NOT'?'NOT ('+items.join(', ')+')':items.join(' '+group.logic+' ');
}
export function describeExtractedRequirement(rule){
 if(!rule.thresholds?.length)return rule.name;
 return rule.thresholds.map(t=>`${rule.metrics?.find(m=>m.key===t.metric_key)?.name||t.metric_key} ${({LTE:'≤',GTE:'≥',GT:'>',LT:'<',EQ:'=',NE:'≠'})[t.operator]||t.operator} ${t.value}${t.unit?' '+t.unit:''}`).join('; ');
}
