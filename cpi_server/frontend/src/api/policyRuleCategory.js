export function policyRuleCategory(rule) {
 const value=rule?.rule_category?.toUpperCase();
 if(value==='QUALITATIVE'||value==='QUANTITATIVE')return value;
 const source=rule?.extracted||rule?.semantic_rule?.extracted||rule?.definition||rule||{};
 return String(source.rule_kind||source.rule_type||'').toUpperCase()==='QUANTITATIVE'||source.thresholds?.length?'QUANTITATIVE':'QUALITATIVE';
}

export function filterByRuleCategory(rules,category='ALL') {
 return category==='ALL'?rules:rules.filter(rule=>policyRuleCategory(rule)===category);
}
