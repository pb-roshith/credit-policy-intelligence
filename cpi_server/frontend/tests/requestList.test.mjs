import test from "node:test";
import assert from "node:assert/strict";
import { loadRequestList } from "../src/api/requestList.js";

const deals = [
  {id:"deal_one",customer:"Borrower One",amount:1000,status:"Draft",facility:"Term Loan"},
  {id:"deal_two",customer:"Borrower Two",amount:2000,status:"In Progress",facility:"Revolver"},
];
test("both Dossier requests appear even when the local request list is empty", async () => {
  const calls = [];
  const request = async path => {
    calls.push(path);
    return path === "/api/deals" ? {deals} : [];
  };
  const {rows,error} = await loadRequestList("session",request);
  assert.deepEqual(calls,["/api/deals","/api/requests","/api/compliance-review/current-summaries"]);
  assert.deepEqual(rows.map(r=>r.credit_request_number),["deal_one","deal_two"]);
  assert.deepEqual(rows.map(r=>r.borrower_name),["Borrower One","Borrower Two"]);
  assert.equal(error,"");
});
test("linked local requests do not duplicate the shared request", async () => {
  const {rows} = await loadRequestList("session",async path => path === "/api/deals" ? {deals} : [
    {shared_deal_id:"deal_one",credit_request_number:"CR-100",compliance_score:90},
  ]);
  assert.equal(rows.length,2);
  assert.deepEqual(new Set(rows.map(r=>r.credit_request_number)),new Set(["deal_one","deal_two"]));
});
test("local-source failure keeps both shared requests and reports the failure", async () => {
  const {rows,error} = await loadRequestList("session",async path => {
    if(path === "/api/deals") return {deals};
    throw new Error("Local requests unavailable");
  });
  assert.equal(rows.length,2);
  assert.equal(error,"Local requests unavailable");
});
test("shared-source failure retains local requests and reports the failure", async () => {
  const {rows,error} = await loadRequestList("session",async path => {
    if(path === "/api/deals") throw new Error("Shared requests unavailable");
    return [{credit_request_number:"CR-100",borrower_name:"Local Borrower",compliance_score:80}];
  });
  assert.equal(rows[0].credit_request_number,"CR-100");
  assert.equal(error,"Shared requests unavailable");
});

test("request list never invents compliance and uses current graph summaries",async()=>{
 const request=async path=>path==='/api/deals'?{deals}:path==='/api/requests'?[]:[{request_id:'deal_two',compliance_score:70,assessment_scope:'current-semantic-graph'}];
 const {rows}=await loadRequestList('session',request);
 assert.equal(rows[0].credit_request_number,'deal_two');
 assert.equal(rows[0].compliance_score,70);
 assert.equal(rows[1].compliance_score,null);
});
