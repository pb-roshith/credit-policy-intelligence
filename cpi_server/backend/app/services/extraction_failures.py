"""Expose persisted group failures without changing historical job outcomes."""
def attach_failures(jobs,connection):
    if not jobs:
        return jobs
    rows=connection.execute("""SELECT a.job_id,pv.policy_id,a.batch_key,a.clause_ids,a.error_details,a.error_code
        FROM inventory_batch_attempts a JOIN policy_versions pv ON pv.id=a.policy_version_id
        WHERE a.job_id=ANY(%s::uuid[]) AND a.status='Failed' AND a.retry_status<>'Resolved by retry'
        ORDER BY a.id""",([str(job['id']) for job in jobs],)).fetchall()
    latest={}
    for row in rows:
        latest[(str(row['job_id']),row['policy_id'],row['batch_key'])]=row
    for job in jobs:
        for progress in job.get('progress') or []:
            if progress.get('status') not in ('Failed','Completed with errors'):
                continue
            failures=[row for (job_id,policy_id,_),row in latest.items() if job_id==str(job['id']) and policy_id==progress['policy_id']]
            if failures:
                progress['batch_errors']=[{'clause_ids':row['clause_ids'],'message':row['error_details'] or row['error_code']} for row in failures]
                if not progress.get('error'):
                    saved=progress.get('rules_proposed',0)
                    progress['error']=f"{len(failures)} clause groups failed; {saved} draft rules saved. "+str(failures[0]['error_details'] or failures[0]['error_code'])
    return jobs
