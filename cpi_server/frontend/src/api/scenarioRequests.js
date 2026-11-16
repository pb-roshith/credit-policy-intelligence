const fields=['facility_amount','collateral_coverage','risk_rating','pricing_bps','tenor_years','covenants'];
function query(requestId){
 if(!requestId?.trim())throw new Error('Select a credit request first.');
 return new URLSearchParams({credit_request_number:requestId}).toString();
}
export const scenarioListPath=id=>'/api/decision-scenarios?'+query(id);
export const scenarioContextPath=id=>'/api/decision-scenarios/request-context?'+query(id);
export const scenarioUnlinkedPath=id=>'/api/decision-scenarios/unlinked?'+query(id);
export const scenarioDetailPath=(scenarioId,id)=>'/api/decision-scenarios/'+encodeURIComponent(scenarioId)+'?'+query(id);
export function scenarioRequestNumber(id){return /^CR-[0-9]+@/.test(id)?id.slice(0,id.indexOf('@')):id}
export function scenarioInputs(context){
 return {...Object.fromEntries(fields.map(field=>[field,context.inputs[field]??''])),currency:context.currency};
}
export function scenarioPayload(requestId,name,inputs){
 query(requestId);
 return {credit_request_number:requestId,scenario_name:name,...Object.fromEntries(fields.map(field=>[field,inputs[field]])),currency:inputs.currency};
}
