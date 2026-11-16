"""Rule semantics are independent of document-wide review bookkeeping."""
from copy import deepcopy
from ..services.inventory_schema import ProposedRule
from .policy_representation import digest

NON_SEMANTIC={'change_rationale','representation_digest','requirement_digest','representation_rule_key',
              'severity','data_source','missing_information','review_label','extraction_confidence',
              'extraction_notes','rule_name','rule_description','check_question','rule_sequence'}


def semantic_definition(definition):
    value=deepcopy(definition)
    value.pop('change_rationale',None)
    value=ProposedRule.model_validate(value).model_dump(mode='json')
    return {k:v for k,v in value.items() if k not in NON_SEMANTIC}


def semantic_digest(definition):
    return digest(semantic_definition(definition))


def source_slot(rep,span_id,index):
    span=next(n['payload'] for n in rep['nodes'] if n['id']==span_id)
    return digest([rep['policy_version_id'],span['clause_id'],span['start'],span['end'],index])


def publish_drafts(rep,definitions,user,connection,effective_from=None):
    """Reuse unchanged versions, including approvals; revise only changed rules."""
    from datetime import date
    from ..services.inventory_schema import GovernedDefinition,GovernedRuleInput
    from ..services.rule_governance import store_rule
    results=[];changed=0
    nodes={n['id']:n for n in rep['nodes']}
    for definition in definitions:
        node=nodes[definition.representation_node_id]
        aliases=list(dict.fromkeys([node['id'],*node['payload'].get('previous_node_ids',[])]))
        connection.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('graph-rule:'+definition.representation_rule_key,))
        prior=connection.execute('''SELECT * FROM policy_rule_versions
            WHERE policy_id=%s AND policy_version_id=%s AND
                (definition->>'representation_rule_key'=%s OR definition->>'representation_node_id'=ANY(%s))
            ORDER BY version DESC,id DESC LIMIT 1 FOR UPDATE''',
            (rep['policy_id'],rep['policy_version_id'],definition.representation_rule_key,aliases)).fetchone()
        if prior and semantic_digest(prior['definition'])==semantic_digest(definition.model_dump(mode='json')):
            results.append(dict(prior));continue
        key='graph-first:'+digest([definition.representation_rule_key,semantic_digest(definition.model_dump(mode='json')),prior['id'] if prior else None])
        governed=GovernedDefinition(**definition.model_dump(),change_rationale='Compiled from source-backed rule semantics; unrelated source reviews do not create versions')
        payload=GovernedRuleInput(policy_id=rep['policy_id'],definition=governed,
                                  effective_from=prior['effective_from'] if prior else effective_from or rep.get('effective_from') or date.today(),
                                  effective_to=prior.get('effective_to') if prior else None)
        row=store_rule(payload,user,previous=prior['id'] if prior else None,extraction_key=key,c=connection,force_draft=True)
        results.append(row);changed+=1
    return results,changed
