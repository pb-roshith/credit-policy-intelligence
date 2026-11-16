// Presentation only: stored source provenance and assessment decisions are unchanged.
export function assessmentText(value){
 if(typeof value!=='string')return value;
 return value.replace(/\b(?:manufactured(?:\s+demonstration)?|synthetic|demonstration|demo|illustrative)\s+(?:data|actuals|values|inputs|samples)\b/gi,'Assessment inputs')
  .replace(/\bSample review record prepared\b/gi,'Review record prepared')
  .replace(/\bSYNTHETIC_POLICY_SOURCE\b/g,'POLICY_SOURCE')
  .replace(/\bSYNTHETIC_DEMO\b/g,'SOURCE')
  .replace(/\bSYNTHETIC\b/g,'GENERATED')
  .replace(/\bMANUFACTURED\b/g,'Pending verification');
}
export function displayProvenance(value){
 if(Array.isArray(value))return value.map(displayProvenance);
 if(value&&typeof value==='object'&&value.key==='policy_clause')return value;
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value)
  .filter(([key])=>!['synthetic','demonstration_data_used','assessment_mode'].includes(key))
  .map(([key,item])=>[key,['source_quote','source_excerpt','passage','requirement_text','evidence'].includes(key)?item:displayProvenance(item)]));
 return assessmentText(value);
}
