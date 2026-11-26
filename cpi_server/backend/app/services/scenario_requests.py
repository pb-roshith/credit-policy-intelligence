"""Account-validated simulator baselines and request-bound scenario storage."""
from datetime import datetime,timezone
import math
import re
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from ..database import db_connection
from .rule_assessment import assessment_request_context
from .scenario_simulator import PD_BY_RATING
from .scenario_policy import ASSUMPTIONS


def available_requests(user):
    """List authoritative accessible sources using the same IDs as baseline lookup."""
    with db_connection() as connection:
        native=connection.execute('''SELECT credit_request_number,borrower_name,facility,requested_amount,user_id,shared_deal_id
            FROM credit_requests ORDER BY credit_request_number''').fetchall()
    from .deal_retrieval import DealRetrievalAgent
    notices=[]
    try:deals=DealRetrievalAgent().run(user).get('deals',[])
    except HTTPException:
        deals=[];notices.append('Credit Dossier requests are temporarily unavailable. Stored requests are listed below.')
    ids={d['id'] for d in deals}
    rows=[{'credit_request_number':d['id'],'borrower_name':d.get('customer'),'facility':d.get('facility'),
           'source':'Credit Dossier'} for d in deals if not d['id'].startswith('CR-')]
    for row in native:
        if row.get('shared_deal_id') in ids:continue
        request_id=row['credit_request_number']
        if not request_id.startswith('CR-'):continue
        if user['role']=='credit_analyst' and row['user_id']!=user['user_id']:request_id+='@'+row['user_id']
        rows.append({'credit_request_number':request_id,'borrower_name':row['borrower_name'],'facility':row['facility'],'source':'Stored credit request'})
    return {'requests':list({r['credit_request_number']:r for r in rows}.values()),'notices':notices}


def create_request_scenario_schema(connection):
    connection.execute('ALTER TABLE "user".decision_scenarios ADD COLUMN IF NOT EXISTS credit_request_number VARCHAR(160)')
    connection.execute("ALTER TABLE \"user\".decision_scenarios ADD COLUMN IF NOT EXISTS request_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb")
    # Existing unlinked scenarios stay unlinked: there is no safe way to infer
    # which request an earlier free-standing scenario was intended for.
    connection.execute('DROP INDEX IF EXISTS "user".decision_scenarios_name_unique')
    connection.execute('''CREATE UNIQUE INDEX IF NOT EXISTS decision_scenarios_request_name_unique
        ON "user".decision_scenarios(user_id,credit_request_number,LOWER(BTRIM(scenario_name)))
        WHERE credit_request_number IS NOT NULL''')
    connection.execute('''CREATE UNIQUE INDEX IF NOT EXISTS decision_scenarios_unlinked_name_unique
        ON "user".decision_scenarios(user_id,LOWER(BTRIM(scenario_name))) WHERE credit_request_number IS NULL''')
    connection.execute('''CREATE INDEX IF NOT EXISTS decision_scenarios_request_history
        ON "user".decision_scenarios(user_id,credit_request_number,created_at DESC,scenario_id DESC)''')


def request_baseline(request_number,user):
    from .assessment_request import normalize_request_id
    request_id=normalize_request_id(request_number)
    playpen = False
    if request_id.startswith('CR-'):
        # A request can be simulated before any compliance assessment exists.
        with db_connection() as connection:
            row=connection.execute('SELECT * FROM credit_requests WHERE credit_request_number=%s',(request_id,)).fetchone()
            playpen = bool(connection.execute("""
                SELECT 1 FROM credit_request_compliance
                WHERE credit_request_number=%s AND synthetic_assessment_data @> '{"scenario_policy_playpen": true}'
            """, (request_id,)).fetchone())
        if not row:raise HTTPException(404,'The selected credit request is unavailable for this account')
        proposal={**dict(row),'currency':'USD'}  # Native CPI requests use the USD manufacturing model.
        from .credit_data import load_record,project_record
        record=load_record(request_id)
        if record:proposal.update(project_record(record))
    else:
        request_id,proposal=assessment_request_context(request_id,user)
    assumptions=[];missing=[]
    def numeric(fields,fallback,low=0,high=float('inf')):
        for field in fields:
            value=proposal.get(field)
            if value is None or isinstance(value,bool):continue
            try: value=float(value)
            except (ValueError,TypeError):continue
            if math.isfinite(value) and low<=value<=high:return value
        if fallback is not None:assumptions.append({'field':fields[0],'value':fallback,'reason':'Not supplied in usable form by the selected request'})
        else:missing.append(fields[0])
        return fallback
    amount=numeric(['requested_amount','loan_amount'],None,low=0.000001,high=1e15)
    currency=proposal.get('currency')
    if not currency:
        currency='USD';assumptions.append({'field':'currency','value':currency,'reason':'Request currency is missing; explicit scenario assumption'})
    coverage=numeric(['collateral_coverage'],None,high=1000)
    if coverage is None:
        collateral=numeric(['adjusted_collateral','collateral_value'],None)
        if collateral is not None and amount:coverage=100*collateral/amount
        if coverage is None or coverage>1000:
            coverage=100;assumptions.append({'field':'collateral_coverage','value':coverage,'reason':'Collateral coverage is unavailable; illustrative scenario assumption'})
    # Coverage can be derived even if the original field was absent.
    missing=[f for f in missing if f not in ('collateral_coverage','adjusted_collateral')]
    pricing=numeric(['recommended_pricing_bps','pricing_bps'],None,high=10000)
    if pricing is None:
        match=re.search(r'(\d+(?:\.\d+)?)\s*bps',str(proposal.get('pricing') or ''),re.I)
        pricing=float(match[1]) if match else 325
        if not match:assumptions.append({'field':'pricing_bps','value':pricing,'reason':'Pricing is missing; illustrative scenario assumption'})
    missing=[f for f in missing if f!='recommended_pricing_bps']
    tenor=numeric(['recommended_tenor_years','tenor_years'],None,low=0.000001,high=50)
    if tenor is None:
        months=numeric(['tenor_months','facility_tenor_months','tenure'],None,low=0.000001,high=600)
        tenor=months/12 if months else 5
        if months is None:assumptions.append({'field':'tenor_years','value':tenor,'reason':'Tenor is missing; illustrative scenario assumption'})
    missing=[f for f in missing if f not in ('recommended_tenor_years','tenor_months')]
    rating=proposal.get('rating') or proposal.get('risk_rating')
    if rating not in PD_BY_RATING:
        missing.append('risk_rating')
        assumptions.append({'field':'risk_rating','value':None,'reason':f"Source rating {rating or 'not supplied'} needs an explicit choice from the simulator's supported rating bands"})
    covenants=proposal.get('covenants')
    if covenants not in ('Full','Partial','None'):
        covenants='Partial';assumptions.append({'field':'covenants','value':covenants,'reason':'Covenant strength is missing; illustrative scenario assumption'})
    inputs={'facility_amount':amount/1e6 if amount is not None else None,'collateral_coverage':coverage,
            'risk_rating':rating if rating in PD_BY_RATING else None,'pricing_bps':pricing,'tenor_years':tenor,'covenants':covenants}
    facts=jsonable_encoder({k:proposal.get(k) for k in ('borrower_name','facility','customer_segment','industry','geography','currency','requested_amount','rating','status',
        'collateral_coverage','adjusted_collateral','collateral_value','pricing','pricing_bps','recommended_pricing_bps',
        'tenure','tenor_months','facility_tenor_months','recommended_tenor_years','tenor_years','covenants')})
    return {'credit_request_number':request_id,'borrower_name':proposal.get('borrower_name'),'facility':proposal.get('facility'),
            'currency':currency,'inputs':inputs,'assumptions':assumptions,'missing_fields':sorted(set(missing)),
            'request_facts':facts,'captured_at':datetime.now(timezone.utc).isoformat(),
            **({'policy_playpen': True, 'policy_assumption_units': ASSUMPTIONS} if playpen else {})}
