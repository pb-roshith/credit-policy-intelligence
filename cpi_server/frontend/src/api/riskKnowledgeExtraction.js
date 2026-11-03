export function extractionPolicyIds(policyFilter, checkedPolicies=[]) {
  const choices=policyFilter ? [Number(policyFilter)] : checkedPolicies.map(Number);
  return [...new Set(choices.filter(id=>Number.isSafeInteger(id)&&id>0))];
}

export function ruleExtractionSummary(job) {
  if (!job) return null;
  if (['Queued','Running'].includes(job.status)) return null;
  const count=Number(job.report?.rules_proposed)||0;
  const incomplete=job.status==='Completed with errors'||job.status==='Failed'||job.error||
    job.report?.policies_failed>0||job.report?.quality_failed>0||job.report?.quality_pending>0||
    (job.progress||[]).some(p=>p.status==='Failed'||p.status==='Completed with errors'||p.partial_result);
  if(count>0)return incomplete
    ? {status:'Completed with errors',message:`${count} rules extracted, but some documents or checks failed. Retry extraction to finish.`}
    : {status:'Completed',message:`${count} rules extracted.`};
  const failed=(job.progress||[]).find(p=>p.error&&(p.status==='Failed'||p.status==='Completed with errors'||p.partial_result))
    ||(job.error?{error:job.error}:null);
  if(!failed)return {status:'Failed',message:'No rules were extracted. Try again.'};
  const stage=failed.stages?.find(s=>s.id===failed.stage)?.label;
  const reason=/unterminated string|json_invalid|incomplete or invalid structured data/i.test(failed.error)
    ? 'The AI returned incomplete or invalid data. Retry extraction.' : failed.error;
  return {status:'Failed',message:`No rules were extracted. ${stage?`${stage} failed: `:''}${reason}`};
}

