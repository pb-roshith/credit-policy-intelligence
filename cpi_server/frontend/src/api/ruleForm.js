export function validateRuleForm(form) {
  const d=form.definition;
  const errors=[];
  if(!d.clause_id) errors.push("Select a source clause.");
  for(const key of ["rule_name","rule_description","check_question","source_excerpt","change_rationale"]) {
    if(typeof d[key]!=="string"||!d[key].trim()) errors.push(`Enter ${key.replaceAll("_"," ")}.`);
  }
  const logic=d.calculation_logic;
  if(logic) {
    if(["direct","date_age","approval_authority"].includes(logic.method)&&!logic.field) errors.push("Select the calculation input field.");
    if(["ratio","percentage"].includes(logic.method)&&(!logic.numerator||!logic.denominator)) errors.push("Enter numerator and denominator input fields.");
    if(logic.method==="document_presence"&&!logic.document_key) errors.push("Enter the required document key.");
    if(logic.method==="compound"&&!logic.condition) errors.push("Enter the compound condition.");
  }
  for(const key of ["input_data_fields","evidence_requirements","missing_information","dependencies"]) {
    if(!Array.isArray(d[key])) errors.push(`${key.replaceAll("_"," ")} must be a list.`);
  }
  if(d.applicable_stage!==null&&!Array.isArray(d.applicable_stage)) errors.push("Applicable stages must be a list or null.");
  if(form.effective_to&&form.effective_to<form.effective_from) errors.push("Effective-to must follow effective-from.");
  return errors;
}
