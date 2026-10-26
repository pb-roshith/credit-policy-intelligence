import test from "node:test";
import assert from "node:assert/strict";
import { validateRuleForm } from "../src/api/ruleForm.js";
const form = () => ({effective_from:"2026-10-13",effective_to:null,definition:{clause_id:1,rule_name:"Exposure",rule_description:"Exposure limit",check_question:"Is exposure within limit?",source_excerpt:"Exposure may not exceed 100.",change_rationale:"Reviewed source",calculation_logic:{method:"direct",field:"exposure"},input_data_fields:["exposure"],evidence_requirements:[],missing_information:[],dependencies:[],applicable_stage:null}});
test("complete draft validation does not fabricate threshold or approval",()=>{const input=form();const before=structuredClone(input);assert.deepEqual(validateRuleForm(input),[]);assert.deepEqual(input,before);});
test("incomplete calculations give business users actionable errors",()=>{const input=form();input.definition.calculation_logic={method:"ratio",numerator:"cash_flow"};assert.ok(validateRuleForm(input).includes("Enter numerator and denominator input fields."));});
test("invalid lists and periods cannot be submitted silently",()=>{const input=form();input.effective_to="2026-10-12";input.definition.evidence_requirements={};const errors=validateRuleForm(input);assert.ok(errors.includes("Effective-to must follow effective-from."));assert.ok(errors.includes("evidence requirements must be a list."));});
